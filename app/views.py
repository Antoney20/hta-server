from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework import permissions, status
from dataclasses import asdict
from rest_framework.views import APIView
from users.permissions import IsAdmin, IsSecretariate, IsContentManager, IsRegularUser, IsSWG, IsAuthenticatedAndActive, IsAuthenticatedOrReadOnly, IsOwnerOrAdminOrReadOnly
from app.services.scoring import ScoringReportService

from .models import SelectionTool, SystemCategory, InterventionSystemCategory, InterventionScore
from .serializers import (
    InterventionScoreCreateSerializer,
    SelectionToolSerializer,
    SystemCategorySerializer,
    InterventionSystemCategorySerializer,
    InterventionScoreSerializer,
)


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



# class InterventionScoreViewSet(viewsets.ModelViewSet):
#     queryset = InterventionScore.objects.select_related("reviewer", "intervention", "criteria")
#     serializer_class = InterventionScoreSerializer
#     permission_classes = [permissions.IsAuthenticated]

#     def get_queryset(self):
#         qs = super().get_queryset()
        
#         # Always scope to the current user's scores only
#         qs = qs.filter(reviewer=self.request.user)
        
#         intervention_id = self.request.query_params.get("intervention")
#         if intervention_id:
#             qs = qs.filter(intervention_id=intervention_id)
#         return qs
     
     
     

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