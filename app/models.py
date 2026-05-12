from django.db import models, IntegrityError, transaction
# Create your models here.
import uuid
from django.contrib.auth import get_user_model
from auditlog.registry import auditlog

from app.core.consts import get_pending_decision
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

    
    
class CriteriaInformation(models.Model):
    """
    Stores detailed qualitative information for HTA criteria
    linked to an intervention.
    """

    BURDEN_TYPE_CHOICES = [
        ("DALY", "DALY"),
        ("QALY", "QALY"),
        ("PREVALENCE", "Prevalence"),
        ("INCIDENCE", "Incidence"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intervention = models.ForeignKey(
        InterventionProposal,
        on_delete=models.CASCADE,
        related_name="criteria_information"
    )

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL,null=True, blank=True)
    brief_info= models.TextField(null=True, blank=True)
    clinical_effectiveness = models.TextField(null=True, blank=True)
    burden_of_disease = models.TextField(null=True, blank=True)
    bod_type = models.CharField(
        max_length=20,
        choices=BURDEN_TYPE_CHOICES,
        null=True,
        blank=True
    ) #will be joining with bod
    population = models.TextField(null=True, blank=True)
    equity = models.TextField(null=True, blank=True)
    cost_effectiveness = models.TextField(null=True, blank=True)
    budget_impact_affordability = models.TextField(null=True, blank=True)
    feasibility_of_implementation = models.TextField(null=True, blank=True)
    catastrophic_health_expenditure = models.TextField(null=True, blank=True)
    access_to_healthcare = models.TextField(null=True, blank=True)
    congruence_with_health_priorities = models.TextField(null=True, blank=True)
    additional_info = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["intervention"], name="idx_criteria_intervention"),
        ]

    def __str__(self):
        return f"Criteria Info — {self.intervention}"    
 

class InterventionScore(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE)
    intervention = models.ForeignKey(
        InterventionProposal, on_delete=models.CASCADE, related_name="scores"
    )
    criteria = models.ForeignKey(SelectionTool, on_delete=models.CASCADE)
    score = models.JSONField(default=dict, blank=True)
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    is_rescored = models.BooleanField(default=False)
    rescored_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rescored_scores",
        help_text="The reviewer who applied the rescore.",
    )

    class Meta:
        unique_together = ("reviewer", "intervention", "criteria")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["reviewer"]),
            models.Index(fields=["intervention"]),
            models.Index(fields=["criteria"]),
            models.Index(fields=["created_at"]),
        ]
    
    def __str__(self):
        return f"{self.reviewer} — {self.intervention} — {self.criteria}"
 
 
 
