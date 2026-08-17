from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AIModelViewSet,
    AIProviderKeyViewSet,
    ActivityViewSet,
    AdminScoreViewSet,
    AppraisalCriteriaEvidenceViewSet,
    AppraisalScoreViewSet,
    AppraisalViewSet,
    AssessmentEvidenceViewSet,
    BenefitPackageViewSet,
    CriteriaAppraisalScoreViewSet,
    CriteriaAppraisalToolViewSet,
    CriteriaInformationViewSet,
    CriteriaRuleViewSet,
    CriteriaViewSet,
    DecisionTemplateViewSet,
    DecisionTypeViewSet,
    EvidenceCoverageViewSet,
    EvidenceCriterionViewSet,
    EvidenceExtractionViewSet,
    EvidenceViewSet,
    FeedbackCategoryViewSet,
    FeedbackEmailLogViewSet,
    InterventionPackageViewSet,
    InterventionPhaseViewSet,
    NationalProgramProposalViewSet,
    NationalProgramViewSet,
    PanelAppraisalScoreViewSet,
    PanelAppraisedViewSet,
    # ProposedPackageViewSet,
    PublicProgramViewSet,
    PublicProposalViewSet,
    RevisedPackageViewSet,
    ScoringReportView,
    SelectionToolViewSet,
    SubActivityViewSet,
    SwgPrioritizedViewSet,
    SystemCategoryViewSet,
    InterventionSystemCategoryViewSet,
    InterventionScoreViewSet,
    TopicPriorityViewSet,
    UsersListView,
    WeightingReportView,
    proposal_detail_any,
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
router.register(r"public-programs", PublicProgramViewSet, basename="public-programs")
# router.register(r"re-open", InterventionProposalViewSet, basename="scoring-reopen")
router.register(r"topic-priority", TopicPriorityViewSet, basename="topic-priority")
router.register(r"decision-types", DecisionTypeViewSet, basename="decision-type")
router.register(r"feedback-categories",  FeedbackCategoryViewSet,    basename="feedback-category")
router.register(r"feedback-email-logs",  FeedbackEmailLogViewSet,    basename="feedback-email-log")
router.register(r"appraisal-criteria", CriteriaAppraisalToolViewSet, basename="appraisal-criteria")
# router.register(r"appraisal-scores",   CriteriaAppraisalScoreViewSet, basename="appraisal-scores"
router.register(r"appraisal-evidence", AppraisalCriteriaEvidenceViewSet, basename="appraisal-evidence",)
router.register(r"activities", ActivityViewSet, basename="activities")
router.register(r"sub-activities", SubActivityViewSet, basename="sub-activities")
router.register(r"assessment-evidence", AssessmentEvidenceViewSet, basename="assessment-evidence")
router.register(r"evidence-criteria", EvidenceCriterionViewSet, basename="evidence-criteria")
router.register(r"evidence-extractions", EvidenceExtractionViewSet, basename="evidence-extraction")
router.register(r"intervention-package", InterventionPackageViewSet, basename="assesment-package")
router.register(r"intervention-phases", InterventionPhaseViewSet, basename="intervention-phase")
router.register(r"benefit-packages", BenefitPackageViewSet, basename="benefit-package")

 
# router.register(r"assessment-evidence", AssessmentEvidenceViewSet, basename="assessment-evidence")
router.register("criteria", CriteriaViewSet, basename="criteria")
router.register("evidence", EvidenceViewSet, basename="evidence")
router.register("evidence-coverage", EvidenceCoverageViewSet, basename="evidence-coverage")
router.register("criteria-rules", CriteriaRuleViewSet, basename="criteria-rules")
router.register("decision-templates", DecisionTemplateViewSet, basename="decision-templates")
#panel score
router.register(r"panel-scores", PanelAppraisalScoreViewSet, basename="panel-score")

#agentic
router.register("ai-keys", AIProviderKeyViewSet, basename="ai-keys")
router.register("ai-models", AIModelViewSet, basename="ai-models")
router.register("appraisals", AppraisalViewSet, basename="appraisals")
router.register(r"appraisal-scores", AppraisalScoreViewSet, basename="appraisal-score")
# 
router.register(r"swg", SwgPrioritizedViewSet, basename="swg")
router.register(r"appraised-lists", PanelAppraisedViewSet, basename="appraised-list")
# router.register(r"proposed-packages", ProposedPackageViewSet, basename="proposed-packages")
router.register(r"revised-packages", RevisedPackageViewSet, basename="revised-packages")


# urlpatterns = router.urls
urlpatterns = [
    path("", include(router.urls)),
    path("users/", UsersListView.as_view()),
    path("scoring-report/", ScoringReportView.as_view(), name="scoring-report"),
    path("interventions/search/", search_interventions),
    path("weighting/", WeightingReportView.as_view(), name="weighting-report"),
    path("proposals/<uuid:pk>/", proposal_detail_any),
    # path("admin-report/", AdminScoreViewSet.as_view(), name="scoring-report"),
]