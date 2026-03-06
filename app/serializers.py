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


class InterventionScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterventionScore
        fields = "__all__"
        read_only_fields = ("reviewer",)