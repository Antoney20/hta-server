from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
from django.db.models import Q, Prefetch, Count, Avg
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from user_agents import parse
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
import logging

from users.models import CustomUser, UserRole

from .models import (
    Announcement,
    Channel,
    DecisionRationale,
    Feedback,
    ImplementationTracking,
    Message,
    ChannelMembership,
    Poll,
    PollVote,
     PollComment,
    ProposalTracker,
    Record,
    Resource,
    Task,
    TaskAssignment,
    TaskStatus, 
    ThematicArea, 
    ReviewerAssignment, 
    ReviewComment,
    Event,
)
from .serializers import (
    AnnouncementSerializer,
    ChannelSerializer,
    DecisionRationaleSerializer,
    EventSerializer,
    FeedbackSerializer,
    ImplementationTrackingSerializer,
    MessageSerializer,
    ChannelMembershipSerializer,
    PollSerializer,
    PollCommentSerializer,
    ProposalTrackerSerializer,
    RecordSerializer,
    ResourceSerializer,
    TaskSerializer,
    ThematicAreaSerializer,
    ReviewerAssignmentSerializer,
    ReviewCommentSerializer,
    UserSerializer, ThreadReplySerializer
)



def get_client_ip(request):
    """Extract client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def get_client_metadata(request):
    """Extract and parse client metadata from request"""
    user_agent_string = request.META.get('HTTP_USER_AGENT', '')
    user_agent = parse(user_agent_string)
    
    return {
        'ip_address': get_client_ip(request),
        'user_agent': user_agent_string,
        'browser': f"{user_agent.browser.family} {user_agent.browser.version_string}",
        'operating_system': f"{user_agent.os.family} {user_agent.os.version_string}",
        'device_type': 'mobile' if user_agent.is_mobile else 'tablet' if user_agent.is_tablet else 'desktop'
    }


    
logger = logging.getLogger(__name__)
User = get_user_model()

class ThematicAreaViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing thematic areas
    """
    queryset = ThematicArea.objects.all()
    serializer_class = ThematicAreaSerializer

    def get_queryset(self):
        queryset = ThematicArea.objects.all()
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            is_active_bool = is_active.lower() in ['true', '1']
            queryset = queryset.filter(is_active=is_active_bool)
        
        # Search by name
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(description__icontains=search)
            )
        
        return queryset.order_by('name')

    @action(detail=True, methods=['patch'])
    def toggle_active(self, request, pk=None):
        """Toggle active status of a thematic area"""
        thematic_area = self.get_object()
        thematic_area.is_active = not thematic_area.is_active
        thematic_area.save()
        
        serializer = self.get_serializer(thematic_area)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def active_only(self, request):
        """Get only active thematic areas"""
        active_areas = self.get_queryset().filter(is_active=True)
        serializer = self.get_serializer(active_areas, many=True)
        return Response(serializer.data)


