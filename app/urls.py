from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ActivityViewSet,
    AdminScoreViewSet,
    AppraisalCriteriaEvidenceViewSet,
    AssessmentEvidenceViewSet,
    CriteriaAppraisalScoreViewSet,
    CriteriaAppraisalToolViewSet,
    CriteriaInformationViewSet,
    DecisionTypeViewSet,
    EvidenceCriterionViewSet,
    EvidenceExtractionViewSet,
    FeedbackCategoryViewSet,
    FeedbackEmailLogViewSet,
    InterventionProposalViewSet,
    InterventionScoringWindowViewSet,
    NationalProgramProposalViewSet,
    NationalProgramViewSet,
    PublicProposalViewSet,
    ScoringReportView,
    SelectionToolViewSet,
    SubActivityViewSet,
    SystemCategoryViewSet,
    InterventionSystemCategoryViewSet,
    InterventionScoreViewSet,
    TopicPriorityViewSet,
    UsersListView,
    WeightingReportView,
    search_interventions,
)

router = DefaultRouter()
router.register(r"national-programs", NationalProgramViewSet, basename="national-program")
router.register(r"program-proposals", NationalProgramProposalViewSet, basename="program-proposal")
router.register("selection-tools", SelectionToolViewSet, basename="selection-tool")
router.register("system-categories", SystemCategoryViewSet, basename="system-category")
router.register("intervention-categories", InterventionSystemCategoryViewSet, basename="intervention-category")
router.register(r"criteria-information", CriteriaInformationViewSet, basename="criteria-information")
router.register("intervention-scores", InterventionScoreViewSet, basename="intervention-score")
router.register(r"admin-report", AdminScoreViewSet, basename="admin-report")
router.register(r"proposals",  PublicProposalViewSet, basename="public-proposals")
# router.register(r"re-open", InterventionProposalViewSet, basename="scoring-reopen")
router.register(r"topic-priority", TopicPriorityViewSet, basename="topic-priority")
router.register(r"decision-types", DecisionTypeViewSet, basename="decision-type")
router.register(r"feedback-categories",  FeedbackCategoryViewSet,    basename="feedback-category")
router.register(r"feedback-email-logs",  FeedbackEmailLogViewSet,    basename="feedback-email-log")
router.register(r"appraisal-criteria", CriteriaAppraisalToolViewSet, basename="appraisal-criteria")
router.register(r"appraisal-scores",   CriteriaAppraisalScoreViewSet, basename="appraisal-scores")
router.register(r"appraisal-evidence", AppraisalCriteriaEvidenceViewSet, basename="appraisal-evidence",)
router.register(r"activities", ActivityViewSet, basename="activities")
router.register(r"sub-activities", SubActivityViewSet, basename="sub-activities")
router.register(r"scoring-windows", InterventionScoringWindowViewSet, basename="scoring-window")
router.register(r"assessment-evidence", AssessmentEvidenceViewSet, basename="assessment-evidence")
router.register(r"evidence-criteria", EvidenceCriterionViewSet, basename="evidence-criteria")
router.register(r"evidence-extractions", EvidenceExtractionViewSet, basename="evidence-extraction")
 
# router.register(r"assessment-criteria", AssessmentCriteriaViewSet, basename="assessment-criteria")
# router.register(r"assessment-evidence", AssessmentEvidenceViewSet, basename="assessment-evidence")
 




# urlpatterns = router.urls
urlpatterns = [
    path("", include(router.urls)),
    path("users/", UsersListView.as_view()),
    path("scoring-report/", ScoringReportView.as_view(), name="scoring-report"),
    path("interventions/search/", search_interventions),
    path("weighting/", WeightingReportView.as_view(), name="weighting-report"),
    # path("admin-report/", AdminScoreViewSet.as_view(), name="scoring-report"),
]