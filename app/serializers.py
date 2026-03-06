from rest_framework import serializers
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


# class InterventionScoreSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = InterventionScore
#         fields = "__all__"
#         read_only_fields = ("reviewer",)


# class InterventionScoreSerializer(serializers.ModelSerializer):
#     # Reviewer details
#     reviewer_name = serializers.SerializerMethodField()
#     reviewer_email = serializers.SerializerMethodField()

#     # Intervention details
#     intervention_name = serializers.SerializerMethodField()
#     intervention_reference = serializers.SerializerMethodField()

#     class Meta:
#         model = InterventionScore
#         fields = [
#             "id",
#             "score",
#             "comment",
#             "created_at",
#             "updated_at",
#             # FKs (raw ids for writes)
#             "reviewer",
#             "intervention",
#             "criteria",
#             # Enriched read fields
#             "reviewer_name",
#             "reviewer_email",
#             "intervention_name",
#             "intervention_reference",
#         ]
#         read_only_fields = ("reviewer", "reviewer_name", "reviewer_email",
#                             "intervention_name", "intervention_reference")

#     def get_reviewer_name(self, obj) -> str:
#         return  obj.reviewer.username

#     def get_reviewer_email(self, obj) -> str:
#         return obj.reviewer.email

#     def get_intervention_name(self, obj) -> str:
#         return getattr(obj.intervention, "intervention_name", str(obj.intervention))

#     def get_intervention_reference(self, obj) -> str:
#         return getattr(obj.intervention, "reference_number", "")




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
