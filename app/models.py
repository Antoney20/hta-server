from django.db import models
# Create your models here.
import uuid
from django.contrib.auth import get_user_model
from auditlog.registry import auditlog

from users.models import InterventionProposal

User = get_user_model()




class SelectionTool(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    criteria = models.CharField(max_length=255)
    description = models.TextField()
    scoring_mechanism = models.TextField(blank=True, null=True)
    scores = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.criteria
    

class SystemCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)       
    description = models.TextField(blank=True)     
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    

class InterventionSystemCategory(models.Model):
    """
    Many-to-many: one intervention can appear under multiple system category tabs.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intervention = models.ForeignKey(         
        InterventionProposal,
        on_delete=models.CASCADE,
        related_name="system_categories"      
    )
    system_category = models.ForeignKey(
        SystemCategory,
        on_delete=models.PROTECT,
        related_name="interventions"          
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("intervention", "system_category")  

    def __str__(self):
        return f"{self.intervention} → {self.system_category}"

    
class InterventionScore(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE)
    intervention = models.ForeignKey(InterventionProposal, on_delete=models.CASCADE, related_name="scores" )
    criteria = models.ForeignKey(SelectionTool, on_delete=models.CASCADE  )
    score = models.JSONField(default=dict, blank=True)
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ("reviewer", "intervention", "criteria")
    
    


auditlog.register(SelectionTool)
auditlog.register(SystemCategory)
auditlog.register(InterventionSystemCategory)
auditlog.register(InterventionScore)