from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.core.cache import cache
from .models import UserPermission
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


@receiver(post_save, sender=User)
def user_post_save(sender, instance, created, **kwargs):
    """
    Handle user post save operations.
    """
    if created:
        logger.info(f"New user created: {instance.phone_number}")

        # Create default permissions for different roles
        if instance.role in ["teacher", "moderator", "admin"]:
            # Add default permissions based on role
            from .models import Permission

            role_permissions = {
                "teacher": ["create_exam", "create_question", "view_results"],
                "moderator": [
                    "create_exam",
                    "create_question",
                    "view_results",
                    "manage_students",
                ],
                "admin": [
                    "create_exam",
                    "create_question",
                    "view_results",
                    "manage_students",
                    "manage_permissions",
                ],
            }

            permissions_to_add = role_permissions.get(instance.role, [])
            for perm_name in permissions_to_add:
                try:
                    permission = Permission.objects.get(name=perm_name)
                    UserPermission.objects.get_or_create(
                        user=instance,
                        permission=permission,
                        defaults={"is_granted": True},
                    )
                except Permission.DoesNotExist:
                    logger.warning(f"Permission {perm_name} does not exist")


@receiver(post_save, sender=UserPermission)
@receiver(post_delete, sender=UserPermission)
def clear_user_permission_cache(sender, instance, **kwargs):
    """
    Clear user permission cache when permissions change.
    """
    cache_key = f"user_permissions:{instance.user.id}"
    cache.delete(cache_key)
    logger.info(f"Cleared permission cache for user: {instance.user.phone_number}")
