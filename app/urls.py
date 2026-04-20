from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AdminScoreViewSet,
    CriteriaInformationViewSet,
    DecisionTypeViewSet,
    FeedbackCategoryViewSet,
    FeedbackEmailLogViewSet,
    InterventionProposalViewSet,
    PublicProposalViewSet,
    ScoringReportView,
    SelectionToolViewSet,
    SystemCategoryViewSet,
    InterventionSystemCategoryViewSet,
    InterventionScoreViewSet,
    TopicPriorityViewSet,
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
router.register(r"topic-priority", TopicPriorityViewSet, basename="topic-priority")
router.register(r"decision-types", DecisionTypeViewSet, basename="decision-type")
router.register(r"feedback-categories",  FeedbackCategoryViewSet,    basename="feedback-category")
router.register(r"feedback-email-logs",  FeedbackEmailLogViewSet,    basename="feedback-email-log")
 




# urlpatterns = router.urls
urlpatterns = [
    path("", include(router.urls)),
    path("scoring-report/", ScoringReportView.as_view(), name="scoring-report"),
    path("interventions/search/", search_interventions),
    path("weighting/", WeightingReportView.as_view(), name="weighting-report"),
    # path("admin-report/", AdminScoreViewSet.as_view(), name="scoring-report"),
]