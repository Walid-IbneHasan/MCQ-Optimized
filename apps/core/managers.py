from django.db import models
from django.utils import timezone


class SoftDeleteManager(models.Manager):
    """
    Manager for models with soft delete functionality.
    """

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def with_deleted(self):
        """Include soft deleted objects"""
        return super().get_queryset()

    def only_deleted(self):
        """Only soft deleted objects"""
        return super().get_queryset().filter(is_deleted=True)
