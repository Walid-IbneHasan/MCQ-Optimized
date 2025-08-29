from rest_framework import serializers


class BaseSerializer(serializers.ModelSerializer):
    """
    Base serializer with common functionality.
    """

    def to_representation(self, instance):
        """
        Convert model instance to dictionary representation.
        """
        data = super().to_representation(instance)

        # Remove null values if requested
        if getattr(self.Meta, "exclude_null", False):
            data = {key: value for key, value in data.items() if value is not None}

        return data
