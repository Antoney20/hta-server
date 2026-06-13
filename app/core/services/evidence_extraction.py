from django.db import transaction

from app.models import EvidenceExtraction
from users.models import UserRole

ADD_ROLES = {UserRole.ADMIN, UserRole.SECRETARIAT, UserRole.ASSESSMENT}   # SWG etc. excluded
EDIT_ROLES = {UserRole.ADMIN, UserRole.SECRETARIAT}                       # + the owner

# fields the client may set on create/update
_WRITABLE = (
    "national_proposal", "intervention_proposal", "routing_decision", "icd_11",
    "disease_definition", "registrar", "assigned_person", "data",
)


class EvidenceExtractionService:
    """Business logic + permission policy for evidence extraction. Viewset stays thin."""

    @staticmethod
    def queryset():
        return EvidenceExtraction.objects.select_related(
            "created_by", "national_proposal", "intervention_proposal",
        )

    # ---- permission policy ----
    @staticmethod
    def can_add(user):
        return getattr(user, "role", None) in ADD_ROLES

    @staticmethod
    def can_edit(user, obj):
        role = getattr(user, "role", None)
        is_owner = obj.created_by_id is not None and obj.created_by_id == getattr(user, "id", None)
        return role in EDIT_ROLES or is_owner

    @staticmethod
    def can_delete(user):
        return getattr(user, "role", None) == UserRole.ADMIN

    # ---- crud ----
    @staticmethod
    @transaction.atomic
    def create(*, user=None, **fields):
        obj = EvidenceExtraction(created_by=_actor(user))
        for f in _WRITABLE:
            if fields.get(f) is not None:
                setattr(obj, f, fields[f])
        obj.full_clean()        # exactly-one-proposal + required-variable + uniqueness checks
        obj.save()
        return obj

    @staticmethod
    @transaction.atomic
    def update(obj, **fields):
        for f in _WRITABLE:
            if f in fields and fields[f] is not None:
                setattr(obj, f, fields[f])
        obj.full_clean()
        obj.save()
        return obj


def _actor(user):
    return user if getattr(user, "is_authenticated", False) else None