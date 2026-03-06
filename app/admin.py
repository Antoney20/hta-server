from django.contrib import admin
from .models import SelectionTool, SystemCategory, InterventionSystemCategory, InterventionScore

admin.site.register(SelectionTool)
admin.site.register(SystemCategory)
admin.site.register(InterventionSystemCategory)
admin.site.register(InterventionScore)