import logging
from django.conf import settings
from django.core.mail import send_mail as django_send_mail, BadHeaderError
from django.core.exceptions import ImproperlyConfigured
from smtplib import SMTPException
from datetime import timedelta
from django.utils import timezone
from users.models import EmailLog 

logger = logging.getLogger(__name__)

def send_email_cron():
    """
    Cron job to process and send queued emails stored in EmailLog.

    This job is designed to:
      - Retry unsent or failed emails (based on retry policy)
      - Update each email's status in the EmailLog table
      - Log all success/failure events
      - Prevent infinite retry loops with a capped retry count

    Recommended schedule: every 5–10 minutes via django-crontab.
 
    """

    MAX_RETRIES = 6
    RETRY_INTERVAL = timedelta(minutes=5)


    # Getss unsent or failed emails eligible for retry
    unsent_emails = (
        EmailLog.objects.filter(status__in=['initial', 'failed'])
        .filter(retry_count__lt=MAX_RETRIES)
        .filter(last_attempt__isnull=True)
        |
        EmailLog.objects.filter(
            status='failed',
            last_attempt__lte=timezone.now() - RETRY_INTERVAL,
            retry_count__lt=MAX_RETRIES,
        )
    ).distinct()

    if not unsent_emails.exists():
        logger.info(" No pending emails to send.")
        return

    logger.info(f"Starting email send job: {unsent_emails.count()} pending emails")

    for email in unsent_emails:
        recipient_list = [
            r.strip() for r in str(email.recipient).split(",") if r.strip()
        ]

        if not recipient_list:
            logger.warning(f"Skipping email {email.id}: No valid recipients")
            email.status = 'failed'
            email.error_message = 'No valid recipients found.'
            email.last_attempt = timezone.now()
            email.retry_count += 1
            email.save()
            continue

        try:
            # Update status
            email.mark_sending()

            django_send_mail(
                subject=email.subject,
                message=email.message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bptap.com'),
                recipient_list=recipient_list,
                fail_silently=False,
                html_message=email.message if email.message.strip().startswith('<') else None,
            )

            email.mark_sent()
            logger.info(f"Email {email.id} sent successfully to {recipient_list}")

        except (SMTPException, TimeoutError, BadHeaderError, ImproperlyConfigured, Exception) as e:
            email.mark_failed(e)
            logger.error(f"Failed to send email {email.id} to {recipient_list}: {e}")

    logger.info(" Email cron job completed.")
