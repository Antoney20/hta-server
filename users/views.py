import os
import threading
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.contrib.auth.tokens import default_token_generator

from django.utils.decorators import method_decorator
from django.views import View
from django.utils import timezone
from django.core.files.base import ContentFile
import json
import logging
from django.db import transaction , IntegrityError
from django.conf import settings

from django.contrib.sessions.models import Session
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError



from rest_framework import viewsets, status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import login
from django.utils.decorators import method_decorator
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.decorators import action


from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str


from users.permissions import IsAuthenticatedOrReadOnly, IsOwnerOrAdminOrReadOnly
from users.serializers import ContactSubmissionSerializer, FAQSerializer, GovernanceSerializer, InterventionProposalSerializer, LoginSerializer, MediaResourceSerializer, MemberListSerializer, MemberSerializer, NewsSerializer, NewsletterSubscriptionSerializer, NewsletterUnsubscribeSerializer, ProposalSubmissionSerializer, RegisterSerializer, UserMeSerializer, UserSerializer, VerifyUserSerializer
from .models import FAQ, ContactSubmission, CustomUser, Governance, InterventionProposal, MediaResource, Member, News, NewsletterSubscription, ProposalSubmission, TemporaryFile, ProposalSubmissionStatus, ProposalDocument, UserStatus
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from .tasks import retry_failed_proposal_submission, send_proposal_confirmation_email_task
from members.models import Announcement, Channel, PriorityLevel, ProposalTracker, ReviewComment, ReviewStage, ReviewerAssignment, Task, TaskStatus, ThematicArea,  Event
from .utils.email import send_confirmation_email, send_password_change_confirmation, send_password_reset_email, send_contact_confirmation_email,  send_user_acknowledgment_email,  send_secretariate_notification_email, send_verification_success_email,  send_rejection_email

from datetime import timedelta
from django.db.models import Count, Q, Avg
from django.utils import timezone
from django.contrib.auth import get_user_model
User = get_user_model()

from rest_framework.generics import ListAPIView,  RetrieveAPIView

ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.jpg', '.png'}
    
logger = logging.getLogger(__name__)

