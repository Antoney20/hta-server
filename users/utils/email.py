from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils import timezone
import logging
from smtplib import SMTPException
from users.models import EmailLog

logger = logging.getLogger(__name__)


def send_confirmation_email(proposal):
    """Send confirmation email for a proposal and log it in the database"""
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bptap.com')
    reply_to = getattr(settings, 'DEFAULT_FROM_EMAIL', from_email)

    recipient = proposal.email
    subject = 'Acknowledgement of Receipt of Health Intervention Proposal'
    user_name = getattr(proposal, 'name', proposal.email.split('@')[0])

    # context data for the template
    context = {
        'proposal': proposal,
        'current_year': timezone.now().year,
        'user_name': user_name,
    }
    html_content = render_to_string('emails/proposal_recieved.html', context)

    # Email log
    email_log = EmailLog.objects.create(
        subject=subject,
        message=html_content,
        sender=from_email,
        recipient=recipient,
        category='proposal',
        status='initial',
    )

    try:
        logger.info(f"Preparing confirmation email for: {recipient}")
        email_log.mark_sending()  #sending

        email = EmailMultiAlternatives(
            subject=subject,
            body='',  # 
            from_email=from_email,
            to=[recipient],
            reply_to=[reply_to] if reply_to != from_email else None
        )
        email.attach_alternative(html_content, "text/html")

        email.send(fail_silently=False)

        email_log.mark_sent()  # Sent sussessfully
        logger.info(f" Confirmation email sent successfully to: {recipient}")
        print(f" Confirmation email sent successfully to: {recipient}")
        return True

    except (SMTPException, Exception) as exc:
        email_log.mark_failed(exc)
        logger.error(f" Failed to send confirmation email to: {recipient} - Error: {exc}")
        print(f" Failed to send confirmation email to: {recipient} - Error: {exc}")
        return False
    
    
def send_contact_confirmation_email(contact_submission):
    """Send confirmation email for a contact submission and log it in the database"""
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bptap.com')
    reply_to = getattr(settings, 'DEFAULT_FROM_EMAIL', from_email)
    recipient = contact_submission.email
    subject = 'Thank You for Contacting Us - Message Received'

    # Render HTML content
    context = {
        'contact': contact_submission,
        'current_year': timezone.now().year,
        'full_name': contact_submission.full_name,
        'subject': contact_submission.subject,
    }
    html_content = render_to_string('emails/contact_received.html', context)

    # Create initial EmailLog
    email_log = EmailLog.objects.create(
        subject=subject,
        message=html_content,
        sender=from_email,
        recipient=recipient,
        category='contact',
        status='initial',
    )

    try:
        logger.info(f"Preparing contact confirmation email for: {recipient}")
        email_log.mark_sending()

        email = EmailMultiAlternatives(
            subject=subject,
            body='',  # HTML only
            from_email=from_email,
            to=[recipient],
            reply_to=[reply_to] if reply_to != from_email else None
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)

        email_log.mark_sent()
        logger.info(f" Contact confirmation email sent to: {recipient}")
        print(f"Contact confirmation email sent to: {recipient}")
        return True

    except Exception as exc:
        email_log.mark_failed(exc)
        logger.error(f" Failed to send contact confirmation email to {recipient}: {exc}")
        print(f"Failed to send contact confirmation email to {recipient}: {exc}")
        return False


def send_password_reset_email(user, reset_link):
    """
    Send password reset email with templated HTML and log it in the database
    """
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bptap.com')
    reply_to = getattr(settings, 'DEFAULT_FROM_EMAIL', from_email)
    recipient = user.email
    subject = 'Password Reset Request - BPTAP Communications Hub'

    user_name = user.first_name or user.username

    # context data
    context = {
        'user_name': user_name,
        'reset_link': reset_link,
        'current_year': timezone.now().year,
    }
    html_content = render_to_string('emails/password_reset.html', context)

    # Log email
    email_log = EmailLog.objects.create(
        subject=subject,
        message=html_content,
        sender=from_email,
        recipient=recipient,
        category='password_reset',
        status='initial',
    )

    try:
        logger.info(f"Preparing password reset email for: {recipient}")
        email_log.mark_sending()

        email = EmailMultiAlternatives(
            subject=subject,
            body='',
            from_email=from_email,
            to=[recipient],
            reply_to=[reply_to] if reply_to != from_email else None
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)

        email_log.mark_sent()
        logger.info(f" Password reset email sent successfully to: {recipient}")
        print(f" Password reset email sent to: {recipient}")
        return True

    except Exception as exc:
        email_log.mark_failed(exc)
        logger.error(f"✗ Failed to send password reset email to {recipient}: {exc}")
        print(f"✗ Failed to send password reset email to {recipient}: {exc}")
        return False




