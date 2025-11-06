import os
import uuid
from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager, Group, Permission
from django.core.validators import MinLengthValidator
from django.utils import timezone
from auditlog.registry import auditlog

import datetime
from django.db import models, transaction
from django.db.models import Max
import uuid
from django.db.utils import OperationalError, InternalError
import time
import logging

logger = logging.getLogger(__name__)

class UserStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    BLOCKED = "blocked", "Blocked"
    
class UserRole:
    ADMIN = 'admin'
    SECRETARIATE = 'secretariate'
    CONTENT_MANAGER = 'content_manager'
    USER = 'user'

    CHOICES = [
        (ADMIN, 'Admin'),
        (SECRETARIATE, 'Secretariate'),
        (CONTENT_MANAGER, 'Content Manager'),
        (USER, 'User'),
    ]


class CustomUserManager(BaseUserManager):
    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        if not username:
            raise ValueError("The Username field must be set")

        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        
        
        user_role_group, _ = Group.objects.get_or_create(name=UserRole.USER)
        user.groups.add(user_role_group)

        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("status", UserStatus.ACTIVE)
        return self.create_user(email, username, password, **extra_fields)

class CustomUser(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=150, unique=True, validators=[MinLengthValidator(5)])
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=30,  blank=True, null=True)
    last_name = models.CharField(max_length=30,  blank=True, null=True)
    profile_image = models.ImageField(upload_to="users/images/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    country = models.CharField(max_length=255, blank=True, null=True)
    is_email_verified = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=UserStatus.choices, default=UserStatus.ACTIVE)
    verification_token = models.CharField(max_length=100, blank=True, null=True)
    
    groups = models.ManyToManyField(
        Group, 
        related_name="custom_users", 
        blank=True,
        help_text="The groups this user belongs to."
    )
    user_permissions = models.ManyToManyField(
        Permission,
        related_name="custom_users",
        blank=True,
        help_text="Specific permissions for this user."
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = CustomUserManager()

    def __str__(self):
        return self.username

    def has_role(self, group_name):
        return self.groups.filter(name=group_name).exists()
    
    def is_admin(self):
        return self.has_role(UserRole.ADMIN)

    def is_secretariate(self):
        return self.has_role(UserRole.SECRETARIATE)

    def is_content_manager(self):
        return self.has_role(UserRole.CONTENT_MANAGER)

    def is_regular_user(self):
        return self.has_role(UserRole.USER)


    @property
    def is_blocked(self):
        return self.status == UserStatus.BLOCKED

    def save(self, *args, **kwargs):
        if self.status == UserStatus.BLOCKED:
            self.is_active = False
        super().save(*args, **kwargs)
        
        
        

class Member(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, null=True, blank=True)
    position = models.CharField(max_length=200)
    organization = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_profile_complete = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.position} - {self.organization}"
    
    
    
    
    
    
    
    
    
    





# def document_upload_path(instance, filename):
#     """Generate upload path with timestamp"""
#     timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
#     name, ext = os.path.splitext(filename)
#     return f'documents/{name}_{timestamp}{ext}'

# class InterventionProposal(models.Model):
#     name = models.CharField(max_length=100)
#     phone = models.CharField(max_length=20)
#     email = models.EmailField(blank=True, null=True)
#     profession = models.CharField(max_length=100, blank=True, null=True)
#     organization = models.CharField(max_length=200, blank=True, null=True)
#     county = models.CharField(max_length=100, blank=True, null=True)
#     intervention_name = models.CharField(max_length=200, blank=True, null=True)
#     intervention_type = models.CharField(max_length=100, blank=True, null=True)
#     beneficiary = models.TextField(blank=True, null=True)
#     justification = models.TextField(blank=True, null=True)
#     expected_impact = models.TextField(blank=True, null=True)
#     additional_info = models.TextField(blank=True, null=True)
#     signature = models.CharField(max_length=200)
#     date = models.DateField(blank=True, null=True)
#     ip_address = models.GenericIPAddressField(blank=True, null=True)
#     user_agent = models.TextField(blank=True, null=True)  
#     submitted_at = models.DateTimeField(auto_now_add=True)
#     user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True)
#     is_public = models.BooleanField(default=False)
    
#     def __str__(self):
#         return f"{self.intervention_name} - {self.name}"
    
#     class Meta:
#             permissions = [
#                 ("can_submit_proposal", "Can submit a proposal"),
#                 ("can_view_all_proposals", "Can view all proposals"),
#             ]

