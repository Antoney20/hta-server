from django.db import models, IntegrityError, transaction
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Max
# Create your models here.
import uuid
from django.contrib.auth import get_user_model
from auditlog.registry import auditlog

from app.core.consts import  get_pending_decision
from users.models import InterventionProposal
from datetime import date



User = get_user_model()


class InterventionPackage(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    field_schema = models.JSONField(default=list, blank=True) 
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class InterventionPhase(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

# program interventions. , sha, nrh, 
class NationalProgram(models.Model):
    name = models.CharField(max_length=200, unique=True)
    code = models.CharField(max_length=40, unique=True)        
    description = models.TextField(blank=True)
    field_schema = models.JSONField(default=list, blank=True)   
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
 
    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["is_active", "name"])]
 
    @property
    def reference_template(self):
        return f"INTERV-{self.code}"
 
    def __str__(self):
        return f"{self.code} — {self.name}"
 
 
def _next_sequence(template, period):
    """Highest existing suffix for this template+period, + 1 (uses the unique index)."""
    prefix = f"{template}-{period}-"
    last = (
        NationalProgramProposal.objects
        .filter(reference_number__startswith=prefix)
        .order_by("-reference_number")              
        .values_list("reference_number", flat=True)
        .first()
    )
    try:
        return int(last.rsplit("-", 1)[-1]) + 1 if last else 1
    except (ValueError, AttributeError):
        return 1
 
 
class NationalProgramProposal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    program = models.ForeignKey(NationalProgram, on_delete=models.PROTECT, related_name="program_proposals")
    reference_number = models.CharField(max_length=64, unique=True, editable=False)
    title = models.CharField(max_length=300)
    justification = models.TextField(blank=True, null=True)
    data = models.JSONField(default=dict, blank=True)
               
    package = models.ForeignKey(
        "app.InterventionPackage",
        on_delete=models.SET_NULL,
        related_name="national_proposals",
        null=True, blank=True,
    )
    phase = models.ForeignKey(
        "app.InterventionPhase",
        on_delete=models.SET_NULL,
        related_name="national_proposals",
        null=True, blank=True,
    )

    submitted_date = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="created_program_proposals",
    )
 
    class Meta:
        ordering = ["-submitted_date", "-created_at"]
        indexes = [
            models.Index(fields=["program", "-submitted_date"]),
            models.Index(fields=["-created_at"]),
        ]
 
    def clean(self):
        for f in self.program.field_schema or []:
            key = f.get("key")
            if key and f.get("required") and not self.data.get(key):
                raise ValidationError({key: "This field is required."})
 
    def save(self, *args, **kwargs):
        if self.reference_number:
            return super().save(*args, **kwargs)
 
        template = self.program.reference_template
        period = (self.submitted_date or timezone.localdate()).strftime("%Y-%m")
        seq = _next_sequence(template, period)
 
        # No locking: optimistic insert. On a unique clash, just try the next number.
        for _ in range(1000):
            self.reference_number = f"{template}-{period}-{seq:04d}"
            try:
                with transaction.atomic():          
                    return super().save(*args, **kwargs)
            except IntegrityError:
                seq += 1
        raise IntegrityError("Could not allocate a reference number")
 
    def __str__(self):
        return f"{self.reference_number} — {self.title}"





class EvidenceCriterion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    code = models.SlugField(max_length=60, unique=True)          # clinical_effectiveness, safety…
    description = models.TextField(blank=True, null=True)
    field_schema = models.JSONField(default=list, blank=True)
    position = models.PositiveSmallIntegerField(default=0)        # column-group order
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        ordering = ["position", "name"]
        indexes = [models.Index(fields=["is_active", "position"])]
 
    def __str__(self):
        return self.name
 
 
