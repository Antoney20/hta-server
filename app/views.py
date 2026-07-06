import json
import logging
import threading
from django.db import transaction
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.request import Request
 
 
from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.mixins import RetrieveModelMixin, ListModelMixin
from rest_framework.viewsets import GenericViewSet
from rest_framework.decorators import action
from rest_framework.decorators import api_view, permission_classes

from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
 


from django.db.models import Q
from django.core.cache import cache

from rest_framework import permissions, status
from dataclasses import asdict
from rest_framework.views import APIView
from app import services
from app.core.emails.feedback import send_feedback_email
from app.core.services.evidence_extraction import EvidenceExtractionService
from app.core.services.feedback import FeedbackService
from app.core.emails.activity import send_activity_assignment_emails
from app.core.services.national import NationalProgramService, ProgramProposalService
from app.services import criteria_info
from app.services.appraisal_panel import AppraisalPanelService
from app.services.evidence_coverage import EvidenceCoverageService as cov
from app.services.criteria_rules import CriteriaRuleService as rules
from app.services.benefits_package import create_package, delete_package, list_packages, update_package
from app.services.evidence import AssessmentEvidenceService
from app.services.phase import InterventionPhaseService
from app.services.program import InterventionPackageService
from app.services.public_view import PublicProposalService
from app.services.scoring_p import bulk_create_scores, get_scores_for_user
from app.services.tp import TopicPriorityService
from app.services.weighting import WeightingReportService
from members.services.notification_service import NotificationService
from users.models import CustomUser, InterventionProposal, UserRole
from users.permissions import IsAdmin, IsAssessment, IsPanel, IsSecretariatOrAdmin, IsSecretariate, IsContentManager, IsRegularUser, IsSWG, IsAuthenticatedAndActive, IsAuthenticatedOrReadOnly, IsOwnerOrAdminOrReadOnly, is_admin
from app.services.scoring import ScoringReportService
from users.serializers import InterventionProposalSerializer

from .models import Activity, AppraisalCriteriaEvidence, AssessmentEvidence, BenefitPackage, CriteriaAppraisalScore, CriteriaAppraisalTool, CriteriaInformation, DecisionType, EvidenceCriterion, EvidenceExtraction, FeedbackCategory, FeedbackEmailLog, InterventionPackage, InterventionPhase, InterventionStatusUpdate, NationalProgram, NationalProgramProposal, SelectionTool, SubActivity, SystemCategory, InterventionSystemCategory, InterventionScore
from .serializers import (
    ActivitySerializer,
    AppraisalCriteriaEvidenceSerializer,
    AppraisalCriteriaEvidenceWriteSerializer,
    AssessmentEvidenceSerializer,
    BenefitPackageSerializer,
    CriteriaAppraisalScoreCreateSerializer,
    CriteriaAppraisalScoreSerializer,
    CriteriaAppraisalToolSerializer,
    CriteriaAppraisalToolWriteSerializer,
    CriteriaInformationCreateSerializer,
    CriteriaInformationSerializer,
    DecisionTypeCreateSerializer,
    DecisionTypeSerializer,
    EvidenceCriterionSerializer,
    EvidenceExtractionSerializer,
    FeedbackCategorySerializer,
    FeedbackCategoryWriteSerializer,
    FeedbackEmailLogSerializer,
    InterventionPackageSerializer,
    InterventionPhaseSerializer,
    InterventionScoreCreateSerializer,
    InterventionStatusUpdateSerializer,
    InterventionStatusUpdateWriteSerializer,
    NationalProgramProposalSerializer,
    NationalProgramSerializer,
    SelectionToolSerializer,
    SubActivitySerializer,
    SystemCategorySerializer,
    InterventionSystemCategorySerializer,
    InterventionScoreSerializer,
    UserSummarySerializer,
)

from django.db.models import ProtectedError


logger = logging.getLogger(__name__)


 
def _ok(data, message="Success", status_code=200):
    return Response({"success": True, "message": message, "data": data}, status=status_code)
 
 
def _err(message, status_code=400):
    return Response({"success": False, "message": message, "data": None}, status=status_code)
 
 
def _get_or_404(model, **kwargs):
    """Returns (instance, None) or (None, error Response)."""
    try:
        return model.objects.get(**kwargs), None
    except model.DoesNotExist:
        return None, _err(f"{model.__name__} not found.", 404)
 



def _notify_assigned_users(sub: SubActivity) -> None:
    """
    Called in a background thread after a sub-activity is created.
    No-op if SubActivity has no assigned users — safe to always call.
    """
    # NotificationService is stateless / read-only, nothing to persist.
    # We call get_alerts() per assigned user so their next poll or
    # page-load reflects the new assignment immediately via the cache.
    for user in sub.assigned_to.all():
        try:
            NotificationService.get_alerts(user)   # warms any future cache
        except Exception:
            pass


_PERMS = {
    "list":           [AllowAny],
    "retrieve":       [AllowAny],
    "create":         [IsSecretariatOrAdmin],
    "update":         [IsAdmin],
    "partial_update": [IsAdmin],
    "destroy":        [IsAdmin],
}



def _validation_message(exc: ValidationError):
    return getattr(exc, "message_dict", None) or exc.messages
 
 
 
class NationalProgramViewSet(viewsets.ViewSet):
    """CRUD for the programs themselves."""

    def get_permissions(self):
        return [p() for p in _PERMS.get(self.action, [IsAdmin])]

    def list(self, request):
        active = request.query_params.get("active") in ("1", "true", "True")
        qs = NationalProgramService.queryset(active_only=active)
        return _ok(NationalProgramSerializer(qs, many=True).data)

    def retrieve(self, request, pk=None):
        obj, err = _get_or_404(NationalProgram, pk=pk)
        if err:
            return err
        return _ok(NationalProgramSerializer(obj).data)

    def create(self, request):
        ser = NationalProgramSerializer(data=request.data)
        if not ser.is_valid():
            return _err(ser.errors)
        try:
            ser.save()
        except Exception:
            logger.exception("Failed to create NationalProgram")
            return _err("Could not create the program due to a server error.", 500)
        return _ok(ser.data, "Program created.", 201)

    def update(self, request, pk=None):
        obj, err = _get_or_404(NationalProgram, pk=pk)
        if err:
            return err
        ser = NationalProgramSerializer(obj, data=request.data, partial=True)
        if not ser.is_valid():
            return _err(ser.errors)
        try:
            ser.save()
        except Exception:
            logger.exception("Failed to update NationalProgram %s", pk)
            return _err("Could not update the program due to a server error.", 500)
        return _ok(ser.data, "Program updated.")

    partial_update = update

    def destroy(self, request, pk=None):
        obj, err = _get_or_404(NationalProgram, pk=pk)
        if err:
            return err
        try:
            obj.delete()
        except Exception:
            logger.exception("Failed to delete NationalProgram %s", pk)
            return _err("Could not delete the program due to a server error.", 500)
        return _ok(None, "Program deleted.")


class NationalProgramProposalViewSet(viewsets.ViewSet):
    """Proposals. Each program owns its rows; filter with ?program=<id|code>."""

    def get_permissions(self):
        return [p() for p in _PERMS.get(self.action, [IsAdmin])]

    def list(self, request):
        qs = ProgramProposalService.queryset(program=request.query_params.get("program"))
        return _ok(NationalProgramProposalSerializer(qs, many=True).data)

    def retrieve(self, request, pk=None):
        obj, err = _get_or_404(NationalProgramProposal, pk=pk)
        if err:
            return err
        return _ok(NationalProgramProposalSerializer(obj).data)

    def create(self, request):
        ser = NationalProgramProposalSerializer(data=request.data)
        if not ser.is_valid():
            return _err(ser.errors)
        v = ser.validated_data
        try:
            proposal = ProgramProposalService.create(
                program=v["program"],
                title=v["title"],
                data=v.get("data") or {},
                justification=v.get("justification"),
                submitted_date=v.get("submitted_date"),
                user=request.user,
            )
        except ValidationError as e:
            return _err(_validation_message(e), 400)
        except Exception:
            logger.exception("Failed to create NationalProgramProposal")
            return _err("Could not create the proposal due to a server error.", 500)
        return _ok(NationalProgramProposalSerializer(proposal).data, "Proposal created.", 201)

    def update(self, request, pk=None):
        obj, err = _get_or_404(NationalProgramProposal, pk=pk)
        if err:
            return err
        ser = NationalProgramProposalSerializer(obj, data=request.data, partial=True)
        if not ser.is_valid():
            return _err(ser.errors)
        v = ser.validated_data
        try:
            proposal = ProgramProposalService.update(
                obj,
                title=v.get("title"),
                data=v.get("data"),
                justification=v.get("justification"),
                submitted_date=v.get("submitted_date"),
            )
        except ValidationError as e:
            return _err(_validation_message(e), 400)
        except Exception:
            logger.exception("Failed to update NationalProgramProposal %s", pk)
            return _err("Could not update the proposal due to a server error.", 500)
        return _ok(NationalProgramProposalSerializer(proposal).data, "Proposal updated.")

    partial_update = update

    def destroy(self, request, pk=None):
        obj, err = _get_or_404(NationalProgramProposal, pk=pk)
        if err:
            return err
        try:
            ref = obj.reference_number
            obj.delete()
        except Exception:
            logger.exception("Failed to delete NationalProgramProposal %s", pk)
            return _err("Could not delete the proposal due to a server error.", 500)
        return _ok(None, f"Proposal {ref} deleted.")
    
    

