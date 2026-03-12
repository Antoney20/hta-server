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

from django.db.models import Q
from django.core.cache import cache

from rest_framework import permissions, status
from dataclasses import asdict
from rest_framework.views import APIView
from app.services import criteria_info
from app.services.public_view import PublicProposalService
from users.models import InterventionProposal
from users.permissions import IsAdmin, IsSecretariate, IsContentManager, IsRegularUser, IsSWG, IsAuthenticatedAndActive, IsAuthenticatedOrReadOnly, IsOwnerOrAdminOrReadOnly
from app.services.scoring import ScoringReportService

from .models import CriteriaInformation, SelectionTool, SystemCategory, InterventionSystemCategory, InterventionScore
from .serializers import (
    CriteriaInformationCreateSerializer,
    CriteriaInformationSerializer,
    InterventionScoreCreateSerializer,
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

class SelectionToolViewSet(viewsets.ModelViewSet):
    queryset = SelectionTool.objects.all()
    serializer_class = SelectionToolSerializer
    # access to everyone except SWGs
    permission_classes = [permissions.IsAuthenticated, ~IsSWG]


class SystemCategoryViewSet(viewsets.ModelViewSet):
    queryset = SystemCategory.objects.all()
    serializer_class = SystemCategorySerializer
    permission_classes = [permissions.IsAuthenticated, ~IsSWG]





class InterventionSystemCategoryViewSet(viewsets.ModelViewSet):
    queryset = InterventionSystemCategory.objects.select_related("intervention", "system_category")
    serializer_class = InterventionSystemCategorySerializer
    permission_classes = [permissions.IsAuthenticated, ~IsSWG]

    def get_queryset(self):
        qs = super().get_queryset()
        intervention_id = self.request.query_params.get("intervention")
        if intervention_id:
            qs = qs.filter(intervention_id=intervention_id)
        return qs



 
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
 
    
class InterventionScoreViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = InterventionScore.objects.select_related(
            "reviewer", "intervention", "criteria"
        ).filter(reviewer=self.request.user)

        intervention_id = self.request.query_params.get("intervention")
        if intervention_id:
            qs = qs.filter(intervention_id=intervention_id)
        return qs

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return InterventionScoreCreateSerializer
        return InterventionScoreSerializer

    def perform_create(self, serializer):
        serializer.save(reviewer=self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.reviewer != self.request.user:
            raise PermissionDenied("You can only edit your own scores.")
        serializer.save()




        
        
class ScoringReportView(APIView):
    """
    GET /v3/scoring-report/
    Returns a full structured scoring report across all interventions.

    Optional query params:
      ?intervention=<uuid>,<uuid>   — filter to specific interventions
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        intervention_ids = None
        raw = request.query_params.get("intervention")
        if raw:
            intervention_ids = [i.strip() for i in raw.split(",") if i.strip()]

        result = ScoringReportService.generate(intervention_ids=intervention_ids)

        if not result.success:
            return Response(
                {"success": False, "message": result.message, "error": result.error},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(asdict(result), status=status.HTTP_200_OK)
    
    


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
    
    
# new public proposals viewset, should allow anyone to see  for now.
class PublicProposalViewSet(ViewSet):
    permission_classes = [AllowAny]

    def list(self, request):
        return Response(PublicProposalService.fetch())


#matching
# - 20 first chars
# - remove special chars numbers only remain with chars (efficient regex)