class EvidenceExtraction(models.Model):
    """One intervention's extracted evidence — a single Outcomes-sheet row.
    Attaches to exactly one proposal, of either type."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    national_proposal = models.OneToOneField(
        NationalProgramProposal, on_delete=models.CASCADE,
        related_name="evidence", null=True, blank=True,
    )
    intervention_proposal = models.OneToOneField(
        InterventionProposal, on_delete=models.CASCADE,
        related_name="evidence", null=True, blank=True,
    )
    routing_decision = models.TextField(blank=True, null=True)
    icd_11 = models.CharField(max_length=120, blank=True, null=True, db_index=True)
    disease_definition = models.TextField(blank=True, null=True)
    # everything else: {criterion_code: {field_key: value}} — flexes with each schema
    data = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True ,related_name="created_evidence_extractions", )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["-updated_at"])]
       
 
    @property
    def proposal(self):
        """Whichever proposal this evidence is attached to."""
        return self.national_proposal or self.intervention_proposal
 
 
    def __str__(self):
        p = self.proposal
        ref = getattr(p, "reference_number", None) or getattr(p, "pk", None)
        return f"Evidence · {ref}"

#  main app

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
        related_name="criteria_information",
        null=True, blank=True,                      
    )
    national_proposal = models.ForeignKey(          
        NationalProgramProposal,
        on_delete=models.CASCADE,
        related_name="criteria_information",
        null=True, blank=True,
    )

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    brief_info = models.TextField(null=True, blank=True)
    clinical_effectiveness = models.TextField(null=True, blank=True)
    burden_of_disease = models.TextField(null=True, blank=True)
    bod_type = models.CharField(max_length=20, choices=BURDEN_TYPE_CHOICES, null=True, blank=True)
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

    @property
    def target(self):
        return self.intervention or self.national_proposal

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["intervention"], name="idx_criteria_intervention"),
            models.Index(fields=["national_proposal"], name="idx_criteria_national"),
        ]
     
      

    def __str__(self):
        return f"Criteria Info — {self.target}"

class InterventionScore(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE)
    intervention = models.ForeignKey(
        InterventionProposal, on_delete=models.CASCADE,
        related_name="scores", null=True, blank=True,          
    )
    national_proposal = models.ForeignKey(                     
        NationalProgramProposal, on_delete=models.CASCADE,
        related_name="scores", null=True, blank=True,
    )
    criteria = models.ForeignKey(SelectionTool, on_delete=models.CASCADE)
    score = models.JSONField(default=dict, blank=True)
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_rescored = models.BooleanField(default=False)
    rescored_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="rescored_scores",
        help_text="The reviewer who applied the rescore.",
    )

    @property
    def target(self):
        return self.intervention or self.national_proposal

    class Meta:
        unique_together = ("reviewer", "intervention", "criteria")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["reviewer"]),
            models.Index(fields=["intervention"]),
            models.Index(fields=["national_proposal"]),
            models.Index(fields=["criteria"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.reviewer} — {self.target} — {self.criteria}"
 
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
        null=True, blank=True,
    )
    national_proposal = models.ForeignKey(
        NationalProgramProposal,
        on_delete=models.CASCADE,
        related_name="status_updates",
        null=True, blank=True,
    )
    decision = models.ForeignKey(
        DecisionType,
        on_delete=models.PROTECT,
        null=True, blank=True,
        default=get_pending_decision,
        related_name="status_updates",
        help_text="Formal HTA decision once reached.",
    )
    routing_decision =models.TextField(blank=True,  help_text="Optional routing decision.",
    )
    decision_date = models.DateField(null=True, blank=True)
    feedback = models.TextField(blank=True, help_text="Plain-language feedback visible to the submitter.")
    additional_info = models.TextField(blank=True, help_text="More info supporting the decision.")
    move_to_panel = models.BooleanField(default=False, help_text="Mark intervention to move to panel review.")
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name="intervention_status_updates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["intervention"], name="idx_status_intervention"),
            models.Index(fields=["national_proposal"], name="idx_status_national"),
            models.Index(fields=["decision_date"], name="idx_status_decision_date"),
            models.Index(fields=["move_to_panel"], name="idx_status_move_to_panel"),
        ]

    def __str__(self):
        return f"{self.intervention or self.national_proposal} — Status Update"



 
class FeedbackCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    subject = models.CharField(  max_length=255, help_text="Email subject line. You may use {{ decision_type }}, {{ submitter_name }}, etc.",  )
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
    headers          = models.JSONField(default=list, blank=True)  
    active           = models.BooleanField(default=True)          
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.criteria


class CriterionEvidence(models.Model):
    id                = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    criterion = models.ForeignKey(CriteriaAppraisalTool, on_delete=models.PROTECT, related_name="evidence")
    intervention      = models.ForeignKey(InterventionProposal, null=True, blank=True,
                                           on_delete=models.CASCADE, related_name="criterion_evidence")
    national_proposal = models.ForeignKey(NationalProgramProposal, null=True, blank=True,
                                           on_delete=models.CASCADE, related_name="criterion_evidence")

    data              = models.JSONField(default=dict, blank=True)     
    score             = models.IntegerField(null=True, blank=True)     
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    @property
    def target(self):
        return self.intervention or self.national_proposal

    def __str__(self):
        return f"{self.criterion.criteria} "
    
    

# not used we changed to  remove this 
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
    URGENT = "urgent", "Urgent"
 
 
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
    

class ScoringLevel(models.TextChoices):
    PANEL = "panel", "Panel (SWG)"
    APPRAISAL = "appraisal", "Appraisal"


# class InterventionScoringWindow(models.Model): # can be removed -- not needed fopr now
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

#     intervention = models.ForeignKey(InterventionProposal, on_delete=models.CASCADE,related_name="scoring_windows",)
#     level = models.CharField( max_length=20, choices=ScoringLevel.choices, db_index=True,)
#     starts_at = models.DateTimeField( help_text="When scoring opens for reviewers.", )
#     ends_at = models.DateTimeField( help_text="When the scoring window closes.", )
#     submission_delay_minutes = models.PositiveIntegerField( default=2, help_text=("Grace period in minutes after ends_at during which late "   "submissions are still accepted."), )
#     is_active = models.BooleanField( default=True, help_text="Set false to disable this window regardless of dates.",)
#     notes = models.TextField(blank=True)
#     created_by = models.ForeignKey( User, on_delete=models.SET_NULL, null=True, blank=True, related_name="scoring_windows_created",)
#     updated_by = models.ForeignKey( User, on_delete=models.SET_NULL, null=True, blank=True, related_name="scoring_windows_updated",)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         unique_together = ("intervention", "level")
#         ordering = ["-created_at"]
#         indexes = [
#             models.Index(fields=["intervention", "level"]),
#             models.Index(fields=["starts_at"]),
#             models.Index(fields=["ends_at"]),
#             models.Index(fields=["is_active"]),
#         ]

#     def __str__(self):
#         ref = getattr(self.intervention, "reference_number", None) or self.intervention_id
#         return f"{ref} — {self.get_level_display()} ({self.starts_at:%Y-%m-%d %H:%M} → {self.ends_at:%Y-%m-%d %H:%M})"

#     # ---------- derived ----------
#     @property
#     def effective_close_at(self):
#         """ends_at + grace period."""
#         return self.ends_at + timedelta(minutes=self.submission_delay_minutes)

#     @property
#     def status(self) -> str:
#         """
#         One of: 'disabled', 'scheduled', 'open', 'grace', 'closed'.
#         """
#         if not self.is_active:
#             return "disabled"
#         now = timezone.now()
#         if now < self.starts_at:
#             return "scheduled"
#         if now <= self.ends_at:
#             return "open"
#         if now <= self.effective_close_at:
#             return "grace"
#         return "closed"