class EvidenceCriterionViewSet(viewsets.ViewSet):
    """The editable code book. Reads open to any user; writes are admin-only."""
 
    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAdmin()]
 
    def list(self, request):
        active = request.query_params.get("active") in ("1", "true", "True")
        qs = EvidenceCriterion.objects.all()
        if active:
            qs = qs.filter(is_active=True)
        return _ok(EvidenceCriterionSerializer(qs, many=True).data)
 
    def retrieve(self, request, pk=None):
        obj, err = _get_or_404(EvidenceCriterion, pk=pk)
        if err:
            return err
        return _ok(EvidenceCriterionSerializer(obj).data)
 
    def create(self, request):
        ser = EvidenceCriterionSerializer(data=request.data)
        if not ser.is_valid():
            return _err(ser.errors)
        try:
            ser.save()
        except Exception:
            logger.exception("Failed to create EvidenceCriterion")
            return _err("Could not create the criterion due to a server error.", 500)
        return _ok(ser.data, "Criterion created.", 201)
 
    def update(self, request, pk=None):
        obj, err = _get_or_404(EvidenceCriterion, pk=pk)
        if err:
            return err
        ser = EvidenceCriterionSerializer(obj, data=request.data, partial=True)
        if not ser.is_valid():
            return _err(ser.errors)
        try:
            ser.save()
        except Exception:
            logger.exception("Failed to update EvidenceCriterion %s", pk)
            return _err("Could not update the criterion due to a server error.", 500)
        return _ok(ser.data, "Criterion updated.")
 
    partial_update = update
 
    def destroy(self, request, pk=None):
        obj, err = _get_or_404(EvidenceCriterion, pk=pk)
        if err:
            return err
        try:
            obj.delete()
        except Exception:
            logger.exception("Failed to delete EvidenceCriterion %s", pk)
            return _err("Could not delete the criterion due to a server error.", 500)
        return _ok(None, "Criterion deleted.")
 
 
class EvidenceExtractionViewSet(viewsets.ViewSet):
 
    def get_permissions(self):
        return [IsAuthenticated()]
 
    def list(self, request):
        qs = EvidenceExtractionService.queryset()
        return _ok(EvidenceExtractionSerializer(qs, many=True).data)
 
    def retrieve(self, request, pk=None):
        obj, err = _get_or_404(EvidenceExtraction, pk=pk)
        if err:
            return err
        return _ok(EvidenceExtractionSerializer(obj).data)
 
    def create(self, request):
        if not EvidenceExtractionService.can_add(request.user):
            return _err("You are not authorized to add evidence extractions.", 403)
        ser = EvidenceExtractionSerializer(data=request.data)
        if not ser.is_valid():
            return _err(ser.errors)
        try:
            obj = EvidenceExtractionService.create(user=request.user, **ser.validated_data)
        except ValidationError as e:
            return _err(_validation_message(e), 400)
        except Exception:
            logger.exception("Failed to create EvidenceExtraction")
            return _err("Could not create the evidence extraction due to a server error.", 500)
        return _ok(EvidenceExtractionSerializer(obj).data, "Evidence extraction created.", 201)
 
    def update(self, request, pk=None):
        obj, err = _get_or_404(EvidenceExtraction, pk=pk)
        if err:
            return err
        if not EvidenceExtractionService.can_edit(request.user, obj):
            return _err("You are not authorized to edit this evidence extraction.", 403)
        ser = EvidenceExtractionSerializer(obj, data=request.data, partial=True)
        if not ser.is_valid():
            return _err(ser.errors)
        try:
            obj = EvidenceExtractionService.update(obj, **ser.validated_data)
        except ValidationError as e:
            return _err(_validation_message(e), 400)
        except Exception:
            logger.exception("Failed to update EvidenceExtraction %s", pk)
            return _err("Could not update the evidence extraction due to a server error.", 500)
        return _ok(EvidenceExtractionSerializer(obj).data, "Evidence extraction updated.")
 
    partial_update = update
 
    def destroy(self, request, pk=None):
        if not EvidenceExtractionService.can_delete(request.user):
            return _err("You are not authorized to delete evidence extractions.", 403)
        obj, err = _get_or_404(EvidenceExtraction, pk=pk)
        if err:
            return err
        try:
            obj.delete()
        except Exception:
            logger.exception("Failed to delete EvidenceExtraction %s", pk)
            return _err("Could not delete the evidence extraction due to a server error.", 500)
        return _ok(None, "Evidence extraction deleted.")
 


class UsersListView(APIView):
    """
    GET /api/v1/users/
    Admin only — returns name, email, profile image, role, and member_id.
    """
    permission_classes = [IsAuthenticated]
 
    def get(self, request: Request):
        users = (
            CustomUser.objects
            .select_related("member")
            .order_by("first_name", "last_name")
        )
        serializer = UserSummarySerializer(users, many=True, context={"request": request})
        count = users.count()
        return _ok(serializer.data, f"{count} user{'s' if count != 1 else ''} loaded.")



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def search_interventions(request):
    """
    Lightweight intervention search for form autofill.
    Query by ?q=  (matches ref_no or intervention_name, first 20 chars)
    Returns minimal payload only.
    """
    q = request.query_params.get("q", "").strip()
    if not q or len(q) < 1:
        return Response({"success": True, "message": "Query too short.", "data": []})

    cache_key = f"intervention_search:{q[:20].lower()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return Response({"success": True, "message": "Success", "data": cached})

    # strip non-alpha for safety, keep spaces
    qs = (
        InterventionProposal.objects
        .filter(
            Q(reference_number__icontains=q) |
            Q(intervention_name__icontains=q)
        )
        .only("id", "reference_number", "intervention_name", "county", "intervention_type")
        .order_by("-submitted_at")[:15]
    )

    data = [
        {
            "id": str(obj.id),
            "reference_number": obj.reference_number,
            "intervention_name": obj.intervention_name,
            "county": obj.county,
            "intervention_type": obj.intervention_type,
        }
        for obj in qs
    ]

    cache.set(cache_key, data, 60 * 2)  # 2 min cache
    return Response({"success": True, "message": "Success", "data": data})


def _can_manage_rescore(user) -> bool:
    """Only admin / SWG / secretariat can open or close a rescore window."""
    return user.role in (UserRole.ADMIN, UserRole.SWG, UserRole.SECRETARIAT)
 

class AdminOrSecretariatDestroyMixin:
    def get_permissions(self):
        if self.action == "destroy":
            if (
                self.request.user.is_authenticated
                and (
                    self.request.user.has_role(UserRole.ADMIN)
                    or self.request.user.has_role(UserRole.SECRETARIAT)
                )
            ):
                return [permissions.AllowAny()]  # already manually validated
            return [permissions.IsAdminUser()]  # forces 403

        return [permissions.IsAuthenticated()]



class SelectionToolViewSet(viewsets.ModelViewSet):
    queryset = SelectionTool.objects.all()
    serializer_class = SelectionToolSerializer
    # access to everyone except SWGs
    permission_classes = [permissions.IsAuthenticated]


class SystemCategoryViewSet(viewsets.ModelViewSet):
    queryset = SystemCategory.objects.all()
    serializer_class = SystemCategorySerializer
    permission_classes = [permissions.IsAuthenticated, ]





class InterventionSystemCategoryViewSet(viewsets.ModelViewSet):
    queryset = InterventionSystemCategory.objects.select_related(
        "intervention", "system_category",
        "intervention__package", "intervention__phase",
    )
    serializer_class = InterventionSystemCategorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        intervention_id = self.request.query_params.get("intervention")
        if intervention_id:
            qs = qs.filter(intervention_id=intervention_id)
        return qs

    def get_permissions(self):
        if self.action == "destroy":
            if (
                self.request.user.is_authenticated
                and (
                    self.request.user.has_role(UserRole.ADMIN)
                    or self.request.user.has_role(UserRole.SECRETARIAT)
                )
            ):
                return [permissions.AllowAny()]  # already manually validated
            return [permissions.IsAdminUser()]  # forces 403

        return [permissions.IsAuthenticated()]
 
