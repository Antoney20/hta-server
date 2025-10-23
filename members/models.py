import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator,  MinLengthValidator
from users.models import InterventionProposal
from auditlog.registry import auditlog

from django.db import models, transaction
from django.db.models import Max
import datetime

User = get_user_model()

class ReviewStage(models.TextChoices):
    
    INITIAL = 'initial', 'Initial'
    UNDER_REVIEW = 'under_review', 'Under Review'
    NEEDS_REVISION = 'needs_revision', 'Needs Revision'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'
    WITHDRAWN = 'withdrawn', 'Withdrawn'

class ImplementationStatus(models.TextChoices):
    NOT_STARTED = 'not_started', 'Not Started'
    PLANNING = 'planning', 'Planning'
    IN_PROGRESS = 'in_progress', 'In Progress'
    ON_HOLD = 'on_hold', 'On Hold'
    COMPLETED = 'completed', 'Completed'
    CANCELLED = 'cancelled', 'Cancelled'



class PriorityLevel(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    URGENT = 'urgent', 'Urgent'

class ThematicArea(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    color_code = models.CharField(max_length=20, default='#007bff', help_text='Hex color code for UI')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']

class ProposalTracker(models.Model):
    id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, primary_key=True)
    proposal = models.OneToOneField(InterventionProposal, on_delete=models.CASCADE, related_name='tracker')
    review_stage = models.CharField(max_length=20, choices=ReviewStage.choices,  default=ReviewStage.INITIAL)
    thematic_area = models.ForeignKey(ThematicArea, on_delete=models.SET_NULL, null=True, blank=True)
    priority_level = models.CharField(max_length=20, choices=PriorityLevel.choices, null= True, blank= True)
    implementation_status = models.CharField(max_length=20, choices=ImplementationStatus.choices,  null=True, blank=True)
    assigned_reviewers = models.ManyToManyField(
        User,  
        through='ReviewerAssignment',    
        through_fields=('tracker', 'reviewer'),   
        related_name='assigned_proposals',
        blank=True
    )
    start_date = models.DateField(null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    progress = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    notes= models.TextField(help_text="Notes on the task")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Tracker: {self.review_stage}"

    class Meta:
        ordering = ['-updated_at']  

        
class ReviewerAssignment(models.Model):
    tracker = models.ForeignKey(ProposalTracker, on_delete=models.CASCADE)
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE)
    notes= models.TextField(help_text="Notes on the task status",null=True, blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='reviewer_assignments_made')
    progress = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)],null=True, blank=True)
    complete_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ['tracker', 'reviewer']


class ReviewComment(models.Model):
    id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, primary_key=True)
    tracker = models.ForeignKey(ProposalTracker, on_delete=models.CASCADE, related_name='comments')
    reviewer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    comment_type = models.CharField(max_length=20, null=True, blank=True)
    content = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True) 
    updated_at = models.DateTimeField(auto_now=True)    

    def __str__(self):
        return f"Comment by {self.reviewer.username if self.reviewer else 'Unknown'}"

    class Meta:
        ordering = ['-created_at']


class DecisionRationale(models.Model):
    tracker = models.OneToOneField(ProposalTracker, on_delete=models.CASCADE, related_name='decision_rationale')
    decision = models.CharField(max_length=20, ) #approved rejected.
    detailed_rationale = models.TextField(help_text="Detailed explanation",null=True, blank=True)
    decided_by = models.ForeignKey(User, on_delete=models.CASCADE)
    approval_conditions = models.TextField(blank=True, null=True)
    decided_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.decision} - {self.tracker.proposal.intervention_name}"
    
    
    
# task manager..

class TaskStatus(models.TextChoices):
    NEW = 'new', 'New'
    IN_PROGRESS = 'in_progress', 'In Progress'
    REVIEW = 'review', 'Under Review'
    COMPLETED = 'completed', 'Completed'
    ON_HOLD = 'on_hold', 'On Hold'
    CANCELLED = 'cancelled', 'Cancelled'