def get_client_ip(request):
    """Get client IP address"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip




# auth 

# class RegisterView(generics.CreateAPIView):
#     """User registration view with member profile"""
#     queryset = CustomUser.objects.all()
#     serializer_class = RegisterSerializer
#     permission_classes = [AllowAny]
   
    
#     def create(self, request, *args, **kwargs):
#         try:
#             serializer = self.get_serializer(data=request.data)
#             serializer.is_valid(raise_exception=True)
            
#             user = serializer.save()
            
#             # Generate tokens
#             refresh = RefreshToken.for_user(user)
#             access_token = refresh.access_token
            
#             logger.info(f"New user registered: {user.email}")
            
#             return Response({
#                 'success': True,
#                 'message': 'User registered successfully',
#                 'tokens': {
#                     'access': str(access_token),
#                     'refresh': str(refresh)
#                 }
#             }, status=status.HTTP_201_CREATED)
            
#         except Exception as e:
#             logger.error(f"Registration error: {str(e)}")
#             return Response({
#                 'success': False,
#                 'message': 'Registration failed. Please try again.',
#                 'errors': getattr(e, 'detail', str(e))
#             }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class RegisterView(generics.CreateAPIView):
    """User registration view with member profile - Step 1: Registration (inactive until verified)"""
    queryset = CustomUser.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            user = serializer.save()
            user.is_active = False  # Set inactive until verified by secretariate
            user.verification_token = default_token_generator.make_token(user)
            user.save()

            send_user_acknowledgment_email(user)

            # Send notification email to secretariate
            send_secretariate_notification_email(user)

            logger.info(f"New user registered (pending verification): {user.email}")

            return Response({
                'success': True,
                'message': 'User registered successfully. Please wait for verification by the secretariate.',
                # No tokens returned; user cannot login until verified
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            return Response({
                'success': False,
                'message': 'Registration failed. Please try again.',
                'errors': getattr(e, 'detail', str(e))
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)





class EmailVerifyView(generics.GenericAPIView):
    """Email link verification view: GET for validation, PATCH/PUT for approve/reject"""
    permission_classes = [AllowAny]
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer

    def get(self, request, user_id, token):
        """Validate token and return user data for review (no action taken)"""
        try:
            user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            return Response({
                'success': False,
                'message': 'User not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        # Verify token
        if not default_token_generator.check_token(user, token):
            return Response({
                'success': False,
                'message': 'Invalid or expired token.'
            }, status=status.HTTP_400_BAD_REQUEST)

   
        return Response({
            'success': True,
            'message': 'Token valid. User pending approval.',
            'user': UserSerializer(user).data
        }, status=status.HTTP_200_OK)

    def patch(self, request, user_id, token):
        """Handle user activation/approval via PATCH"""
        return self._handle_action(request, user_id, token)

    def put(self, request, user_id, token):
        """Alias for PATCH - handle user activation/approval via PUT"""
        return self._handle_action(request, user_id, token)

    def _handle_action(self, request, user_id, token):
        """Shared logic for approve/reject actions"""
        action = request.data.get('action')
        
        if action not in ['approve', 'reject']:
            return Response({
                'success': False,
                'message': 'Invalid action. Must be "approve" or "reject".'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            return Response({
                'success': False,
                'message': 'User not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        # Verify token
        if not default_token_generator.check_token(user, token):
            return Response({
                'success': False,
                'message': 'Invalid or expired token.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if user already processed
        if user.is_active and user.status == UserStatus.ACTIVE:
            return Response({
                'success': False,
                'message': 'User account has already been activated.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if action == 'approve':
            user.is_active = True
            user.status = UserStatus.ACTIVE
            user.save()
            send_verification_success_email(user)
            message = 'User account approved and activated successfully.'
            logger.info(f"User approved via email verification: {user.email}")
            
        else:  # reject
            user.status = UserStatus.BLOCKED  # Or UserStatus.REJECTED if defined
            user.is_active = False
            user.save()
            send_rejection_email(user)
            message = 'User account rejected.'
            logger.info(f"User rejected via email verification: {user.email}")

        return Response({
            'success': True,
            'message': message,
            'user': UserSerializer(user).data
        }, status=status.HTTP_200_OK)


class LoginView(APIView):
    """User login view"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        try:
            serializer = LoginSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            user = serializer.validated_data['user']
            
            refresh = RefreshToken.for_user(user)
            access_token = refresh.access_token
            
            # Update last login
            login(request, user)
            
            logger.info(f"User logged in: {user.email}")
            
            return Response({
                'success': True,
                'message': 'Login successful',
                'user': UserSerializer(user).data,
                'tokens': {
                    'access': str(access_token),
                    'refresh': str(refresh)
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return Response({
                'success': False,
                'message': 'Login failed. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PasswordResetRequestView(generics.GenericAPIView):
    """
    Request password reset - sends email with reset link
    Accepts either email or username
    """
    permission_classes = [AllowAny]
    
    def post(self, request, *args, **kwargs):
        try:
            # Get email or username from request
            email_or_username = request.data.get('email_or_username', '').strip()
            
            if not email_or_username:
                return Response({
                    'success': False,
                    'message': 'Email or username is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Try to find user by email or username
            user = None
            try:
                if '@' in email_or_username:
                    # It's an email
                    user = CustomUser.objects.get(email=email_or_username)
                else:
                    # It's a username
                    user = CustomUser.objects.get(username=email_or_username)
            except CustomUser.DoesNotExist:
                # For security, don't reveal if user exists or not
                logger.warning(f"Password reset requested for non-existent user: {email_or_username}")
                return Response({
                    'success': True,
                    'message': 'If an account exists with this information, you will receive a password reset email shortly.'
                }, status=status.HTTP_200_OK)
            
            # Generate token
            token_generator = PasswordResetTokenGenerator()
            token = token_generator.make_token(user)
            
            # Encode user ID
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # Create reset link (valid for 2 hours)
            frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
            reset_link = f"{frontend_url}/auth/reset-password?uid={uid}&token={token}"
            
            # Send email using utility function
            email_sent = send_password_reset_email(user, reset_link)
            
            if email_sent:
                logger.info(f"Password reset email sent to: {user.email}")
                return Response({
                    'success': True,
                    'message': 'If an account exists with this information, you will receive a password reset email shortly.'
                }, status=status.HTTP_200_OK)
            else:
                logger.error(f"Failed to send password reset email to: {user.email}")
                return Response({
                    'success': False,
                    'message': 'Failed to send reset email. Please try again later.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        except Exception as e:
            logger.error(f"Password reset request error: {str(e)}")
            return Response({
                'success': False,
                'message': 'An error occurred. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PasswordResetConfirmView(generics.GenericAPIView):
    """
    Confirm password reset with token
    Validates token and sets new password
    """
    permission_classes = [AllowAny]
    
    def post(self, request, *args, **kwargs):
        try:
            uid = request.data.get('uid')
            token = request.data.get('token')
            new_password = request.data.get('new_password')
            confirm_password = request.data.get('confirm_password')
            
            # Validate input
            if not all([uid, token, new_password, confirm_password]):
                return Response({
                    'success': False,
                    'message': 'All fields are required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check passwords match
            if new_password != confirm_password:
                return Response({
                    'success': False,
                    'message': 'Passwords do not match'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate password strength
            if len(new_password) < 8:
                return Response({
                    'success': False,
                    'message': 'Password must be at least 8 characters long'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Decode user ID
            try:
                user_id = force_str(urlsafe_base64_decode(uid))
                user = CustomUser.objects.get(pk=user_id)
            except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
                return Response({
                    'success': False,
                    'message': 'Invalid reset link'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate token
            token_generator = PasswordResetTokenGenerator()
            if not token_generator.check_token(user, token):
                return Response({
                    'success': False,
                    'message': 'Invalid or expired reset link. Please request a new password reset.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Set new password
            user.set_password(new_password)
            user.save()
            
            logger.info(f"Password reset successful for user: {user.email}")
            
            # Send confirmation email using utility function
            send_password_change_confirmation(user)
            
            return Response({
                'success': True,
                'message': 'Password has been reset successfully. You can now login with your new password.'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Password reset confirm error: {str(e)}")
            return Response({
                'success': False,
                'message': 'An error occurred. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



# class UserProfileView(generics.RetrieveUpdateAPIView):
#     """Get and update user profile"""
#     serializer_class = UserSerializer
#     permission_classes = [IsAuthenticated]
    
#     def get_object(self):
#         return self.request.user
    
#     def update(self, request, *args, **kwargs):
#         try:
#             partial = kwargs.pop('partial', False)
#             instance = self.get_object()
#             serializer = self.get_serializer(instance, data=request.data, partial=partial)
#             serializer.is_valid(raise_exception=True)
#             self.perform_update(serializer)
            
#             return Response({
#                 'success': True,
#                 'message': 'Profile updated successfully',
#                 'user': serializer.data
#             })
            
#         except Exception as e:
#             logger.error(f"Profile update error: {str(e)}")
#             return Response({
#                 'success': False,
#                 'message': 'Profile update failed. Please try again.'
#             }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# class MemberProfileView(generics.RetrieveUpdateAPIView):
#     """Get and update member profile"""
#     serializer_class = MemberSerializer
#     permission_classes = [IsAuthenticated]
    
#     def get_object(self):
#         member, created = Member.objects.get_or_create(
#             user=self.request.user,
#             defaults={
#                 'position': '',
#                 'organization': ''
#             }
#         )
#         return member
    
#     def update(self, request, *args, **kwargs):
#         try:
#             partial = kwargs.pop('partial', False)
#             instance = self.get_object()
#             serializer = self.get_serializer(instance, data=request.data, partial=partial)
#             serializer.is_valid(raise_exception=True)
#             self.perform_update(serializer)
      
#             instance.save()
            
#             return Response({
#                 'success': True,
#                 'message': 'Member profile updated successfully',
#                 'member': serializer.data
#             })
            
#         except Exception as e:
#             logger.error(f"Member profile update error: {str(e)}")
#             return Response({
#                 'success': False,
#                 'message': 'Member profile update failed. Please try again.'
#             }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserProfileViewSet(viewsets.ViewSet):
    """Unified profile management - GET, UPDATE, IMAGE operations"""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def _get_member(self, user):
        member, _ = Member.objects.get_or_create(
            user=user,
            defaults={'position': '', 'organization': '', 'is_profile_complete': False}
        )
        return member
    
    def _build_response(self, user, member, request):
        return {
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'profile_image': request.build_absolute_uri(user.profile_image.url) if user.profile_image else None,
                'country': user.country,
                'is_email_verified': user.is_email_verified,
                'status': user.status,
                'is_active': user.is_active,
                'date_joined': getattr(user, 'date_joined', None),
            },
            'member': {
                'id': member.id,
                'position': member.position,
                'organization': member.organization,
                'phone_number': member.phone_number,
                'notes': member.notes,
                'is_profile_complete': member.is_profile_complete,
                'created_at': member.created_at,
            },
            'roles': list(user.groups.values_list('name', flat=True)),
            'permissions': {
                'is_admin': user.is_admin(),
                'is_secretariate': user.is_secretariate(),
                'is_content_manager': user.is_content_manager(),
            }
        }
    
    def list(self, request):
        """GET /profile/ - Retrieve profile"""
        try:
            member = self._get_member(request.user)
            return Response({
                'success': True,
                'profile': self._build_response(request.user, member, request)
            })
        except Exception as e:
            logger.error(f"Profile retrieval error: {str(e)}")
            return Response({'success': False, 'message': 'Failed to retrieve profile'}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @transaction.atomic
    def update(self, request, pk=None):
        """PUT/PATCH /profile/ - Update profile"""
        try:
            user = request.user
            member = self._get_member(user)
            
            for field in ['first_name', 'last_name', 'country', 'username']:
                if field in request.data:
                    setattr(user, field, request.data[field])
            
            if 'profile_image' in request.FILES:
                if user.profile_image:
                    user.profile_image.delete(save=False)
                user.profile_image = request.FILES['profile_image']
            
            user.save()
            
            for field in ['position', 'organization', 'phone_number', 'notes']:
                if field in request.data:
                    setattr(member, field, request.data[field])
            
            member.is_profile_complete = bool(member.position and member.organization)
            member.save()
            
            return Response({
                'success': True,
                'message': 'Profile updated successfully',
                'profile': self._build_response(user, member, request)
            })
        except Exception as e:
            logger.error(f"Profile update error: {str(e)}")
            return Response({'success': False, 'message': str(e)}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def upload_image(self, request):
        """POST /profile/upload_image/ - Upload profile image"""
        try:
            if 'profile_image' not in request.FILES:
                return Response({'success': False, 'message': 'No image provided'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            user = request.user
            if user.profile_image:
                user.profile_image.delete(save=False)
            
            user.profile_image = request.FILES['profile_image']
            user.save()
            
            return Response({
                'success': True,
                'message': 'Image uploaded successfully',
                'profile_image': request.build_absolute_uri(user.profile_image.url)
            })
        except Exception as e:
            return Response({'success': False, 'message': str(e)}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['delete'])
    def delete_image(self, request):
        """DELETE /profile/delete_image/ - Delete profile image"""
        try:
            user = request.user
            if not user.profile_image:
                return Response({'success': False, 'message': 'No image to delete'}, 
                              status=status.HTTP_404_NOT_FOUND)
            
            user.profile_image.delete(save=False)
            user.profile_image = None
            user.save()
            
            return Response({'success': True, 'message': 'Image deleted successfully'})
        except Exception as e:
            return Response({'success': False, 'message': str(e)}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
 
class UserSettingsViewSet(viewsets.ViewSet):
    """Unified settings management - password, email, devices, account"""
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """GET /settings/ - Get all settings"""
        try:
            user = request.user
            active_sessions = self._get_user_sessions(user)
            
            return Response({
                'success': True,
                'settings': {
                    'account': {
                        'email': user.email,
                        'username': user.username,
                        'is_email_verified': user.is_email_verified,
                        'status': user.status,
                        'is_active': user.is_active,
                        'date_joined': getattr(user, 'date_joined', None),
                        'last_login': user.last_login,
                    },
                    'security': {
                        'active_sessions': len(active_sessions),
                    },
                    'roles': list(user.groups.values_list('name', flat=True)),
                }
            })
        except Exception as e:
            logger.error(f"Settings retrieval error: {str(e)}")
            return Response({'success': False, 'message': 'Failed to retrieve settings'}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def change_password(self, request):
        """POST /settings/change_password/ - Change password"""
        try:
            user = request.user
            current = request.data.get('current_password')
            new = request.data.get('new_password')
            confirm = request.data.get('confirm_password')
            
            if not all([current, new, confirm]):
                return Response({'success': False, 'message': 'All fields required'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            if not user.check_password(current):
                return Response({'success': False, 'message': 'Current password incorrect'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            if new != confirm:
                return Response({'success': False, 'message': 'Passwords do not match'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            try:
                validate_password(new, user)
            except ValidationError as e:
                return Response({'success': False, 'message': list(e.messages)[0]}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            user.set_password(new)
            user.save()
            update_session_auth_hash(request, user)
            
            return Response({'success': True, 'message': 'Password changed successfully'})
        except Exception as e:
            logger.error(f"Password change error: {str(e)}")
            return Response({'success': False, 'message': 'Failed to change password'}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    



    @action(detail=False, methods=['get'])
    def devices(self, request):
        """GET /settings/devices/ - Get active devices (max 10 most recent)"""
        try:
            user = request.user
            current_key = request.session.session_key
            sessions = self._get_user_sessions(user, include_details=True)

            # last 10
            recent_sessions = sorted(
                sessions, 
                key=lambda s: s['expire'], 
                reverse=True
            )[:10]

            devices = [{
                'session_key': s['key'],
                'is_current': s['key'] == current_key,
                'expire_date': s['expire'],
            } for s in recent_sessions]

            return Response({
                'success': True,
                'devices': devices,
                'total': len(devices)
            })

        except Exception as e:
            logger.error(f"Devices retrieval error: {str(e)}")
            return Response({'success': False, 'message': 'Failed to retrieve devices'}, 
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def logout_device(self, request):
        """POST /settings/logout_device/ - Logout specific device"""
        try:
            session_key = request.data.get('session_key')
            current = request.session.session_key
            
            if not session_key:
                return Response({'success': False, 'message': 'Session key required'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            if session_key == current:
                return Response({'success': False, 'message': 'Cannot logout current session'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            Session.objects.filter(session_key=session_key).delete()
            return Response({'success': True, 'message': 'Device logged out successfully'})
        except Exception as e:
            return Response({'success': False, 'message': str(e)}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def logout_all(self, request):
        """POST /settings/logout_all/ - Logout all devices"""
        try:
            user = request.user
            current = request.session.session_key
            count = 0
            
            for session in Session.objects.filter(expire_date__gte=timezone.now()):
                try:
                    data = session.get_decoded()
                    if data.get('_auth_user_id') == str(user.id) and session.session_key != current:
                        session.delete()
                        count += 1
                except:
                    continue
            
            return Response({
                'success': True,
                'message': f'Logged out from {count} device(s)'
            })
        except Exception as e:
            return Response({'success': False, 'message': str(e)}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def delete_account(self, request):
        """POST /settings/delete_account/ - Delete account"""
        try:
            user = request.user
            password = request.data.get('password')
            
            if not password:
                return Response({'success': False, 'message': 'Password required'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            if not user.check_password(password):
                return Response({'success': False, 'message': 'Incorrect password'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            
            user.is_active = False
            user.status = 'inactive'
            user.save()
            
            return Response({'success': True, 'message': 'Account deleted successfully'})
        except Exception as e:
            return Response({'success': False, 'message': str(e)}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _get_user_sessions(self, user, include_details=False):
        """Helper to get user sessions"""
        sessions = []
        for session in Session.objects.filter(expire_date__gte=timezone.now()):
            try:
                data = session.get_decoded()
                if data.get('_auth_user_id') == str(user.id):
                    if include_details:
                        sessions.append({
                            'key': session.session_key,
                            'expire': session.expire_date.isoformat(),
                        })
                    else:
                        sessions.append(session)
            except:
                continue
        return sessions           
            
            
            
class LogoutView(APIView):
    """User logout view"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            return Response({
                'success': True,
                'message': 'Logout successful'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Logout error: {str(e)}")
            return Response({
                'success': False,
                'message': 'Logout failed'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_me(request):
    """Get current user profile with member info"""
    try:
        # Check if user exists and is authenticated
        user = request.user
        if not user or not user.is_authenticated:
            return Response({
                'success': False,
                'message': 'User not authenticated'
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Check if user is AnonymousUser
        if user.is_anonymous:
            return Response({
                'success': False,
                'message': 'Anonymous user not allowed'
            }, status=status.HTTP_401_UNAUTHORIZED)

        print(f"User logged in: {user}, Type: {type(user)}")  # debug log
        
     
        serializer = UserMeSerializer(user, context={'request': request})
        
        return Response({
            'success': True,
            'data': serializer.data,
            'message': 'User profile retrieved successfully'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Failed to retrieve user profile: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)















class InterventionProposalListView(ListAPIView):
    queryset = InterventionProposal.objects.all()
    serializer_class = InterventionProposalSerializer
    
    
class InterventionProposalDetailView(RetrieveAPIView):
    queryset = InterventionProposal.objects.all()
    serializer_class = InterventionProposalSerializer
    lookup_field = 'id'



class ProposalSubmissionListView(ListAPIView):
    queryset = ProposalSubmission.objects.all()
    serializer_class = ProposalSubmissionSerializer
       
        
class InterventionProposalView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [AllowAny]
    
    def post(self, request):
        try:
            # Use atomic transaction for better error handling
            with transaction.atomic():
                serializer = InterventionProposalSerializer(data=request.data)
                if not serializer.is_valid():
                    logger.error(f"Serializer errors: {serializer.errors}")
                    return Response({
                        'success': False,
                        'message': 'Invalid submission data',
                        'errors': serializer.errors
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Add IP and user agent to validated data
                serializer.validated_data['ip_address'] = get_client_ip(request)
                serializer.validated_data['user_agent'] = request.META.get('HTTP_USER_AGENT', '')
                
                proposal = serializer.save()

                # Create proposal tracker
                try:
                    ProposalTracker.objects.create(
                        proposal=proposal,
                        progress=0,
                        notes="Proposal submitted successfully"
                    )
                except Exception as tracker_error:
                    logger.warning(f"Failed to create ProposalTracker for proposal {proposal.id}: {tracker_error}")

            def send_email_in_background(proposal):
                try:
                    email_sent = send_confirmation_email(proposal)
                    if email_sent:
                        logger.info(f"✓ Background email sent successfully for proposal {proposal.id}")
                    else:
                        logger.warning(f"✗ Background email failed for proposal {proposal.id}")
                except Exception as e:
                    logger.error(f"Error in background email for proposal {proposal.id}: {e}")

            threading.Thread(target=send_email_in_background, args=(proposal,), daemon=True).start()

            # Return success immediately after save
            return Response({
                'success': True,
                'message': 'Proposal submitted successfully',
                'proposal_id': proposal.id,
                'documents_count': proposal.documents.count()
            })

        except Exception as e:
            logger.error(f"Error creating proposal: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'message': 'Error submitting proposal. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    def _extract_form_data_for_retry(self, request_data):
        """
        Extract form data for retry, excluding file objects that can't be serialized.
        Files are already saved via the serializer, so we only need form fields.
        """
        form_data = {}
        
        for key, value in request_data.items():
            # Skip file fields - they're already processed and saved
            if key == 'uploaded_documents':
                # Instead of the files, just store the count and names
                if isinstance(value, list):
                    form_data['uploaded_documents_count'] = len(value)
                    form_data['uploaded_documents_names'] = [
                        getattr(file, 'name', 'unknown') for file in value 
                        if hasattr(file, 'name')
                    ]
                else:
                    form_data['uploaded_documents_count'] = 1
                    form_data['uploaded_documents_names'] = [getattr(value, 'name', 'unknown')]
            elif not isinstance(value, InMemoryUploadedFile):
                # Include all non-file data
                form_data[key] = value
        
        return form_data
     

@csrf_exempt
@login_required
@permission_required('proposals.can_view_all_proposals', raise_exception=True)
def check_multiple_submissions(request):
    """Check status of multiple submissions (authenticated users with permission only)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        data = json.loads(request.body)
        submission_ids = data.get('submission_ids', [])
        
        # Restrict to submissions the user is allowed to see
        submissions = ProposalSubmission.objects.filter(
            submission_id__in=submission_ids,
            user=request.user
        ).values(
            'submission_id', 'status', 'submitted_at', 'completed_at'
        )
        
        if request.user.has_role('Content Managers') or request.user.has_role('Reviewers'):
            submissions = ProposalSubmission.objects.filter(
                submission_id__in=submission_ids
            ).values(
                'submission_id', 'status', 'submitted_at', 'completed_at'
            )

        return JsonResponse({
            'success': True,
            'submissions': list(submissions)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    
    
class MemberListAPIView(generics.ListAPIView):
    """
    List all members with their user information.
    """
    queryset = Member.objects.select_related('user').all()
    serializer_class = MemberListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Only return members that have associated users.
        """
        queryset = super().get_queryset()
        return queryset.filter(user__isnull=False)
    
    
    

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_dashboard_data(request):
    """
    Get complete dashboard data with all statistics and reports
    """
    try:
        # Calculate all stats
        stats = {
            'total_proposals': ProposalTracker.objects.count(),
            'total_users': User.objects.filter(is_active=True).count(),
            'total_announcements': Announcement.objects.count(),
            'total_tasks': Task.objects.exclude(status=TaskStatus.COMPLETED).count(),
            'total_events': Event.objects.filter(start_date__gte=timezone.now()).count(),
            'total_channels': Channel.objects.count(),
            'active_reviewers': ReviewerAssignment.objects.values('reviewer').distinct().count(),
            'pending_reviews': ProposalTracker.objects.filter(
                review_stage__in=[ReviewStage.INITIAL, ReviewStage.UNDER_REVIEW]
            ).count(),
        }

        # Proposal status distribution
        proposal_status_distribution = []
        status_counts = ProposalTracker.objects.values('review_stage').annotate(
            count=Count('id')
        ).order_by('review_stage')
        
        total_proposals = stats['total_proposals'] or 1
        for item in status_counts:
            stage_label = dict(ReviewStage.choices).get(item['review_stage'], item['review_stage'])
            proposal_status_distribution.append({
                'status': stage_label,
                'count': item['count'],
                'percentage': round((item['count'] / total_proposals) * 100, 2)
            })

        # Recent activities (last 10)
        recent_activities = []
        
        # Recent proposals
        recent_proposals = ProposalTracker.objects.select_related('proposal').order_by('-created_at')[:3]
        for tracker in recent_proposals:
            recent_activities.append({
                'id': str(tracker.id),
                'type': 'proposal',
                'title': 'New Proposal Submitted',
                'description': tracker.proposal.intervention_name,
                'user': tracker.proposal.proposer_name if hasattr(tracker.proposal, 'proposer_name') else 'Unknown',
                'timestamp': get_time_ago(tracker.created_at),
                'status': dict(ReviewStage.choices).get(tracker.review_stage, tracker.review_stage)
            })

        # Recent announcements
        recent_announcements = Announcement.objects.order_by('-created_at')[:3]
        for announcement in recent_announcements:
            recent_activities.append({
                'id': str(announcement.id),
                'type': 'announcement',
                'title': announcement.title,
                'description': announcement.content[:100] + '...' if len(announcement.content) > 100 else announcement.content,
                'user': announcement.created_by.username if announcement.created_by else 'Admin',
                'timestamp': get_time_ago(announcement.created_at)
            })

        # Recent tasks
        recent_tasks = Task.objects.filter(status=TaskStatus.COMPLETED).order_by('-completed_at')[:2]
        for task in recent_tasks:
            recent_activities.append({
                'id': str(task.id),
                'type': 'task',
                'title': 'Task Completed',
                'description': task.title,
                'user': task.created_by.username if task.created_by else 'Unknown',
                'timestamp': get_time_ago(task.completed_at) if task.completed_at else 'Recently',
                'status': 'Completed'
            })

        # Recent comments
        recent_comments = ReviewComment.objects.select_related('reviewer', 'tracker').order_by('-created_at')[:2]
        for comment in recent_comments:
            recent_activities.append({
                'id': str(comment.id),
                'type': 'comment',
                'title': 'Review Comment Added',
                'description': comment.content[:100] + '...' if len(comment.content) > 100 else comment.content,
                'user': comment.reviewer.username if comment.reviewer else 'Unknown',
                'timestamp': get_time_ago(comment.created_at)
            })

        # Sort by timestamp and limit to 10
        recent_activities = sorted(recent_activities, key=lambda x: x.get('timestamp', ''), reverse=False)[:10]

        # Thematic area statistics
        thematic_areas = []
        thematic_stats = ThematicArea.objects.filter(is_active=True).annotate(
            proposal_count=Count('proposaltracker')
        ).order_by('-proposal_count')
        
        for area in thematic_stats:
            thematic_areas.append({
                'id': str(area.id),
                'name': area.name,
                'proposal_count': area.proposal_count,
                'color_code': area.color_code
            })

        # Priority distribution
        priority_distribution = []
        priority_counts = ProposalTracker.objects.filter(
            priority_level__isnull=False
        ).values('priority_level').annotate(count=Count('id'))
        
        total_with_priority = sum(item['count'] for item in priority_counts) or 1
        for item in priority_counts:
            priority_label = dict(PriorityLevel.choices).get(item['priority_level'], item['priority_level'])
            priority_distribution.append({
                'priority': priority_label,
                'count': item['count'],
                'percentage': round((item['count'] / total_with_priority) * 100, 2)
            })

        # Reviewer workload
        reviewer_workload = []
        reviewers = ReviewerAssignment.objects.values('reviewer').annotate(
            assigned_count=Count('id'),
            avg_progress=Avg('progress')
        ).order_by('-assigned_count')[:5]
        
        for reviewer_data in reviewers:
            reviewer = User.objects.get(id=reviewer_data['reviewer'])
            assignments = ReviewerAssignment.objects.filter(reviewer=reviewer)
            completed = assignments.filter(progress=100).count()
            pending = assignments.exclude(progress=100).count()
            
            reviewer_workload.append({
                'id': str(reviewer.id),
                'reviewer_name': reviewer.username or reviewer.username,
                'assigned_proposals': reviewer_data['assigned_count'],
                'completed_reviews': completed,
                'pending_reviews': pending,
                'average_progress': round(reviewer_data['avg_progress'] or 0, 2)
            })

        # Implementation progress
        implementation_progress = []
        impl_counts = ProposalTracker.objects.filter(
            implementation_status__isnull=False
        ).values('implementation_status').annotate(count=Count('id'))
        
        total_impl = sum(item['count'] for item in impl_counts) or 1
        for item in impl_counts:
            from .models import ImplementationStatus
            status_label = dict(ImplementationStatus.choices).get(item['implementation_status'], item['implementation_status'])
            implementation_progress.append({
                'status': status_label,
                'count': item['count'],
                'percentage': round((item['count'] / total_impl) * 100, 2)
            })

        # Monthly trends (last 6 months)
        monthly_trends = []
        today = timezone.now()
        for i in range(5, -1, -1):
            month_start = (today - timedelta(days=30*i)).replace(day=1)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
            
            submitted = ProposalTracker.objects.filter(
                created_at__gte=month_start,
                created_at__lte=month_end
            ).count()
            
            approved = ProposalTracker.objects.filter(
                review_stage=ReviewStage.APPROVED,
                updated_at__gte=month_start,
                updated_at__lte=month_end
            ).count()
            
            rejected = ProposalTracker.objects.filter(
                review_stage=ReviewStage.REJECTED,
                updated_at__gte=month_start,
                updated_at__lte=month_end
            ).count()
            
            monthly_trends.append({
                'month': month_start.strftime('%b'),
                'proposals_submitted': submitted,
                'proposals_approved': approved,
                'proposals_rejected': rejected
            })

        # Compile response
        dashboard_data = {
            'stats': stats,
            'proposal_status_distribution': proposal_status_distribution,
            'recent_activities': recent_activities,
            'thematic_areas': thematic_areas,
            'priority_distribution': priority_distribution,
            'reviewer_workload': reviewer_workload,
            'implementation_progress': implementation_progress,
            'monthly_trends': monthly_trends
        }

        return Response(dashboard_data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {'error': str(e), 'message': 'Failed to fetch dashboard data'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_dashboard_stats(request):
    """
    Get only dashboard statistics
    """
    try:
        stats = {
            'total_proposals': ProposalTracker.objects.count(),
            'total_users': User.objects.filter(is_active=True).count(),
            'total_announcements': Announcement.objects.count(),
            'total_tasks': Task.objects.exclude(status=TaskStatus.COMPLETED).count(),
            'total_events': Event.objects.filter(start_date__gte=timezone.now()).count(),
            'total_channels': Channel.objects.count(),
            'active_reviewers': ReviewerAssignment.objects.values('reviewer').distinct().count(),
            'pending_reviews': ProposalTracker.objects.filter(
                review_stage__in=[ReviewStage.INITIAL, ReviewStage.UNDER_REVIEW]
            ).count(),
        }
        return Response(stats, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def get_time_ago(dt):
    """Helper function to convert datetime to 'time ago' format"""
    if not dt:
        return 'Unknown'
    
    now = timezone.now()
    diff = now - dt
    
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return 'Just now'
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f'{minutes} minute{"s" if minutes != 1 else ""} ago'
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f'{hours} hour{"s" if hours != 1 else ""} ago'
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f'{days} day{"s" if days != 1 else ""} ago'
    elif seconds < 2592000:
        weeks = int(seconds / 604800)
        return f'{weeks} week{"s" if weeks != 1 else ""} ago'
    else:
        months = int(seconds / 2592000)
        return f'{months} month{"s" if months != 1 else ""} ago'






class FAQViewSet(viewsets.ModelViewSet):
    queryset = FAQ.objects.all()
    serializer_class = FAQSerializer
    permission_classes = [IsOwnerOrAdminOrReadOnly]

class NewsViewSet(viewsets.ModelViewSet):
    queryset = News.objects.all()
    serializer_class = NewsSerializer
    permission_classes = [IsOwnerOrAdminOrReadOnly]

class GovernanceViewSet(viewsets.ModelViewSet):
    queryset = Governance.objects.all()
    serializer_class = GovernanceSerializer
    permission_classes = [IsOwnerOrAdminOrReadOnly]

class MediaResourceViewSet(viewsets.ModelViewSet):
    queryset = MediaResource.objects.all()
    serializer_class = MediaResourceSerializer
    permission_classes = [IsOwnerOrAdminOrReadOnly]
    
    
    





class ContactSubmissionViewSet(viewsets.ModelViewSet):
    queryset = ContactSubmission.objects.all()
    serializer_class = ContactSubmissionSerializer
    
    def get_permissions(self):
        """
        POST: Public (AllowAny)
        LIST, RETRIEVE, DELETE, UPDATE: Requires authentication
        """
        if self.action == 'create':
            return [AllowAny()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        try:
            # Get client IP
            ip_address = get_client_ip(request)
            
            # Check submission count for this IP
            submission_count = ContactSubmission.objects.filter(ip_address=ip_address).count()
            
            if submission_count >= 10:
                return Response(
                    {
                        'success': False,
                        'message': 'Maximum submission limit reached. Please contact us directly.'
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )
            
            data = request.data.copy()
            data['ip_address'] = ip_address
            
            with transaction.atomic():
                serializer = self.get_serializer(data=data)
                if not serializer.is_valid():
                    return Response(
                        {
                            'success': False,
                            'message': 'Please check your form data.',
                            'errors': serializer.errors
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                contact_submission = serializer.save()

            def send_email_in_background(contact_submission):
                try:
                    email_sent = send_contact_confirmation_email(contact_submission)
                    if email_sent:
                        logger.info(f" Background email sent successfully for contact submission {contact_submission.id}")
                    else:
                        logger.warning(f"Background email failed for contact submission {contact_submission.id}")
                except Exception as e:
                    logger.error(f"Error in background email for contact submission {contact_submission.id}: {e}")

            threading.Thread(target=send_email_in_background, args=(contact_submission,), daemon=True).start()
            
            return Response(
                {
                    'success': True,
                    'message': 'Thank you for contacting us! We will get back to you soon.',
                    'submission_id': contact_submission.id
                },
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            logger.error(f"Error creating contact submission: {str(e)}", exc_info=True)
            return Response(
                {
                    'success': False,
                    'message': 'Error submitting contact form. Please try again.'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



class NewsletterSubscriptionViewSet(viewsets.ModelViewSet):
    queryset = NewsletterSubscription.objects.all()
    serializer_class = NewsletterSubscriptionSerializer
    
    def get_permissions(self):
        """
        POST (subscribe): Public (AllowAny)
        POST (unsubscribe): Public (AllowAny)
        LIST, RETRIEVE, DELETE, UPDATE: Requires authentication
        """
        if self.action in ['create', 'unsubscribe']:
            return [AllowAny()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        """Subscribe to newsletter"""
        email = request.data.get('email', '').strip().lower()
        
        if not email:
            return Response(
                {
                    'success': False,
                    'message': 'Email address is required.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Check if email already exists
            existing = NewsletterSubscription.objects.filter(email=email).first()
            
            if existing:
                if existing.is_active:
                    return Response(
                        {
                            'success': False,
                            'message': 'This email is already subscribed to our newsletter.'
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                else:
                    # Reactivate subscription
                    existing.is_active = True
                    existing.unsubscribed_at = None
                    existing.ip_address = get_client_ip(request)
                    existing.save()
                    
                    return Response(
                        {
                            'success': True,
                            'message': 'Welcome back! You have been resubscribed to our newsletter.'
                        },
                        status=status.HTTP_200_OK
                    )
            
            # Create new subscription
            subscription = NewsletterSubscription.objects.create(
                email=email,
                ip_address=get_client_ip(request)
            )
            
            logger.info(f"New newsletter subscription: {email}")
            
            return Response(
                {
                    'success': True,
                    'message': 'Thank you for subscribing to our newsletter!'
                },
                status=status.HTTP_201_CREATED
            )
            
        except IntegrityError:
            return Response(
                {
                    'success': False,
                    'message': 'This email is already subscribed.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error subscribing to newsletter: {e}")
            return Response(
                {
                    'success': False,
                    'message': 'An error occurred. Please try again.'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], url_path='unsubscribe')
    def unsubscribe(self, request):
        """Unsubscribe from newsletter"""
        serializer = NewsletterUnsubscribeSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Please provide a valid email address.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        email = serializer.validated_data['email'].strip().lower()
        
        try:
            subscription = NewsletterSubscription.objects.filter(
                email=email,
                is_active=True
            ).first()
            
            if not subscription:
                return Response(
                    {
                        'success': False,
                        'message': 'This email is not subscribed to our newsletter.'
                    },
                    status=status.HTTP_404_NOT_FOUND
                )
            
            subscription.unsubscribe()
            logger.info(f"Newsletter unsubscription: {email}")
            
            return Response(
                {
                    'success': True,
                    'message': 'You have been successfully unsubscribed from our newsletter.'
                },
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Error unsubscribing from newsletter: {e}")
            return Response(
                {
                    'success': False,
                    'message': 'An error occurred. Please try again.'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )