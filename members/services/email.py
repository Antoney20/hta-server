import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


def _send_single_task_assignment_email(task, user) -> bool:
    try:
        subject = f"New Task Assigned: {task.title}"
        context = {
            "subject": subject,
            "user_name":   user.username or user.email,
            "task": task,
            "frontend_url": getattr(settings, "FRONTEND_URL", ""),
            "btap_email": getattr(settings, "BTAP_EMAIL", "antony.muchiri@cema.africa"),
            "bptap": getattr(settings, "BPTAP_NAME", "BPTAP"),
            "current_year": timezone.now().year,
        }
        html_body = render_to_string("emails/task_assignment.html", context)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=f"You have been assigned a new task: {task.title}",
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[user.email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception as e:
        logger.exception(f"Failed to send task assignment email to {user.email}: {e}")
        return False


def send_task_assignment_emails(task, users=None):
    """
    Send assignment notification emails for a Task.

    Args:
        task: Task instance
        users: optional list/queryset of users to notify.
               Defaults to all active users in task.assigned_users.

    Returns: { "sent": [...emails], "failed": [...emails] }
    """
    if not getattr(settings, "SEND_TASK_EMAILS", True):
        logger.info("Task assignment emails are disabled via settings.")
        return {"sent": [], "failed": []}

    recipients = users if users is not None else task.assigned_users.filter(is_active=True)
    results = {"sent": [], "failed": []}

    for user in recipients:
        if not user.email:
            logger.warning(f"User '{user.username}' has no email address — skipping.")
            continue
        success = _send_single_task_assignment_email(task, user)
        (results["sent"] if success else results["failed"]).append(user.email)

    if results["failed"]:
        logger.warning(
            f"Task assignment emails for '{task.title}': "
            f"{len(results['sent'])} sent, {len(results['failed'])} failed — {results['failed']}"
        )
    else:
        logger.info(f"All task assignment emails sent for '{task.title}' ({len(results['sent'])} recipients).")

    return results