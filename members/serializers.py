from rest_framework import serializers
from django.contrib.auth import get_user_model

from users.serializers import ProposalDocumentSerializer
from django.utils import timezone


from .models import (
    Announcement,
    Channel,
    ChannelMembership,
    DecisionRationale,
    Feedback,
    ImplementationTracking,
    Poll,
    PollComment,
    PollOption,
    ProposalTracker,
    Record,
    Resource,
    Task,
    TaskAssignment,
    TaskStatus, 
    ThematicArea, 
    ReviewerAssignment, 
    ReviewComment,
     Message,
     Event
)
from users.models import CustomUser, InterventionProposal, ProposalDocument

User = get_user_model()


class InterventionProposalSerializer(serializers.ModelSerializer):
    documents = ProposalDocumentSerializer(many=True, read_only=True)
    uploaded_documents = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False
    )
    
    class Meta:
        model = InterventionProposal
        fields = [
            'id', 
            'reference_number',
            'name', 
            'phone', 
            'email', 
            
            'profession', 
            'organization', 
            'county',
            'intervention_name', 
            'intervention_type', 
            'beneficiary', 
            'justification', 
            'expected_impact', 
            'additional_info', 
            'signature', 
            'date',
            'submitted_at',
            'is_public',
            'documents',
            'uploaded_documents'
        ]
        read_only_fields = ('submitted_at', 'user')
        
   

class ThematicAreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ThematicArea
        fields = [
            'id', 'name', 'description', 'color_code', 
            'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class ReviewerAssignmentSerializer(serializers.ModelSerializer):
    reviewer = UserSerializer(read_only=True)
    reviewer_id = serializers.IntegerField(write_only=True)
    assigned_by = UserSerializer(read_only=True)
    tracker_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = ReviewerAssignment
        fields = [
            'id', 'tracker', 'reviewer', 'reviewer_id', 'tracker_id',
            'notes', 'assigned_at', 'assigned_by', 'progress', 'complete_date'
        ]
        read_only_fields = ['id', 'assigned_at', 'assigned_by']



class ReviewCommentSerializer(serializers.ModelSerializer):
    reviewer = UserSerializer(read_only=True)
    tracker_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = ReviewComment
        fields = [
            'id', 'tracker', 'reviewer', 'tracker_id', 'comment_type',
            'content', 'is_resolved', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'reviewer', 'tracker']
        

class ProposalTrackerSerializer(serializers.ModelSerializer):
    proposal = InterventionProposalSerializer(read_only=True)
    thematic_area = ThematicAreaSerializer(read_only=True)
    assigned_reviewers = UserSerializer(many=True, read_only=True)
    comments = ReviewCommentSerializer(many=True, read_only=True)
    
    # Write-only fields for updates
    thematic_area_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = ProposalTracker
        fields = [
            'id', 'proposal', 'review_stage', 
            'thematic_area', 'thematic_area_id', 'priority_level',
            'implementation_status', 'assigned_reviewers', 'start_date',
            'completion_date', 'progress', 'notes', 'created_at',
            'updated_at', 'comments'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def update(self, instance, validated_data):
        thematic_area_id = validated_data.pop('thematic_area_id', None)
        
        if thematic_area_id:
            try:
                thematic_area = ThematicArea.objects.get(id=thematic_area_id)
                validated_data['thematic_area'] = thematic_area
            except ThematicArea.DoesNotExist:
                raise serializers.ValidationError("Thematic area not found")
        
        return super().update(instance, validated_data)
    
    
    
    
    # tasks



class DecisionRationaleSerializer(serializers.ModelSerializer):
    decided_by = serializers.StringRelatedField(read_only=True)
    decided_by_id = serializers.IntegerField(source='decided_by.id', read_only=True)
    tracker_id = serializers.UUIDField(write_only=True)  # Changed from IntegerField to UUIDField
    proposal_reference = serializers.CharField(source='tracker.proposal.reference_number', read_only=True)
    intervention_name = serializers.CharField(source='tracker.proposal.intervention_name', read_only=True)
    
    class Meta:
        model = DecisionRationale
        fields = [
            'id',
            'tracker',
            'tracker_id',
            'decision',
            'detailed_rationale',
            'decided_by',
            'decided_by_id',
            'approval_conditions',
            'decided_at',
            'proposal_reference',
            'intervention_name'
        ]
        read_only_fields = ['id', 'decided_at', 'decided_by', 'tracker']
    
    def validate_tracker_id(self, value):
        """Validate that the tracker exists and doesn't already have a decision"""
    
        # Check if tracker exists
        try:
            tracker = ProposalTracker.objects.get(id=value)
        except ProposalTracker.DoesNotExist:
            raise serializers.ValidationError("Proposal tracker not found")
        
        # Check if decision already exists for this tracker (OneToOne constraint)
        if hasattr(tracker, 'decision_rationale'):
            raise serializers.ValidationError(
                "A decision has already been made for this tracker. "
                "Please update the existing decision instead."
            )
        
        return value
    
    def validate_decision(self, value):
        """Validate decision choices"""
        valid_choices = ['approved', 'rejected', 'not_sure']
        if value not in valid_choices:
            raise serializers.ValidationError(
                f"Invalid decision. Must be one of: {', '.join(valid_choices)}"
            )
        return value
    
    def create(self, validated_data):
        tracker_id = validated_data.pop('tracker_id')
        tracker = ProposalTracker.objects.get(id=tracker_id)
        
        # Set the decided_by to the current user
        validated_data['decided_by'] = self.context['request'].user
        validated_data['tracker'] = tracker
        
        # Update tracker review_stage based on decision
        if validated_data['decision'] == 'approved':
            tracker.review_stage = 'approved'
        elif validated_data['decision'] == 'rejected':
            tracker.review_stage = 'rejected'
        elif validated_data['decision'] == 'not_sure':
            tracker.review_stage = 'needs_revision'
        
        tracker.save()
        
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        """Update existing decision"""
        # Don't allow changing the tracker
        validated_data.pop('tracker_id', None)
        
        # Update tracker review_stage if decision changes
        if 'decision' in validated_data:
            tracker = instance.tracker
            if validated_data['decision'] == 'approved':
                tracker.review_stage = 'approved'
            elif validated_data['decision'] == 'rejected':
                tracker.review_stage = 'rejected'
            elif validated_data['decision'] == 'not_sure':
                tracker.review_stage = 'needs_revision'
            tracker.save()
        
        return super().update(instance, validated_data)

class TaskAssignmentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    assigned_by = UserSerializer(read_only=True)
    
    class Meta:
        model = TaskAssignment
        fields = ['user', 'assigned_by', 'assigned_at', 'notes']


class TaskSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    assignments = TaskAssignmentSerializer(many=True, read_only=True)
    assigned_user_ids = serializers.ListField(
        child=serializers.IntegerField(), 
        write_only=True, 
        required=False,
        help_text="List of user IDs to assign this task to"
    )
    is_overdue = serializers.ReadOnlyField()
    is_completed = serializers.ReadOnlyField()
    
    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'notes', 'status', 'priority',
            'due_date', 'completed_at', 'progress', 'position_x', 'position_y',
            'created_at', 'updated_at', 'created_by', 'assignments', 'assigned_users',
            'assigned_user_ids', 'is_overdue', 'is_completed'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'completed_at']

    def create(self, validated_data):
        assigned_user_ids = validated_data.pop('assigned_user_ids', [])
        validated_data['created_by'] = self.context['request'].user
        
        task = Task.objects.create(**validated_data)
        
        # Assign task to users if provided
        if assigned_user_ids:
            self._assign_users_to_task(task, assigned_user_ids)
        
        return task

    def update(self, instance, validated_data):
        assigned_user_ids = validated_data.pop('assigned_user_ids', None)
        
        # Update task fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Handle completion
        if validated_data.get('status') == TaskStatus.COMPLETED and not instance.completed_at:
            instance.completed_at = timezone.now()
        elif validated_data.get('status') != TaskStatus.COMPLETED:
            instance.completed_at = None
            
        instance.save()
        
        # Update assignments if provided
        if assigned_user_ids is not None:
            # Remove existing assignments
            instance.assignments.all().delete()
            # Add new assignments
            self._assign_users_to_task(instance, assigned_user_ids)
        
        return instance

    def _assign_users_to_task(self, task, user_ids):
        """Helper method to assign users to a task"""
        request_user = self.context['request'].user
        
        for user_id in user_ids:
            try:
                user = CustomUser.objects.get(id=user_id, status='active')
                TaskAssignment.objects.get_or_create(
                    task=task,
                    user=user,
                    defaults={'assigned_by': request_user}
                )
            except CustomUser.DoesNotExist:
                continue  # Skip invalid use
            
            
            
            
# class ChannelMembershipSerializer(serializers.ModelSerializer):
#     user = UserSerializer(read_only=True)
#     user_id = serializers.PrimaryKeyRelatedField(
#         queryset=User.objects.all(), 
#         source='user', 
#         write_only=True
#     )

#     class Meta:
#         model = ChannelMembership
#         fields = '__all__'

#     def validate(self, attrs):
#         channel = attrs.get('channel')
#         user = attrs.get('user')
#         role = attrs.get('role')

#         # Prevent duplicate memberships
#         if ChannelMembership.objects.filter(channel=channel, user=user).exists():
#             raise serializers.ValidationError({
#                 'user': 'This user is already a member of the channel.'
#             })

#         # Ensure only valid roles are assigned
#         if role not in dict(ChannelMembership.ROLE_CHOICES).keys():
#             raise serializers.ValidationError({
#                 'role': 'Invalid role specified.'
#             })

#         return attrs

# class MessageSerializer(serializers.ModelSerializer):
#     user = UserSerializer(read_only=True)
#     user_id = serializers.PrimaryKeyRelatedField(
#         queryset=User.objects.all(), 
#         source='user', 
#         write_only=True
#     )

#     class Meta:
#         model = Message
#         fields = '__all__'

#     def validate(self, attrs):
#         channel = attrs.get('channel')
#         user = attrs.get('user')

#         # Ensure user is a member of the channel
#         if not ChannelMembership.objects.filter(channel=channel, user=user).exists():
#             raise serializers.ValidationError({
#                 'user': 'User must be a member of the channel to post messages.'
#             })

#         return attrs

# class ChannelSerializer(serializers.ModelSerializer):
#     created_by = UserSerializer(read_only=True)
#     members = UserSerializer(many=True, read_only=True, source='members.all')
#     memberships = ChannelMembershipSerializer(many=True, read_only=True)
#     messages = MessageSerializer(many=True, read_only=True)

#     class Meta:
#         model = Channel
#         fields = ['id', 'name', 'description', 'is_private', 'created_at', 
#                  'updated_at', 'created_by', 'members', 'memberships', 'messages']
      

#     def validate(self, attrs):
#         name = attrs.get('name')
        
#         if Channel.objects.filter(name__iexact=name).exists():
#             raise serializers.ValidationError({
#                 'name': 'A channel with this name already exists.'
#             })

#         return attrs



class ChannelMembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), 
        source='user', 
        write_only=True
    )

    class Meta:
        model = ChannelMembership
        fields = '__all__'

    def validate(self, attrs):
        channel = attrs.get('channel')
        user = attrs.get('user')
        role = attrs.get('role')

        # Prevent duplicate memberships
        if ChannelMembership.objects.filter(channel=channel, user=user).exists():
            raise serializers.ValidationError({
                'user': 'This user is already a member of the channel.'
            })

        # Ensure only valid roles are assigned
        if role not in dict(ChannelMembership.ROLE_CHOICES).keys():
            raise serializers.ValidationError({
                'role': 'Invalid role specified.'
            })

        return attrs


class MessageSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), 
        source='user', 
        write_only=True
    )
    
    # Thread support
    parent_message_id = serializers.PrimaryKeyRelatedField(
        queryset=Message.objects.all(),
        source='parent_message',
        write_only=True,
        required=False,
        allow_null=True
    )
    parent_message = serializers.SerializerMethodField(read_only=True)
    reply_count = serializers.ReadOnlyField()
    is_thread_reply = serializers.ReadOnlyField()

    class Meta:
        model = Message
        fields = ['id', 'channel', 'user', 'user_id', 'content', 'parent_message_id', 
                 'parent_message', 'reply_count', 'is_thread_reply', 'created_at', 'updated_at']

    def get_parent_message(self, obj):
        """Return basic info about the parent message if it exists"""
        if obj.parent_message:
            return {
                'id': obj.parent_message.id,
                'content': obj.parent_message.content[:100] + ('...' if len(obj.parent_message.content) > 100 else ''),
                'user': obj.parent_message.user.username,
                'created_at': obj.parent_message.created_at
            }
        return None

    def validate(self, attrs):
        channel = attrs.get('channel')
        user = attrs.get('user')
        parent_message = attrs.get('parent_message')

        # Ensure user is a member of the channel
        if not ChannelMembership.objects.filter(channel=channel, user=user).exists():
            raise serializers.ValidationError({
                'user': 'User must be a member of the channel to post messages.'
            })

        # If replying to a message, ensure parent message is in the same channel
        if parent_message and parent_message.channel != channel:
            raise serializers.ValidationError({
                'parent_message_id': 'Parent message must be in the same channel.'
            })

        return attrs


# Thread-specific serializer for displaying thread replies
class ThreadReplySerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Message
        fields = ['id', 'user', 'content', 'created_at', 'updated_at']


class ChannelSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    members = UserSerializer(many=True, read_only=True, source='members.all')
    memberships = ChannelMembershipSerializer(many=True, read_only=True)
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Channel
        fields = ['id', 'name', 'description', 'is_private', 'created_at', 
                 'updated_at', 'created_by', 'members', 'memberships', 'messages']
      
    def validate(self, attrs):
        name = attrs.get('name')
        
        if Channel.objects.filter(name__iexact=name).exists():
            raise serializers.ValidationError({
                'name': 'A channel with this name already exists.'
            })

        return attrs


#

#

class RecordSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = Record
        fields = '__all__'
        read_only_fields = ('id', 'created_by','created_by_name', 'created_at', 'updated_at')

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)



class ResourceSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = Resource
        fields = ('id', 'title', 'type', 'description', 'documents', 'images', 'link', 
                 'is_public', 'complainant_name', 'complainant_email', 'reference_number',
                 'tags', 'resolution_notes', 'created_by', 'created_by_name', 'created_at')
        read_only_fields = ('id', 'reference_number', 'created_at', 'created_by_name')

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class AnnouncementSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    is_expired = serializers.ReadOnlyField()
    
    class Meta:
        model = Announcement
        fields = (
            'id', 'title', 'content', 'type', 'priority', 'documents', 'images', 
            'link', 'is_public', 'is_pinned', 'expires_at', 'reference_number', 
            'tags', 'created_by', 'created_by_name', 'created_at', 'updated_at', 
            'is_expired'
        )
        read_only_fields = ('id', 'reference_number', 'created_at', 'updated_at', 'created_by_name', 'is_expired')

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class EventSerializer(serializers.ModelSerializer):
    is_upcoming = serializers.BooleanField(read_only=True)
    is_past = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Event
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']
        


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = ['id', 'subject', 'message', 'status', 'created_at', 'ip_address', 'user_agent', 'reference_number']
        read_only_fields = ['id', 'status', 'created_at', 'ip_address', 'user_agent', 'reference_number']







class PollOptionSerializer(serializers.ModelSerializer):
    vote_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = PollOption
        fields = ['id', 'text', 'vote_count', 'created_at']
        read_only_fields = ['id', 'created_at']


class PollCommentSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    
    class Meta:
        model = PollComment
        fields = ['id', 'user', 'content', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_user(self, obj):
        return {
            'id': str(obj.user.id),
            'username': obj.user.username
        }


class PollSerializer(serializers.ModelSerializer):
    options = PollOptionSerializer(many=True, required=False)
    created_by_username = serializers.CharField(
        source='created_by.username', 
        read_only=True
    )
    is_active = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Poll
        fields = [
            'id', 'question', 'description', 'channel',
            'is_anonymous', 'allow_multiple_choices', 'allow_comments',
            'expires_at', 'created_by', 'created_by_username',
            'created_at', 'updated_at', 'options', 'is_active'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']
        extra_kwargs = {
            'channel': {'required': False, 'allow_null': True}
        }
    
    def create(self, validated_data):
        options_data = validated_data.pop('options', [])
        poll = Poll.objects.create(**validated_data)
        
        for option_data in options_data:
            PollOption.objects.create(poll=poll, **option_data)
        
        return poll
    
    def update(self, instance, validated_data):
        # Don't allow updating options after creation
        validated_data.pop('options', None)
        return super().update(instance, validated_data)




class ImplementationTrackingSerializer(serializers.ModelSerializer):
    created_by_details = UserSerializer(source='created_by', read_only=True)
    last_updated_by_details = UserSerializer(source='last_updated_by', read_only=True)
    proposal_reference = serializers.CharField(source='decision_rationale.tracker.proposal.reference_number', read_only=True)
    intervention_name = serializers.CharField(source='decision_rationale.tracker.proposal.intervention_name', read_only=True)
    county = serializers.CharField(source='decision_rationale.tracker.proposal.county', read_only=True)
    decision_rationale_id = serializers.IntegerField(write_only=True, required=False)
    is_overdue = serializers.BooleanField(read_only=True)
    days_remaining = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = ImplementationTracking
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'last_updated_by', 'decision_rationale']
    
    def create(self, validated_data):
        decision_rationale_id = validated_data.pop('decision_rationale_id', None)
        if decision_rationale_id:
            from .models import DecisionRationale
            validated_data['decision_rationale'] = DecisionRationale.objects.get(id=decision_rationale_id)
        validated_data['created_by'] = self.context['request'].user
        validated_data['last_updated_by'] = self.context['request'].user
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        validated_data.pop('decision_rationale_id', None)
        validated_data['last_updated_by'] = self.context['request'].user
        return super().update(instance, validated_data)





