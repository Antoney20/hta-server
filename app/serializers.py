from rest_framework import serializers

from users.models import InterventionProposal
from .models import SelectionTool, SystemCategory, InterventionSystemCategory, InterventionScore


class SelectionToolSerializer(serializers.ModelSerializer):
    class Meta:
        model = SelectionTool
        fields = "__all__"


class SystemCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemCategory
        fields = "__all__"


class InterventionSystemCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = InterventionSystemCategory
        fields = "__all__"




class InterventionScoreCreateSerializer(serializers.ModelSerializer):
    """Used for POST/PATCH — minimal fields, reviewer injected from request."""
    class Meta:
        model = InterventionScore
        fields = ["id", "intervention", "criteria", "score", "comment"]
        read_only_fields = ["id"]


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