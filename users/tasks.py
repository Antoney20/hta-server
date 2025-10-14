from celery import shared_task, current_task
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
import logging
import os
import uuid

from django.core.exceptions import ObjectDoesNotExist
from .models import InterventionProposal
from .utils.email import (
    send_confirmation_email,
    send_password_change_confirmation,
    send_password_reset_email
)



from members.models import ProposalTracker
from .models import ProposalSubmission, InterventionProposal, ProposalDocument, ProposalSubmissionStatus, TemporaryFile

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def retry_failed_proposal_submission(self, submission_id):
    """Retry processing for failed aspects of a proposal submission"""
    try:
        submission = ProposalSubmission.objects.get(submission_id=submission_id)
        submission.status = ProposalSubmissionStatus.PROCESSING
        submission.processing_started_at = timezone.now()
        submission.task_id = self.request.id
        submission.attempts += 1
        submission.save()
        
        proposal = submission.proposal
        if not proposal:
            raise ValueError("No proposal associated with this submission")
        
        files_processed = 0
        file_errors = []
        email_sent = False
        
        for temp_file in submission.temp_files.all():
            try:
                process_single_file(proposal.id, temp_file.id)
                files_processed += 1
                print(f"✓ Processed file: {temp_file.original_name}")
            except Exception as file_error:
                file_errors.append(f"Failed to process {temp_file.original_name}: {str(file_error)}")
                print(f"✗ Failed to process file: {temp_file.original_name} - {file_error}")
                logger.error(f"Error processing file {temp_file.original_name}: {file_error}")

        if "Failed to send confirmation email" in submission.error_message:
            try:
                email_sent = send_confirmation_email(proposal)
                if email_sent:
                    print(f"✓ Confirmation email sent successfully to: {proposal.email}")
                else:
                    file_errors.append("Failed to send confirmation email")
            except Exception as email_error:
                file_errors.append(f"Email error: {str(email_error)}")
                logger.error(f"Error sending confirmation email for proposal {proposal.id}: {email_error}")

        if file_errors:
            submission.status = ProposalSubmissionStatus.FAILED
            submission.error_message = "; ".join(file_errors)
            submission.save()
            
            logger.error(f"Retry partially failed for submission {submission_id}: {file_errors}")
            return f"Retry completed with errors for submission {submission_id}: {len(file_errors)} errors"
        else:
            submission.status = ProposalSubmissionStatus.COMPLETED
            submission.error_message = ""
            submission.processing_completed_at = timezone.now()
            submission.save()
            
            logger.info(f"Retry completed successfully for submission {submission_id}")
            return f"Retry completed successfully for submission {submission_id}. Files processed: {files_processed}, Email sent: {email_sent}"
        
    except ProposalSubmission.DoesNotExist:
        logger.error(f"ProposalSubmission {submission_id} not found")
        raise Exception(f"ProposalSubmission {submission_id} not found")
        
    except Exception as exc:
        try:
            submission = ProposalSubmission.objects.get(submission_id=submission_id)
            submission.error_message = str(exc)
            submission.status = ProposalSubmissionStatus.RETRYING if submission.attempts < submission.max_attempts else ProposalSubmissionStatus.FAILED
            submission.save()
        except:
            pass  
        
        logger.error(f"Error in retry for submission {submission_id}: {exc}")
        print(f"✗ Retry failed for submission {submission_id}: {exc}")
        
        # Retry with exponential backoff if we haven't exceeded max attempts
        if submission.attempts < submission.max_attempts:
            raise self.retry(exc=exc, countdown=60 * (2 ** submission.attempts))
        else:
            # Mark as permanently failed
            try:
                submission.status = ProposalSubmissionStatus.FAILED
                submission.save()
            except:
                pass
            print(f"✗ Max retries reached for submission {submission_id}")
            raise exc

def process_single_file(proposal_id, temp_file_id):
    """Process a single temporary file"""
    try:
        proposal = InterventionProposal.objects.get(id=proposal_id)
        temp_file = TemporaryFile.objects.get(id=temp_file_id)
        
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        name, ext = os.path.splitext(temp_file.original_name)
        new_filename = f'{name}_{timestamp}{ext}'
        
        with temp_file.file.open('rb') as f:
            content = f.read()
            
        doc = ProposalDocument.objects.create(
            proposal=proposal,
            original_name=temp_file.original_name
        )
        
        doc.document.save(new_filename, ContentFile(content))
        
        # Clean up temporary file
        temp_file.file.delete()
        temp_file.delete()
        

    except Exception as exc:
        logger.error(f"Error processing file for proposal {proposal_id}: {exc}")
        raise exc
    
    
    
 



@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_proposal_confirmation_email_task(self, proposal_id):
    """Celery task to send confirmation email asynchronously"""
    try:
        proposal = InterventionProposal.objects.get(id=proposal_id)
        sent = send_confirmation_email(proposal)
        if not sent:
            logger.warning(f"[Task {self.request.id}] Failed to send confirmation email for proposal {proposal_id}")
        return sent
    except ObjectDoesNotExist:
        logger.error(f"[Task {self.request.id}] Proposal {proposal_id} not found")
        return False
    except Exception as e:
        logger.exception(f"[Task {self.request.id}] Error sending confirmation email for proposal {proposal_id}: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_password_reset_email_task(self, user_id, token):
    """Send password reset email asynchronously"""
    try:
        sent = send_password_reset_email(user_id, token)
        if not sent:
            logger.warning(f"Password reset email failed for user {user_id}")
        return sent
    except Exception as e:
        logger.exception(f"Error in password reset email for user {user_id}: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_password_change_confirmation_task(self, user_id):
    """Send password change confirmation asynchronously"""
    try:
        sent = send_password_change_confirmation(user_id)
        if not sent:
            logger.warning(f"Password change confirmation email failed for user {user_id}")
        return sent
    except Exception as e:
        logger.exception(f"Error sending password change confirmation for user {user_id}: {e}")
        raise self.retry(exc=e)
    
    
    