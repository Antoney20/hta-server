PENDING_DECISION_NAME = "Pending"

def get_pending_decision():
    """Returns the id of the 'Pending' DecisionType, creating it if needed."""
    from app.models import DecisionType
    obj, _ = DecisionType.objects.get_or_create(
        name=PENDING_DECISION_NAME,
        defaults={"description": "This is system generated, acts as a default fallback for proposals without a decision type (but proceeded to the panel for appraisal)"},
    )
    return obj.id