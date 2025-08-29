from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from apps.core.models import BaseModel
from apps.core.managers import SoftDeleteManager
import uuid

User = get_user_model()


class SubscriptionPlan(BaseModel):
    """
    Subscription plans available for users.
    """

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="BDT")

    # Plan features
    exam_limit = models.PositiveIntegerField(help_text="Number of exams allowed")
    duration_days = models.PositiveIntegerField(help_text="Plan duration in days")

    # Additional features
    allows_scheduled_exams = models.BooleanField(default=True)
    allows_unlimited_retakes = models.BooleanField(default=True)
    includes_analytics = models.BooleanField(default=True)

    # Plan settings
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    objects = SoftDeleteManager()

    class Meta:
        db_table = "subscription_plans"
        ordering = ["sort_order", "price"]
        indexes = [
            models.Index(fields=["is_active", "sort_order"]),
            models.Index(fields=["price"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.price} {self.currency}"


class Subscription(BaseModel):
    """
    User subscription records.
    """

    PAYMENT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="subscriptions"
    )
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE)

    # Subscription period
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()

    # Usage tracking
    exams_used = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=False)

    # Payment information
    transaction_id = models.CharField(max_length=100, unique=True)
    payment_method = models.CharField(max_length=50, default="sslcommerz")
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default="pending"
    )
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2)

    # Renewal tracking
    auto_renewal = models.BooleanField(default=False)
    renewal_reminder_sent = models.BooleanField(default=False)

    objects = SoftDeleteManager()

    class Meta:
        db_table = "subscriptions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["end_date"]),
            models.Index(fields=["payment_status"]),
            models.Index(fields=["transaction_id"]),
        ]

    def __str__(self):
        return f"{self.user.phone_number} - {self.plan.name}"

    @property
    def is_expired(self):
        """Check if subscription is expired."""
        return timezone.now() > self.end_date

    @property
    def days_remaining(self):
        """Get remaining days in subscription."""
        if self.is_expired:
            return 0
        return (self.end_date - timezone.now()).days

    @property
    def exams_remaining(self):
        """Get remaining exam attempts."""
        return max(0, self.plan.exam_limit - self.exams_used)

    def can_take_exam(self):
        """Check if user can take an exam."""
        return self.is_active and not self.is_expired and self.exams_remaining > 0

    def use_exam_attempt(self):
        """Use one exam attempt."""
        if self.can_take_exam():
            self.exams_used += 1
            self.save(update_fields=["exams_used"])
            return True
        return False


class PaymentTransaction(BaseModel):
    """
    Payment transaction records.
    """

    TRANSACTION_TYPES = [
        ("subscription", "Subscription Payment"),
        ("renewal", "Subscription Renewal"),
        ("refund", "Refund"),
    ]

    GATEWAY_CHOICES = [
        ("sslcommerz", "SSLCommerz"),
        ("bkash", "bKash"),
        ("nagad", "Nagad"),
        ("rocket", "Rocket"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="payment_transactions"
    )
    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="transactions"
    )

    # Transaction details
    transaction_id = models.CharField(max_length=100, unique=True)
    gateway_transaction_id = models.CharField(max_length=100, blank=True)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)

    # Payment details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="BDT")
    payment_gateway = models.CharField(
        max_length=20, choices=GATEWAY_CHOICES, default="sslcommerz"
    )

    # Status and metadata
    status = models.CharField(
        max_length=20, choices=Subscription.PAYMENT_STATUS_CHOICES, default="pending"
    )
    gateway_response = models.JSONField(blank=True, null=True)

    # Processing details
    processed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)

    objects = SoftDeleteManager()

    class Meta:
        db_table = "payment_transactions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["transaction_id"]),
            models.Index(fields=["gateway_transaction_id"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.transaction_id} - {self.amount} {self.currency}"


class SubscriptionUsage(BaseModel):
    """
    Track detailed subscription usage.
    """

    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="usage_records"
    )
    exam = models.ForeignKey("exams.Exam", on_delete=models.CASCADE)

    # Usage details
    exam_taken_at = models.DateTimeField(auto_now_add=True)
    score_achieved = models.FloatField(null=True, blank=True)
    time_spent_minutes = models.PositiveIntegerField(null=True, blank=True)

    objects = SoftDeleteManager()

    class Meta:
        db_table = "subscription_usage"
        ordering = ["-exam_taken_at"]
        unique_together = ["subscription", "exam", "exam_taken_at"]
        indexes = [
            models.Index(fields=["subscription", "exam_taken_at"]),
            models.Index(fields=["exam", "exam_taken_at"]),
        ]

    def __str__(self):
        return f"{self.subscription.user.phone_number} - {self.exam.title}"
