import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from smtplib import SMTPException
from users.models import EmailLog

logger = logging.getLogger(__name__)

def send_email_cron():

    MAX_RETRIES = 2
    BATCH_SIZE = 100

    unsent_emails = (
        EmailLog.objects
        .filter(status__in=['initial', 'failed'], retry_count__lt=MAX_RETRIES)
        .order_by('id')
        .iterator(chunk_size=BATCH_SIZE)
    )

    for email in unsent_emails:
        try:
            recipients = [r.strip() for r in str(email.recipient).split(',') if r.strip()]
            if not recipients:
                email.mark_failed("No valid recipients")
                continue

            email.mark_sending()

            # send as HTML
            msg = EmailMultiAlternatives(
                subject=email.subject,
                body='', # 
                from_email=f'{getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@bptap.com")} <{email.sender}>',
                to=recipients,
            )
            msg.attach_alternative(email.message, "text/html")
            msg.send(fail_silently=False)

            email.mark_sent()
            logger.info(f" Sent email {email.id} to {recipients}")

        except (SMTPException, TimeoutError, Exception) as e:
            email.mark_failed(e)
            logger.error(f" Failed email {email.id}: {e}")

    logger.info("Email cron job completed.")
