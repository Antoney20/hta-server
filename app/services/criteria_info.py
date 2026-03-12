from django.core.cache import cache
from app.models import CriteriaInformation

CACHE_TTL = 60 * 1


def _cache_key(intervention_id: str) -> str:
    return f"criteria_info:{intervention_id}"


def _fetch_from_db(intervention_id: str) -> list:
    qs = (
        CriteriaInformation.objects
        .filter(intervention_id=intervention_id)
        .select_related("intervention",  "created_by")
        .only(
            "id", "brief_info", "clinical_effectiveness",
            "burden_of_disease", "bod_type", "population",
            "equity", "cost_effectiveness",
            "budget_impact_affordability",
            "feasibility_of_implementation",
            "catastrophic_health_expenditure",
            "access_to_healthcare",
            "congruence_with_health_priorities",
            "additional_info", "created_at", "updated_at",
            "intervention__id", "intervention__name",
            "created_by__id", "created_by__first_name", "created_by__last_name",
        )
    )
    return list(qs)  


def get_criteria_for_intervention(intervention_id: str) -> list:
    key = _cache_key(intervention_id)
    cached = cache.get(key)
    if cached is not None:
        return cached
    result = _fetch_from_db(intervention_id)
    cache.set(key, result, CACHE_TTL)
    return result


def _invalidate(intervention_id: str) -> None:
    cache.delete(_cache_key(str(intervention_id)))


def create_criteria(validated_data: dict, user) -> CriteriaInformation:
    obj = CriteriaInformation.objects.create(created_by=user, **validated_data)
    _invalidate(validated_data["intervention"].id)
    return obj


def update_criteria(instance: CriteriaInformation, validated_data: dict) -> CriteriaInformation:
    for attr, value in validated_data.items():
        setattr(instance, attr, value)
    instance.save(update_fields=list(validated_data.keys()) + ["updated_at"])
    _invalidate(instance.intervention_id)
    return instance