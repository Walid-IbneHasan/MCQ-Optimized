from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.db.models import Count, Q
from .models import (
    NotificationType,
    NotificationPreference,
    Notification,
    NotificationTemplate,
    NotificationLog,
    BulkNotification,
)


@admin.register(NotificationType)
class NotificationTypeAdmin(admin.ModelAdmin):
    list_display = [
        "display_name",
        "name",
        "priority",
        "is_system_generated",
        "default_delivery_methods",
        "is_active",
        "created_at",
    ]
    list_filter = [
        "priority",
        "is_system_generated",
        "is_active",
        "default_email",
        "default_sms",
        "default_in_app",
        "created_at",
    ]
    search_fields = ["name", "display_name", "description"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("name", "display_name", "description", "is_active")},
        ),
        ("Notification Behavior", {"fields": ("priority", "is_system_generated")}),
        (
            "Default Delivery Methods",
            {"fields": ("default_email", "default_sms", "default_in_app")},
        ),
        (
            "Templates",
            {
                "fields": ("email_template", "sms_template", "in_app_template"),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def default_delivery_methods(self, obj):
        methods = []
        if obj.default_email:
            methods.append("📧 Email")
        if obj.default_sms:
            methods.append("📱 SMS")
        if obj.default_in_app:
            methods.append("🔔 In-App")
        return " | ".join(methods) if methods else "None"

    default_delivery_methods.short_description = "Default Methods"


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "notification_type",
        "enabled_methods",
        "digest_frequency",
        "quiet_hours",
        "is_active",
    ]
    list_filter = [
        "notification_type",
        "email_enabled",
        "sms_enabled",
        "in_app_enabled",
        "digest_frequency",
        "is_active",
        "created_at",
    ]
    search_fields = [
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
        "notification_type__display_name",
    ]
    readonly_fields = ["created_at", "updated_at"]
    raw_id_fields = ["user"]

    fieldsets = (
        ("User & Type", {"fields": ("user", "notification_type", "is_active")}),
        (
            "Delivery Preferences",
            {"fields": ("email_enabled", "sms_enabled", "in_app_enabled")},
        ),
        (
            "Timing & Frequency",
            {"fields": ("quiet_hours_start", "quiet_hours_end", "digest_frequency")},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def enabled_methods(self, obj):
        methods = []
        if obj.email_enabled:
            methods.append("📧")
        if obj.sms_enabled:
            methods.append("📱")
        if obj.in_app_enabled:
            methods.append("🔔")
        return " ".join(methods) if methods else "❌"

    enabled_methods.short_description = "Methods"

    def quiet_hours(self, obj):
        if obj.quiet_hours_start and obj.quiet_hours_end:
            return f"{obj.quiet_hours_start.strftime('%H:%M')} - {obj.quiet_hours_end.strftime('%H:%M')}"
        return "None"

    quiet_hours.short_description = "Quiet Hours"


class NotificationLogInline(admin.TabularInline):
    model = NotificationLog
    extra = 0
    readonly_fields = ["attempted_at", "success", "error_message"]
    fields = [
        "delivery_method",
        "attempt_number",
        "success",
        "attempted_at",
        "error_message",
    ]


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "recipient",
        "notification_type",
        "status_badge",
        "delivery_status",
        "scheduled_for",
        "created_at",
    ]
    list_filter = [
        "status",
        "notification_type",
        "email_sent",
        "sms_sent",
        "in_app_read",
        "created_at",
        "scheduled_for",
    ]
    search_fields = [
        "title",
        "message",
        "recipient__username",
        "recipient__email",
        "recipient__first_name",
        "recipient__last_name",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
        "email_sent_at",
        "sms_sent_at",
        "in_app_read_at",
        "is_delivered",
        "is_read",
    ]
    raw_id_fields = ["recipient"]
    inlines = [NotificationLogInline]
    date_hierarchy = "created_at"

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("recipient", "notification_type", "title", "message")},
        ),
        (
            "Rich Content",
            {
                "fields": ("html_content", "action_url", "action_text"),
                "classes": ("collapse",),
            },
        ),
        ("Context & Metadata", {"fields": ("context_data",), "classes": ("collapse",)}),
        (
            "Email Delivery",
            {
                "fields": ("email_sent", "email_sent_at", "email_delivered"),
                "classes": ("collapse",),
            },
        ),
        (
            "SMS Delivery",
            {
                "fields": ("sms_sent", "sms_sent_at", "sms_delivered"),
                "classes": ("collapse",),
            },
        ),
        (
            "In-App Delivery",
            {
                "fields": ("in_app_sent", "in_app_read", "in_app_read_at"),
                "classes": ("collapse",),
            },
        ),
        (
            "Scheduling & Status",
            {"fields": ("scheduled_for", "status", "error_message")},
        ),
        (
            "Retry Settings",
            {"fields": ("retry_count", "max_retries"), "classes": ("collapse",)},
        ),
        (
            "Computed Properties",
            {"fields": ("is_delivered", "is_read"), "classes": ("collapse",)},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def status_badge(self, obj):
        colors = {
            "pending": "#ffc107",
            "sent": "#17a2b8",
            "delivered": "#28a745",
            "failed": "#dc3545",
            "read": "#6f42c1",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"

    def delivery_status(self, obj):
        statuses = []
        if obj.email_sent:
            icon = "✅" if obj.email_delivered else "📤"
            statuses.append(f"📧{icon}")
        if obj.sms_sent:
            icon = "✅" if obj.sms_delivered else "📤"
            statuses.append(f"📱{icon}")
        if obj.in_app_sent:
            icon = "👁️" if obj.in_app_read else "🔔"
            statuses.append(f"{icon}")
        return " ".join(statuses) if statuses else "❌"

    delivery_status.short_description = "Delivery"

    actions = ["mark_as_read", "resend_notification"]

    def mark_as_read(self, request, queryset):
        updated = 0
        for notification in queryset:
            if not notification.in_app_read:
                notification.mark_as_read()
                updated += 1
        self.message_user(request, f"{updated} notifications marked as read.")

    mark_as_read.short_description = "Mark selected notifications as read"

    def resend_notification(self, request, queryset):
        updated = queryset.filter(status__in=["failed", "pending"]).update(
            status="pending", retry_count=0, error_message=""
        )
        self.message_user(request, f"{updated} notifications queued for resending.")

    resend_notification.short_description = "Resend failed/pending notifications"


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = [
        "notification_type",
        "template_type",
        "language",
        "is_active",
        "has_variables",
        "created_at",
    ]
    list_filter = [
        "template_type",
        "language",
        "is_active",
        "notification_type",
        "created_at",
    ]
    search_fields = [
        "notification_type__display_name",
        "subject_template",
        "content_template",
    ]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (
            "Template Information",
            {"fields": ("notification_type", "template_type", "language", "is_active")},
        ),
        (
            "Template Content",
            {"fields": ("subject_template", "content_template", "html_template")},
        ),
        (
            "Variables",
            {
                "fields": ("available_variables",),
                "description": "JSON array of available template variables",
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def has_variables(self, obj):
        return "✅" if obj.available_variables else "❌"

    has_variables.short_description = "Variables"


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = [
        "notification_title",
        "delivery_method",
        "attempt_number",
        "success_badge",
        "provider_name",
        "attempted_at",
    ]
    list_filter = [
        "delivery_method",
        "success",
        "provider_name",
        "attempted_at",
    ]
    search_fields = [
        "notification__title",
        "notification__recipient__username",
        "provider_name",
        "provider_message_id",
        "error_message",
    ]
    readonly_fields = [
        "notification",
        "attempted_at",
        "response_data",
        "created_at",
        "updated_at",
    ]
    date_hierarchy = "attempted_at"

    fieldsets = (
        (
            "Log Information",
            {"fields": ("notification", "delivery_method", "attempt_number")},
        ),
        ("Results", {"fields": ("success", "error_message", "response_data")}),
        ("Provider Details", {"fields": ("provider_name", "provider_message_id")}),
        (
            "Timestamps",
            {
                "fields": ("attempted_at", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def notification_title(self, obj):
        return obj.notification.title

    notification_title.short_description = "Notification"

    def success_badge(self, obj):
        if obj.success:
            return format_html('<span style="color: green;">✅ Success</span>')
        else:
            return format_html('<span style="color: red;">❌ Failed</span>')

    success_badge.short_description = "Result"


@admin.register(BulkNotification)
class BulkNotificationAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "notification_type",
        "recipient_type",
        "status_badge",
        "progress",
        "success_rate_display",
        "created_by",
        "scheduled_for",
        "created_at",
    ]
    list_filter = [
        "status",
        "recipient_type",
        "notification_type",
        "created_by",
        "scheduled_for",
        "created_at",
    ]
    search_fields = [
        "title",
        "description",
        "notification_title",
        "notification_message",
        "created_by__username",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
        "total_recipients",
        "sent_count",
        "delivered_count",
        "read_count",
        "started_at",
        "completed_at",
        "success_rate",
        "read_rate",
    ]
    raw_id_fields = ["created_by"]
    date_hierarchy = "created_at"

    fieldsets = (
        (
            "Campaign Information",
            {"fields": ("title", "description", "notification_type", "created_by")},
        ),
        ("Recipients", {"fields": ("recipient_type", "custom_recipients")}),
        (
            "Notification Content",
            {
                "fields": (
                    "notification_title",
                    "notification_message",
                    "notification_html_content",
                    "notification_action_url",
                    "notification_action_text",
                )
            },
        ),
        ("Scheduling & Status", {"fields": ("scheduled_for", "status")}),
        (
            "Campaign Statistics",
            {
                "fields": (
                    "total_recipients",
                    "sent_count",
                    "delivered_count",
                    "read_count",
                    "success_rate",
                    "read_rate",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("started_at", "completed_at", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def status_badge(self, obj):
        colors = {
            "draft": "#6c757d",
            "scheduled": "#ffc107",
            "sending": "#17a2b8",
            "completed": "#28a745",
            "failed": "#dc3545",
            "cancelled": "#6c757d",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"

    def progress(self, obj):
        if obj.total_recipients == 0:
            return "0%"
        progress_pct = (obj.sent_count / obj.total_recipients) * 100
        return f"{obj.sent_count}/{obj.total_recipients} ({progress_pct:.1f}%)"

    progress.short_description = "Progress"

    def success_rate_display(self, obj):
        return f"{obj.success_rate:.1f}%"

    success_rate_display.short_description = "Success Rate"

    actions = ["cancel_campaign", "duplicate_campaign"]

    def cancel_campaign(self, request, queryset):
        updated = queryset.filter(status__in=["draft", "scheduled"]).update(
            status="cancelled"
        )
        self.message_user(request, f"{updated} campaigns cancelled.")

    cancel_campaign.short_description = "Cancel selected campaigns"

    def duplicate_campaign(self, request, queryset):
        for campaign in queryset:
            campaign.pk = None
            campaign.title = f"Copy of {campaign.title}"
            campaign.status = "draft"
            campaign.total_recipients = 0
            campaign.sent_count = 0
            campaign.delivered_count = 0
            campaign.read_count = 0
            campaign.started_at = None
            campaign.completed_at = None
            campaign.scheduled_for = None
            campaign.save()
        self.message_user(request, f"{queryset.count()} campaigns duplicated.")

    duplicate_campaign.short_description = "Duplicate selected campaigns"


# Custom admin site configuration
admin.site.site_header = "Notifications Administration"
admin.site.site_title = "Notifications Admin"
admin.site.index_title = "Notification System Management"
