from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)



def send_confirmation_email(proposal):
    """Send confirmation email for a proposal"""
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bptap.com')
    reply_to = getattr(settings, 'DEFAULT_FROM_EMAIL', from_email)
    
    try:
        print(f"Preparing confirmation email for: {proposal.email}")
        
        user_name = getattr(proposal, 'name', proposal.email.split('@')[0])
        
        context = {
            'proposal': proposal,
            'current_year': timezone.now().year,
            'user_name': user_name,
        }
        
        subject = 'Acknowledgement of Receipt of Health Intervention Proposal'
        
        # Render HTML template
        html_content = render_to_string('emails/proposal_recieved.html', context)
        
        # Create email with HTML only
        email = EmailMultiAlternatives(
            subject=subject,
            body='',  # Empty body since we're using HTML
            from_email=from_email,
            to=[proposal.email],
            reply_to=[reply_to] if reply_to != from_email else None
        )
        
        # Attach HTML content
        email.attach_alternative(html_content, "text/html")
        
        email.send()
        
        print(f"✓ Confirmation email sent successfully to: {proposal.email}")
        logger.info(f"Confirmation email sent for proposal {proposal.id} to {proposal.email}")
        return True
        
    except Exception as exc:
        print(f"✗ Failed to send confirmation email to: {proposal.email} - Error: {exc}")
        logger.error(f"Error sending confirmation email for proposal {proposal.id}: {exc}")
        return False
    
    

def send_contact_confirmation_email(contact_submission):
    """Send confirmation email for a contact submission"""
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bptap.com')
    reply_to = getattr(settings, 'DEFAULT_FROM_EMAIL', from_email)
    
    try:
        print(f"Preparing confirmation email for: {contact_submission.email}")
        
        context = {
            'contact': contact_submission,
            'current_year': timezone.now().year,
            'full_name': contact_submission.full_name,
            'subject': contact_submission.subject,
        }
        
        subject = 'Thank You for Contacting Us - Message Received'
        
        # Render HTML template
        html_content = render_to_string('emails/contact_received.html', context)
        
        # Create email with HTML only
        email = EmailMultiAlternatives(
            subject=subject,
            body='',  # Empty body since we're using HTML
            from_email=from_email,
            to=[contact_submission.email],
            reply_to=[reply_to] if reply_to != from_email else None
        )
        
        # Attach HTML content
        email.attach_alternative(html_content, "text/html")
        
        email.send()
        
        print(f"✓ Confirmation email sent successfully to: {contact_submission.email}")
        logger.info(f"Confirmation email sent for contact submission {contact_submission.id} to {contact_submission.email}")
        return True
        
    except Exception as exc:
        print(f"✗ Failed to send confirmation email to: {contact_submission.email} - Error: {exc}")
        logger.error(f"Error sending confirmation email for contact submission {contact_submission.id}: {exc}")
        return False
    

def send_password_reset_email(user, reset_link):
    """
    Send password reset email with templated HTML
    
    Args:
        user: CustomUser instance
        reset_link: Full reset URL with token
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@hbtap.com')
    reply_to = getattr(settings, 'DEFAULT_FROM_EMAIL', from_email)
    
    try:
        logger.info(f"Preparing password reset email for: {user.email}")
        
        user_name = user.first_name or user.username
        
        # Prepare context for template
        context = {
            'user_name': user_name,
            'reset_link': reset_link,
            'current_year': timezone.now().year,
        }
        
        # Email subject
        subject = 'Password Reset Request - BPTAP Communications Hub'
        
        # Render HTML template
        html_content = render_to_string('emails/password_reset.html', context)
        
        # Create email with HTML only
        email = EmailMultiAlternatives(
            subject=subject,
            body='',  # Empty body since we're using HTML
            from_email=from_email,
            to=[user.email],
            reply_to=[reply_to] if reply_to != from_email else None
        )
        
        # Attach HTML version
        email.attach_alternative(html_content, "text/html")
        
        # Send email
        email.send(fail_silently=False)
        
        logger.info(f"✓ Password reset email sent successfully to: {user.email}")
        print(f"✓ Password reset email sent to: {user.email}")
        return True
        
    except Exception as exc:
        logger.error(f"✗ Failed to send password reset email to {user.email}: {exc}")
        print(f"✗ Failed to send password reset email to {user.email}: {exc}")
        return False


def send_password_change_confirmation(user):
    """
    Send confirmation email after password has been changed
    
    Args:
        user: CustomUser instance
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@hbtap.com')
    reply_to = getattr(settings, 'DEFAULT_FROM_EMAIL', from_email)
    
    try:
        logger.info(f"Preparing password change confirmation for: {user.email}")
        
        # Get user's display name
        user_name = user.first_name or user.username
        
        # Prepare context for template
        context = {
            'user_name': user_name,
            'reset_date': timezone.now().strftime('%B %d, %Y at %I:%M %p'),
            'current_year': timezone.now().year,
        }
        
        # Email subject
        subject = 'Password Changed Successfully - BPTAP Communications Hub'
        
        # Render HTML template
        html_content = render_to_string('emails/password_reset_confirmation.html', context)
        
        # Create email with HTML only
        email = EmailMultiAlternatives(
            subject=subject,
            body='',  # Empty body since we're using HTML
            from_email=from_email,
            to=[user.email],
            reply_to=[reply_to] if reply_to != from_email else None
        )
        
        # Attach HTML version
        email.attach_alternative(html_content, "text/html")
        
        # Send email
        email.send(fail_silently=False)
        
        logger.info(f"✓ Password change confirmation sent to: {user.email}")
        print(f"✓ Password change confirmation sent to: {user.email}")
        return True
        
    except Exception as exc:
        logger.error(f"✗ Failed to send password change confirmation to {user.email}: {exc}")
        print(f"✗ Failed to send confirmation to {user.email}: {exc}")
        return False