class PriorityLevel(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    URGENT = 'urgent', 'Urgent'


class Task(models.Model):
    id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, primary_key=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True, help_text="Additional notes for the task")
    
    status = models.CharField(max_length=20, choices=TaskStatus.choices, default=TaskStatus.NEW)
    priority = models.CharField(max_length=20, choices=PriorityLevel.choices, default=PriorityLevel.MEDIUM)
    
    assigned_users = models.ManyToManyField(
        User, 
        through='TaskAssignment', 
        through_fields=('task', 'user'), 
        related_name='assigned_tasks', 
        blank=True
    )
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_tasks')
    
    # Dates
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    progress = models.IntegerField(
        default=0, 
        validators=[MinValueValidator(0), MaxValueValidator(100)], 
        null=True, 
        blank=True
    )
    position_x = models.IntegerField(default=0, help_text="Horizontal position in the board")
    position_y = models.IntegerField(default=0, help_text="Vertical position in the board")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.status}"

    @property
    def is_completed(self):
        return self.status == TaskStatus.COMPLETED

    @property
    def is_overdue(self):
        if not self.due_date:
            return False
        from django.utils import timezone
        return self.due_date < timezone.now().date() and not self.is_completed

    class Meta:
        ordering = ['position_y', 'position_x', '-created_at']


class TaskAssignment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='assignments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    assigned_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='tasks_assigned'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True, help_text="Assignment-specific notes")

    class Meta:
        unique_together = ['task', 'user']

    def __str__(self):
        return f"{self.user.username} -> {self.task.title}"



# here we cover the forums/channels
# class Channel(models.Model):
#     name = models.CharField(max_length=100)
#     description = models.TextField(blank=True)
#     created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
#     is_private = models.BooleanField(default=False)
#     # related_tracker = models.ForeignKey(ProposalTracker, on_delete=models.SET_NULL, null=True, blank=True)
#     members = models.ManyToManyField( User , through='ChannelMembership', related_name='channels')
#     created_at = models.DateTimeField(auto_now_add=True)
    
    
# class ChannelMembership(models.Model):
#     channel = models.ForeignKey(Channel, on_delete=models.CASCADE)
#     user = models.ForeignKey(User, on_delete=models.CASCADE)
#     ROLE_CHOICES = [   ('owner', 'Owner'),   ('moderator', 'Moderator'), ('member', 'Member'),  ]
#     role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    
#     joined_at = models.DateTimeField(auto_now_add=True)
#     created_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         unique_together = ('channel', 'user')


# class Message(models.Model):
#     channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='messages')
#     user = models.ForeignKey(User, on_delete=models.CASCADE)
#     content = models.TextField()
#     related_task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True)
#     related_poll = models.ForeignKey('Poll', on_delete=models.SET_NULL, null=True, blank=True)

#     created_at = models.DateTimeField(auto_now_add=True)



# class Poll(models.Model):
#     question = models.CharField(max_length=255)
#     description = models.TextField(blank=True, null=True)
#     channel = models.ForeignKey(Channel, on_delete=models.SET_NULL, null=True, blank=True)
#     tracker = models.ForeignKey(ProposalTracker, on_delete=models.SET_NULL, null=True, blank=True)
#     task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True)
    
#     is_anonymous = models.BooleanField(default=False)
#     multiple_choice = models.BooleanField(default=False)
#     expires_at = models.DateTimeField(null=True, blank=True)

#     created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
#     created_at = models.DateTimeField(auto_now_add=True)

# class PollOption(models.Model):
#     poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='options')
#     text = models.CharField(max_length=255, null=True, blank=True)

# class PollVote(models.Model):
#     poll = models.ForeignKey(Poll, on_delete=models.CASCADE)
#     option = models.ForeignKey(PollOption, on_delete=models.SET_NULL , null=True, blank=True)
#     user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
#     voted_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         unique_together = ['poll', 'user']



