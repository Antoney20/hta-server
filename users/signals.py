from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import ProposalSubmission, ProposalSubmissionStatus
from .tasks import retry_failed_proposal_submission

@receiver(post_save, sender=ProposalSubmission)
def auto_retry_failed_submission(sender, instance, created, **kwargs):
    """
    Automatically queue Celery retry tasks for:
    1. The current failed submission (if retries left)
    2. Any other previously failed submissions that still have retries left
    """
    # Skip brand-new PENDING ones
    if created and instance.status != ProposalSubmissionStatus.FAILED:
        return

    def queue_retry(sub):
        """Helper to enqueue retry with exponential delay"""
        countdown = 30 * (2 ** sub.attempts)
        retry_failed_proposal_submission.apply_async(
            args=[str(sub.submission_id)],
            countdown=countdown
        )
        sub.status = ProposalSubmissionStatus.RETRYING
        sub.error_message = "Auto requeued via signal"
        sub.save(update_fields=["status", "error_message"])
        print(f"🔁 Queued retry for {sub.submission_id} (attempt {sub.attempts + 1}) in {countdown}s")

    # Handle the current instance if it's failed
    if instance.status == ProposalSubmissionStatus.FAILED and instance.attempts < instance.max_attempts:
        queue_retry(instance)

    # Also check for any older failed submissions that still have retries left
    failed_others = ProposalSubmission.objects.filter(
        status=ProposalSubmissionStatus.FAILED,
        attempts__lt=3
    ).exclude(pk=instance.pk)

    if failed_others.exists():
        print(f"📦 Found {failed_others.count()} old failed submissions. Queuing retries...")
        for sub in failed_others:
            queue_retry(sub)
