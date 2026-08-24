from django.contrib import admin

from .models import (
    SelectionTool,
    SystemCategory,
    InterventionSystemCategory,
    InterventionScore,
    CriteriaInformation,
    DecisionType,
    CriteriaAppraisalScore,
    FeedbackEmailLog,
    CriteriaAppraisalTool,
    InterventionStatusUpdate,
    AppraisalCriteriaEvidence,
    Activity,
    SubActivity,
    BenefitPackage,
    AIModel,
    AppraisalRun,
    AppraisalScore,
    AssessmentEvidence,
    AssessmentEvidenceDocument,
    CriteriaGuideDocument,
    CriteriaReferenceScale,
    CriteriaRule,
    CriterionEvidence,
    DecisionTemplate,
    DecisionTemplateCriterion,
    EvidenceCriterion,
    EvidenceExtraction,
    FeedbackCategory,
    InterventionPackage,
    InterventionPhase,
    NationalProgram,
    NationalProgramProposal,
    PanelAppraisal,
    PanelAppraisalScore,
    PanelAppraisedList,
    PanelScoringRule,
    ProposedBenefitPackage,
    RevisedBenefitPackage,
    SwgPrioritizedList,
    WeightingAllocation,
    WeightingKillerFlag,
    WeightingResponse,
    WeightingSurvey,
)


admin.site.register(SelectionTool)
admin.site.register(SystemCategory)
admin.site.register(InterventionSystemCategory)
admin.site.register(InterventionScore)
admin.site.register(CriteriaInformation)
admin.site.register(DecisionType)
admin.site.register(CriteriaAppraisalScore)
admin.site.register(FeedbackEmailLog)
admin.site.register(CriteriaAppraisalTool)
admin.site.register(InterventionStatusUpdate)
admin.site.register(AppraisalCriteriaEvidence)
admin.site.register(Activity)
admin.site.register(SubActivity)
admin.site.register(BenefitPackage)

# New models
admin.site.register(AIModel)
admin.site.register(AppraisalRun)
admin.site.register(AppraisalScore)
admin.site.register(AssessmentEvidence)
admin.site.register(AssessmentEvidenceDocument)
admin.site.register(CriteriaGuideDocument)
admin.site.register(CriteriaReferenceScale)
admin.site.register(CriteriaRule)
admin.site.register(CriterionEvidence)
admin.site.register(DecisionTemplate)
admin.site.register(DecisionTemplateCriterion)
admin.site.register(EvidenceCriterion)
admin.site.register(EvidenceExtraction)
admin.site.register(FeedbackCategory)
admin.site.register(InterventionPackage)
admin.site.register(InterventionPhase)
admin.site.register(NationalProgram)
admin.site.register(NationalProgramProposal)
admin.site.register(PanelAppraisal)
admin.site.register(PanelAppraisalScore)
admin.site.register(PanelAppraisedList)
admin.site.register(PanelScoringRule)
admin.site.register(ProposedBenefitPackage)
admin.site.register(RevisedBenefitPackage)
admin.site.register(SwgPrioritizedList)
admin.site.register(WeightingAllocation)
admin.site.register(WeightingKillerFlag)
admin.site.register(WeightingResponse)
admin.site.register(WeightingSurvey)

# Intentionally not registered:
# admin.site.register(InterventionScoringWindow)