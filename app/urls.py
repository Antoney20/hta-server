from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AdminScoreViewSet,
    ScoringReportView,
    SelectionToolViewSet,
    SystemCategoryViewSet,
    InterventionSystemCategoryViewSet,
    InterventionScoreViewSet,
)

router = DefaultRouter()
router.register("selection-tools", SelectionToolViewSet, basename="selection-tool")
router.register("system-categories", SystemCategoryViewSet, basename="system-category")
router.register("intervention-categories", InterventionSystemCategoryViewSet, basename="intervention-category")
router.register("intervention-scores", InterventionScoreViewSet, basename="intervention-score")
router.register(r"admin-report", AdminScoreViewSet, basename="admin-report")



# urlpatterns = router.urls
urlpatterns = [
    path("", include(router.urls)),
    path("scoring-report/", ScoringReportView.as_view(), name="scoring-report"),
    # path("admin-report/", AdminScoreViewSet.as_view(), name="scoring-report"),
]