# class ProposalDocument(models.Model):
#     proposal = models.ForeignKey(InterventionProposal, on_delete=models.CASCADE, related_name='documents')
#     document = models.FileField(upload_to=document_upload_path)
#     original_name = models.CharField(max_length=255)
#     uploaded_at = models.DateTimeField(auto_now_add=True)
#     is_public = models.BooleanField(default=False)
    
#     def __str__(self):
#         return f"Document for {self.proposal.intervention_name} - {self.original_name}"
 
   
   
   
def document_upload_path(instance, filename):
    """Generate upload path with UUID to avoid collisions"""
    ext = os.path.splitext(filename)[1]
    unique_filename = f"{uuid.uuid4().hex}{ext}"
    return f'documents/{timezone.now().strftime("%Y/%m")}/{unique_filename}'


# class InterventionProposal(models.Model):
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
#     # Contact Information
#     name = models.CharField(max_length=100, db_index=True)
#     phone = models.CharField(max_length=20)
#     email = models.EmailField(blank=True, null=True, db_index=True)
    
#     # Professional Details
#     profession = models.CharField(max_length=100, blank=True, null=True)
#     organization = models.CharField(max_length=200, blank=True, null=True)
#     county = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    
#     # Intervention Details
#     intervention_name = models.CharField(max_length=200, blank=True, null=True, db_index=True)
#     intervention_type = models.CharField(max_length=100, blank=True, null=True, db_index=True)
#     beneficiary = models.TextField(blank=True, null=True)
#     justification = models.TextField(blank=True, null=True)
#     expected_impact = models.TextField(blank=True, null=True)
#     additional_info = models.TextField(blank=True, null=True)
    
#     # Submission Details
#     signature = models.CharField(max_length=200)
#     date = models.DateField(blank=True, null=True)
#     ip_address = models.GenericIPAddressField(blank=True, null=True)
#     user_agent = models.TextField(blank=True, null=True)
    
#     # Tracking
#     submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)
#     user = models.ForeignKey(
#         CustomUser, 
#         on_delete=models.SET_NULL, 
#         null=True, 
#         blank=True,
#         db_index=True
#     )
#     is_public = models.BooleanField(default=False, db_index=True)
    
#     reference_number = models.CharField(
#         max_length=50, 
#         unique=True, 
#         blank=True, 
#         null=True,
#         db_index=True
#     )
    
#     def __str__(self):
#         ref = self.reference_number or str(self.id)[:8]
#         return f"{ref} - {self.intervention_name} - {self.name}"
    
#     class Meta:
#         permissions = [
#             ("can_submit_proposal", "Can submit a proposal"),
#             ("can_view_all_proposals", "Can view all proposals"),
#         ]
#         indexes = [
#             models.Index(fields=['-submitted_at', 'is_public']),
#             models.Index(fields=['user', '-submitted_at']),
#             models.Index(fields=['county', '-submitted_at']),
#             models.Index(fields=['intervention_type', '-submitted_at']),
#         ]
#         ordering = ['-submitted_at']


