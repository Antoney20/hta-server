from rest_framework import serializers

from users.models import InterventionProposal
from .models import CriteriaInformation, SelectionTool, SystemCategory, InterventionSystemCategory, InterventionScore


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


# class InterventionScoreCreateSerializer(serializers.ModelSerializer):
#     """Used for POST/PATCH — minimal fields, reviewer injected from request."""
#     class Meta:
#         model = InterventionScore
#         fields = ["id", "intervention", "criteria", "score", "comment"]
#         read_only_fields = ["id"]


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
        read_only_fields = fields  # everything is read-only on GET

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