#     @property
#     def is_open(self) -> bool:
#         """True if scoring is currently allowed (including grace period)."""
#         return self.status in ("open", "grace")

#     @property
#     def is_in_grace(self) -> bool:
#         return self.status == "grace"

#     @property
#     def time_remaining(self):
#         """timedelta until effective_close_at, or None if already closed."""
#         now = timezone.now()
#         if now >= self.effective_close_at:
#             return None
#         return self.effective_close_at - now

#     # ---------- validation ----------
#     def clean(self):
#         if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
#             raise ValidationError({"ends_at": "Must be after starts_at."})

#     # ---------- lookup helpers ----------
#     @classmethod
#     def get_window(cls, intervention, level: str):
#         """Fetch the window for an (intervention, level), or None."""
#         return cls.objects.filter(intervention=intervention, level=level).first()

#     @classmethod
#     def can_score(cls, intervention, level: str) -> bool:
#         """
#         Convenience check used by serializers/services before accepting a score.
#         Returns True if a window exists, is active, and is currently open.
#         """
#         window = cls.get_window(intervention, level)
#         return bool(window and window.is_open)




 
def assessment_evidence_document_path(instance, filename):
    # assessment/evidence/<refno>/documents/<filename> ; the evidence id is the refno
    return f"assessment/evidence/{instance.evidence_id}/documents/{filename}"
 
 