class InterventionProposal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Contact Information
    name = models.CharField(max_length=100, db_index=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True, db_index=True)

    # Professional Details
    profession = models.CharField(max_length=100, blank=True, null=True)
    organization = models.CharField(max_length=200, blank=True, null=True)
    county = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    # Intervention Details
    intervention_name = models.CharField(max_length=200, blank=True, null=True, db_index=True)
    intervention_type = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    beneficiary = models.TextField(blank=True, null=True)
    justification = models.TextField(blank=True, null=True)
    expected_impact = models.TextField(blank=True, null=True)
    additional_info = models.TextField(blank=True, null=True)

    # Submission Details
    signature = models.CharField(max_length=200)
    date = models.DateField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)

    # Tracking
    submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey('users.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, db_index=True)
    is_public = models.BooleanField(default=False, db_index=True)

    reference_number = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        db_index=True
    )

    class Meta:
        permissions = [
            ("can_submit_proposal", "Can submit a proposal"),
            ("can_view_all_proposals", "Can view all proposals"),
        ]
        indexes = [
            models.Index(fields=['-submitted_at', 'is_public']),
            models.Index(fields=['user', '-submitted_at']),
            models.Index(fields=['county', '-submitted_at']),
            models.Index(fields=['intervention_type', '-submitted_at']),
        ]
        ordering = ['-submitted_at']

    def save(self, *args, **kwargs):
        if not self.reference_number:
            self.reference_number = self._generate_reference_number()
        super().save(*args, **kwargs)

    def _generate_reference_number(self):
        """
        Generates a unique reference number in the format:
        INTERV-YYYY-MM-DD-0001
        Safe under concurrent submissions via SELECT FOR UPDATE with retry on deadlock
        """
        max_retries = 5
        base_delay = 0.1  # Initial delay in seconds

        today = datetime.date.today()
        prefix = f"INTERV-{today.strftime('%Y-%m-%d')}"
        
        for attempt in range(max_retries):
            try:
                with transaction.atomic():
                    # Use select_for_update on the queryset to lock rows
                    locked_qs = InterventionProposal.objects.select_for_update() \
                        .filter(reference_number__startswith=prefix)
                    
                    # Aggregate max number (cast the suffix to int)
                    last_number = locked_qs.annotate(
                        num_part=models.functions.Cast(
                            models.functions.Substr('reference_number', len(prefix) + 2),
                            models.IntegerField()
                        )
                    ).aggregate(max_num=Max('num_part'))['max_num'] or 0

                    next_number = last_number + 1
                    return f"{prefix}-{next_number:04d}"
                    
            except (OperationalError, InternalError) as e:
                error_msg = str(e).lower()
                is_deadlock = 'deadlock' in error_msg or '40p01' in error_msg  # PostgreSQL deadlock code
                
                if not is_deadlock or attempt == max_retries - 1:
                    logger.error(f"Failed to generate reference number after {attempt + 1} attempts: {e}")
                    if attempt == max_retries - 1:
                        raise
                    continue
                
                # For deadlocks, retry with exponential backoff
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Deadlock detected on attempt {attempt + 1}/{max_retries}. Retrying in {delay:.2f}s")
                time.sleep(delay)
            except Exception as e:
                logger.error(f"Unexpected error generating reference number: {e}")
                raise

        # Fallback: if all retries fail, generate a UUID-based fallback (non-sequential)
        fallback_ref = f"INTERV-{today.strftime('%Y-%m-%d')}-UUID-{str(uuid.uuid4())[:8].upper()}"
        logger.warning(f"All retries failed; using fallback reference: {fallback_ref}")
        return fallback_ref

    def __str__(self):
        ref = self.reference_number or str(self.id)[:8]
        return f"{ref} - {self.intervention_name} - {self.name}"


class ProposalDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proposal = models.ForeignKey(
        InterventionProposal, 
        on_delete=models.CASCADE, 
        related_name='documents',
        db_index=True
    )
    document = models.FileField(upload_to=document_upload_path)
    original_name = models.CharField(max_length=255)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)  # Store size in bytes
    content_type = models.CharField(max_length=100, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_public = models.BooleanField(default=False, db_index=True)
    
    def __str__(self):
        return f"{self.original_name} ({self.proposal.reference_number or self.proposal.id})"
    
    class Meta:
        indexes = [
            models.Index(fields=['proposal', '-uploaded_at']),
        ]
        ordering = ['-uploaded_at']
   
    
class ProposalSubmissionStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    PROCESSING = 'processing', 'Processing'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'
    RETRYING = 'retrying', 'Retrying'

class ProposalSubmission(models.Model):
    """Tracks submission attempts and status"""
    submission_id = models.UUIDField(default=uuid.uuid4, unique=True)
    status = models.CharField(max_length=20, choices=ProposalSubmissionStatus.choices, default=ProposalSubmissionStatus.PENDING)
    form_data = models.JSONField()
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    task_id = models.CharField(max_length=255, null=True, blank=True)
    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=3)
    error_message = models.TextField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    proposal = models.OneToOneField(InterventionProposal, on_delete=models.CASCADE, null=True, blank=True)
    
    def __str__(self):
        return f"Submission {self.submission_id} - {self.status}"

class TemporaryFile(models.Model):
    """Temporarily stores uploaded files before processing"""
    submission = models.ForeignKey(ProposalSubmission, on_delete=models.CASCADE, related_name='temp_files')
    file = models.FileField(upload_to='temp_uploads/')
    original_name = models.CharField(max_length=255)
    file_size = models.BigIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Temp file: {self.original_name}"
    
    
    
    


class FAQ(models.Model):
    question = models.CharField(max_length=500, blank=True, null=True)
    answer = models.TextField(blank=True, null=True)
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    order = models.IntegerField(default=0, blank=True, null=True, help_text="Display order (lower numbers first)")

    class Meta:
        ordering = ['order', 'id']
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question[:100]

