from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied

from .models import SelectionTool, SystemCategory, InterventionSystemCategory, InterventionScore
from .serializers import (
    SelectionToolSerializer,
    SystemCategorySerializer,
    InterventionSystemCategorySerializer,
    InterventionScoreSerializer,
)


class SelectionToolViewSet(viewsets.ModelViewSet):
    queryset = SelectionTool.objects.all()
    serializer_class = SelectionToolSerializer
    # permission_classes = [permissions.IsAuthenticated]


class SystemCategoryViewSet(viewsets.ModelViewSet):
    queryset = SystemCategory.objects.all()
    serializer_class = SystemCategorySerializer
    permission_classes = [permissions.IsAuthenticated]


class InterventionSystemCategoryViewSet(viewsets.ModelViewSet):
    queryset = InterventionSystemCategory.objects.select_related("intervention", "system_category")
    serializer_class = InterventionSystemCategorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        intervention_id = self.request.query_params.get("intervention")
        if intervention_id:
            qs = qs.filter(intervention_id=intervention_id)
        return qs


class InterventionScoreViewSet(viewsets.ModelViewSet):
    queryset = InterventionScore.objects.select_related("reviewer", "intervention", "criteria")
    serializer_class = InterventionScoreSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        intervention_id = self.request.query_params.get("intervention")
        if intervention_id:
            qs = qs.filter(intervention_id=intervention_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(reviewer=self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.reviewer != self.request.user:
            raise PermissionDenied("You can only edit your own scores.")
        serializer.save()