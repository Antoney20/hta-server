from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AdminScoreViewSet,
    CriteriaInformationViewSet,
    InterventionProposalViewSet,
    PublicProposalViewSet,
    ScoringReportView,
    SelectionToolViewSet,
    SystemCategoryViewSet,
    InterventionSystemCategoryViewSet,
    InterventionScoreViewSet,
    WeightingReportView,
    search_interventions,
)

router = DefaultRouter()
router.register("selection-tools", SelectionToolViewSet, basename="selection-tool")
router.register("system-categories", SystemCategoryViewSet, basename="system-category")
router.register("intervention-categories", InterventionSystemCategoryViewSet, basename="intervention-category")
router.register(r"criteria-information", CriteriaInformationViewSet, basename="criteria-information")
router.register("intervention-scores", InterventionScoreViewSet, basename="intervention-score")
router.register(r"admin-report", AdminScoreViewSet, basename="admin-report")
router.register(r"proposals",  PublicProposalViewSet, basename="public-proposals")
router.register(r"re-open", InterventionProposalViewSet, basename="scoring-reopen")




# urlpatterns = router.urls
urlpatterns = [
    path("", include(router.urls)),
    path("scoring-report/", ScoringReportView.as_view(), name="scoring-report"),
    path("interventions/search/", search_interventions),
    path("weighting/", WeightingReportView.as_view(), name="weighting-report"),
    # path("admin-report/", AdminScoreViewSet.as_view(), name="scoring-report"),
]