class News(models.Model):
    title = models.CharField(max_length=300, blank=True, null=True)
    excerpt = models.TextField(max_length=500, blank=True, null=True)
    content = models.TextField(blank=True, null=True)
    author = models.CharField(max_length=100, blank=True, null=True)
    author_role = models.CharField(max_length=100, blank=True, null=True)
    featured = models.BooleanField(default=False)
    published = models.BooleanField(default=False)
    date = models.DateField(blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    image = models.ImageField(upload_to='news/', blank=True, null=True)
    tags = models.CharField(max_length=500, blank=True, help_text="Comma-separated tags")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = "News Article"
        verbose_name_plural = "News Articles"

    def __str__(self):
        return self.title



    def get_tags_list(self):
        """Return tags as a list"""
        return [tag.strip() for tag in self.tags.split(',') if tag.strip()]
       
class Governance(models.Model):
    name = models.CharField(max_length=200)
    image = models.ImageField(upload_to='governance/', blank=True, null=True)
    title = models.CharField(max_length=100, blank=True, null=True, help_text="e.g., Prof., Dr.")
    role = models.CharField(max_length=100, blank=True, null=True, help_text="e.g., Chairperson, Member")
    from_organization = models.CharField(max_length=200, blank=True, null=True, verbose_name="From")
    description = models.TextField(blank=True, null=True)
    is_secretariat = models.BooleanField(default=False)
    is_panel_member = models.BooleanField(default=False)
    hide_profile = models.BooleanField(default=False)
    deactivate_user = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [ 'name']
        verbose_name = "Governance Member"
        verbose_name_plural = "Governance Members"

    def __str__(self):
        title_prefix = f"{self.title} " if self.title else ""
        return f"{title_prefix}{self.name}"

class MediaResource(models.Model):
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, null=True)
    category = models.CharField(max_length=50,  default='general')
    type = models.CharField(max_length=50, blank=True, null=True)
    url = models.URLField(max_length=500, blank=True, null=True)
    featured = models.BooleanField(default=False)
    hide_resource = models.BooleanField(default=False)
    date = models.CharField(max_length=100, blank=True, null=True, help_text="e.g., January 2024, Updated Monthly")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-featured',  '-created_at']
        verbose_name = "Media Resource"
        verbose_name_plural = "Media Resources"

    def __str__(self):
        return self.title





class ContactSubmission(models.Model):
    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    organization = models.CharField(max_length=200, blank=True, null=True)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Contact Submission"
        verbose_name_plural = "Contact Submissions"

    def __str__(self):
        return f"{self.full_name} - {self.subject}"




class NewsletterSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-subscribed_at']
        verbose_name = "Newsletter Subscription"
        verbose_name_plural = "Newsletter Subscriptions"

    def __str__(self):
        status = "Active" if self.is_active else "Unsubscribed"
        return f"{self.email} - {status}"
    
    def unsubscribe(self):
        """Unsubscribe the user"""
        from django.utils import timezone
        self.is_active = False
        self.unsubscribed_at = timezone.now()
        self.save()
    
    
    
    
    
    
 
 
 
#  new model for email logics


class EmailLog(models.Model):
    STATUS_CHOICES = [
        ('initial', 'Initial'),
        ('sending', 'Sending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]
    
    subject = models.TextField()
    message = models.TextField(blank=True, null=True)
    sender = models.CharField(max_length=255, default=settings.DEFAULT_FROM_EMAIL)
    recipient = models.TextField(help_text="Reciever")
    category = models.CharField(max_length=50,  default='other')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='initial')
    error_message = models.TextField(blank=True, null=True) 
    retry_count = models.PositiveIntegerField(default=0) # in cdjango cron , handle retries count
    last_attempt = models.DateTimeField(blank=True, null=True) 

    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(blank=True, null=True)


    def mark_sending(self):
        self.status = 'sending'
        self.last_attempt = timezone.now()
        self.save(update_fields=['status', 'last_attempt'])

    def mark_sent(self):
        self.status = 'sent'
        self.sent_at = timezone.now()
        self.error_message = None
        self.save(update_fields=['status', 'sent_at', 'error_message'])

    def mark_failed(self, exc):
        self.status = 'failed'
        self.error_message = str(exc)
        self.retry_count += 1
        self.last_attempt = timezone.now()
        self.save(update_fields=['status', 'error_message', 'retry_count', 'last_attempt'])

    def __str__(self):
        return f"[{self.category}] {self.subject} → {self.recipient} ({self.status})"
    

auditlog.register(CustomUser)
auditlog.register(InterventionProposal)
auditlog.register(Member)
auditlog.register(ProposalSubmission)
auditlog.register(TemporaryFile)
auditlog.register(ProposalDocument)

auditlog.register(FAQ)
auditlog.register(News)
auditlog.register(Governance)
auditlog.register(MediaResource)
auditlog.register(ContactSubmission)
auditlog.register(NewsletterSubscription)