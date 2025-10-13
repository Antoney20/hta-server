from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AnnouncementViewSet,
    EventViewSet,
    ForumViewSet,
    ProposalTrackerViewSet,
    RecordViewSet,
    ResourceViewSet,
    ReviewerAssignmentViewSet,
    ReviewCommentViewSet,
    ThematicAreaViewSet,
    ThematicAreaAssignmentViewSet,
    UserViewSet
)
from . import views

router = DefaultRouter()
router.register(r'proposal-trackers', ProposalTrackerViewSet, basename='proposal-tracker')
router.register(r'reviewer-assignments', ReviewerAssignmentViewSet, basename='reviewer-assignment')
router.register(r'review-comments', ReviewCommentViewSet, basename='review-comment')
router.register(r'thematic-areas', ThematicAreaViewSet, basename='thematic-area')
router.register(r'thematic-area', ThematicAreaAssignmentViewSet, basename='thematic-area-assignment')
router.register(r'users', UserViewSet, basename='user')
router.register(r'tasks', views.TaskViewSet, basename='task')
router.register(r'forums', ForumViewSet),
router.register(r'records', RecordViewSet),
router.register(r'resources', ResourceViewSet),
router.register(r'announcements', AnnouncementViewSet),
router.register(r'events', EventViewSet, basename='event'),
router.register(r'feedback', views.FeedbackViewSet, basename='feedback'),
router.register(r'polls', views.PollViewSet, basename='poll')
router.register(r'decision-rationales', views.DecisionRationaleViewSet, basename='decision-rationale')

router.register(r'implementations', views.ImplementationTrackingViewSet, basename='implementation')




urlpatterns = [
    path('proj/', include(router.urls)),
]