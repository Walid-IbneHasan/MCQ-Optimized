from django.contrib import admin
from django.utils.html import format_html
from .models import (
    SubscriptionPlan,
    Subscription,
    PaymentTransaction,
    SubscriptionUsage,
)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    """
    Admin for subscription plans.
    """

    list_display = [
        "name",
        "price",
        "currency",
        "exam_limit",
        "duration_days",
        "is_active",
        "sort_order",
        "created_at",
    ]
    list_filter = ["is_active", "allows_scheduled_exams", "created_at"]
    search_fields = ["name", "description"]
    ordering = ["sort_order", "price"]

    fieldsets = (
        ("Basic Information", {"fields": ("name", "description", "price", "currency")}),
        (
            "Plan Features",
            {
                "fields": (
                    "exam_limit",
                    "duration_days",
                    "allows_scheduled_exams",
                    "allows_unlimited_retakes",
                    "includes_analytics",
                )
            },
        ),
        ("Settings", {"fields": ("is_active", "sort_order")}),
    )


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """
    Admin for subscriptions.
    """

    list_display = [
        "user_phone",
        "plan_name",
        "start_date",
        "end_date",
        "exams_used",
        "exams_remaining",
        "is_active",
        "payment_status_badge",
    ]
    list_filter = ["is_active", "payment_status", "plan", "created_at"]
    search_fields = [
        "user__phone_number",
        "user__first_name",
        "user__last_name",
        "transaction_id",
    ]
    raw_id_fields = ["user", "plan"]
    ordering = ["-created_at"]

    def user_phone(self, obj):
        return obj.user.phone_number

    user_phone.short_description = "User Phone"

    def plan_name(self, obj):
        return obj.plan.name

    plan_name.short_description = "Plan"

    def payment_status_badge(self, obj):
        colors = {
            "pending": "orange",
            "completed": "green",
            "failed": "red",
            "refunded": "blue",
        }
        color = colors.get(obj.payment_status, "gray")
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_payment_status_display(),
        )

    payment_status_badge.short_description = "Payment Status"


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    """
    Admin for payment transactions.
    """

    list_display = [
        "transaction_id",
        "user_phone",
        "amount",
        "currency",
        "payment_gateway",
        "status_badge",
        "created_at",
    ]
    list_filter = ["status", "payment_gateway", "transaction_type", "created_at"]
    search_fields = ["transaction_id", "gateway_transaction_id", "user__phone_number"]
    raw_id_fields = ["user", "subscription"]
    ordering = ["-created_at"]
    readonly_fields = ["gateway_response"]

    def user_phone(self, obj):
        return obj.user.phone_number

    user_phone.short_description = "User Phone"

    def status_badge(self, obj):
        colors = {
            "pending": "orange",
            "completed": "green",
            "failed": "red",
            "refunded": "blue",
        }
        color = colors.get(obj.status, "gray")
        return format_html(
            '<span style="color: {};">{}</span>', color, obj.get_status_display()
        )

    status_badge.short_description = "Status"


@admin.register(SubscriptionUsage)
class SubscriptionUsageAdmin(admin.ModelAdmin):
    """
    Admin for subscription usage.
    """

    list_display = [
        "user_phone",
        "exam_title",
        "exam_taken_at",
        "score_achieved",
        "time_spent_minutes",
    ]
    list_filter = ["exam_taken_at", "score_achieved"]
    search_fields = ["subscription__user__phone_number", "exam__title"]
    raw_id_fields = ["subscription", "exam"]
    ordering = ["-exam_taken_at"]

    def user_phone(self, obj):
        return obj.subscription.user.phone_number

    user_phone.short_description = "User Phone"

    def exam_title(self, obj):
        return obj.exam.title

    exam_title.short_description = "Exam"
