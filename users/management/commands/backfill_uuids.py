
from django.core.management.base import BaseCommand
from django.db import transaction
import uuid


class Command(BaseCommand):
    help = 'Backfill UUID values for existing InterventionProposal records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--start-id',
            type=int,
            default=1,
            help='Start ID (default: 1)',
        )
        parser.add_argument(
            '--end-id',
            type=int,
            default=None,
            help='End ID (default: update all)',
        )

    def handle(self, *args, **options):
        from users.models import InterventionProposal, ProposalDocument
        
        dry_run = options['dry_run']
        start_id = options['start_id']
        end_id = options['end_id']
        
        # Build query
        proposals_query = InterventionProposal.objects.filter(id__gte=start_id)
        if end_id:
            proposals_query = proposals_query.filter(id__lte=end_id)
        
        proposals = proposals_query.order_by('id')
        total = proposals.count()
        
        if dry_run:
            self.stdout.write(self.style.WARNING(f'DRY RUN: Would update {total} proposals'))
        else:
            self.stdout.write(f'Updating {total} proposals...')
        
        updated_proposals = 0
        updated_documents = 0
        
        for proposal in proposals:
            try:
                with transaction.atomic():
                    # Check if UUID already exists
                    if hasattr(proposal, 'uuid') and proposal.uuid:
                        self.stdout.write(f'  Proposal {proposal.id} already has UUID: {proposal.uuid}')
                        continue
                    
                    # Generate and assign UUID
                    new_uuid = uuid.uuid4()
                    
                    if not dry_run:
                        proposal.uuid = new_uuid
                        proposal.save(update_fields=['uuid'])
                        updated_proposals += 1
                    else:
                        self.stdout.write(f'  Would assign UUID {new_uuid} to proposal {proposal.id}')
                    
                    # Update related documents
                    documents = proposal.documents.all()
                    for doc in documents:
                        if hasattr(doc, 'uuid') and not doc.uuid:
                            doc_uuid = uuid.uuid4()
                            if not dry_run:
                                doc.uuid = doc_uuid
                                doc.save(update_fields=['uuid'])
                                updated_documents += 1
                            else:
                                self.stdout.write(f'    Would assign UUID {doc_uuid} to document {doc.id}')
                    
                    if not dry_run and updated_proposals % 10 == 0:
                        self.stdout.write(f'  Processed {updated_proposals}/{total}...')
                        
            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f'Error updating proposal {proposal.id}: {e}')
                )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'\nDRY RUN COMPLETE: Would update {total} proposals and their documents'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nSuccessfully updated:\n'
                    f'  - {updated_proposals} proposals\n'
                    f'  - {updated_documents} documents'
                )
            )
