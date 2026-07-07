from django.core.cache import cache
from app.models import CriteriaInformation

CACHE_TTL = 60 * 15


def _cache_key(target_type: str, target_id: str) -> str:
    return f"criteria_info:{target_type}:{target_id}"


def _target_of(obj: CriteriaInformation) -> tuple[str, str] | None:
    if obj.intervention_id:
        return ("intervention", str(obj.intervention_id))
    if obj.national_proposal_id:
        return ("national_proposal", str(obj.national_proposal_id))
    return None


def _fetch_from_db(target_type: str, target_id: str) -> list:
    field = "intervention_id" if target_type == "intervention" else "national_proposal_id"
    qs = (
        CriteriaInformation.objects
        .filter(**{field: target_id})
        .select_related("intervention", "national_proposal", "created_by")
    )
    return list(qs)


def get_criteria_for_target(target_type: str, target_id: str) -> list:
    key = _cache_key(target_type, target_id)
    cached = cache.get(key)
    if cached is not None:
        return cached
    result = _fetch_from_db(target_type, target_id)
    cache.set(key, result, CACHE_TTL)
    return result


# Back-compat shim — intervention-only callers
def get_criteria_for_intervention(intervention_id: str) -> list:
    return get_criteria_for_target("intervention", intervention_id)


def _invalidate(obj: CriteriaInformation) -> None:
    target = _target_of(obj)
    if target:
        cache.delete(_cache_key(*target))


def create_criteria(validated_data: dict, user) -> CriteriaInformation:
    obj = CriteriaInformation.objects.create(created_by=user, **validated_data)
    _invalidate(obj)
    return obj


def update_criteria(instance: CriteriaInformation, validated_data: dict) -> CriteriaInformation:
    for attr, value in validated_data.items():
        setattr(instance, attr, value)
    instance.save(update_fields=list(validated_data.keys()) + ["updated_at"])
    _invalidate(instance)
    return instance