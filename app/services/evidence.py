from django.db import transaction

from app.models import (
    AssessmentEvidence,
    AssessmentEvidenceDocument,
    InterventionProposal,
    NationalProgramProposal,
)


class AssessmentEvidenceService:
    """All business logic for assessment evidence. Viewset stays thin."""

    @staticmethod
    def queryset():
        return (
            AssessmentEvidence.objects
            .select_related("created_by")
            .prefetch_related("documents", "interventions", "program_proposals")
        )

    @staticmethod
    @transaction.atomic
    def create(*, summary="", intervention_ids=None, program_proposal_ids=None,
               documents=None, user=None):
        evidence = AssessmentEvidence.objects.create(
            summary=summary or "",
            created_by=_actor(user),
        )
        AssessmentEvidenceService._sync_targets(evidence, intervention_ids, program_proposal_ids)
        AssessmentEvidenceService._add_documents(evidence, documents or [], user)
        return evidence

    @staticmethod
    @transaction.atomic
    def update(evidence, *, summary=None, intervention_ids=None,
               program_proposal_ids=None, documents=None, user=None):
        if summary is not None:
            evidence.summary = summary
            evidence.save(update_fields=["summary", "updated_at"])

        if intervention_ids is not None or program_proposal_ids is not None:
            AssessmentEvidenceService._sync_targets(evidence, intervention_ids, program_proposal_ids)

        if documents:  # append, never silently wipe existing files
            AssessmentEvidenceService._add_documents(evidence, documents, user)
        return evidence

    @staticmethod
    def add_document(evidence, *, file, description="", user=None):
        return AssessmentEvidenceDocument.objects.create(
            evidence=evidence, file=file, description=description or "", uploaded_by=_actor(user),
        )

    @staticmethod
    def delete_document(document):
        document.delete()

    # internals
    @staticmethod
    def _sync_targets(evidence, intervention_ids, program_proposal_ids):
        if intervention_ids is not None:
            evidence.interventions.set(InterventionProposal.objects.filter(id__in=intervention_ids))
        if program_proposal_ids is not None:
            evidence.program_proposals.set(NationalProgramProposal.objects.filter(id__in=program_proposal_ids))

    @staticmethod
    def _add_documents(evidence, documents, user):
        """documents: iterable of {"file": <UploadedFile>, "description": str}.
        Saved one-by-one (not bulk_create) so FileField storage runs."""
        actor = _actor(user)
        for d in documents:
            f = d.get("file")
            if not f:
                continue
            AssessmentEvidenceDocument(
                evidence=evidence, file=f,
                description=d.get("description", "") or "", uploaded_by=actor,
            ).save()


def _actor(user):
    return user if getattr(user, "is_authenticated", False) else None