def send_password_change_confirmation(user):
    """
    Send confirmation email after password has been changed and log it in the database
    """
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bptap.com')
    reply_to = getattr(settings, 'DEFAULT_FROM_EMAIL', from_email)
    recipient = user.email
    subject = 'Password Changed Successfully - BPTAP Communications Hub'

    user_name = user.first_name or user.username
    context = {
        'user_name': user_name,
        'reset_date': timezone.now().strftime('%B %d, %Y at %I:%M %p'),
        'current_year': timezone.now().year,
    }
    html_content = render_to_string('emails/password_reset_confirmation.html', context)

    email_log = EmailLog.objects.create(
        subject=subject,
        message=html_content,
        sender=from_email,
        recipient=recipient,
        category='password_change',
        status='initial',
    )

    try:
        logger.info(f"Preparing password change confirmation for: {recipient}")
        email_log.mark_sending()

        email = EmailMultiAlternatives(
            subject=subject,
            body='',
            from_email=from_email,
            to=[recipient],
            reply_to=[reply_to] if reply_to != from_email else None
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)

        email_log.mark_sent()
        logger.info(f"✓ Password change confirmation sent to: {recipient}")
        print(f"✓ Password change confirmation sent to: {recipient}")
        return True

    except Exception as exc:
        email_log.mark_failed(exc)
        logger.error(f"✗ Failed to send password change confirmation to {recipient}: {exc}")
        print(f"✗ Failed to send password change confirmation to {recipient}: {exc}")
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
    """Send acknowledgment email to the newly registered user and log it"""
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bptap.com')
    reply_to = getattr(settings, 'DEFAULT_FROM_EMAIL', from_email)
    recipient = user.email
    subject = 'Account Registration Acknowledged - Awaiting Verification'

    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email.split('@')[0]
    context = {
        'full_name': full_name,
        'email': user.email,
        'current_year': timezone.now().year,
    }
    html_content = render_to_string('emails/registration_acknowledged.html', context)

    email_log = EmailLog.objects.create(
        subject=subject,
        message=html_content,
        sender=from_email,
        recipient=recipient,
        category='user_acknowledgment',
        status='initial',
    )

    try:
        logger.info(f"Preparing acknowledgment email for: {recipient}")
        email_log.mark_sending()

        email = EmailMultiAlternatives(
            subject=subject,
            body='',
            from_email=from_email,
            to=[recipient],
            reply_to=[reply_to] if reply_to != from_email else None
        )
        email.attach_alternative(html_content, "text/html")
        email.send()

        email_log.mark_sent()
        logger.info(f"✓ Acknowledgment email sent to user: {recipient}")
        return True

    except Exception as exc:
        email_log.mark_failed(exc)
        logger.error(f"✗ Failed to send acknowledgment email to {recipient}: {exc}")
        print(f"✗ Failed to send acknowledgment email to {recipient}: {exc}")
        return False


def send_secretariate_notification_email(user):
    """Send notification email to secretariate for verification and log it"""
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bptap.com')
    secretariate_email = getattr(settings, 'DEFAULT_FROM_EMAIL', from_email)
    subject = 'New Account Registration Request - Requires Verification'

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
    html_content = render_to_string('emails/secretariate_notification.html', context)

    email_log = EmailLog.objects.create(
        subject=subject,
        message=html_content,
        sender=from_email,
        recipient=secretariate_email,
        category='secretariate_notification',
        status='initial',
    )

    try:
        logger.info(f"Preparing secretariate notification for: {user.email}")
        email_log.mark_sending()

        email = EmailMultiAlternatives(
            subject=subject,
            body='',
            from_email=from_email,
            to=[secretariate_email],
        )
        email.attach_alternative(html_content, "text/html")
        email.send()

        email_log.mark_sent()
        logger.info(f"✓ Notification email sent to secretariate for user: {user.email}")
        return True

    except Exception as exc:
        email_log.mark_failed(exc)
        logger.error(f"✗ Failed to send secretariate notification for {user.email}: {exc}")
        print(f"✗ Failed to send secretariate notification for {user.email}: {exc}")
        return False



def send_verification_success_email(user):
    """Send verification success email to the user and log it"""
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bptap.com')
    reply_to = getattr(settings, 'DEFAULT_FROM_EMAIL', from_email)
    recipient = user.email
    subject = 'Account Verified - You Can Now Login'

    # Prepare context
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email.split('@')[0]
    context = {
        'full_name': full_name,
        'email': user.email,
        'current_year': timezone.now().year,
    }

    html_content = render_to_string('emails/verification_success.html', context)

    email_log = EmailLog.objects.create(
        subject=subject,
        message=html_content,
        sender=from_email,
        recipient=recipient,
        category='user_verification',
        status='initial',
    )

    try:
        logger.info(f"Preparing verification success email for: {recipient}")
        email_log.mark_sending()

        email = EmailMultiAlternatives(
            subject=subject,
            body='',
            from_email=from_email,
            to=[recipient],
            reply_to=[reply_to] if reply_to != from_email else None
        )
        email.attach_alternative(html_content, "text/html")

        email.send(fail_silently=False)
        email_log.mark_sent()
        logger.info(f"✓ Verification success email sent to: {recipient}")
        return True

    except Exception as exc:
        email_log.mark_failed(exc)
        logger.error(f"✗ Failed to send verification success email to {recipient}: {exc}")
        return False


def send_rejection_email(user):
    """Send rejection email to the user and log it"""
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bptap.com')
    reply_to = getattr(settings, 'DEFAULT_FROM_EMAIL', from_email)
    recipient = user.email
    subject = 'Account Registration Declined'

    # Prepare context
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email.split('@')[0]
    context = {
        'full_name': full_name,
        'email': user.email,
        'current_year': timezone.now().year,
    }

    html_content = render_to_string('emails/rejection.html', context)

    email_log = EmailLog.objects.create(
        subject=subject,
        message=html_content,
        sender=from_email,
        recipient=recipient,
        category='user_rejection',
        status='initial',
    )

    try:
        logger.info(f"Preparing rejection email for: {recipient}")
        email_log.mark_sending()

        email = EmailMultiAlternatives(
            subject=subject,
            body='',
            from_email=from_email,
            to=[recipient],
            reply_to=[reply_to] if reply_to != from_email else None
        )
        email.attach_alternative(html_content, "text/html")

        email.send(fail_silently=False)
        email_log.mark_sent()
        logger.info(f"Rejection email sent to: {recipient}")
        return True

    except Exception as exc:
        email_log.mark_failed(exc)
        logger.error(f" Failed to send rejection email to {recipient}: {exc}")
        return False