class DecisionType(models.Model):
    """
    save decision type
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name



class InterventionStatusUpdate(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    intervention = models.ForeignKey(
        InterventionProposal,
        on_delete=models.CASCADE,
        related_name="status_updates",
    )

    decision = models.ForeignKey(
        DecisionType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        default=get_pending_decision, 
        related_name="status_updates",
        help_text="Formal HTA decision once reached.",
    )

    decision_date = models.DateField(null=True, blank=True)

    feedback = models.TextField(
        blank=True,
        help_text="Plain-language feedback visible to the submitter.",
    )

    additional_info = models.TextField(
        blank=True,
        help_text="More info supporting the decision.",
    )

    move_to_panel = models.BooleanField(
        default=False,
        help_text="Mark intervention to move to panel review.",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="intervention_status_updates",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["intervention"], name="idx_status_intervention"),
            models.Index(fields=["decision_date"], name="idx_status_decision_date"),
            models.Index(fields=["move_to_panel"], name="idx_status_move_to_panel"),
        ]

    def __str__(self):
        return f"{self.intervention} — Status Update"
    
    



 
class FeedbackCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    subject = models.CharField(
        max_length=255,
        help_text="Email subject line. You may use {{ decision_type }}, {{ submitter_name }}, etc.",
    )
    template = models.TextField(
        help_text=(
            "Full HTML email body. Available variables: "
            "{{ submitter_name }}, {{ submitter_email }}, {{ decision_type }}, "
            "{{ decision_date }}, {{ feedback }}, {{ org_name }}, {{ org_email }}, {{ current_year }}."
        )
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        ordering = ["name"]
        verbose_name = "Feedback Category"
        verbose_name_plural = "Feedback Categories"
 
    def __str__(self):
        return self.name
 


class FeedbackEmailLog(models.Model):
    """
    Tracks every feedback email sent against an InterventionProposal.
    Keeps a per-category send count and full status history.
    """
 
    STATUS_CHOICES = [
        ("initial", "Initial"),
        ("sending", "Sending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]
 
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
 
    intervention = models.ForeignKey(
        InterventionProposal,             
        on_delete=models.CASCADE,
        related_name="feedback_email_logs",
    )
    category = models.ForeignKey(
        FeedbackCategory,
        on_delete=models.PROTECT,
        related_name="email_logs",
    )

    subject_sent = models.TextField()
    message_sent = models.TextField()
 
    recipient = models.EmailField()
    sender = models.CharField(max_length=255)
 
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="initial")
    error_message = models.TextField(blank=True, null=True)
    retry_count = models.PositiveIntegerField(default=0)
    last_attempt = models.DateTimeField(blank=True, null=True)
 
    sent_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_emails_sent",
        help_text="Staff member who triggered the send.",
    )
 
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(blank=True, null=True)
 
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["intervention"], name="idx_femail_intervention"),
            models.Index(fields=["category"], name="idx_femail_category"),
            models.Index(fields=["status"], name="idx_femail_status"),
        ]
 
    def __str__(self):
        return (
            f"[{self.category}] → {self.recipient} "
            f"({self.status}) #{self.retry_count}"
        )
 
    def mark_sending(self):
        from django.utils import timezone
        self.status = "sending"
        self.last_attempt = timezone.now()
        self.save(update_fields=["status", "last_attempt"])
 
    def mark_sent(self):
        from django.utils import timezone
        self.status = "sent"
        self.sent_at = timezone.now()
        self.error_message = None
        self.save(update_fields=["status", "sent_at", "error_message"])
 
    def mark_failed(self, exc):
        from django.utils import timezone
        self.status = "failed"
        self.error_message = str(exc)
        self.retry_count += 1
        self.last_attempt = timezone.now()
        self.save(update_fields=["status", "error_message", "retry_count", "last_attempt"])


class CriteriaAppraisalTool(models.Model):
    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    criteria         = models.CharField(max_length=255)
    description      = models.TextField(blank=True)
    scoring_approach = models.TextField(blank=True)
    score            = models.IntegerField(null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.criteria


class CriteriaAppraisalScore(models.Model):
    """Captures a reviewer's score for one criterion on one intervention."""
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reviewer     = models.ForeignKey(User, on_delete=models.CASCADE)
    intervention = models.ForeignKey(
      InterventionProposal , on_delete=models.CASCADE, related_name="appraisal_scores"
    )
    criteria     = models.ForeignKey(CriteriaAppraisalTool, on_delete=models.CASCADE)
    score        = models.JSONField(default=dict)
    comment      = models.TextField(blank=True, null=True)
    is_rescored  = models.BooleanField(default=False)
    rescored_by  = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="rescored_appraisals"
    )
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("reviewer", "intervention", "criteria")

    def __str__(self):
        return f"{self.reviewer} — {self.intervention} — {self.criteria}"






def evidence_document_path(instance, filename):
    return f"appraisal/evidence/{instance.evidence.id}/documents/{filename}"
 
 
def evidence_image_path(instance, filename):
    return f"appraisal/evidence/{instance.evidence.id}/images/{filename}"
 
 