class AssessmentEvidence(models.Model):
    """
    Evidence captured by the assessment group,
 
    A single piece of evidence can apply to one OR more targets, and the target
    can be an InterventionProposal, a NationalProgramProposal, or both. The
    summary is optional; supporting files live in AssessmentEvidenceDocument.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

 
    interventions = models.ManyToManyField(
        InterventionProposal, blank=True, related_name="assessment_group",
    )
    program_proposals = models.ManyToManyField(
        NationalProgramProposal,  blank=True, related_name="assessment_group",
    )
 
    summary = models.TextField(blank=True)   # optional
 
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="evidence_created_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=[ "-created_at"])]
 
    def __str__(self):
        return f"Evidence {self.id} "
 
 
class AssessmentEvidenceDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    evidence = models.ForeignKey(
        AssessmentEvidence, on_delete=models.CASCADE, related_name="documents",
    )
    # file = models.FileField(upload_to=assessment_evidence_document_path)
    file = models.FileField(upload_to="assessment/evidence/documents/")
    description = models.CharField(max_length=500, blank=True)   # per-document summary
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assessment_documents_uploaded",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ["uploaded_at"]
 
    def __str__(self):
        return f"{self.file.name.split('/')[-1]} — {self.evidence_id}"


class CriteriaRule(models.Model):
    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    criterion     = models.ForeignKey(CriteriaAppraisalTool, on_delete=models.CASCADE, related_name="rules")
    description   = models.TextField(blank=True)
    kind          = models.CharField(max_length=30, default="descriptive")
    target_fields = models.JSONField(default=list, blank=True)
    aggregate     = models.CharField(max_length=20, blank=True)
    items         = models.JSONField(default=list, blank=True)  
    bands         = models.JSONField(default=list, blank=True)  
    active        = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["criterion__criteria"]

    def __str__(self):
        return f"{self.criterion.criteria} rule"

class CriteriaGuideDocument(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule        = models.ForeignKey(CriteriaRule, on_delete=models.CASCADE, related_name="documents")
    label       = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    link        = models.TextField(blank=True)              
    file        = models.FileField(upload_to="panel/assessment/rules/", blank=True, null=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.rule.criterion.criteria} — {self.label}"

class CriteriaReferenceScale(models.Model):
    """
    Structured reference a criterion is graded against
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule        = models.ForeignKey(CriteriaRule, on_delete=models.CASCADE, related_name="scales")
    label       = models.CharField(max_length=255)             # based on package
    source      = models.CharField(max_length=120, blank=True) # "CTCAE" | "GRADE" | "NICE", for 
    description = models.TextField(blank=True)                 # package,, a description of this rule
    data        = models.JSONField(default=dict, blank=True)   # the diverse structured payload
    active      = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["rule__criterion__criteria", "label"]

    def __str__(self):
        return f"{self.rule.criterion.criteria} — {self.label}"

class DecisionTemplate(models.Model):
    id                = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name              = models.CharField(max_length=255, editable=False)
    title             = models.CharField(max_length=300, blank=True)
    description       = models.TextField(blank=True)

    intervention      = models.ForeignKey(InterventionProposal, null=True, blank=True,
                                          on_delete=models.CASCADE, related_name="decision_templates")
    national_proposal = models.ForeignKey(NationalProgramProposal, null=True, blank=True,
                                          on_delete=models.CASCADE, related_name="decision_templates")

    generated_by      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                          related_name="decision_templates")
    active            = models.BooleanField(default=True)
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def target(self):
        return self.intervention or self.national_proposal

    def __str__(self):
        return self.name

    @staticmethod
    def _next_ref():
        prefix = f"DEC-{date.today():%Y-%m}"
        last = (
            DecisionTemplate.objects
            .filter(name__startswith=prefix)
            .aggregate(m=Max("name"))["m"]
        )
        seq = int(last.split("-")[-1]) + 1 if last else 1
        return f"{prefix}-{seq:04d}"

    def save(self, *args, **kwargs):
        if not self.name:
            with transaction.atomic():
                prefix = f"TT-{date.today():%Y-%m}"
                list(
                    DecisionTemplate.objects
                    .select_for_update()
                    .filter(name__startswith=prefix)
                    .values_list("id", flat=True)
                )
                self.name = self._next_ref()
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