class CriteriaInformationViewSet(RetrieveModelMixin, ListModelMixin, GenericViewSet):
    queryset = CriteriaInformation.objects.none()
    permission_classes = [permissions.IsAuthenticated]
 
    def get_serializer_class(self):
        if self.action in ("create_criteria", "update_criteria"):
            return CriteriaInformationCreateSerializer
        return CriteriaInformationSerializer
 

    def list(self, request, *args, **kwargs):
        qs = (
            CriteriaInformation.objects
            .select_related("intervention", "created_by")
        )
        serializer = CriteriaInformationSerializer(qs, many=True)
        return Response({
            "success": True,
            "message": "Success",
            "data": serializer.data,
        })
 
    def retrieve(self, request, *args, **kwargs):
        try:
            instance = (
                CriteriaInformation.objects
                .select_related("intervention", "created_by")
                .get(pk=kwargs["pk"])
            )
        except CriteriaInformation.DoesNotExist:
            return Response(
                {"success": False, "message": "Criteria information not found.", "data": None},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({
            "success": True,
            "message": "Success",
            "data": CriteriaInformationSerializer(instance).data,
        })
 
     

    @action(detail=False, methods=["get"], url_path="by-intervention",
            permission_classes=[permissions.IsAuthenticated])
    def by_intervention(self, request):
        intervention_id = request.query_params.get("intervention")
        if not intervention_id:
            return Response(
                {"success": False, "message": "intervention query param is required.", "data": None},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = criteria_info.get_criteria_for_intervention(intervention_id)
        return Response({
            "success": True,
            "message": "Success",
            "data": CriteriaInformationSerializer(qs, many=True).data,
        })
 

    @action(detail=False, methods=["post"], url_path="create",
            permission_classes=[permissions.IsAuthenticated, IsAdmin | IsSecretariate])
    def create_criteria(self, request):
        intervention_id = request.data.get("intervention")
        if intervention_id and CriteriaInformation.objects.filter(intervention_id=intervention_id).exists():
            return Response(
                {
                    "success": False,
                    "message": "Criteria information already exists for this intervention. Use the update endpoint instead.",
                    "data": None,
                },
                status=status.HTTP_409_CONFLICT,
            )
 
        serializer = CriteriaInformationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"success": False, "message": serializer.errors, "data": None},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        obj = criteria_info.create_criteria(serializer.validated_data, request.user)
        return Response(
            {"success": True, "message": "Criteria created.", "data": CriteriaInformationSerializer(obj).data},
            status=status.HTTP_201_CREATED,
        )
 
    @action(detail=True, methods=["patch"], url_path="update",
            permission_classes=[permissions.IsAuthenticated, IsAdmin | IsSecretariate])
    def update_criteria(self, request, pk=None):
        try:
            instance = CriteriaInformation.objects.get(pk=pk)
        except CriteriaInformation.DoesNotExist:
            return Response(
                {"success": False, "message": "Not found.", "data": None},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = CriteriaInformationCreateSerializer(instance, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(
                {"success": False, "message": serializer.errors, "data": None},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        obj = criteria_info.update_criteria(instance, serializer.validated_data)
        return Response({
            "success": True,
            "message": "Criteria updated.",
            "data": CriteriaInformationSerializer(obj).data,
        })

    @action(detail=True, methods=["delete"], url_path="delete",
            permission_classes=[permissions.IsAuthenticated, IsAdmin | IsSecretariate])
    def delete_criteria(self, request, pk=None):
        try:
            instance = CriteriaInformation.objects.get(pk=pk)
        except CriteriaInformation.DoesNotExist:
            return Response(
                {"success": False, "message": "Not found.", "data": None},
                status=status.HTTP_404_NOT_FOUND,
            )
        instance.delete()
        return Response(
            {"success": True, "message": "Criteria deleted.", "data": None},
            status=status.HTTP_200_OK,
        )

class InterventionProposalViewSet(viewsets.ModelViewSet):
    queryset = InterventionProposal.objects.select_related("user").order_by("-submitted_at")
    serializer_class = InterventionProposalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()

        # ?rescore_open=true  →  only interventions with open rescore window
        rescore_open = self.request.query_params.get("rescore_open")
        if rescore_open is not None:
            qs = qs.filter(rescore_open=rescore_open.lower() == "true")

        return qs


    @action(detail=True, methods=["post"], url_path="open-rescore")
    def open_rescore(self, request, pk=None):
        if not _can_manage_rescore(request.user):
            raise PermissionDenied("Only admins, SWG, or secretariat can open rescoring.")

        intervention = self.get_object()

        if intervention.rescore_open:
            return Response(
                {"detail": "Rescore window is already open."},
                status=status.HTTP_200_OK,
            )

        intervention.rescore_open = True
        intervention.save(update_fields=["rescore_open"])
        return Response({"detail": "Rescore window opened."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="close-rescore")
    def close_rescore(self, request, pk=None):
        if not _can_manage_rescore(request.user):
            raise PermissionDenied("Only admins, SWG, or secretariat can close rescoring.")

        intervention = self.get_object()

        if not intervention.rescore_open:
            return Response(
                {"detail": "Rescore window is already closed."},
                status=status.HTTP_200_OK,
            )

        intervention.rescore_open = False
        intervention.save(update_fields=["rescore_open"])
        return Response({"detail": "Rescore window closed."}, status=status.HTTP_200_OK)


# class InterventionScoreViewSet(viewsets.ModelViewSet):
#     permission_classes = [permissions.IsAuthenticated]

#     def get_queryset(self):
#         qs = InterventionScore.objects.select_related(
#             "reviewer", "intervention", "criteria"
#         ).filter(reviewer=self.request.user)
#         intervention_id = self.request.query_params.get("intervention")
#         if intervention_id:
#             qs = qs.filter(intervention_id=intervention_id)
#         return qs

#     def get_serializer_class(self):
#         if self.action in ("create", "update", "partial_update"):
#             return InterventionScoreCreateSerializer
#         return InterventionScoreSerializer

#     def perform_create(self, serializer):
#         serializer.save(reviewer=self.request.user)

#     def perform_update(self, serializer):
#         if serializer.instance.reviewer != self.request.user:
#             raise PermissionDenied("You can only edit your own scores.")
#         serializer.save()

#     @action(detail=False, methods=["post"], url_path="bulk")
#     def bulk_create(self, request):
#         items = request.data.get("scores", [])

#         if not items:
#             raise ValidationError({"detail": "No scores provided."})

#         errors = []

#         try:
#             with transaction.atomic():
#                 created = []
#                 for i, item in enumerate(items):
#                     s = InterventionScoreCreateSerializer(data=item)
#                     if not s.is_valid():
#                         # Collect all item errors before raising so the
#                         # response tells the client exactly what went wrong
#                         errors.append({
#                             "index": i,
#                             "criteria": item.get("criteria"),
#                             "errors": s.errors,
#                         })
#                     else:
#                         created.append(s.save(reviewer=request.user))

#                 if errors:
#                     # Raising inside atomic() rolls everything back
#                     raise ValidationError({
#                         "detail": "Validation failed — no scores were saved.",
#                         "errors": errors,
#                     })

#         except ValidationError:
#             raise  # already structured, let DRF handle the 400

#         except Exception as exc:
#             raise ValidationError({
#                 "detail": "An unexpected error occurred — no scores were saved.",
#                 "error": str(exc),
#             })

#         return Response(
#             InterventionScoreSerializer(created, many=True).data,
#             status=status.HTTP_201_CREATED,
#         )



class InterventionScoreViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    def _assert_can_score(self, user) -> None:
        """Only admin or SWG members may submit scores."""
        if user.role not in (UserRole.ADMIN, UserRole.SWG):
            raise PermissionDenied("Only SWG members and admins can submit scores.")


    
    def get_queryset(self):
        qs = InterventionScore.objects.select_related(
            "reviewer", "intervention", "criteria", "rescored_by"
        ).filter(reviewer=self.request.user)
        intervention_id = self.request.query_params.get("intervention")
        if intervention_id:
            qs = qs.filter(intervention_id=intervention_id)
        return qs
 
    def get_serializer_class(self):
        if self.action in ("create", "bulk_create", "rescore", "bulk_rescore"):
            return InterventionScoreCreateSerializer
        return InterventionScoreSerializer
 
    # def perform_create(self, serializer):
    #     serializer.save(reviewer=self.request.user)
    
    def perform_create(self, serializer):
        self._assert_can_score(self.request.user)
        serializer.save(reviewer=self.request.user)

 
    def perform_update(self, serializer):
        raise PermissionDenied(
            "Scores cannot be edited directly. "
            "Use the rescore endpoint once a rescore window is open."
        )
 
    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk_create(self, request):
        items = request.data.get("scores", [])
        if not items:
            raise ValidationError({"detail": "No scores provided."})
 
        errors = []
        try:
            with transaction.atomic():
                created = []
                for i, item in enumerate(items):
                    s = InterventionScoreCreateSerializer(data=item)
                    if not s.is_valid():
                        errors.append(
                            {"index": i, "criteria": item.get("criteria"), "errors": s.errors}
                        )
                    else:
                        created.append(s.save(reviewer=request.user))
 
                if errors:
                    raise ValidationError(
                        {"detail": "Validation failed — no scores were saved.", "errors": errors}
                    )
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError({"detail": "Unexpected error.", "error": str(exc)})
 
        return Response(
            InterventionScoreSerializer(created, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["patch"], url_path="rescore")
    def rescore(self, request, pk=None):
        """
        Reviewer patches their own existing score — in-place, no new row.
 
        Guards:
          1. Caller must own the score (reviewer == request.user)
          2. intervention.rescore_open must be True
          3. is_rescored must be False  (max once)
 
        PATCH /intervention-scores/<id>/rescore/
        Payload: { "score": {...}, "comment": "..." }
        """
        instance = self.get_object()
 
        if instance.reviewer != request.user:
            raise PermissionDenied("You can only rescore your own scores.")
 
        if not instance.intervention.rescore_open:
            raise PermissionDenied(
                "Rescoring is not open for this intervention. "
                "Ask an admin, SWG, or secretariat member to open it."
            )
 
        if instance.is_rescored:
            raise ValidationError(
                {"detail": "This score has already been rescored and cannot be edited again."}
            )
 
        s = InterventionScoreCreateSerializer(instance, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        # Patch the existing row in-place; mark it as rescored
        updated = s.save(is_rescored=True, rescored_by=request.user)
 
        return Response(InterventionScoreSerializer(updated).data, status=status.HTTP_200_OK)
 
    @action(detail=False, methods=["patch"], url_path="bulk")
    def bulk_update(self, request):
        """
        Bulk-patch existing scores.
        When rescore_open is True this acts as the rescore endpoint.
    
        PATCH /v3/intervention-scores/bulk/
        {
            "intervention": "<uuid>",
            "scores": [
                {"id": "<score-uuid>", "score": {...}, "comment": "..."},
                ...
            ]
        }
        """
        intervention_id = request.data.get("intervention")
        items = request.data.get("scores", [])
    
        if not intervention_id:
            raise ValidationError({"detail": "`intervention` is required."})
        if not items:
            raise ValidationError({"detail": "No scores provided."})
    
        # Rescore window must be open
        try:
            intervention = InterventionProposal.objects.get(pk=intervention_id)
        except InterventionProposal.DoesNotExist:
            raise ValidationError({"detail": "Intervention not found."})
    
        if not intervention.rescore_open:
            raise PermissionDenied(
                "Rescoring is not open for this intervention. "
                "Ask an admin, SWG, or secretariat member to open it."
            )
    
        errors = []
        try:
            with transaction.atomic():
                updated = []
                for i, item in enumerate(items):
                    score_id = item.get("id")
                    if not score_id:
                        errors.append({"index": i, "errors": {"id": "Score `id` is required."}})
                        continue
    
                    try:
                        existing = InterventionScore.objects.get(
                            pk=score_id,
                            reviewer=request.user,
                        )
                    except InterventionScore.DoesNotExist:
                        errors.append({
                            "index": i,
                            "id": score_id,
                            "errors": {"id": "Score not found or does not belong to you."},
                        })
                        continue
    
                    if existing.is_rescored:
                        errors.append({
                            "index": i,
                            "id": score_id,
                            "errors": {"detail": "This score has already been rescored once."},
                        })
                        continue
    
                    s = InterventionScoreCreateSerializer(existing, data=item, partial=True)
                    if not s.is_valid():
                        errors.append({"index": i, "id": score_id, "errors": s.errors})
                    else:
                        updated.append(s.save(is_rescored=True, rescored_by=request.user))
    
                if errors:
                    raise ValidationError(
                        {"detail": "Validation failed — no scores were updated.", "errors": errors}
                    )
    
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError({"detail": "Unexpected error.", "error": str(exc)})
    
        return Response(
            InterventionScoreSerializer(updated, many=True).data,
            status=status.HTTP_200_OK,
        )
        
            
class ScoringReportView(APIView):
    """
    GET /v3/scoring-report/
    Optional: ?intervention=<uuid>,<uuid>
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        raw = request.query_params.get("intervention", "")
        intervention_ids = [i.strip() for i in raw.split(",") if i.strip()] or None

        report = ScoringReportService.generate(intervention_ids=intervention_ids)

        if not report.success:
            return Response(
                {"success": False, "message": report.message, "error": report.error},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(asdict(report), status=status.HTTP_200_OK)



class AdminScoreViewSet(viewsets.ModelViewSet):
    queryset = InterventionScore.objects.select_related(
        "reviewer", "intervention", "criteria"
    )
    serializer_class = InterventionScoreSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        # Admins and Secretariate see all scores
        if not (user.is_admin() or user.is_secretariate()):
            qs = qs.filter(reviewer=user)

        intervention_id = self.request.query_params.get("intervention")
        if intervention_id:
            qs = qs.filter(intervention_id=intervention_id)

        return qs
    
    


class WeightingReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        raw = request.query_params.get("intervention", "")
        intervention_ids = [i.strip() for i in raw.split(",") if i.strip()] or None

        report = WeightingReportService.generate(intervention_ids=intervention_ids)

        if not report.success:
            return Response(
                {"success": False, "message": report.message, "error": report.error},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        data = asdict(report)

        if not is_admin(request.user):
            data = {
                "success": report.success,
                "message": report.message,
                "reviewer_results": [],
                "reviewer_scores": [],
                "reviewer_rankings": [],
                "average_scores": data["average_scores"],   
                "average_ranking": data["average_ranking"],
                "error": None,
            }

        return Response(data, status=status.HTTP_200_OK)


class PublicProposalViewSet(ViewSet):
    permission_classes = [AllowAny]

    def list(self, request):
        return Response(PublicProposalService.fetch())


def _can_manage(user) -> bool:
    return user.role in (UserRole.ADMIN, UserRole.SECRETARIAT)

class TopicPriorityViewSet(viewsets.ModelViewSet):
    """Returns status info about an intervention or national program proposal."""

    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        return (
            InterventionStatusUpdate.objects
            .select_related(
                "intervention", "decision",
                "national_proposal",
            )
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return InterventionStatusUpdateWriteSerializer
        return InterventionStatusUpdateSerializer

    def _assert_can_manage(self, user):
        if not _can_manage(user):
            raise PermissionDenied(
                "Only secretariat and admin can modify topic priority records."
            )

    @action(
        detail=False,
        methods=["post"],
        url_path="bulk-move-to-panel",
        permission_classes=[IsAdmin],
    )
    def bulk_move_to_panel(self, request):
        intervention_ids = request.data.get("intervention_ids")

        if not intervention_ids or not isinstance(intervention_ids, list):
            return Response(
                {"detail": "A non-empty list of 'intervention_ids' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = TopicPriorityService.bulk_move_to_panel(intervention_ids, request.user)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)

        return Response(result, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["post"],
        url_path="move-to-panel",
        permission_classes=[IsAdmin],
    )
    def move_to_panel(self, request, pk=None):
        instance = self.get_object()

        if not instance.intervention_id:
            return Response(
                {"detail": "Move-to-panel applies to interventions only."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = TopicPriorityService.move_to_panel(
            str(instance.intervention_id), request.user
        )
        return Response(InterventionStatusUpdateSerializer(result).data)

    @action(
        detail=True,
        methods=["post"],
        url_path="undo-move-to-panel",
        permission_classes=[IsAdmin],
    )
    def undo_move_to_panel(self, request, pk=None):
        instance = self.get_object()

        if not instance.intervention_id:
            return Response(
                {"detail": "Move-to-panel applies to interventions only."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        has_scores = CriteriaAppraisalScore.objects.filter(
            intervention=instance.intervention
        ).exists()

        if has_scores:
            return Response(
                {
                    "detail": "This intervention has existing appraisal scores and cannot be removed from panel.",
                    "reason": "has_scores",
                },
                status=status.HTTP_409_CONFLICT,
            )

        if not instance.move_to_panel:
            return Response(
                {
                    "detail": "This intervention is not currently on the panel.",
                    "reason": "not_on_panel",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        instance.move_to_panel = False
        instance.updated_by = request.user
        instance.save(update_fields=["move_to_panel", "updated_by", "updated_at"])

        TopicPriorityService.invalidate()

        return Response(
            {
                "detail": "Intervention successfully removed from panel.",
                "intervention_id": str(instance.intervention_id),
                "intervention_name": instance.intervention.intervention_name,
            },
            status=status.HTTP_200_OK,
        )

    def list(self, request, *args, **kwargs):
        return Response(TopicPriorityService.fetch())

    def create(self, request, *args, **kwargs):
        self._assert_can_manage(request.user)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = TopicPriorityService.create(serializer.validated_data, request.user)
        return Response(
            InterventionStatusUpdateSerializer(instance).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        self._assert_can_manage(request.user)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=kwargs.get("partial", False)
        )
        serializer.is_valid(raise_exception=True)
        instance = TopicPriorityService.update(instance, serializer.validated_data, request.user)
        return Response(InterventionStatusUpdateSerializer(instance).data)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_can_manage(request.user)
        instance = self.get_object()
        TopicPriorityService.delete(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

class DecisionTypeViewSet(viewsets.ModelViewSet):
    """
   Viewset for decisions
    """

    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    queryset = DecisionType.objects.all().order_by("name")

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return DecisionTypeCreateSerializer
        return DecisionTypeSerializer

    def _assert_can_manage(self, user):
        if not _can_manage(user):
            raise PermissionDenied(
                "Only secretariat and admin can manage decision types."
            )

    def create(self, request, *args, **kwargs):
        self._assert_can_manage(request.user)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._assert_can_manage(request.user)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._assert_can_manage(request.user)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._assert_can_manage(request.user)
        return super().destroy(request, *args, **kwargs)



class FeedbackCategoryViewSet(RetrieveModelMixin, ListModelMixin, GenericViewSet):
    queryset = FeedbackCategory.objects.none()
    permission_classes = [permissions.IsAuthenticated]
 
    def get_serializer_class(self):
        if self.action in ("create_category", "update_category"):
            return FeedbackCategoryWriteSerializer
        return FeedbackCategorySerializer
 
    def list(self, request, *args, **kwargs):
        return _ok(FeedbackCategorySerializer(FeedbackCategory.objects.all(), many=True).data)
 
    def retrieve(self, request, *args, **kwargs):
        instance, err = _get_or_404(FeedbackCategory, pk=kwargs["pk"])
        if err:
            return err
        return _ok(FeedbackCategorySerializer(instance).data)
 
    @action(detail=False, methods=["post"], url_path="create",
            permission_classes=[permissions.IsAuthenticated, IsAdmin])
    def create_category(self, request):
        name = request.data.get("name", "").strip()
        if name and FeedbackCategory.objects.filter(name__iexact=name).exists():
            return _err("A feedback category with this name already exists.", 409)
        serializer = FeedbackCategoryWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return _err(serializer.errors, 422)
        instance = serializer.save()
        return _ok(FeedbackCategorySerializer(instance).data, "Feedback category created.", 201)
 
    @action(detail=True, methods=["patch"], url_path="update",
            permission_classes=[permissions.IsAuthenticated, IsAdmin])
    def update_category(self, request, pk=None):
        instance, err = _get_or_404(FeedbackCategory, pk=pk)
        if err:
            return err
        serializer = FeedbackCategoryWriteSerializer(instance, data=request.data, partial=True)
        if not serializer.is_valid():
            return _err(serializer.errors, 422)
        return _ok(FeedbackCategorySerializer(serializer.save()).data, "Feedback category updated.")
 
    @action(detail=True, methods=["delete"], url_path="delete",
            permission_classes=[permissions.IsAuthenticated, IsAdmin])
    def delete_category(self, request, pk=None):
        instance, err = _get_or_404(FeedbackCategory, pk=pk)
        if err:
            return err
        instance.delete()
        return _ok(None, "Feedback category deleted.")
 
 



class FeedbackEmailLogViewSet(RetrieveModelMixin, ListModelMixin, GenericViewSet):
    queryset = FeedbackEmailLog.objects.none()
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    serializer_class = FeedbackEmailLogSerializer
 
    def _qs(self):
        return (
            FeedbackEmailLog.objects
            .select_related("intervention", "category", "sent_by")
            .prefetch_related(
                "intervention__system_categories__system_category",
                "intervention__status_updates__decision",
            )
            .order_by("-created_at")
        )
 
    def list(self, request, *args, **kwargs):
        qs = self._qs()
        # optional filters
        if s := request.query_params.get("status"):
            qs = qs.filter(status=s)
        if cid := request.query_params.get("category"):
            qs = qs.filter(category_id=cid)
        if iid := request.query_params.get("intervention"):
            qs = qs.filter(intervention_id=iid)
        if date_from := request.query_params.get("date_from"):
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to := request.query_params.get("date_to"):
            qs = qs.filter(created_at__date__lte=date_to)
        return _ok(FeedbackEmailLogSerializer(qs, many=True).data)
 
    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self._qs().get(pk=kwargs["pk"])
        except FeedbackEmailLog.DoesNotExist:
            return _err("Email log not found.", 404)
        return _ok(FeedbackEmailLogSerializer(instance).data)
 
    @action(detail=False, methods=["get"], url_path="by-intervention")
    def by_intervention(self, request):
        iid = request.query_params.get("intervention")
        if not iid:
            return _err("'intervention' query param is required.")
        return _ok(FeedbackEmailLogSerializer(self._qs().filter(intervention_id=iid), many=True).data)
 
    @action(detail=False, methods=["get"], url_path="by-category")
    def by_category(self, request):
        cid = request.query_params.get("category")
        if not cid:
            return _err("'category' query param is required.")
        return _ok(FeedbackEmailLogSerializer(self._qs().filter(category_id=cid), many=True).data)
 

    @action(detail=False, methods=["post"], url_path="send")
    def send_email(self, request):
        from users.models import InterventionProposal
        
 
        iid = request.data.get("intervention")
        cid = request.data.get("category")
        if not iid: return _err("'intervention' is required.")
        if not cid: return _err("'category' is required.")
 
        intervention, err = _get_or_404(InterventionProposal, pk=iid)
        if err: return err
        category, err = _get_or_404(FeedbackCategory, pk=cid, is_active=True)
        if err: return _err("Feedback category not found or inactive.", 404)
 
        su = None
        if su_id := request.data.get("status_update"):
            su, err = _get_or_404(InterventionStatusUpdate, pk=su_id, intervention=intervention)
            if err: return _err("Status update not found for this intervention.", 404)
 
        ok = send_feedback_email(
            intervention=intervention, category=category,
            status_update=su, sent_by=request.user,
        )
        if not ok:
            return _err("Failed to send email. Check logs for details.", 500)
 
        FeedbackService.invalidate()
        log = self._qs().filter(intervention=intervention, category=category).first()
        return _ok(FeedbackEmailLogSerializer(log).data if log else None, "Email sent successfully.")

    @action(detail=True, methods=["post"], url_path="resend")
    def resend_email(self, request, pk=None):
        """Re-send an existing log entry. Creates a fresh log — does not mutate the original."""
        ok, message = FeedbackService.resend(log_id=pk, sent_by=request.user)
        if not ok:
            return _err(message, 400)
        log = self._qs().filter(
            intervention_id=FeedbackEmailLog.objects.get(pk=pk).intervention_id
        ).first()
        return _ok(FeedbackEmailLogSerializer(log).data if log else None, message)
 
    @action(detail=True, methods=["delete"], url_path="delete")
    def delete_log(self, request, pk=None):
        instance, err = _get_or_404(FeedbackEmailLog, pk=pk)
        if err: return err
        instance.delete()
        FeedbackService.invalidate()
        return _ok(None, "Email log deleted.")
 
    @action(detail=False, methods=["post"], url_path="bulk-send")
    def bulk_send(self, request):
        cid  = request.data.get("category")
        iids = request.data.get("intervention_ids", [])
        if not cid: return _err("'category' is required.")
        if not iids or not isinstance(iids, list): return _err("'intervention_ids' must be a non-empty list.")
        if len(iids) > 100: return _err("Maximum 100 interventions per bulk send.")
 
        result = FeedbackService.bulk_send(
            intervention_ids=iids, category_id=cid, sent_by=request.user,
        )
        return Response(
            {
                "success": result.success,
                "message": f"Sent {result.sent_count}/{result.total}. Failed: {result.failed_count}.",
                "data": {
                    "total": result.total, "sent_count": result.sent_count,
                    "failed_count": result.failed_count, "sent": result.sent,
                    "failed": result.failed, "errors": result.errors,
                },
            },
            status=status.HTTP_200_OK if result.success else status.HTTP_207_MULTI_STATUS,
        )

    @action(detail=False, methods=["get"], url_path="intervention-statuses")
    def intervention_statuses(self, request):
        from dataclasses import asdict
        date_from = request.query_params.get("date_from")
        date_to   = request.query_params.get("date_to")
        statuses  = FeedbackService.get_all_statuses(date_from=date_from, date_to=date_to)
        return _ok([asdict(s) for s in statuses])

    
    
    

class CriteriaAppraisalToolViewSet(viewsets.ModelViewSet):
 
    queryset = CriteriaAppraisalTool.objects.all().order_by("criteria")
 
    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [IsAdmin()]
 
    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CriteriaAppraisalToolWriteSerializer
        return CriteriaAppraisalToolSerializer
 


class CriteriaAppraisalScoreViewSet(viewsets.ModelViewSet):
 
    permission_classes = [permissions.IsAuthenticated]
 
    def _assert_can_score(self, user) -> None:
        if user.role not in (UserRole.ADMIN, UserRole.PANEL):
            raise PermissionDenied("Only panel members and admins can submit appraisal scores.")
 

    def get_queryset(self):
        return get_scores_for_user(
            self.request.user,
            intervention_id=self.request.query_params.get("intervention"),
        )
 
    def get_serializer_class(self):
        if self.action in ("create", "bulk_create"):
            return CriteriaAppraisalScoreCreateSerializer
        return CriteriaAppraisalScoreSerializer
 
 
    def perform_create(self, serializer):
        self._assert_can_score(self.request.user)
        vd = serializer.validated_data
        instance = bulk_create_scores(
            user=self.request.user,
            intervention_id=str(vd["intervention"].id),
            items=[{
                "criteria_id": str(vd["criteria"].id),
                "score": vd["score"],
                "comment": vd.get("comment", ""),
            }],
        )[0]
        serializer.instance = instance
 
 
    def perform_update(self, serializer):
        raise PermissionDenied(
            "Scores are immutable after creation."
        )
 
 
    def destroy(self, request, *args, **kwargs):
        if request.user.role != UserRole.ADMIN:
            raise PermissionDenied("Only admins can delete appraisal scores.")
        return super().destroy(request, *args, **kwargs)
 
    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk_create(self, request):
        self._assert_can_score(request.user)
 
        intervention_id = request.data.get("intervention_id")
        items = request.data.get("scores", [])
 
        if not intervention_id:
            raise ValidationError({"detail": "'intervention_id' is required."})
        if not items:
            raise ValidationError({"detail": "No scores provided."})
 

        errors = []
        validated = []
        for i, item in enumerate(items):
            s = CriteriaAppraisalScoreCreateSerializer(data={
                "intervention": intervention_id,
                "criteria": item.get("criteria_id"),
                "score": item.get("score"),
                "comment": item.get("comment", ""),
            })
            if not s.is_valid():
                errors.append({"index": i, "criteria": item.get("criteria_id"), "errors": s.errors})
            else:
                validated.append({
                    "criteria_id": item["criteria_id"],
                    "score": item["score"],
                    "comment": item.get("comment", ""),
                })
 
        if errors:
            raise ValidationError({"detail": "Validation failed — nothing saved.", "errors": errors})
 
        created = bulk_create_scores(
            user=request.user,
            intervention_id=intervention_id,
            items=validated,
        )
 
        return Response(
            CriteriaAppraisalScoreSerializer(created, many=True).data,
            status=status.HTTP_201_CREATED,
        )

class AppraisalCriteriaEvidenceViewSet(viewsets.ModelViewSet):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        if self.action == "destroy":
            return [IsAdmin()]
        return [IsSecretariatOrAdmin()]  # create, update, partial_update

    def get_queryset(self):
        qs = AppraisalCriteriaEvidence.objects.select_related(
            "intervention", "created_by"
        ).prefetch_related("documents", "images")

        intervention_id = self.request.query_params.get("intervention")
        if intervention_id:
            qs = qs.filter(intervention_id=intervention_id)

        return qs

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return AppraisalCriteriaEvidenceWriteSerializer
        return AppraisalCriteriaEvidenceSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        user = self.request.user
        is_owner = instance.created_by == user
        is_admin = user.has_role(UserRole.ADMIN)
        if not (is_owner or is_admin):
            raise PermissionDenied("You are not authorized to perform this action.")
        instance.delete()



class ActivityViewSet(viewsets.ModelViewSet):
    serializer_class = ActivitySerializer
    http_method_names = ["get", "post", "delete", "head", "options"]
 
    def get_permissions(self):
        if self.action in ("create", "destroy"):
            return [IsAdmin()]
        return [IsAuthenticatedAndActive()]
 
    def get_queryset(self):
        user = self.request.user
        if IsAdmin().has_permission(self.request, self):
            return Activity.objects.all()
        return Activity.objects.filter(sub_activities__assigned_to=user).distinct()
 
    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        if not qs.exists():
            return _ok([], "No activities found.")
        return _ok(self.get_serializer(qs, many=True).data, f"{qs.count()} activit{'y' if qs.count() == 1 else 'ies'} loaded.")
 
    def retrieve(self, request, *args, **kwargs):
        try:
            activity = self.get_object()
        except Exception:
            return _err("This activity does not exist or you do not have access to it.", 404)
        return _ok(self.get_serializer(activity).data, f"Activity '{activity.name}' loaded.")
 
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return _err(serializer.errors)
        activity = serializer.save(created_by=request.user)
        return _ok(serializer.data, f"Activity '{activity.name}' created successfully.", 201)
 
    def destroy(self, request, *args, **kwargs):
        try:
            activity = self.get_object()
        except Exception:
            return _err("Activity not found. It may have already been deleted.", 404)
        name = activity.name
        activity.delete()
        return _ok(None, f"Activity '{name}' and all its sub-activities have been permanently deleted.")
 
 
class SubActivityViewSet(viewsets.ModelViewSet):
    serializer_class = SubActivitySerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
 
    def get_permissions(self):
        if self.action in ("create", "destroy"):
            return [IsAdmin()]
        return [IsAuthenticatedAndActive()]
 
    def get_queryset(self):
        user = self.request.user
        qs = SubActivity.objects.select_related("activity", "completed_by").prefetch_related("assigned_to")
        if IsAdmin().has_permission(self.request, self):
            return qs.all()
        return qs.filter(assigned_to=user)
 
    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        if not qs.exists():
            return _ok([], "No sub-activities assigned to you at the moment.")
        return _ok(self.get_serializer(qs, many=True).data, f"{qs.count()} sub-activit{'y' if qs.count() == 1 else 'ies'} loaded.")
 
    def retrieve(self, request, *args, **kwargs):
        try:
            sub = self.get_object()
        except Exception:
            return _err("This sub-activity does not exist or you are not assigned to it.", 404)
        return _ok(self.get_serializer(sub).data, f"Sub-activity '{sub.name}' loaded.")
 

    
    # def create(self, request, *args, **kwargs):
    #     serializer = self.get_serializer(data=request.data)
    #     if not serializer.is_valid():
    #         return _err(serializer.errors)
    #     sub = serializer.save()
    #     # thread the responses in background
    #     if sub.send_email_alert:
    #         threading.Thread(
    #             target=send_activity_assignment_emails,
    #             args=(sub,),
    #             daemon=True,
    #         ).start()
 
    #     return _ok(serializer.data, f"Sub-activity '{sub.name}' created and added to '{sub.activity.name}'.", 201)
    
    #     threading.Thread(
    #         target=_notify_assigned_users,
    #         args=(sub,),
    #         daemon=True,
    #     ).start()
 
    #     return _ok(
    #         serializer.data,
    #         f"Sub-activity '{sub.name}' created and added to '{sub.activity.name}'.",
    #         201,
    #     )
 
 
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return _err(serializer.errors)

        sub = serializer.save()

        if sub.send_email_alert:
            threading.Thread(
                target=send_activity_assignment_emails,
                args=(sub,),
                daemon=True,
            ).start()

        threading.Thread(
            target=_notify_assigned_users,
            args=(sub,),
            daemon=True,
        ).start()

        return _ok(
            serializer.data,
            f"Sub-activity '{sub.name}' created and added to '{sub.activity.name}'.",
            201,
        )
 
    def partial_update(self, request, *args, **kwargs):
        try:
            sub = self.get_object()
        except Exception:
            return _err("Sub-activity not found or you are not assigned to it.", 404)
 
        if sub.status == "completed":
            return _err(f"'{sub.name}' is already completed and cannot be edited.")
 
        serializer = self.get_serializer(sub, data=request.data, partial=True)
        if not serializer.is_valid():
            return _err(serializer.errors)
        serializer.save()
        return _ok(serializer.data, f"Sub-activity '{sub.name}' updated successfully.")
 
    def destroy(self, request, *args, **kwargs):
        try:
            sub = self.get_object()
        except Exception:
            return _err("Sub-activity not found. It may have already been deleted.", 404)
        name = sub.name
        sub.delete()
        return _ok(None, f"Sub-activity '{name}' has been permanently deleted.")
 
    @action(detail=True, methods=["patch"], url_path="complete")
    def complete(self, request, pk=None):
        try:
            sub = self.get_object()
        except Exception:
            return _err("Sub-activity not found or you are not assigned to it.", 404)
 
        if not IsAdmin().has_permission(request, self):
            if not sub.assigned_to.filter(pk=request.user.pk).exists():
                return _err("You can only complete sub-activities that are assigned to you.", 403)
 
        if sub.status == "completed":
            return _err(
                f"'{sub.name}' was already completed"
            )
 
        sub.status = "completed"
        sub.completed_at = timezone.now()
        sub.completed_by = request.user
        sub.save(update_fields=["status", "completed_at", "completed_by"])
        return _ok(self.get_serializer(sub).data, f"'{sub.name}' marked as completed. Well done!")




def _ids(request, key):
    """Accept repeated multipart fields or a JSON array string/list."""
    data = request.data
    vals = data.getlist(key) if hasattr(data, "getlist") else data.get(key)
    if isinstance(vals, str):
        try:
            vals = json.loads(vals)
        except ValueError:
            vals = [vals] if vals else []
    return vals or []


def _documents(request):
    """Pair uploaded files with their parallel descriptions[]."""
    files = request.FILES.getlist("files")
    descs = request.data.getlist("descriptions") if hasattr(request.data, "getlist") else []
    return [{"file": f, "description": descs[i] if i < len(descs) else ""} for i, f in enumerate(files)]


class AssessmentEvidenceViewSet(viewsets.ViewSet):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update"):
            return [(IsAssessment | IsSecretariatOrAdmin)()]   # assessment, secretariat, admin
        if self.action == "destroy":
            return [IsAdmin()]                               
        return [IsAuthenticated()]                           
    def list(self, request):
        qs = AssessmentEvidenceService.queryset()
        return _ok(AssessmentEvidenceSerializer(qs, many=True).data)

    def retrieve(self, request, pk=None):
        obj, err = _get_or_404(AssessmentEvidence, pk=pk)
        if err:
            return err
        return _ok(AssessmentEvidenceSerializer(obj).data)

    def create(self, request):
        try:
            evidence = AssessmentEvidenceService.create(
                summary=request.data.get("summary", ""),
                intervention_ids=_ids(request, "intervention_ids"),
                program_proposal_ids=_ids(request, "program_proposal_ids"),
                documents=_documents(request),
                user=request.user,
            )
        except Exception:
            logger.exception("Failed to create assessment evidence")
            return _err("Could not save the evidence due to a server error.", 500)
        return _ok(AssessmentEvidenceSerializer(evidence).data, "Evidence saved.", 201)

    def update(self, request, pk=None):
        obj, err = _get_or_404(AssessmentEvidence, pk=pk)
        if err:
            return err
        try:
            evidence = AssessmentEvidenceService.update(
                obj,
                summary=request.data.get("summary"),
                intervention_ids=_ids(request, "intervention_ids") if "intervention_ids" in request.data else None,
                program_proposal_ids=_ids(request, "program_proposal_ids") if "program_proposal_ids" in request.data else None,
                documents=_documents(request),
                user=request.user,
            )
        except Exception:
            logger.exception("Failed to update assessment evidence %s", pk)
            return _err("Could not update the evidence due to a server error.", 500)
        return _ok(AssessmentEvidenceSerializer(evidence).data, "Evidence updated.")

    partial_update = update


    @action(detail=True, methods=["get"])
    def group(self, request, pk=None):
        obj, err = _get_or_404(AssessmentEvidence, pk=pk)
        if err:
            return err
        qs = AssessmentEvidenceService.related_by_reference(obj)
        return _ok(AssessmentEvidenceSerializer(qs, many=True).data)
    
    
    def destroy(self, request, pk=None):
        obj, err = _get_or_404(AssessmentEvidence, pk=pk)
        if err:
            return err
        try:
            obj.delete()
        except Exception:
            logger.exception("Failed to delete assessment evidence %s", pk)
            return _err("Could not delete the evidence due to a server error.", 500)
        return _ok(None, "Evidence deleted.")
    
    


class InterventionPackageViewSet(viewsets.ViewSet):

    ADMIN_ACTIONS = {
        "create", "update", "partial_update", "destroy",
        "link", "unlink", "bulk_upload",
    }

    def get_permissions(self):
        if self.action in self.ADMIN_ACTIONS:
            return [IsAdmin()]
        return [IsAuthenticated()]

    def list(self, request):
        qs = InterventionPackageService.list_packages()
        return _ok(InterventionPackageSerializer(qs, many=True).data)

    def retrieve(self, request, pk=None):
        pkg, err = _get_or_404(InterventionPackage, pk=pk)
        if err:
            return err
        return _ok(InterventionPackageSerializer(pkg).data)

    def create(self, request):
        s = InterventionPackageSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        pkg = InterventionPackageService.create_package(s.validated_data)
        return _ok(InterventionPackageSerializer(pkg).data, status_code=201)

    def partial_update(self, request, pk=None):
        pkg, err = _get_or_404(InterventionPackage, pk=pk)
        if err:
            return err
        s = InterventionPackageSerializer(pkg, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        pkg = InterventionPackageService.update_package(pkg, s.validated_data)
        return _ok(InterventionPackageSerializer(pkg).data)

    def destroy(self, request, pk=None):
        if getattr(request.user, "role", None) != "admin":
            return _err("Not authorized to perform this action", status_code=403)
        pkg, err = _get_or_404(InterventionPackage, pk=pk)
        if err:
            return err
        InterventionPackageService.delete_package(pkg)
        return _ok({"deleted": True})
    
    @action(detail=True, methods=["post"], url_path="link")
    def link(self, request, pk=None):
        pkg, err = _get_or_404(InterventionPackage, pk=pk)
        if err:
            return err
        ref = (request.data.get("reference_number") or "").strip()
        if not ref:
            return _err("reference_number is required", status_code=400)
        ok = InterventionPackageService.link_one(pkg, ref)  # returns True/False
        return _ok({"linked": ok}) if ok else _err("No proposal found for reference", status_code=404)

    @action(detail=True, methods=["post"], url_path="unlink")
    def unlink(self, request, pk=None):
        ref = (request.data.get("reference_number") or "").strip()
        if not ref:
            return _err("reference_number is required", status_code=400)
        proposal = (
            InterventionProposal.objects.filter(reference_number=ref, package_id=pk).first()
            or NationalProgramProposal.objects.filter(reference_number=ref, package_id=pk).first()
        )
        if not proposal:
            return _err("No linked proposal found for that reference", status_code=404)
        proposal.package = None
        proposal.save(update_fields=["package"])
        return _ok({"unlinked": True})

    @action(detail=False, methods=["post"], url_path="bulk-upload")
    def bulk_upload(self, request):
        rows = request.data.get("rows", [])
        if not isinstance(rows, list):
            return _err("rows must be a list", status_code=400)
        return _ok(InterventionPackageService.bulk_upload(rows))


    @action(detail=False, methods=["get"], url_path="grouped")
    def grouped(self, request):
        return _ok(InterventionPackageService.grouped())



# we need to group into batched here
class InterventionPhaseViewSet(viewsets.ViewSet):

    ADMIN_ACTIONS = {
        "create", "update", "partial_update", "destroy",
        "link", "unlink", "bulk_upload",
    }

    def get_permissions(self):
        if self.action in self.ADMIN_ACTIONS:
            return [IsAdmin()]
        return [IsAuthenticated()]

    def list(self, request):
        qs = InterventionPhaseService.list_phases()
        return _ok(InterventionPhaseSerializer(qs, many=True).data)

    def retrieve(self, request, pk=None):
        phase, err = _get_or_404(InterventionPhase, pk=pk)
        if err:
            return err
        return _ok(InterventionPhaseSerializer(phase).data)

    def create(self, request):
        s = InterventionPhaseSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        phase = InterventionPhaseService.create_phase(s.validated_data)
        return _ok(InterventionPhaseSerializer(phase).data, status_code=201)

    def partial_update(self, request, pk=None):
        phase, err = _get_or_404(InterventionPhase, pk=pk)
        if err:
            return err
        s = InterventionPhaseSerializer(phase, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        phase = InterventionPhaseService.update_phase(phase, s.validated_data)
        return _ok(InterventionPhaseSerializer(phase).data)

    def destroy(self, request, pk=None):
        if getattr(request.user, "role", None) != "admin":
            return _err("Not authorized to perform this action", status_code=403)
        phase, err = _get_or_404(InterventionPhase, pk=pk)
        if err:
            return err
        InterventionPhaseService.delete_phase(phase)
        return _ok({"deleted": True})

    @action(detail=True, methods=["post"], url_path="link")
    def link(self, request, pk=None):
        phase, err = _get_or_404(InterventionPhase, pk=pk)
        if err:
            return err
        ref = (request.data.get("reference_number") or "").strip()
        if not ref:
            return _err("reference_number is required", status_code=400)
        ok = InterventionPhaseService.link_one(phase, ref)
        return _ok({"linked": ok}) if ok else _err("No proposal found for reference", status_code=404)

    @action(detail=True, methods=["post"], url_path="unlink")
    def unlink(self, request, pk=None):
        ref = (request.data.get("reference_number") or "").strip()
        if not ref:
            return _err("reference_number is required", status_code=400)
        proposal = (
            InterventionProposal.objects.filter(reference_number=ref, phase_id=pk).first()
            or NationalProgramProposal.objects.filter(reference_number=ref, phase_id=pk).first()
        )
        if not proposal:
            return _err("No linked proposal found for that reference", status_code=404)
        proposal.phase = None
        proposal.save(update_fields=["phase"])
        return _ok({"unlinked": True})

    @action(detail=False, methods=["post"], url_path="bulk-upload")
    def bulk_upload(self, request):
        rows = request.data.get("rows", [])
        if not isinstance(rows, list):
            return _err("rows must be a list", status_code=400)
        return _ok(InterventionPhaseService.bulk_upload(rows))

    @action(detail=False, methods=["get"], url_path="grouped")
    def grouped(self, request):
        return _ok(InterventionPhaseService.grouped())



class BenefitPackageViewSet(viewsets.ViewSet):
    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        return [IsAuthenticated(), IsAdmin()]
 
    def list(self, request):
        qs = list_packages(request.query_params.get("fund"))
        return _ok(BenefitPackageSerializer(qs, many=True).data)
 
    def retrieve(self, request, pk=None):
        obj, err = _get_or_404(BenefitPackage, pk=pk)
        if err:
            return err
        return _ok(BenefitPackageSerializer(obj).data)
 
    def create(self, request):
        ser = BenefitPackageSerializer(data=request.data)
        if not ser.is_valid():
            return _err(ser.errors, status.HTTP_400_BAD_REQUEST)
        obj = create_package(**ser.validated_data)
        return _ok(BenefitPackageSerializer(obj).data, status.HTTP_201_CREATED)
 
    def update(self, request, pk=None):
        obj, err = _get_or_404(BenefitPackage, pk=pk)
        if err:
            return err
        ser = BenefitPackageSerializer(obj, data=request.data, partial=True)
        if not ser.is_valid():
            return _err(ser.errors, status.HTTP_400_BAD_REQUEST)
        obj = update_package(obj, **ser.validated_data)
        return _ok(BenefitPackageSerializer(obj).data)
 
    partial_update = update
 
    def destroy(self, request, pk=None):
        obj, err = _get_or_404(BenefitPackage, pk=pk)
        if err:
            return err
        delete_package(obj)
        return _ok({"deleted": str(pk)})




def _respond(env):
    if env["ok"]:
        return Response(env.get("data"), status=env.get("status", 200))
    return Response({"error": env.get("error")}, status=env.get("status", 400))

class CriteriaViewSet(viewsets.ViewSet):
    ADMIN_ACTIONS = {"destroy"}
    WRITE_ACTIONS = {"create", "update", "partial_update", "panel"}

    def get_permissions(self):
        if self.action in self.ADMIN_ACTIONS: return [IsAdmin()]
        if self.action in self.WRITE_ACTIONS: return [IsSecretariatOrAdmin()]
        return [IsAuthenticated()]

    def list(self, request):              
        return _respond(AppraisalPanelService.list_criteria(request.query_params))
    
    def retrieve(self, request, pk=None): 
        return _respond(AppraisalPanelService.get_criterion(pk))
    def create(self, request):            
        return _respond(AppraisalPanelService.create_criterion(request.data))
    def update(self, request, pk=None):   
        return _respond(AppraisalPanelService.update_criterion(pk, request.data, False))
    def partial_update(self, request, pk=None): 
        return _respond(AppraisalPanelService.update_criterion(pk, request.data, True))
    def destroy(self, request, pk=None):  
        return _respond(AppraisalPanelService.delete_criterion(pk))

    @action(detail=True, methods=["patch"], url_path="panel")
    def panel(self, request, pk=None):    
        return _respond(AppraisalPanelService.configure_criterion(pk, request.data))

class EvidenceViewSet(viewsets.ViewSet):
    ADMIN_ACTIONS = {"destroy", "bulk_delete"}
    WRITE_ACTIONS = {"create", "update", "partial_update", "bulk_upload"}

    def get_permissions(self):
        if self.action in self.ADMIN_ACTIONS: 
            return [IsAdmin()]
        if self.action in self.WRITE_ACTIONS: 
            return [IsSecretariatOrAdmin()]
        return [IsAuthenticated()]

    def list(self, request):              
        return _respond(AppraisalPanelService.list_evidence(request.query_params))
    def create(self, request):            
        return _respond(AppraisalPanelService.create_evidence(request.data))
    def update(self, request, pk=None):   
        return _respond(AppraisalPanelService.update_evidence(pk, request.data, False))
    def partial_update(self, request, pk=None): 
        return _respond(AppraisalPanelService.update_evidence(pk, request.data, True))
    def destroy(self, request, pk=None):  
        return _respond(AppraisalPanelService.delete_evidence(pk))

    @action(detail=False, methods=["post"], url_path="bulk-upload")
    def bulk_upload(self, request):       
        return _respond(AppraisalPanelService.bulk_upload_evidence(request.data.get("rows", request.data)))

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):       
        return _respond(AppraisalPanelService.bulk_delete_evidence(request.data.get("ids", [])))


class EvidenceCoverageViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        return _respond(cov.list_coverage(request.query_params))
    def retrieve(self, request, pk=None):
        return _respond(cov.target_detail_by_id(pk))



class CriteriaRuleViewSet(viewsets.ViewSet):
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    ADMIN_ACTIONS = {"destroy", "delete_document"}
    WRITE_ACTIONS = {"create", "update", "partial_update", "bulk_upsert", "add_document"}

    def get_permissions(self):
        if self.action in self.ADMIN_ACTIONS: return [IsAdmin()]
        if self.action in self.WRITE_ACTIONS: return [IsSecretariatOrAdmin()]
        return [IsAuthenticated()]

    def list(self, request):              
        return _respond(rules.list_rules(request.query_params))
    def retrieve(self, request, pk=None): 
        return _respond(rules.get_rule(pk))
    def create(self, request):            
        return _respond(rules.create_rule(request.data))
    def update(self, request, pk=None):   
        return _respond(rules.update_rule(pk, request.data, False))
    def partial_update(self, request, pk=None): 
        return _respond(rules.update_rule(pk, request.data, True))
    def destroy(self, request, pk=None):  
        return _respond(rules.delete_rule(pk))

    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk_upsert(self, request):
        return _respond(rules.bulk_upsert_rules(request.data.get("rules", request.data)))

    @action(detail=True, methods=["post"], url_path="documents")
    def add_document(self, request, pk=None):
        return _respond(rules.add_document(pk, request.data, request.FILES.get("file"), request))

    @action(detail=False, methods=["delete"], url_path=r"documents/(?P<doc_id>[^/.]+)")
    def delete_document(self, request, doc_id=None):
        return _respond(rules.delete_document(doc_id))
