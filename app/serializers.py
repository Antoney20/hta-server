from rest_framework import serializers

from users.models import InterventionProposal
from .models import CriteriaInformation, DecisionType, FeedbackCategory, FeedbackEmailLog, InterventionStatusUpdate, SelectionTool, SystemCategory, InterventionSystemCategory, InterventionScore


class SelectionToolSerializer(serializers.ModelSerializer):
    class Meta:
        model = SelectionTool
        fields = "__all__"


class SystemCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemCategory
        fields = "__all__"


class InterventionSystemCategorySerializer(serializers.ModelSerializer):
    system_category_detail = SystemCategorySerializer(
        source="system_category",
        read_only=True
    )

    class Meta:
        model = InterventionSystemCategory
        fields = [
            "id",
            "intervention",
            "system_category",
            "system_category_detail",
            "assigned_by",
            "created_at",
        ]



class CriteriaInformationSerializer(serializers.ModelSerializer):
    intervention_name = serializers.CharField(
        source="intervention.intervention_name", read_only=True
    )
    intervention_reference_number = serializers.CharField(
        source="intervention.reference_number", read_only=True
    )
    system_category_name = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(
        source="created_by.get_full_name", read_only=True
    )
 
    class Meta:
        model = CriteriaInformation
        fields = [
            "id",
            "intervention",
            "intervention_name",
            "intervention_reference_number",
            "system_category_name",
            "created_by",
            "created_by_name",
            "brief_info",
            "clinical_effectiveness",
            "burden_of_disease",
            "bod_type",
            "population",
            "equity",
            "cost_effectiveness",
            "budget_impact_affordability",
            "feasibility_of_implementation",
            "catastrophic_health_expenditure",
            "access_to_healthcare",
            "congruence_with_health_priorities",
            "additional_info",
            "created_at",
            "updated_at",
        ]
 
    def get_system_category_name(self, obj) -> str | None:
        """
        Resolve the system category name via InterventionSystemCategory.
        Returns None if no category has been assigned to the intervention.
        """
        isc = (
            InterventionSystemCategory.objects
            .select_related("system_category")
            .filter(intervention=obj.intervention)
            .first()
        )
        return isc.system_category.name if isc else None

class CriteriaInformationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CriteriaInformation
        fields = [
            "intervention", 
            "brief_info", "clinical_effectiveness",
            "burden_of_disease", "bod_type", "population",
            "equity", "cost_effectiveness",
            "budget_impact_affordability",
            "feasibility_of_implementation",
            "catastrophic_health_expenditure",
            "access_to_healthcare",
            "congruence_with_health_priorities",
            "additional_info",
        ]


class InterventionScoreCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterventionScore
        fields = ["id", "intervention", "criteria", "score", "comment"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        comment = (attrs.get("comment") or "").strip()
        score = attrs.get("score")
        if comment and not score:
            raise serializers.ValidationError({
                "score": "A score must be selected when a comment is provided."
            })
        return attrs

class InterventionScoreSerializer(serializers.ModelSerializer):
    """Used for GET — enriched with reviewer + intervention details."""
    reviewer_name = serializers.SerializerMethodField()
    reviewer_email = serializers.SerializerMethodField()
    intervention_name = serializers.SerializerMethodField()
    intervention_reference = serializers.SerializerMethodField()

    class Meta:
        model = InterventionScore
        fields = [
            "id", "score", "comment", "created_at", "updated_at",
            "reviewer", "intervention", "criteria",
            "reviewer_name", "reviewer_email",
            "intervention_name", "intervention_reference",
        ]
        read_only_fields = fields  

    def get_reviewer_name(self, obj) -> str:
        return  obj.reviewer.username

    def get_reviewer_email(self, obj) -> str:
        return obj.reviewer.email

    def get_intervention_name(self, obj) -> str:
        return getattr(obj.intervention, "intervention_name", str(obj.intervention))

    def get_intervention_reference(self, obj) -> str:
        return getattr(obj.intervention, "reference_number", "")




class PublicProposalSerializer(serializers.ModelSerializer):
    date = serializers.SerializerMethodField()
    justification = serializers.SerializerMethodField()  

    class Meta:
        model = InterventionProposal
        fields = [
            "id",
            "reference_number",
            "intervention_name",
            "intervention_type",
            "beneficiary",
            "justification",  
            "expected_impact",
            "date",
        ]

    def get_date(self, obj):
        """
        Return ISO date format: YYYY-MM-DD
        """
        if obj.submitted_at:
            return obj.submitted_at.strftime("%Y-%m-%d")
        return None

    def get_justification(self, obj):
        """
        Ensure a clean fallback instead of null/empty.
        """
        return obj.justification or "No justification provided"
    
    
class DecisionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DecisionType
        fields = ["id", "name", "description"]

class DecisionTypeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DecisionType
        fields = ["name", "description"]


class InterventionStatusUpdateSerializer(serializers.ModelSerializer):
    reference_number = serializers.CharField(source="intervention.reference_number")
    intervention_id = serializers.CharField(source="intervention.id")
    intervention_name = serializers.CharField(source="intervention.intervention_name")
    decision = DecisionTypeSerializer(read_only=True)
    system_categories = serializers.SerializerMethodField()
    is_scored = serializers.BooleanField(read_only=True)  # from annotation

    class Meta:
        model = InterventionStatusUpdate
        fields = [
            "id",
            "reference_number",
            "intervention_id",
            "intervention_name",
            "decision",
            "decision_date",
            "feedback",
            "system_categories",
            "is_scored",
            "created_at",
            "updated_at",
        ]

    def get_system_categories(self, obj):
        return list(
            obj.intervention.system_categories.values_list(
                "system_category__name", flat=True
            )
        )
        
        

class InterventionStatusUpdateWriteSerializer(serializers.ModelSerializer):
    """Write — secretariat / admin only."""

    class Meta:
        model = InterventionStatusUpdate
        fields = [
            "intervention",
            "decision",
            "decision_date",
            "feedback",
            "additional_info",
        ]

    def validate(self, attrs):
        # decision_date is required when a formal decision is set
        if attrs.get("decision") and not attrs.get("decision_date"):
            raise serializers.ValidationError(
                {"decision_date": "A decision date is required when setting a decision."}
            )
        return attrs





class FeedbackCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = FeedbackCategory
        fields = ["id", "name", "description", "subject", "template", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
 
 
class FeedbackCategoryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = FeedbackCategory
        fields = ["name", "description", "subject", "template", "is_active"]
 
 
# ─────────────────────────────────────────────
#  FeedbackEmailLog
# ─────────────────────────────────────────────
 
class FeedbackEmailLogSerializer(serializers.ModelSerializer):
    """Read serializer — full detail with nested labels + decision from latest status update."""
 
    category_name     = serializers.CharField(source="category.name",                  read_only=True)
    sent_by_name      = serializers.SerializerMethodField()
    intervention_id   = serializers.UUIDField(source="intervention.id",                read_only=True)
    intervention_name = serializers.CharField(source="intervention.intervention_name", read_only=True)
    reference_number  = serializers.CharField(source="intervention.reference_number",  read_only=True)
 
    # decision info pulled from the latest InterventionStatusUpdate
    decision     = serializers.SerializerMethodField()
    decision_date = serializers.SerializerMethodField()
    is_discussed  = serializers.SerializerMethodField()
 
    class Meta:
        model  = FeedbackEmailLog
        fields = [
            "id",
            "intervention_id",
            "intervention_name",
            "reference_number",
            "category",
            "category_name",
            "is_discussed",
            "decision",
            "decision_date",
            "subject_sent",
            "message_sent",
            "recipient",
            "sender",
            "status",
            "error_message",
            "retry_count",
            "last_attempt",
            "sent_by",
            "sent_by_name",
            "created_at",
            "sent_at",
        ]
        read_only_fields = fields
 
    def get_sent_by_name(self, obj) -> str | None:
        if obj.sent_by:
            return obj.sent_by.get_full_name() or obj.sent_by.username
        return None
 
    def _latest_su(self, obj):
        """Fetch and cache the latest status update per log instance to avoid N+1."""
        if not hasattr(obj, "_cached_su"):
            su = (
                obj.intervention.status_updates
                .select_related("decision")
                .order_by("-created_at")
                .first()
            )
            obj._cached_su = su
        return obj._cached_su
 
    def get_is_discussed(self, obj) -> bool:
        return self._latest_su(obj) is not None
 
    def get_decision(self, obj) -> str | None:
        su = self._latest_su(obj)
        return str(su.decision) if su and su.decision else None
 
    def get_decision_date(self, obj) -> str | None:
        su = self._latest_su(obj)
        return su.decision_date.strftime("%d %B %Y") if su and su.decision_date else None
 


