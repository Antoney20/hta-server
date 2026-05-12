from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils import timezone
import logging
from smtplib import SMTPException
from users.models import EmailLog

logger = logging.getLogger(__name__)


def _build_assignment_context(sub_activity, user):
    return {
        "sub_activity": sub_activity,
        "user_name":  user.username or user.email ,
        "current_year": timezone.now().year,
        "subject": f"Task Assigned: {sub_activity.name}",
        "btap_email": getattr(settings, "BTAP_EMAIL", "noreply@btap.com"),
        "bptap": getattr(settings, "BTAP_NAME", "BTAP"),
        "frontend_url": getattr(settings, "FRONTEND_URL", "").rstrip("/"),
    }


def _send_single_assignment_email(sub_activity, user):
    """Send assignment email to one user. Returns True on success, False on failure."""
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@btap.com")
    recipient = user.email
    subject = f"Task Assigned: {sub_activity.name}"

    context = _build_assignment_context(sub_activity, user)
    html_content = render_to_string("emails/activity_assigned.html", context)

    email_log = EmailLog.objects.create(
        subject=subject,
        message=html_content,
        sender=from_email,
        recipient=recipient,
        category="activity_assignment",
        status="initial",
    )

    try:
        logger.info(f"Sending assignment email to: {recipient} for sub-activity '{sub_activity.name}'")
        email_log.mark_sending()

        email = EmailMultiAlternatives(
            subject=subject,
            body="",
            from_email=from_email,
            to=[recipient],
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)

        email_log.mark_sent()
        logger.info(f"Assignment email sent to: {recipient}")
        return True

    except (SMTPException, Exception) as exc:
        email_log.mark_failed(exc)
        logger.error(f"Failed to send assignment email to {recipient} — {exc}")
        return False


def send_activity_assignment_emails(sub_activity, users=None):
    """
    Send assignment notification emails for a SubActivity.

    Args:
        sub_activity: SubActivity instance
        users: optional list/queryset of users to notify.
               Defaults to all users in sub_activity.assigned_to.

    Returns a dict: { "sent": [...emails], "failed": [...emails] }
    """
    if not getattr(settings, "SEND_ACTIVITY_EMAILS", True):
        logger.info("Activity assignment emails are disabled via settings.")
        return {"sent": [], "failed": []}

    recipients = users if users is not None else sub_activity.assigned_to.filter(is_active=True)
    results = {"sent": [], "failed": []}

    for user in recipients:
        if not user.email:
            logger.warning(f"User '{user.username}' has no email address — skipping.")
            continue
        success = _send_single_assignment_email(sub_activity, user)
        (results["sent"] if success else results["failed"]).append(user.email)

    if results["failed"]:
        logger.warning(
            f"Assignment emails for '{sub_activity.name}': "
            f"{len(results['sent'])} sent, {len(results['failed'])} failed — {results['failed']}"
        )
    else:
        logger.info(f"All assignment emails sent for '{sub_activity.name}' ({len(results['sent'])} recipients).")

    return results