class DecisionTemplateCriterion(models.Model):
    """One row per criterion on the worksheet — type, decision fields, and selected bands."""
    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template      = models.ForeignKey(DecisionTemplate, on_delete=models.CASCADE, related_name="criteria")

    criterion     = models.ForeignKey(CriteriaAppraisalTool, on_delete=models.PROTECT, related_name="+")
    rule          = models.ForeignKey(CriteriaRule, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    kind          = models.CharField(max_length=30, blank=True)   
    target_fields = models.JSONField(default=list, blank=True)        
    selected_bands = models.JSONField(default=list, blank=True)       
    score          = models.IntegerField(null=True, blank=True)

    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["criterion__criteria"]

    def __str__(self):
        return f"{self.template.name} — {self.criterion.criteria}"
    

class PanelAppraisal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intervention = models.ForeignKey(
        InterventionProposal, on_delete=models.CASCADE,
        related_name="panel_appraisals", null=True, blank=True,
    )
    national_proposal = models.ForeignKey(
        NationalProgramProposal, on_delete=models.CASCADE,
        related_name="panel_appraisals", null=True, blank=True,
    )

    # run-level outcome
    success = models.BooleanField(default=False)   
    rank = models.PositiveIntegerField(null=True, blank=True)
    selected = models.BooleanField(default=False)
    final_comments = models.TextField(null=True, blank=True) 
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def target(self):
        return self.intervention or self.national_proposal

    @property
    def target_type(self) -> str:
        return "national_proposal" if self.national_proposal_id else "intervention"

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Appraisal — {self.target}"


class AppraisalScore(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appraisal = models.ForeignKey(PanelAppraisal, on_delete=models.CASCADE, related_name="scores")
    criterion = models.ForeignKey(CriteriaAppraisalTool, on_delete=models.PROTECT, related_name="appraisal_scores")

    ok = models.BooleanField(default=False)                 # did this criterion score
    score = models.FloatField(null=True, blank=True)        # null when not ok
    reasoning = models.TextField(null=True, blank=True)     # required when ok
    failure_reason = models.TextField(null=True, blank=True)  # required when not ok (e.g. "blank / no data")
    notes = models.TextField(null=True, blank=True)  

    # human iputs
    final_score = models.FloatField(null=True, blank=True)
    verified = models.BooleanField(default=False)
    edited = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def effective_score(self):
        return self.final_score if self.final_score is not None else self.score

    class Meta:
        ordering = ["criterion__criteria"]

    def __str__(self):
        state = f"{self.effective_score}" if (self.ok or self.final_score is not None) else "—"
        return f"{self.criterion.criteria}: {state}"



class AppraisalNote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appraisal = models.ForeignKey(PanelAppraisal, on_delete=models.CASCADE, related_name="notes_old")
    score = models.ForeignKey(
        AppraisalScore, on_delete=models.CASCADE,
        related_name="note_entries", null=True, blank=True,   
    )

    body = models.TextField()
    is_prompt = models.BooleanField(default=False)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{'Prompt' if self.is_prompt else 'Comment'} — {self.appraisal_id}"

 
 
 
#agentic
class AIProviderKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=50)
    label = models.CharField(max_length=120, blank=True)
    key = models.CharField(max_length=300)
    model_string = models.CharField(max_length=200,blank=True)
    temperature = models.FloatField(default=0.3)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["provider", "-is_default", "-created_at"]

    def __str__(self):
        return f"{self.provider} key ({self.label or 'default'})"
    

class AIModel(models.Model): # not used
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    provider = models.CharField(max_length=50)        # free-text
    model_string = models.CharField(max_length=200)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    temperature = models.FloatField(default=0.2)
    max_tokens = models.IntegerField(default=8000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "name"]

    def save(self, *args, **kwargs):
        if self.is_default:
            AIModel.objects.exclude(pk=self.pk).filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.provider})"
    

