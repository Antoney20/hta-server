from django.db import transaction
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


from django.db.models import Q
from django.core.cache import cache

from rest_framework import permissions, status
from dataclasses import asdict
from rest_framework.views import APIView
from app.services import criteria_info
from app.services.public_view import PublicProposalService
from app.services.tp import TopicPriorityService
from app.services.weighting import WeightingReportService
from users.models import InterventionProposal, UserRole
from users.permissions import IsAdmin, IsSecretariate, IsContentManager, IsRegularUser, IsSWG, IsAuthenticatedAndActive, IsAuthenticatedOrReadOnly, IsOwnerOrAdminOrReadOnly
from app.services.scoring import ScoringReportService
from users.serializers import InterventionProposalSerializer

from .models import CriteriaInformation, DecisionType, InterventionStatusUpdate, SelectionTool, SystemCategory, InterventionSystemCategory, InterventionScore
from .serializers import (
    CriteriaInformationCreateSerializer,
    CriteriaInformationSerializer,
    DecisionTypeCreateSerializer,
    DecisionTypeSerializer,
    InterventionScoreCreateSerializer,
    InterventionStatusUpdateSerializer,
    InterventionStatusUpdateWriteSerializer,
    SelectionToolSerializer,
    SystemCategorySerializer,
    InterventionSystemCategorySerializer,
    InterventionScoreSerializer,
)

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
        "intervention", "system_category"
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

        # All other actions → authenticated users
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

    # ------------------------------------------------------------------
    # Rescore window management
    # ------------------------------------------------------------------

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
    # permission_classes = [IsAuthenticated]

    def get(self, request):
        raw = request.query_params.get("intervention", "")
        intervention_ids = [i.strip() for i in raw.split(",") if i.strip()] or None

        report = WeightingReportService.generate(intervention_ids=intervention_ids)

        if not report.success:
            return Response(
                {"success": False, "message": report.message, "error": report.error},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(asdict(report), status=status.HTTP_200_OK)    



# new public proposals viewset, should allow anyone to see  for now.
class PublicProposalViewSet(ViewSet):
    permission_classes = [AllowAny]

    def list(self, request):
        return Response(PublicProposalService.fetch())


def _can_manage(user) -> bool:
    return user.role in (UserRole.ADMIN, UserRole.SECRETARIAT)


class TopicPriorityViewSet(viewsets.ModelViewSet):
    """
returns status info about an intervention
    """

    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        return (
            InterventionStatusUpdate.objects
            .select_related("intervention", "decision")
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
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get("partial", False))
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




#matching
# - 20 first chars
# - remove special chars numbers only remain with chars (efficient regex)