class Channel(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    name = models.CharField(max_length=100, validators=[MinLengthValidator(1)], db_index=True)
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_channels'
    )
    is_private = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    members = models.ManyToManyField(
        User, 
        through='ChannelMembership', 
        related_name='channels'
    )

    class Meta:
        indexes = [
            models.Index(fields=['name', 'is_private']),
            models.Index(fields=['created_at']),
        ]
       

    def __str__(self):
        return f"{self.name} ({'Private' if self.is_private else 'Public'})"

class ChannelMembership(models.Model):
    channel = models.ForeignKey(
        Channel, 
        on_delete=models.CASCADE, 
        related_name='memberships'
    )
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='channel_memberships'
    )
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('moderator', 'Moderator'),
        ('member', 'Member'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('channel', 'user')
        indexes = [
            models.Index(fields=['channel', 'user']),
            models.Index(fields=['role']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.channel.name} ({self.role})"

# Updated Message model with thread support
class Message(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    channel = models.ForeignKey(
        Channel, 
        on_delete=models.CASCADE, 
        related_name='messages'
    )
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='messages'
    )
    content = models.TextField(validators=[MinLengthValidator(1)])
    
    # Thread support - add parent message reference
    parent_message = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['channel', 'created_at']),
            models.Index(fields=['user']),
            models.Index(fields=['parent_message']), 
        ]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(content=''),
                name='non_empty_message_content'
            )
        ]

    def __str__(self):
        if self.parent_message:
            return f"Reply by {self.user.username} to message in {self.channel.name}"
        return f"Message by {self.user.username} in {self.channel.name}"

    @property
    def is_thread_reply(self):
        """Check if this message is a reply to another message"""
        return self.parent_message is not None

    @property
    def reply_count(self):
        """Get the number of replies to this message"""
        return self.replies.count()