class AgentPrompt(models.Model): # not used
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)  
    template = models.TextField()                          
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class AppraisalRun(models.Model):
    """
    Audit record of one agent invocation. Stores the exact prompt + raw response
    so any score traces back to what the model saw and said.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appraisal = models.ForeignKey(
        PanelAppraisal, on_delete=models.CASCADE,
        related_name="runs", null=True, blank=True,  
    )
    model = models.ForeignKey(AIModel, on_delete=models.SET_NULL, null=True, blank=True)
    prompt_sent = models.TextField()
    raw_response = models.TextField(blank=True)
    parsed_ok = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Run {self.id} — {'ok' if self.parsed_ok else 'failed'}"



class BenefitPackage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, db_index=True)
    fund = models.CharField(max_length=160, blank=True, db_index=True)
    data = models.JSONField(default=dict, blank=True)   
    items = models.JSONField(default=list, blank=True)    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fund", "name"]
        indexes = [models.Index(fields=["fund", "name"])]

    def __str__(self):
        return f"{self.name} · {self.fund}"


class ProposedBenefitPackage(models.Model):
    """Proposed package stage. Same shape as BenefitPackage; `items` holds the
    proposed intervention set, so intervention↔package grouping lives in `items`."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, db_index=True)
    fund = models.CharField(max_length=160, blank=True, db_index=True)
    data = models.JSONField(default=dict, blank=True)
    items = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fund", "name"]
        indexes = [models.Index(fields=["fund", "name"])]

    def __str__(self):
        return f"{self.name} · {self.fund}"


class RevisedBenefitPackage(models.Model):
    """Revised package stage — post-appraisal / post-decision. Same shape."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, db_index=True)
    fund = models.CharField(max_length=160, blank=True, db_index=True)
    data = models.JSONField(default=dict, blank=True)
    items = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fund", "name"]
        indexes = [models.Index(fields=["fund", "name"])]

    def __str__(self):
        return f"{self.name} · {self.fund}"


class SwgPrioritizedList(models.Model):
    """SWG-prioritised topics that proceed to the panel. Rows kept as flexible
    JSON so the list tracks evolving SWG spreadsheet columns without migrations.

    Suggested (unenforced) `items` row:
        {
            "ref": "INTERV-2026-03-23-0005",
            "intervention": "High-risk antenatal mothers ...",
            "package": "Maternity, Neonatal and Child Health Services",
            "justification": "...",
            "next_steps": "Rapid Assessment for tariff determination",
            "decision": "",            # include | exclude | ""
            "service_type": "",
            "package_access": "",
            "hta_type": "rapid",       # rapid | full
        }
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, db_index=True)
    cycle = models.CharField(max_length=120, blank=True, db_index=True)
    data = models.JSONField(default=dict, blank=True)     # meta / header
    items = models.JSONField(default=list, blank=True)    # prioritised rows
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
    
    
class PanelAppraisedList(models.Model):
    """Panel-appraised interventions — the post-appraisal counterpart to
    SwgPrioritizedList. Same flexible-JSON shape so the list tracks evolving
    panel/decision columns without migrations.

    Suggested (unenforced) `items` row:
        {
            "ref": "INTERV-2026-03-23-0005",
            "intervention": "High-risk antenatal mothers ...",
            "package": "Maternity, Neonatal and Child Health Services",
            "phase": "",              # intervention phase / package
            "score": "",              # aggregate deterministic score
            "recommendation": "",     # include | exclude | conditional | ""
            "rationale": "",
            "conditions": "",         # any conditions attached to inclusion
            "decision": "",           # include | exclude | ""
            "hta_type": "rapid",      # rapid | full
        }
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, db_index=True)
    data = models.JSONField(default=dict, blank=True)    
    items = models.JSONField(default=list, blank=True)    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

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
# auditlog.register(InterventionScoringWindow)
auditlog.register(BenefitPackage)

