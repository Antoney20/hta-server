from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

def send_confirmation_email(proposal):
    """Send confirmation email for a proposal"""
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@yoursite.com')
    reply_to = getattr(settings, 'PROPOSAL_REPLY_TO_EMAIL', from_email)
    
    try:
        print(f"Preparing confirmation email for: {proposal.email}")
        
        user_name = getattr(proposal, 'name', proposal.email.split('@')[0])
        
        context = {
            'proposal': proposal,
            'current_year': timezone.now().year,
            'user_name': user_name,
        }
        
        subject = 'Acknowledgement of Receipt of Health Intervention Proposal'
        
        html_content = render_to_string('emails/proposal_recieved.html', context)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=html_content,
            from_email=from_email,
            to=[proposal.email],
            reply_to=[reply_to] if reply_to != from_email else None
        )
        
        email.send()
        
        print(f"✓ Confirmation email sent successfully to: {proposal.email}")
        logger.info(f"Confirmation email sent for proposal {proposal.id} to {proposal.email}")
        return True
        
    except Exception as exc:
        print(f"✗ Failed to send confirmation email to: {proposal.email} - Error: {exc}")
        logger.error(f"Error sending confirmation email for proposal {proposal.id}: {exc}")
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
    reply_to = getattr(settings, 'SUPPORT_EMAIL', from_email)
    
    try:
        logger.info(f"Preparing password reset email for: {user.email}")
        
        # Get user's display name
        user_name = user.first_name or user.username
        
        # Prepare context for template
        context = {
            'user_name': user_name,
            'reset_link': reset_link,
            'current_year': timezone.now().year,
        }
        
        # Email subject
        subject = 'Password Reset Request - HBTAP Communications Hub'
        
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
    reply_to = getattr(settings, 'SUPPORT_EMAIL', from_email)
    
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
        subject = 'Password Changed Successfully - HBTAP Communications Hub'
        
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
        self.from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@yoursite.com')
        self.reply_to = getattr(settings, 'PROPOSAL_REPLY_TO_EMAIL', self.from_email)
    
    def send_confirmation_email(self, proposal):
        """Send confirmation email for a proposal"""
        return send_confirmation_email(proposal)