class AppraisalCriteriaEvidence(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intervention = models.ForeignKey(
        InterventionProposal,
        on_delete=models.CASCADE,
        related_name="appraisal_evidence",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="appraisal_evidence_created",
    )

    brief_info                        = models.TextField(null=True, blank=True)

    # Criteria 1
    clinical_effectiveness            = models.TextField(null=True, blank=True)

    # Criteria 2
    safety                            = models.TextField(null=True, blank=True)

    # Criteria 3
    quality                           = models.TextField(null=True, blank=True)

    # Criteria 4 — Burden of Disease
    burden_of_disease_mortality       = models.TextField(null=True, blank=True)
    burden_of_disease_morbidity       = models.TextField(null=True, blank=True)  # incidence/occurrence

    # Criteria 5
    population                        = models.TextField(null=True, blank=True)

    # Criteria 6
    equity                            = models.TextField(null=True, blank=True)

    # Criteria 7
    cost_effectiveness                = models.TextField(null=True, blank=True)

    # Criteria 8
    budget_impact_affordability       = models.TextField(null=True, blank=True)

    # Criteria 9
    feasibility_of_implementation     = models.TextField(null=True, blank=True)

    # Criteria 10
    catastrophic_health_expenditure   = models.TextField(null=True, blank=True)

    # Criteria 11
    access_to_healthcare              = models.TextField(null=True, blank=True)

    # Criteria 12
    congruence_with_health_priorities = models.TextField(null=True, blank=True)

    additional_info                   = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Appraisal Evidence — {self.intervention}"


class AppraisalEvidenceDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    evidence = models.ForeignKey(
        AppraisalCriteriaEvidence,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appraisal_documents_uploaded",
    )
 
    file        = models.FileField(upload_to=evidence_document_path)
    filename    = models.CharField(max_length=255, blank=True)   
    description = models.CharField(max_length=500, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]
 
    def save(self, *args, **kwargs):
        if self.file and not self.filename:
            self.filename = self.file.name.split("/")[-1]
        super().save(*args, **kwargs)
 
    def __str__(self):
        return f"{self.filename} — {self.evidence}"
 
 
class AppraisalEvidenceImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    evidence = models.ForeignKey(
        AppraisalCriteriaEvidence,
        on_delete=models.CASCADE,
        related_name="images",
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appraisal_images_uploaded",
    )
 
    image       = models.ImageField(upload_to=evidence_image_path)
    caption     = models.CharField(max_length=500, blank=True)
    alt_text    = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ["uploaded_at"]
 
    def __str__(self):
        return f"Image — {self.evidence} ({self.caption or 'no caption'})"
    
    
    

 
class UrgencyLevel(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"
 
 
class StatusChoice(models.TextChoices):
    PENDING = "pending", "Pending"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
 
 
class Activity(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    urgency = models.CharField(max_length=20, choices=UrgencyLevel.choices, default=UrgencyLevel.MEDIUM, db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="activity_owner")
 
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=[ "urgency"]),
        ]
 

    def __str__(self):
        return f" {self.name}"
 
 
class SubActivity(models.Model):
    hta_id = models.CharField(max_length=20, unique=True, editable=False, db_index=True,null=True,blank=True)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="sub_activities", db_index=True)
    name = models.CharField(max_length=255)
    urgency = models.CharField(max_length=20, choices=UrgencyLevel.choices, default=UrgencyLevel.MEDIUM)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    assigned_to = models.ManyToManyField(User, related_name="sub_activities", blank=True)
    status = models.CharField(max_length=20, choices=StatusChoice.choices, default=StatusChoice.PENDING, db_index=True)
    notes = models.TextField(blank=True)
    send_email_alert = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="completed_sub_activities")
    created_at = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ["created_at"]
 



    def save(self, *args, **kwargs):

        is_new = self.pk is None

        # First save WITHOUT hta_id
        super().save(*args, **kwargs)

        # Generate once after ID exists
        if is_new and not self.hta_id:

            generated_id = f"HTA-{self.pk:04d}"

            type(self).objects.filter(pk=self.pk).update(
                hta_id=generated_id
            )

            self.hta_id = generated_id

    def __str__(self):
        return f"{self.hta_id} — {self.name}"

auditlog.register(SelectionTool)
auditlog.register(SystemCategory)
auditlog.register(InterventionSystemCategory)
auditlog.register(InterventionScore)
auditlog.register(CriteriaInformation)
auditlog.register(DecisionType)
auditlog.register(CriteriaAppraisalScore)
auditlog.register(FeedbackEmailLog)
auditlog.register(CriteriaAppraisalTool)
auditlog.register(InterventionStatusUpdate)
auditlog.register(AppraisalCriteriaEvidence)
auditlog.register(Activity)
auditlog.register(SubActivity)

