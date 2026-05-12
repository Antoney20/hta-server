from django.contrib import admin
from .models import SelectionTool, SystemCategory, InterventionSystemCategory, InterventionScore,CriteriaInformation,InterventionStatusUpdate, CriteriaAppraisalScore,CriteriaAppraisalTool, Activity, SubActivity, FeedbackEmailLog, FeedbackCategory

admin.site.register(SelectionTool)
admin.site.register(SystemCategory)
admin.site.register(InterventionSystemCategory)
admin.site.register(InterventionScore)
admin.site.register(CriteriaInformation)
admin.site.register(InterventionStatusUpdate)
admin.site.register(FeedbackCategory)
admin.site.register(FeedbackEmailLog)
admin.site.register(Activity)
admin.site.register(SubActivity)
admin.site.register(CriteriaAppraisalScore)
admin.site.register(CriteriaAppraisalTool)