class ThematicAreaAssignmentViewSet(viewsets.ViewSet):
    """
    ViewSet for assigning thematic areas to proposal trackers
    """
    # permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['patch'])
    def assign(self, request):
        """
        Assign thematic area to trackers
        Body: {
            "tracker_ids": ["uuid1", "uuid2"],
            "thematic_area_id": 5
        }
        """
        tracker_ids = request.data.get('tracker_ids', [])
        thematic_area_id = request.data.get('thematic_area_id')
        
        if not tracker_ids or not thematic_area_id:
            return Response(
                {'error': 'tracker_ids and thematic_area_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate thematic area
        try:
            thematic_area = ThematicArea.objects.get(id=thematic_area_id, is_active=True)
        except ThematicArea.DoesNotExist:
            return Response(
                {'error': f'Thematic area {thematic_area_id} does not exist or is inactive'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        results = []
        for tracker_id in tracker_ids:
            try:
                tracker = ProposalTracker.objects.get(id=tracker_id)
                tracker.thematic_area = thematic_area
                tracker.save()
                results.append({'tracker_id': tracker_id, 'success': True})
            except ProposalTracker.DoesNotExist:
                results.append({'tracker_id': tracker_id, 'success': False, 'error': 'Tracker not found'})
        
        return Response({'results': results}, status=status.HTTP_200_OK)





class ProposalTrackerViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing proposal trackers
    """
    serializer_class = ProposalTrackerSerializer
    # permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'patch', 'delete']

    def get_queryset(self):
        return ProposalTracker.objects.select_related(
            'proposal', 'thematic_area'
        ).prefetch_related(
            'assigned_reviewers',
            Prefetch('comments', queryset=ReviewComment.objects.select_related('reviewer')),
            'proposal__documents'
        ).all()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    @action(detail=True, methods=['get'])
    def comments(self, request, pk=None):
        """Get all comments for a specific tracker"""
        tracker = self.get_object()
        comments = tracker.comments.select_related('reviewer').all()
        serializer = ReviewCommentSerializer(comments, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'])
    def update_stage(self, request, pk=None):
        """Update review stage of a tracker"""
        tracker = self.get_object()
        new_stage = request.data.get('review_stage')
        valid_stages = [choice[0] for choice in ProposalTracker._meta.get_field('review_stage').choices]
        
        if new_stage not in valid_stages:
            return Response(
                {'error': f'Invalid review stage: {new_stage}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        tracker.review_stage = new_stage
        tracker.save()
        
        serializer = self.get_serializer(tracker)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'])
    def update_progress(self, request, pk=None):
        """Update progress percentage"""
        tracker = self.get_object()
        progress = request.data.get('progress')
        
        try:
            progress_int = int(progress)
            if not (0 <= progress_int <= 100):
                raise ValueError()
        except (ValueError, TypeError):
            return Response(
                {'error': 'Progress must be an integer between 0 and 100'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        tracker.progress = progress_int
        tracker.save()
        
        serializer = self.get_serializer(tracker)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def assignments(self, request, pk=None):
        """Get all reviewer assignments for this tracker"""
        tracker = self.get_object()
        assignments = ReviewerAssignment.objects.filter(tracker=tracker).select_related('reviewer', 'assigned_by')
        serializer = ReviewerAssignmentSerializer(assignments, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_assignments(self, request):
        """Get proposal trackers assigned to the current user"""
        if not request.user.is_authenticated:
            return Response(
                {'error': 'Authentication required'}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Get tracker IDs where the user is assigned as a reviewer
        assigned_tracker_ids = ReviewerAssignment.objects.filter(
            reviewer=request.user
        ).values_list('tracker_id', flat=True)
        
        # Filter trackers by those IDs - USE the base queryset with proper prefetches
        trackers = ProposalTracker.objects.select_related(
            'proposal', 
            'thematic_area'
        ).prefetch_related(
            'assigned_reviewers',
            Prefetch('comments', queryset=ReviewComment.objects.select_related('reviewer')),  # This is the key fix
            'proposal__documents'
        ).filter(
            id__in=assigned_tracker_ids
        ).order_by('-updated_at')
        
        page = self.paginate_queryset(trackers)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(trackers, many=True)
        return Response({
            'count': trackers.count(),
            'results': serializer.data
        })



class ReviewerAssignmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing reviewer assignments
    """
    serializer_class = ReviewerAssignmentSerializer
    # permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ReviewerAssignment.objects.select_related(
            'tracker', 'reviewer', 'assigned_by'
        ).all()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    @action(detail=False, methods=['get'])
    def by_tracker(self, request):
        """Get assignments for a specific tracker"""
        tracker_id = request.query_params.get('tracker_id')
        if not tracker_id:
            return Response(
                {'error': 'tracker_id parameter required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        assignments = self.get_queryset().filter(tracker_id=tracker_id)
        serializer = self.get_serializer(assignments, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'])
    def update_progress(self, request, pk=None):
        """Update assignment progress"""
        assignment = self.get_object()
        progress = request.data.get('progress')
        
        try:
            progress_int = int(progress)
            if not (0 <= progress_int <= 100):
                raise ValueError()
        except (ValueError, TypeError):
            return Response(
                {'error': 'Progress must be between 0 and 100'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        assignment.save()
        
        serializer = self.get_serializer(assignment)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def bulk_assign(self, request):
        """Assign multiple reviewers to a tracker at once"""
        tracker_id = request.data.get('tracker_id')
        reviewer_ids = request.data.get('reviewer_ids', [])
        notes = request.data.get('notes', '')
        
        if not tracker_id:
            return Response(
                {'error': 'tracker_id is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not reviewer_ids:
            return Response(
                {'error': 'reviewer_ids list is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            tracker = ProposalTracker.objects.get(id=tracker_id)
        except ProposalTracker.DoesNotExist:
            return Response(
                {'error': 'Tracker not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        assignments = []
        for reviewer_id in reviewer_ids:
            try:
                reviewer = User.objects.get(id=reviewer_id)
                assignment, created = ReviewerAssignment.objects.get_or_create(
                    tracker=tracker,
                    reviewer=reviewer,
                    defaults={
                        'notes': notes,
                        'assigned_by': request.user
                    }
                )
                assignments.append(assignment)
            except User.DoesNotExist:
                continue
        
        serializer = self.get_serializer(assignments, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    
class ReviewCommentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing review comments
    """
    serializer_class = ReviewCommentSerializer
    # permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ReviewComment.objects.select_related('tracker', 'reviewer').all()


    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def perform_create(self, serializer):
        """Automatically set the reviewer from authenticated user and resolve tracker"""
        tracker_id = serializer.validated_data.get('tracker_id')
        
        try:
            tracker = ProposalTracker.objects.get(id=tracker_id)
        except ProposalTracker.DoesNotExist:
            raise serializers.ValidationError({"tracker_id": ["Tracker not found"]})
        
        # Save with the authenticated user as reviewer
        serializer.save(
            reviewer=self.request.user,
            tracker=tracker
        )

    @action(detail=False, methods=['get'])
    def by_tracker(self, request):
        """Get comments for a specific tracker"""
        tracker_id = request.query_params.get('tracker_id')
        if not tracker_id:
            return Response(
                {'error': 'tracker_id parameter required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        comments = self.get_queryset().filter(tracker_id=tracker_id)
        serializer = self.get_serializer(comments, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def unresolved(self, request):
        """Get all unresolved comments"""
        unresolved_comments = self.get_queryset().filter(is_resolved=False)
        serializer = self.get_serializer(unresolved_comments, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_type(self, request):
        """Get comments by type"""
        comment_type = request.query_params.get('comment_type')
        if not comment_type:
            return Response(
                {'error': 'comment_type parameter required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        comments = self.get_queryset().filter(comment_type=comment_type)
        serializer = self.get_serializer(comments, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'])
    def toggle_resolved(self, request, pk=None):
        """Toggle resolved status of a comment"""
        comment = self.get_object()
        comment.is_resolved = not comment.is_resolved
        comment.save()
        
        serializer = self.get_serializer(comment)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'])
    def mark_resolved(self, request, pk=None):
        """Mark comment as resolved"""
        comment = self.get_object()
        comment.is_resolved = True
        comment.save()
        
        serializer = self.get_serializer(comment)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'])
    def mark_unresolved(self, request, pk=None):
        """Mark comment as unresolved"""
        comment = self.get_object()
        comment.is_resolved = False
        comment.save()
        
        serializer = self.get_serializer(comment)
        return Response(serializer.data)





class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for getting users (for reviewer assignments)
    """
    queryset = User.objects.filter(is_active=True)
    serializer_class = UserSerializer
    # permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = User.objects.filter(is_active=True)
        
        # Search by username, email, first_name, last_name
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        
        # Filter by group
        group = self.request.query_params.get('group')
        if group:
            queryset = queryset.filter(groups__name=group)
        
        return queryset.order_by('username')

    @action(detail=False, methods=['get'])
    def reviewers(self, request):
        """Get users who can be assigned as reviewers"""
        # Filter by group if you have a specific reviewers group
        reviewers = self.get_queryset()
        
        # You can add group-based filtering here if needed
        # reviewers = reviewers.filter(groups__name='Reviewers')
        
        serializer = self.get_serializer(reviewers, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_group(self, request):
        """Get users by group name"""
        group_name = request.query_params.get('group_name')
        if not group_name:
            return Response(
                {'error': 'group_name parameter required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        users = self.get_queryset().filter(groups__name=group_name)
        serializer = self.get_serializer(users, many=True)
        return Response(serializer.data)
    
    
    
    
    
    
    
#tasks


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return tasks based on user role and filters"""
        user = self.request.user
        
        # Base queryset
        if (user.groups.filter(name__in=['admin', 'manager']).exists() or 
            user.is_staff or user.is_superuser):
            # Admins and managers can see all tasks
            queryset = Task.objects.all()
        else:
            # Regular users see only their tasks (assigned to them or created by them)
            queryset = Task.objects.filter(
                Q(assigned_users=user) | Q(created_by=user)
            ).distinct()
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by priority if provided
        priority_filter = self.request.query_params.get('priority', None)
        if priority_filter:
            queryset = queryset.filter(priority=priority_filter)
        
        # Filter by due date
        due_filter = self.request.query_params.get('due', None)
        if due_filter:
            today = timezone.now().date()
            if due_filter == 'today':
                queryset = queryset.filter(due_date=today)
            elif due_filter == 'overdue':
                queryset = queryset.filter(
                    due_date__lt=today, 
                    status__in=[TaskStatus.NEW, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW]
                )
            elif due_filter == 'upcoming':
                queryset = queryset.filter(due_date__gt=today)
            elif due_filter == 'no_date':
                queryset = queryset.filter(due_date__isnull=True)
        
        return queryset.select_related('created_by').prefetch_related(
            'assignments__user', 'assignments__assigned_by'
        )

    def perform_create(self, serializer):
        """Ensure created_by is set to the current user"""
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Mark a task as completed"""
        task = self.get_object()
        
        # Check if user can complete this task
        if not (task.created_by == request.user or 
                task.assigned_users.filter(id=request.user.id).exists() or
                request.user.groups.filter(name__in=['admin', 'manager']).exists() or 
                request.user.is_staff or request.user.is_superuser):
            return Response(
                {'error': 'You do not have permission to complete this task'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        task.status = TaskStatus.COMPLETED
        task.completed_at = timezone.now()
        task.save()
        
        serializer = self.get_serializer(task)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        """Reopen a completed task"""
        task = self.get_object()
        
        # Check if user can reopen this task
        if not (task.created_by == request.user or 
                task.assigned_users.filter(id=request.user.id).exists() or
                request.user.groups.filter(name__in=['admin', 'manager']).exists() or 
                request.user.is_staff or request.user.is_superuser):
            return Response(
                {'error': 'You do not have permission to reopen this task'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        task.status = TaskStatus.NEW
        task.completed_at = None
        task.save()
        
        serializer = self.get_serializer(task)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_tasks(self, request):
        """Get current user's tasks"""
        tasks = Task.objects.filter(
            Q(assigned_users=request.user) | Q(created_by=request.user)
        ).distinct().select_related('created_by').prefetch_related(
            'assignments__user', 'assignments__assigned_by'
        )
        
        # Apply same filters as get_queryset
        status_filter = request.query_params.get('status', None)
        if status_filter:
            tasks = tasks.filter(status=status_filter)
            
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def completed_tasks(self, request):
        """Get completed tasks"""
        tasks = self.get_queryset().filter(status=TaskStatus.COMPLETED)
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def assign_users(self, request, pk=None):
        """Assign multiple users to a task (users with manager/admin groups only)"""
        # Check if user has permission to assign tasks (using groups)
        if not (request.user.groups.filter(name__in=['admin', 'manager']).exists() or 
                request.user.is_staff or request.user.is_superuser):
            return Response(
                {'error': 'Only users with admin or manager role can assign tasks to users'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        task = self.get_object()
        user_ids = request.data.get('user_ids', [])
        
        if not user_ids:
            return Response(
                {'error': 'user_ids list is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Clear existing assignments
        task.assignments.all().delete()
        
        assigned_users = []
        for user_id in user_ids:
            try:
                user = CustomUser.objects.get(id=user_id, status='active')
                TaskAssignment.objects.create(
                    task=task,
                    user=user,
                    assigned_by=request.user
                )
                assigned_users.append(user.username)
            except CustomUser.DoesNotExist:
                continue
        
        serializer = self.get_serializer(task)
        return Response({
            'task': serializer.data,
            'assigned_to': assigned_users,
            'message': f'Task assigned to {len(assigned_users)} users'
        })

    @action(detail=True, methods=['patch'])
    def update_progress(self, request, pk=None):
        """Update task progress"""
        task = self.get_object()

        if not (task.created_by == request.user or 
                task.assigned_users.filter(id=request.user.id).exists() or
                request.user.groups.filter(name__in=['admin', 'manager']).exists() or 
                request.user.is_staff or request.user.is_superuser):
            return Response(
                {'error': 'You do not have permission to update this task'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        progress = request.data.get('progress')
        if progress is None or not (0 <= progress <= 100):
            return Response(
                {'error': 'Progress must be between 0 and 100'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        task.progress = progress
        
        # Auto-complete task if progress reaches 100%
        if progress == 100:
            task.status = TaskStatus.COMPLETED
            task.completed_at = timezone.now()
        
        task.save()
        
        serializer = self.get_serializer(task)
        return Response(serializer.data)




class ForumViewSet(viewsets.ModelViewSet):
    queryset = Channel.objects.all()
    serializer_class = ChannelSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['is_private', 'name']

    def get_queryset(self):
        """
        Return channels the user has access to:
        - Public channels
        - Private channels where the user is a member
        """
        user = self.request.user
        return Channel.objects.filter(
            Q(is_private=False) | 
            Q(is_private=True, memberships__user=user)
        ).distinct()

    def perform_create(self, serializer):
        """
        Automatically set the creator and add them as owner when creating a channel.
        """
        channel = serializer.save(created_by=self.request.user)
        ChannelMembership.objects.create(
            channel=channel,
            user=self.request.user,
            role='owner'
        )

    def perform_update(self, serializer):
        """
        Ensure only owners can update channel details.
        """
        channel = self.get_object()
        if not ChannelMembership.objects.filter(
            channel=channel, 
            user=self.request.user, 
            role='owner'
        ).exists():
            raise serializers.ValidationError({
                'detail': 'Only channel owners can update channel details.'
            })
        serializer.save()

    def perform_destroy(self, instance):
        """
        Ensure only owners can delete a channel.
        """
        if not ChannelMembership.objects.filter(
            channel=instance, 
            user=self.request.user, 
            role='owner'
        ).exists():
            raise serializers.ValidationError({
                'detail': 'Only channel owners can delete the channel.'
            })
        instance.delete()

    @action(detail=True, methods=['get', 'post'], url_path='members')
    def manage_members(self, request, pk=None):
        """
        GET: List all members of the channel.
        POST: Add a new member to the channel (owners/moderators only).
        """
        channel = self.get_object()

        if request.method == 'POST' and not ChannelMembership.objects.filter(
            channel=channel, 
            user=request.user, 
            role__in=['owner', 'moderator']
        ).exists():
            return Response(
                {'detail': 'Only owners or moderators can add members.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if request.method == 'GET':
            memberships = ChannelMembership.objects.filter(channel=channel)
            serializer = ChannelMembershipSerializer(memberships, many=True)
            return Response(serializer.data)

        elif request.method == 'POST':
            data = request.data.copy()
            data['channel'] = channel.id
            
            serializer = ChannelMembershipSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get', 'post'], url_path='messages')
    def manage_messages(self, request, pk=None):
        """
        GET: List all messages in the channel (only main messages, no replies).
        POST: Post a new message to the channel.
        """
        channel = self.get_object()

        if not ChannelMembership.objects.filter(channel=channel, user=request.user).exists():
            return Response(
                {'detail': 'You must be a member of the channel to view or post messages.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if request.method == 'GET':
            messages = Message.objects.filter(
                channel=channel, 
                parent_message=None  # Only main messages
            ).order_by('-created_at')
            
            page = self.paginate_queryset(messages)
            if page is not None:
                serializer = MessageSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            serializer = MessageSerializer(messages, many=True)
            return Response(serializer.data)

        elif request.method == 'POST':
            data = request.data.copy()
            data['channel'] = channel.id
            data['user_id'] = request.user.id
            
            serializer = MessageSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get', 'post'], url_path='messages/(?P<message_id>[^/.]+)/replies')
    def manage_thread_replies(self, request, pk=None, message_id=None):
        """
        GET: List all replies to a specific message.
        POST: Reply to a specific message.
        """
        channel = self.get_object()
        
        if not ChannelMembership.objects.filter(channel=channel, user=request.user).exists():
            return Response(
                {'detail': 'You must be a member of the channel to view or post replies.'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            parent_message = Message.objects.get(id=message_id, channel=channel)
        except Message.DoesNotExist:
            return Response(
                {'detail': 'Parent message not found in this channel.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if request.method == 'GET':
            # Get all replies to this message
            replies = Message.objects.filter(
                parent_message=parent_message
            ).order_by('created_at')
            
            serializer = ThreadReplySerializer(replies, many=True)
            return Response(serializer.data)

        elif request.method == 'POST':
            data = request.data.copy()
            data['channel'] = channel.id
            data['user_id'] = request.user.id
            data['parent_message_id'] = parent_message.id
            
            serializer = MessageSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
# 







class RecordViewSet(viewsets.ModelViewSet):
    queryset = Record.objects.all()
    serializer_class = RecordSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = Record.objects.all()
        search = self.request.query_params.get('search')
        
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | 
                Q(description__icontains=search)
            )
            
        return queryset
    
    

class ResourceViewSet(viewsets.ModelViewSet):
    queryset = Resource.objects.all()
    serializer_class = ResourceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = Resource.objects.all()
    
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_public=True)
        
        # Search and filter parameters
        search = self.request.query_params.get('search')
        resource_type = self.request.query_params.get('type')
        is_public = self.request.query_params.get('is_public')
        
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | 
                Q(description__icontains=search) |
                Q(type__icontains=search) |
                Q(reference_number__icontains=search)
            )
            
        if resource_type:
            queryset = queryset.filter(type__icontains=resource_type)
            
        if is_public and self.request.user.is_staff:
            queryset = queryset.filter(is_public=is_public.lower() == 'true')
            
        return queryset
    
    @action(detail=False, methods=['get'])
    def public(self, request):
        """Get only public resources"""
        public_resources = Resource.objects.filter(is_public=True)
        serializer = self.get_serializer(public_resources, many=True)
        return Response(serializer.data)
    
    
    

class AnnouncementViewSet(viewsets.ModelViewSet):
    queryset = Announcement.objects.all()
    serializer_class = AnnouncementSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = Announcement.objects.all()
    
        # Non-staff users only see public announcements
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_public=True)
        
        # Search and filter parameters
        search = self.request.query_params.get('search')
        announcement_type = self.request.query_params.get('type')
        priority = self.request.query_params.get('priority')
        is_public = self.request.query_params.get('is_public')
        is_pinned = self.request.query_params.get('is_pinned')
        include_expired = self.request.query_params.get('include_expired', 'false')
        
        # Exclude expired announcements by default
        if include_expired.lower() != 'true':
            now = timezone.now()
            queryset = queryset.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | 
                Q(content__icontains=search) |
                Q(type__icontains=search) |
                Q(priority__icontains=search) |
                Q(reference_number__icontains=search) |
                Q(tags__icontains=search)
            )
            
        if announcement_type:
            queryset = queryset.filter(type__icontains=announcement_type)
            
        if priority:
            queryset = queryset.filter(priority__icontains=priority)
            
        if is_public and self.request.user.is_staff:
            queryset = queryset.filter(is_public=is_public.lower() == 'true')
            
        if is_pinned:
            queryset = queryset.filter(is_pinned=is_pinned.lower() == 'true')
            
        return queryset
    
    @action(detail=False, methods=['get'])
    def public(self, request):
        """Get only public announcements (excluding expired)"""
        now = timezone.now()
        public_announcements = Announcement.objects.filter(
            is_public=True
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        )
        serializer = self.get_serializer(public_announcements, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def pinned(self, request):
        """Get pinned announcements"""
        now = timezone.now()
        pinned_announcements = Announcement.objects.filter(
            is_pinned=True,
            is_public=True if not request.user.is_staff else True
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        )
        serializer = self.get_serializer(pinned_announcements, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def toggle_pin(self, request, pk=None):
        """Toggle pin status of an announcement (staff only)"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Permission denied'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        announcement = self.get_object()
        announcement.is_pinned = not announcement.is_pinned
        announcement.save()
        
        serializer = self.get_serializer(announcement)
        return Response(serializer.data)
    
    
    
class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = Event.objects.all()
        
        # Filter by event type if provided
        event_type = self.request.query_params.get('event_type')
        if event_type:
            queryset = queryset.filter(event_type__icontains=event_type)
        
        # Search functionality
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | 
                Q(description__icontains=search)
            )
        
        return queryset
    
    def perform_create(self, serializer):
        """Set created_by to current user"""
        serializer.save(created_by=self.request.user)
    
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get all upcoming events"""
        now = timezone.now()
        upcoming_events = Event.objects.filter(start_date__gt=now)
        serializer = self.get_serializer(upcoming_events, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def past(self, request):
        """Get all past events"""
        now = timezone.now()
        past_events = Event.objects.filter(start_date__lt=now)
        serializer = self.get_serializer(past_events, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def training(self, request):
        """Get all training events"""
        training_events = Event.objects.filter(event_type__icontains='training')
        serializer = self.get_serializer(training_events, many=True)
        return Response(serializer.data)
    
    

class FeedbackViewPermission:
    """
    Custom permission class for feedback management
    - Anyone can submit (create)
    - Authenticated users can view (list, retrieve)
    - Admins and Secretariate can update status, respond, or delete
    """
    def has_permission(self, request, view):
        # Allow anyone to submit feedback
        if view.action == 'create':
            return True

        # Allow authenticated users to view feedback
        if view.action in ['list', 'retrieve']:
            return request.user and request.user.is_authenticated
        if view.action in ['update', 'partial_update', 'destroy', 'respond', 'update_status']:
            return request.user and request.user.is_authenticated and (
                request.user.has_role(UserRole.ADMIN) or request.user.has_role(UserRole.SECRETARIATE)
            )

        return False

class FeedbackViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing feedback submissions
    
    POST /feedback/              - Submit feedback (public, no auth required)
    GET /feedback/               - List all feedback (authenticated users)
    GET /feedback/{id}/          - Get specific feedback (authenticated users)
    POST /feedback/{id}/respond/ - Respond to feedback (admin only)
    PATCH /feedback/{id}/        - Update status (admin only)
    DELETE /feedback/{id}/       - Delete feedback (admin only)
    """
    serializer_class = FeedbackSerializer
    queryset = Feedback.objects.all()
    permission_classes = [FeedbackViewPermission]
    
    def get_permissions(self):
        """Dynamic permissions based on action"""
        if self.action == 'create':
            return [AllowAny()]
        elif self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        else:
            return [IsAdminUser()]

    def create(self, request, *args, **kwargs):
        """Submit feedback - available to anyone"""
        try:
            serializer = self.get_serializer(data=request.data)
            if not serializer.is_valid():
                logger.error(f"Serializer errors: {serializer.errors}")
                return Response({
                    'success': False,
                    'message': 'Invalid data',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            metadata = get_client_metadata(request)
            feedback = serializer.save(**metadata)
            
            logger.info(f"Feedback submitted: {feedback.id} from IP: {metadata.get('ip_address')}")
            
            return Response({
                'success': True,
                'message': 'Thank you for your feedback! We appreciate your input.',
                'feedback_id': str(feedback.id)
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Feedback submission failed: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'message': f'Failed to submit feedback: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def list(self, request, *args, **kwargs):
        """List all feedback - authenticated users can view"""
        queryset = self.get_queryset()
        
        # Filter by status if provided
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Search by subject or message
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(subject__icontains=search) | 
                models.Q(message__icontains=search) |
                models.Q(reference_number__icontains=search)
            )
        
        # Order by most recent first
        queryset = queryset.order_by('-created_at')
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    def retrieve(self, request, *args, **kwargs):
        """Get specific feedback - authenticated users can view"""
        return super().retrieve(request, *args, **kwargs)
    
    def update(self, request, *args, **kwargs):
        """Update feedback - admin only"""
        if not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'You do not have permission to update feedback'
            }, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)
    
    def partial_update(self, request, *args, **kwargs):
        """Partially update feedback - admin only"""
        if not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'You do not have permission to update feedback'
            }, status=status.HTTP_403_FORBIDDEN)
        return super().partial_update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Delete feedback - admin only"""
        if not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'You do not have permission to delete feedback'
            }, status=status.HTTP_403_FORBIDDEN)
        
        feedback = self.get_object()
        logger.info(f"Feedback {feedback.id} deleted by admin {request.user.username}")
        return super().destroy(request, *args, **kwargs)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def respond(self, request, pk=None):
        """Admin response to feedback - admin only"""
        feedback = self.get_object()
        admin_response = request.data.get('admin_response')
        
        if not admin_response or not admin_response.strip():
            return Response({
                'success': False,
                'message': 'Response text is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        feedback.admin_response = admin_response
        feedback.responded_at = timezone.now()
        feedback.responded_by = request.user
        feedback.status = 'resolved'
        feedback.save()

        return Response({
            'success': True,
            'message': 'Response added successfully',
            'feedback': self.get_serializer(feedback).data
        })
    
    @action(detail=True, methods=['patch'], permission_classes=[IsAdminUser])
    def update_status(self, request, pk=None):
        """Update feedback status - admin only"""
        feedback = self.get_object()
        new_status = request.data.get('status')
        
        if new_status not in dict(Feedback.STATUS_CHOICES):
            return Response({
                'success': False,
                'message': 'Invalid status'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        feedback.status = new_status
        feedback.save()
        

        return Response({
            'success': True,
            'message': 'Status updated successfully',
            'feedback': self.get_serializer(feedback).data
        })




class PollViewSet(viewsets.ModelViewSet):
    queryset = Poll.objects.all()
    serializer_class = PollSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return polls from channels user has access to or standalone polls"""
        user = self.request.user
        return Poll.objects.filter(
            Q(channel__isnull=True) |  # Standalone polls
            Q(channel__is_private=False) | 
            Q(channel__is_private=True, channel__memberships__user=user)
        ).distinct().select_related('channel', 'created_by').prefetch_related('options')

    def retrieve(self, request, *args, **kwargs):
        """Get single poll with is_owner field"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data
        data['is_owner'] = instance.created_by == request.user
        return Response(data)

    def perform_create(self, serializer):
        """Create poll and optionally link to channel"""
        channel = serializer.validated_data.get('channel')
        if channel:
            if not ChannelMembership.objects.filter(channel=channel, user=self.request.user).exists():
                raise serializers.ValidationError({'detail': 'Must be a channel member to create polls.'})
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'], url_path='vote')
    def vote(self, request, pk=None):
        """Vote on a poll option"""
        poll = self.get_object()
        option_id = request.data.get('option_id')
        
        if not poll.is_active:
            return Response({'detail': 'Poll has expired.'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            option = poll.options.get(id=option_id)
        except PollOption.DoesNotExist:
            return Response({'detail': 'Invalid option.'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check if already voted
        existing_votes = PollVote.objects.filter(poll=poll, user=request.user)
        
        if not poll.allow_multiple_choices and existing_votes.exists():
            return Response({'detail': 'Already voted. Multiple choices not allowed.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        # Create vote
        vote, created = PollVote.objects.get_or_create(
            poll=poll,
            option=option,
            user=None if poll.is_anonymous else request.user,
            defaults={'user': None if poll.is_anonymous else request.user}
        )
        
        if not created:
            return Response({'detail': 'Already voted for this option.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        return Response({'detail': 'Vote recorded successfully.'}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='results')
    def results(self, request, pk=None):
        """Get poll results with vote counts"""
        poll = self.get_object()
        
        options_data = poll.options.annotate(
            vote_count=Count('votes')
        ).values('id', 'text', 'vote_count')
        
        total_votes = poll.votes.count()
        user_voted = poll.votes.filter(user=request.user).exists()
        
        return Response({
            'poll_id': poll.id,
            'question': poll.question,
            'total_votes': total_votes,
            'user_has_voted': user_voted,
            'is_active': poll.is_active,
            'options': list(options_data)
        })

    @action(detail=True, methods=['get'], url_path='analytics')
    def analytics(self, request, pk=None):
        """Owner-only: Detailed analytics with voter information for CSV export"""
        poll = self.get_object()
        
        if poll.created_by != request.user:
            return Response({'detail': 'Only poll creator can view analytics.'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        if poll.is_anonymous:
            return Response({'detail': 'Cannot view voter details for anonymous polls.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        # Get all votes with related data
        votes = PollVote.objects.filter(poll=poll).select_related('user', 'option').order_by('-voted_at')
        
        # Get all comments
        comments = PollComment.objects.filter(poll=poll).select_related('user')
        comments_by_user = {comment.user.username: comment.content for comment in comments}
        
        analytics_data = {
            'total_votes': votes.count(),
            'unique_voters': votes.values('user').distinct().count(),
            'votes_by_option': {},
            'detailed_votes': []  # Structured for easy table/CSV export
        }
        
        # Build detailed vote data
        for vote in votes:
            option_text = vote.option.text
            username = vote.user.username if vote.user else 'Anonymous'
            
            # Group by option
            if option_text not in analytics_data['votes_by_option']:
                analytics_data['votes_by_option'][option_text] = []
            
            analytics_data['votes_by_option'][option_text].append({
                'username': username,
                'voted_at': vote.voted_at
            })
            
            # Add to detailed votes for table/CSV
            analytics_data['detailed_votes'].append({
                'timestamp': vote.voted_at,
                'username': username,
                'vote': option_text,
                'comment': comments_by_user.get(username, '')
            })
        
        return Response(analytics_data)

    @action(detail=True, methods=['get'], url_path='analytics/export')
    def export_analytics(self, request, pk=None):
        """Owner-only: Export analytics as CSV"""
        import csv
        from django.http import HttpResponse
        
        poll = self.get_object()
        
        if poll.created_by != request.user:
            return Response({'detail': 'Only poll creator can export analytics.'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        if poll.is_anonymous:
            return Response({'detail': 'Cannot export voter details for anonymous polls.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="poll_{poll.id}_analytics.csv"'
        
        writer = csv.writer(response)
        
        # Header information
        writer.writerow(['Poll Analytics Report'])
        writer.writerow(['Poll Question', poll.question])
        writer.writerow(['Created By', poll.created_by.username])
        writer.writerow(['Created At', poll.created_at])
        writer.writerow(['Total Votes', poll.votes.count()])
        writer.writerow(['Unique Voters', poll.votes.values('user').distinct().count()])
        writer.writerow([])
        
        # Data table
        writer.writerow(['Timestamp', 'Username', 'Vote', 'Comment'])
        
        # Get votes and comments
        votes = PollVote.objects.filter(poll=poll).select_related('user', 'option').order_by('-voted_at')
        comments = PollComment.objects.filter(poll=poll).select_related('user')
        comments_by_user = {comment.user.username: comment.content for comment in comments}
        
        for vote in votes:
            username = vote.user.username if vote.user else 'Anonymous'
            writer.writerow([
                vote.voted_at.strftime('%Y-%m-%d %H:%M:%S'),
                username,
                vote.option.text,
                comments_by_user.get(username, '')
            ])
        
        return response

    @action(detail=True, methods=['get', 'post'], url_path='comments')
    def comments(self, request, pk=None):
        """GET: List comments, POST: Add comment (if enabled)"""
        poll = self.get_object()
        
        if not poll.allow_comments:
            return Response({'detail': 'Comments are disabled for this poll.'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        if request.method == 'GET':
            comments = PollComment.objects.filter(poll=poll).select_related('user')
            serializer = PollCommentSerializer(comments, many=True)
            return Response(serializer.data)
        
        elif request.method == 'POST':
            content = request.data.get('content', '').strip()
            if not content:
                return Response({'detail': 'Comment cannot be empty.'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            comment = PollComment.objects.create(
                poll=poll,
                user=request.user,
                content=content
            )
            
            serializer = PollCommentSerializer(comment)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], url_path='toggle-comments')
    def toggle_comments(self, request, pk=None):
        """Owner-only: Enable/disable comments"""
        poll = self.get_object()
        
        if poll.created_by != request.user:
            return Response({'detail': 'Only poll creator can toggle comments.'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        poll.allow_comments = not poll.allow_comments
        poll.save()
        
        return Response({
            'detail': 'Comments toggled successfully.',
            'allow_comments': poll.allow_comments
        })






class DecisionRationaleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for creating and managing decision rationales
    """
    serializer_class = DecisionRationaleSerializer

    
    def get_queryset(self):
        queryset = DecisionRationale.objects.select_related(
            'tracker__proposal',
            'tracker__thematic_area',
            'decided_by'
        ).all()
        
        # Filter by tracker if provided
        tracker_id = self.request.query_params.get('tracker_id')
        if tracker_id:
            queryset = queryset.filter(tracker_id=tracker_id)
        
        # Filter by decision type
        decision = self.request.query_params.get('decision')
        if decision:
            queryset = queryset.filter(decision=decision)
        
        # Filter by decided_by user
        decided_by = self.request.query_params.get('decided_by')
        if decided_by:
            queryset = queryset.filter(decided_by_id=decided_by)
        
        return queryset.order_by('-decided_at')
    
    def perform_create(self, serializer):
        """Create decision rationale and optionally add a comment"""
        decision_rationale = serializer.save()
        
        # If there's a comment in the request, create a ReviewComment
        comment_content = self.request.data.get('comment_content')
        if comment_content:
            ReviewComment.objects.create(
                tracker=decision_rationale.tracker,
                reviewer=self.request.user,
                content=comment_content,
                comment_type='decision'
            )
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get decision statistics"""
        queryset = self.get_queryset()
        
        stats = {
            'total': queryset.count(),
            'approved': queryset.filter(decision='approved').count(),
            'rejected': queryset.filter(decision='rejected').count(),
            'not_sure': queryset.filter(decision='not_sure').count(),
        }
        
        return Response(stats)
    
    @action(detail=True, methods=['post'])
    def add_comment(self, request, pk=None):
        """Add a comment to a decision"""
        decision = self.get_object()
        content = request.data.get('content')
        
        if not content:
            return Response(
                {'error': 'Comment content is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        comment = ReviewComment.objects.create(
            tracker=decision.tracker,
            reviewer=request.user,
            content=content,
            comment_type='decision'
        )
        
        serializer = ReviewCommentSerializer(comment)
        return Response(serializer.data, status=status.HTTP_201_CREATED)




class ImplementationTrackingViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing implementation tracking
    """
    serializer_class = ImplementationTrackingSerializer
    # permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = ImplementationTracking.objects.select_related(
            'decision_rationale__tracker__proposal',
            'decision_rationale__tracker__thematic_area',
            'decision_rationale__decided_by',
            'created_by',
            'last_updated_by'
        ).all()
        
        # Filter by decision rationale
        decision_rationale_id = self.request.query_params.get('decision_rationale_id')
        if decision_rationale_id:
            queryset = queryset.filter(decision_rationale_id=decision_rationale_id)
        
        # Filter by completion status
        is_completed = self.request.query_params.get('is_completed')
        if is_completed is not None:
            queryset = queryset.filter(is_completed=is_completed.lower() == 'true')
        
        # Filter by county
        county = self.request.query_params.get('county')
        if county:
            queryset = queryset.filter(
                decision_rationale__tracker__proposal__county=county
            )
        
        # Filter by progress range
        min_progress = self.request.query_params.get('min_progress')
        max_progress = self.request.query_params.get('max_progress')
        if min_progress:
            queryset = queryset.filter(progress_percentage__gte=min_progress)
        if max_progress:
            queryset = queryset.filter(progress_percentage__lte=max_progress)
        
        # Filter overdue
        show_overdue = self.request.query_params.get('overdue')
        if show_overdue == 'true':
            from django.utils import timezone
            queryset = [impl for impl in queryset if impl.is_overdue]
        
        return queryset.order_by('-updated_at')
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get implementation statistics"""
        queryset = self.get_queryset()
        
        total = len(queryset) if isinstance(queryset, list) else queryset.count()
        completed = sum(1 for impl in queryset if impl.is_completed) if isinstance(queryset, list) else queryset.filter(is_completed=True).count()
        in_progress = total - completed
        
        if isinstance(queryset, list):
            overdue = sum(1 for impl in queryset if impl.is_overdue and not impl.is_completed)
            avg_progress = sum(impl.progress_percentage for impl in queryset) / total if total > 0 else 0
        else:
            from django.utils import timezone
            overdue = queryset.filter(
                is_completed=False,
                expected_completion_date__lt=timezone.now().date()
            ).count()
            avg_progress = queryset.aggregate(Avg('progress_percentage'))['progress_percentage__avg'] or 0
        
        stats = {
            'total': total,
            'completed': completed,
            'in_progress': in_progress,
            'overdue': overdue,
            'average_progress': round(avg_progress, 2),
            'completion_rate': round((completed / total * 100), 2) if total > 0 else 0
        }
        
        return Response(stats)
    
    @action(detail=True, methods=['post'])
    def mark_complete(self, request, pk=None):
        """Mark implementation as complete"""
        implementation = self.get_object()
        
        completion_remarks = request.data.get('completion_remarks')
        actual_completion_date = request.data.get('actual_completion_date')
        
        if not completion_remarks:
            return Response(
                {'error': 'Completion remarks are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not actual_completion_date:
            from django.utils import timezone
            actual_completion_date = timezone.now().date()
        
        implementation.is_completed = True
        implementation.completion_remarks = completion_remarks
        implementation.actual_completion_date = actual_completion_date
        implementation.progress_percentage = 100
        implementation.last_updated_by = request.user
        implementation.save()
        
        serializer = self.get_serializer(implementation)
        return Response(serializer.data)

