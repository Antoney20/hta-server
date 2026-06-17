"""
Protocol service layer for scoring models and protocol guides.

Owns all business logic; viewsets stay thin. Includes the deterministic scoring
engine (evidence field -> score via the protocol rules). The engine never
invents a score: it only maps stated evidence to a rule band, so every score is
traceable to the value and condition that produced it.
"""

import re

from django.db import transaction
from django.utils import timezone

from app.models import ProtocolGuide, ScoringModel

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")

_OPERATORS = {
    "<":  lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">":  lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "in": lambda a, b: a in b,
    "between": lambda a, b: b[0] <= a <= b[1],  # value = [low, high], inclusive
}


def coerce_number(value):
    """
    Pull a comparable number out of stored evidence values such as "97 %",
    "0.12", "178 per 100,000 women". Returns None for categorical codes like
    "E1" / "R2" / "N0" (letter-led), so they compare as strings.
    """
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    s = str(value).strip()
    if s[:1].isalpha():
        return None
    m = _NUM_RE.search(s)
    return float(m.group()) if m else None


def _resolve(row_value, target):
    rv = coerce_number(row_value)
    if isinstance(target, list):
        coerced = [coerce_number(t) if coerce_number(t) is not None else t for t in target]
        return (rv if rv is not None else str(row_value).strip()), coerced
    tv = coerce_number(target)
    if rv is not None and tv is not None:
        return rv, tv
    return str(row_value).strip(), str(target).strip()


def _clause_true(row, clause):
    op = _OPERATORS.get(clause.get("op"))
    field = clause.get("field")
    if op is None or field is None or field not in row:
        return False
    left, right = _resolve(row[field], clause.get("value"))
    try:
        return bool(op(left, right))
    except (TypeError, ValueError):
        return False


def _condition_matches(row, condition):
    if condition.get("else"):
        return True
    if "all" in condition:
        return all(_clause_true(row, c) for c in condition["all"])
    if "any" in condition:
        return any(_clause_true(row, c) for c in condition["any"])
    return False


def _score_criterion(row, criterion_rules):
    for condition in criterion_rules.get("conditions", []):
        if _condition_matches(row, condition):
            used = {}
            for c in condition.get("all", []) + condition.get("any", []):
                f = c.get("field")
                if f in row:
                    used[f] = row[f]
            return {
                "score": condition.get("score"),
                "label": condition.get("label", ""),
                "evidence": used,
            }
    return {"score": None, "label": "No rule matched", "evidence": {}}


def apply_protocol(row, rules):
    """Score one evidence row against a rules dict. Auditable per criterion."""
    return {
        criterion: _score_criterion(row, criterion_rules)
        for criterion, criterion_rules in (rules or {}).items()
    }


def score_rows(rows, rules):
    """Score every row, keyed by intervention_ref."""
    results = {}
    for row in rows or []:
        ref = row.get("intervention_ref")
        if ref:
            results[ref] = apply_protocol(row, rules)
    return results


def list_scoring_models():
    return ScoringModel.objects.all()


def create_scoring_model(**data):
    data.setdefault("status", ScoringModel.Status.DRAFT)
    return ScoringModel.objects.create(**data)


def update_scoring_model(instance, **data):
    for key, value in data.items():
        setattr(instance, key, value)
    instance.save()
    return instance


@transaction.atomic
def score_scoring_model(instance, guide):
    """Apply a ProtocolGuide's rules to every row; record what scored it."""
    instance.scores = {
        "protocol": {
            "name": guide.name,
            "version": guide.version,
            "scored_at": timezone.now().isoformat(),
        },
        "results": score_rows(instance.rows, guide.rules),
    }
    instance.status = ScoringModel.Status.SCORED
    instance.save(update_fields=["scores", "status", "updated_at"])
    return instance


def finalize_scoring_model(instance):
    instance.status = ScoringModel.Status.FINAL
    instance.save(update_fields=["status", "updated_at"])
    return instance


def delete_scoring_model(instance):
    instance.delete()


# ---------------------------------------------------------------------------
# ProtocolGuide services
# ---------------------------------------------------------------------------
def list_protocol_guides():
    return ProtocolGuide.objects.all()


def get_active_protocol():
    return ProtocolGuide.objects.filter(is_active=True).first()


def resolve_protocol(*, protocol_id=None, version=None):
    """Pick a guide by id, then by version, else the active one."""
    if protocol_id:
        return ProtocolGuide.objects.filter(pk=protocol_id).first()
    if version:
        return ProtocolGuide.objects.filter(version=version).first()
    return get_active_protocol()


@transaction.atomic
def create_protocol_guide(**data):
    make_active = data.get("is_active", False)
    guide = ProtocolGuide.objects.create(**data)
    if make_active:
        ProtocolGuide.objects.filter(is_active=True).exclude(pk=guide.pk).update(is_active=False)
    return guide


@transaction.atomic
def update_protocol_guide(instance, **data):
    for key, value in data.items():
        setattr(instance, key, value)
    instance.save()
    if instance.is_active:
        ProtocolGuide.objects.filter(is_active=True).exclude(pk=instance.pk).update(is_active=False)
    return instance


@transaction.atomic
def activate_protocol_guide(instance):
    ProtocolGuide.objects.filter(is_active=True).exclude(pk=instance.pk).update(is_active=False)
    if not instance.is_active:
        instance.is_active = True
        instance.save(update_fields=["is_active", "updated_at"])
    return instance


def delete_protocol_guide(instance):
    instance.delete()