class ProposalEmailService:
    """Service class for sending proposal-related emails"""
    
    def __init__(self):
        self.from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bptap.com')
        self.reply_to = getattr(settings, 'DEFAULT_FROM_EMAIL', self.from_email)
    
    def send_confirmation_email(self, proposal):
        """Send confirmation email for a proposal"""
        return send_confirmation_email(proposal)
    
    
    
    
def send_user_acknowledgment_email(user):
    """Send acknowledgment email to the newly registered user"""
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bptap.com')
    reply_to = getattr(settings, 'DEFAULT_FROM_EMAIL', from_email)
    
    try:
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email.split('@')[0]
        
        context = {
            'full_name': full_name,
            'email': user.email,
            'current_year': timezone.now().year,
        }
        
        subject = 'Account Registration Acknowledged - Awaiting Verification'
        
        # Render HTML template
        html_content = render_to_string('emails/registration_acknowledged.html', context)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body='',  # Empty body since using HTML
            from_email=from_email,
            to=[user.email],
            reply_to=[reply_to] if reply_to != from_email else None
        )
        
        email.attach_alternative(html_content, "text/html")
        email.send()
        
        logger.info(f"Acknowledgment email sent to user: {user.email}")
        return True
        
    except Exception as exc:
        logger.error(f"Error sending acknowledgment email to {user.email}: {exc}")
        return False



def send_secretariate_notification_email(user):
    """Send notification email to secretariate for verification"""
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bptap.com')
    secretariate_email = getattr(settings, 'DEFAULT_FROM_EMAIL', from_email)
    
    try:
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email.split('@')[0]
        frontend_url = getattr(settings, 'FRONTEND_URL', 'FRONTEND_URL')

        context = {
            'full_name': full_name,
            'email': user.email,
            'user_id': user.id,
            'token': user.verification_token,
            'frontend_url': frontend_url,
            'current_year': timezone.now().year,
        }

        subject = 'New Account Registration Request - Requires Verification'
        html_content = render_to_string('emails/secretariate_notification.html', context)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body='',
            from_email=from_email,
            to=[secretariate_email],
        )
        email.attach_alternative(html_content, "text/html")
        email.send()

        logger.info(f"Notification email sent to secretariate for user: {user.email}")
        return True
        
    except Exception as exc:
        logger.error(f"Error sending notification email for {user.email}: {exc}")
        return False

def send_verification_success_email(user):
    """Send verification success email to the user"""
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bptap.com')
    reply_to = getattr(settings, 'DEFAULT_FROM_EMAIL', from_email)
    
    try:
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email.split('@')[0]
        
        context = {
            'full_name': full_name,
            'email': user.email,
            'current_year': timezone.now().year,
        }
        
        subject = 'Account Verified - You Can Now Login'
        
        # Render HTML template
        html_content = render_to_string('emails/verification_success.html', context)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body='',  # Empty body since using HTML
            from_email=from_email,
            to=[user.email],
            reply_to=[reply_to] if reply_to != from_email else None
        )
        
        email.attach_alternative(html_content, "text/html")
        email.send()
        
        logger.info(f"Verification success email sent to: {user.email}")
        return True
        
    except Exception as exc:
        logger.error(f"Error sending verification success email to {user.email}: {exc}")
        return False
    
    
def send_rejection_email(user):
    """Send rejection email to the user"""
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bptap.com')
    reply_to = getattr(settings, 'DEFAULT_FROM_EMAIL', from_email)
    
    try:
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email.split('@')[0]
        
        context = {
            'full_name': full_name,
            'email': user.email,
            'current_year': timezone.now().year,
        }
        
        subject = 'Account Registration Declined'
        
        html_content = render_to_string('emails/rejection.html', context)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body='',
            from_email=from_email,
            to=[user.email],
            reply_to=[reply_to] if reply_to != from_email else None
        )
        
        email.attach_alternative(html_content, "text/html")
        email.send()
        
        logger.info(f"Rejection email sent to: {user.email}")
        return True
        
    except Exception as exc:
        logger.error(f"Error sending rejection email to {user.email}: {exc}")
        return False