class Poll(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    question = models.CharField(max_length=255, validators=[MinLengthValidator(1)])
    description = models.TextField(blank=True, null=True)
    channel = models.ForeignKey(
        Channel, 
        on_delete=models.CASCADE, 
        related_name='polls',
        null=True,
        blank=True
    )
    
    is_anonymous = models.BooleanField(default=False)
    allow_multiple_choices = models.BooleanField(default=False)
    allow_comments = models.BooleanField(default=True)
    
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_polls'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['channel', 'created_at']),
            models.Index(fields=['created_by']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        channel_name = self.channel.name if self.channel else "Standalone"
        return f"Poll: {self.question} in {channel_name}"

    @property
    def is_active(self):
        if not self.expires_at:
            return True
        return self.expires_at > timezone.now()


class PollOption(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    poll = models.ForeignKey(
        Poll, 
        on_delete=models.CASCADE, 
        related_name='options'
    )
    text = models.CharField(max_length=255, validators=[MinLengthValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['poll']),
        ]

    def __str__(self):
        return f"Option: {self.text} for {self.poll.question}"


class PollVote(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    poll = models.ForeignKey(
        Poll, 
        on_delete=models.CASCADE, 
        related_name='votes'
    )
    option = models.ForeignKey(
        PollOption, 
        on_delete=models.CASCADE, 
        related_name='votes'
    )
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='poll_votes'
    )
    voted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('poll', 'user', 'option')
        indexes = [
            models.Index(fields=['poll', 'user']),
            models.Index(fields=['option']),
        ]

    def __str__(self):
        return f"Vote by {self.user.username if self.user else 'Anonymous'} on {self.poll.question}"


class PollComment(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    poll = models.ForeignKey(
        Poll,
        on_delete=models.CASCADE,
        related_name='poll_comments'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='poll_comments'
    )
    content = models.TextField(validators=[MinLengthValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['poll', 'created_at']),
            models.Index(fields=['user']),
        ]
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.user.username} on {self.poll.question}"

    
    
    
    
class Record(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    title = models.CharField(max_length=255, validators=[MinLengthValidator(1)])
    type = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    
    documents = models.FileField(upload_to='records/documents/', blank=True, null=True)
    images = models.ImageField(upload_to='records/images/', blank=True, null=True)
    reference_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    
    link = models.URLField(blank=True, null=True)
    
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_records'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['created_by']),
        ]
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.reference_number:
            self.reference_number = self._generate_reference_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_reference_number():
        """Generate a unique reference number with retry logic"""
        with transaction.atomic():
            year = datetime.datetime.now().year
            
            last_record = Record.objects.select_for_update().filter(
                reference_number__startswith=f"REC-{year}-"
            ).order_by('-reference_number').first()
            
            if last_record and last_record.reference_number:
                try:
                    last_count = int(last_record.reference_number.split('-')[-1])
                    count = last_count + 1
                except (ValueError, IndexError):
                    count = 1
            else:
                count = 1
            
            return f"REC-{year}-{count:04d}"

    def __str__(self):
        if self.reference_number:
            return f"{self.reference_number}: {self.title}"
        return self.title    
    


class Resource(models.Model):
    """
    Single model for both Resources and Grievances
    Resources: SHA guidelines, panel mandate, templates, SOPs, policies and frameworks
    Grievances: Complaints logged and categorized by type
    """
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    title = models.CharField(max_length=255, validators=[MinLengthValidator(1)])
    type = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    
    documents = models.FileField(upload_to='resources/documents/', blank=True, null=True)
    images = models.ImageField(upload_to='resources/images/', blank=True, null=True)

    link = models.URLField(blank=True, null=True)
    is_public = models.BooleanField(default=True)
    complainant_name = models.CharField(max_length=255, blank=True, null=True)
    complainant_email = models.EmailField(blank=True, null=True)
    reference_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    resolution_notes = models.TextField(blank=True, null=True)
    tags = models.TextField(blank=True, null=True)
    
    # Metadata
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_resources'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['created_by']),
            models.Index(fields=['is_public']),
            models.Index(fields=['type']),
            models.Index(fields=['reference_number']),
        ]
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.reference_number:
            import datetime
            year = datetime.datetime.now().year
            count = Resource.objects.filter(created_at__year=year).count() + 1
            self.reference_number = f"RSC-{year}-{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        if self.reference_number:
            return f"{self.reference_number}: {self.title}"
        return self.title




class Announcement(models.Model):
    """
    Model for managing announcements and notices
    Internal updates, major decisions, urgent alerts, policy changes
    """
    
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    title = models.CharField(max_length=255, validators=[MinLengthValidator(1)])
    content = models.TextField()
    type = models.TextField(blank=True, null=True)  # e.g., policy, urgent, decision, news, reminder
    priority = models.TextField(blank=True, null=True)  # e.g., low, medium, high, urgent
    documents = models.FileField(upload_to='announcements/documents/', blank=True, null=True)
    images = models.ImageField(upload_to='announcements/images/', blank=True, null=True)
    link = models.URLField(blank=True, null=True)
    is_public = models.BooleanField(default=True)
    is_pinned = models.BooleanField(default=False)
    expires_at = models.DateTimeField(blank=True, null=True)
    reference_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    
    # Additional metadata
    tags = models.TextField(blank=True, null=True)  # Comma-separated tags
    
    # Metadata
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_announcements'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['created_by']),
            models.Index(fields=['is_public']),
            models.Index(fields=['is_pinned']),
     
        ]
        ordering = ['-is_pinned', '-created_at']  # Pinned items first, then by date

    def save(self, *args, **kwargs):
        if not self.reference_number:
            import datetime
            year = datetime.datetime.now().year
            count = Announcement.objects.filter(created_at__year=year).count() + 1
            self.reference_number = f"ANN-{year}-{count:04d}"
        super().save(*args, **kwargs)
    
    @property
    def is_expired(self):
        """Check if announcement has expired"""
        if not self.expires_at:
            return False
        from django.utils import timezone
        return timezone.now() > self.expires_at

    def __str__(self):
        if self.reference_number:
            return f"{self.reference_number}: {self.title}"
        return self.title
    
    
class Event(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200, db_index=True)
    description = models.TextField(blank=True, null=True)
    event_type = models.CharField(max_length=100, blank=True, null=True)  # meeting, training, deadline, 
    
    start_date = models.DateTimeField(db_index=True)
    end_date = models.DateTimeField(blank=True, null=True)
    
    location = models.CharField(max_length=255, blank=True, null=True) 
    link = models.URLField(blank=True, null=True)  # Meeting/invite link
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_events')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['start_date']
        indexes = [
            models.Index(fields=['start_date', 'event_type']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.start_date.strftime('%Y-%m-%d')}"
    
    @property
    def is_upcoming(self):
        """Check if event is in the future"""
        return self.start_date > timezone.now()
    
    @property
    def is_past(self):
        """Check if event is in the past"""
        end = self.end_date or self.start_date
        return end < timezone.now()


class Feedback(models.Model):
    """User feedback submission with anonymous support and metadata tracking"""

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    type = models.TextField(blank=True, null=True)
    subject = models.CharField(max_length=255, blank=True, null=True)
    message = models.TextField(help_text="Feedback message")

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    browser = models.CharField(max_length=100, blank=True, null=True)
    operating_system = models.CharField(max_length=100, blank=True, null=True)
    device_type = models.CharField(max_length=50, blank=True, null=True)

    STATUS_CHOICES = [
        ('new', 'New'),
        ('reviewing', 'Reviewing'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    reference_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    admin_response = models.TextField(blank=True, null=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    responded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='feedback_responses'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status']),
        ]

    def save(self, *args, **kwargs):
        if not self.reference_number:
            year = datetime.datetime.now().year
            count = Feedback.objects.filter(created_at__year=year).count() + 1
            self.reference_number = f"FB-{year}-{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        if self.subject:
            return f"{self.subject} - {self.created_at.strftime('%Y-%m-%d')}"
        return f"Feedback {self.id} - {self.created_at.strftime('%Y-%m-%d')}"
    
    
    
    
class ImplementationTracking(models.Model):
    """
    Track the implementation of approved proposals
    """
    id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, primary_key=True)
    decision_rationale = models.OneToOneField(
       DecisionRationale, 
        on_delete=models.CASCADE,
        related_name='implementation'
    )
    
    implementation_start_date = models.DateField( null=True, 
        blank=True, 
        help_text="When implementation actually started"
    )
    
    expected_completion_date = models.DateField(
        null=True, 
        blank=True, 
        help_text="Expected completion date"
    )
    
    actual_completion_date = models.DateField(
        null=True, 
        blank=True, 
        help_text="When implementation was completed"
    )
    
    progress_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Overall implementation progress (0-100%)"
    )
    
    # Status and updates
    current_status = models.TextField(
        help_text="Current implementation status description",
        blank=True
    )
    
    # Key achievements and activities
    key_activities_completed = models.TextField(
        help_text="Description of key activities completed",
        blank=True
    )
    
    # Documentation
    implementation_notes = models.TextField(
        help_text="Detailed notes about implementation progress",
        blank=True
    )
    
    # Completion
    is_completed = models.BooleanField(
        default=False,
        help_text="Mark as true when implementation is complete"
    )
    
    completion_remarks = models.TextField(
        help_text="Final remarks upon completion",
        blank=True
    )
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_implementations'
    )
    last_updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='updated_implementations'
    )
    
    def __str__(self):
        proposal_ref = self.decision_rationale.tracker.proposal.reference_number
        return f"Implementation: {proposal_ref} - {self.progress_percentage}%"
    
    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Implementation Tracking"
        verbose_name_plural = "Implementation Trackings"
    
    @property
    def is_overdue(self):
        """Check if implementation is overdue"""
        from django.utils import timezone
        if self.expected_completion_date and not self.is_completed:
            return timezone.now().date() > self.expected_completion_date
        return False
    



auditlog.register(Announcement)
auditlog.register(Channel)
auditlog.register(Message)
auditlog.register(ChannelMembership)
auditlog.register(ProposalTracker)
auditlog.register(Record)
auditlog.register(Resource)
auditlog.register(Task)
auditlog.register(TaskAssignment)
auditlog.register(ThematicArea)
auditlog.register(ReviewerAssignment)
auditlog.register(ReviewComment)
auditlog.register(Event)
auditlog.register(ImplementationTracking)