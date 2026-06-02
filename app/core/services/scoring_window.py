from rest_framework.exceptions import PermissionDenied
from app.models import InterventionScoringWindow



def _is_admin(user) -> bool:
    return user.is_authenticated and (
        user.is_staff or user.is_superuser
        or user.groups.filter(name__in=["admin"]).exists()
    )


class ScoringWindowService:

    @classmethod
    def list(cls, params: dict | None = None):
        params = params or {}
        qs = InterventionScoringWindow.objects.select_related("intervention", "created_by")
        if iv := params.get("intervention"):
            qs = qs.filter(intervention_id=iv)
        if ref := params.get("ref"):
            qs = qs.filter(intervention__reference_number=ref)
        if lvl := params.get("level"):
            qs = qs.filter(level=lvl)
        return qs

    @classmethod
    def create(cls, user, serializer):
        if not _is_admin(user):
            raise PermissionDenied("Only admins can create scoring windows.")
        return serializer.save(created_by=user, updated_by=user)

    @classmethod
    def update(cls, user, serializer):
        if not _is_admin(user):
            raise PermissionDenied("Only admins can modify scoring windows.")
        return serializer.save(updated_by=user)

    @classmethod
    def delete(cls, user, instance):
        if not _is_admin(user):
            raise PermissionDenied("Only admins can delete scoring windows.")
        instance.delete()