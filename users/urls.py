from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import InterventionProposalListView, InterventionProposalView, LoginView, LogoutView, MemberListAPIView, PasswordResetConfirmView, PasswordResetRequestView,  ProposalSubmissionListView, RegisterView, check_multiple_submissions
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,)
router = DefaultRouter()
router.register(r'profile', views.UserProfileViewSet, basename='profile')
router.register(r'settings', views.UserSettingsViewSet, basename='settings')
router.register(r'faqs', views.FAQViewSet, basename='faq')
router.register(r'news', views.NewsViewSet, basename='news')
router.register(r'governance', views.GovernanceViewSet, basename='governance')
router.register(r'media-resources', views.MediaResourceViewSet, basename='mediaresource')
router.register(r'contact', views.ContactSubmissionViewSet, basename='contact')
router.register(r'newsletter', views.NewsletterSubscriptionViewSet, basename='newsletter')



app_name = 'members'

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/user/me/', views.user_me, name='user-me'),
    path('auth/password-reset/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('auth/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),

    
    path('', include(router.urls)),
    
    # Profile URLs
    # path('profile/', UserProfileView.as_view(), name='user-profile'),
    # path('member-profile/', MemberProfileView.as_view(), name='member-profile'),
    
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    

    path('intervention-proposal/', InterventionProposalView.as_view(), name='intervention_proposal'),
    path('check-multiple-submissions/', check_multiple_submissions, name='check_multiple_submissions'),
    path('proposals/', InterventionProposalListView.as_view(), name='intervention-proposal-list'),
    path('proposals/<int:id>/', views.InterventionProposalDetailView.as_view(), name='intervention-proposal-detail'),
    path('proposal-submissions/', ProposalSubmissionListView.as_view(), name='proposal-submission-list'),
    
    path('members/', MemberListAPIView.as_view(), name='member-list'),
    
    path('dashboard/', views.get_dashboard_data , name='dash'),
    path('dashboard/stats/', views.get_dashboard_stats , name='dash- stats'),
]
