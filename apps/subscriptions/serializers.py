from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    SubscriptionPlan,
    Subscription,
    PaymentTransaction,
    SubscriptionUsage,
)
from apps.core.utils import generate_transaction_id
from datetime import timedelta, timezone
import logging
from drf_spectacular.utils import extend_schema_serializer, OpenApiExample

logger = logging.getLogger(__name__)
User = get_user_model()


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """
    Serializer for subscription plans.
    """

    class Meta:
        model = SubscriptionPlan
        fields = [
            "id",
            "name",
            "description",
            "price",
            "currency",
            "exam_limit",
            "duration_days",
            "allows_scheduled_exams",
            "allows_unlimited_retakes",
            "includes_analytics",
            "is_active",
        ]
        read_only_fields = ["id"]


class SubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializer for subscriptions.
    """

    plan_detail = SubscriptionPlanSerializer(source="plan", read_only=True)
    days_remaining = serializers.ReadOnlyField()
    exams_remaining = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()

    class Meta:
        model = Subscription
        fields = [
            "id",
            "plan",
            "plan_detail",
            "start_date",
            "end_date",
            "exams_used",
            "is_active",
            "transaction_id",
            "payment_status",
            "paid_amount",
            "days_remaining",
            "exams_remaining",
            "is_expired",
            "auto_renewal",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "transaction_id",
            "exams_used",
            "is_active",
            "payment_status",
            "created_at",
        ]


class PaymentTransactionSerializer(serializers.ModelSerializer):
    """
    Serializer for payment transactions.
    """

    class Meta:
        model = PaymentTransaction
        fields = [
            "id",
            "transaction_id",
            "gateway_transaction_id",
            "transaction_type",
            "amount",
            "currency",
            "payment_gateway",
            "status",
            "processed_at",
            "created_at",
        ]
        read_only_fields = ["id", "transaction_id", "created_at"]



@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Basic Plan Purchase',
            summary='Purchase basic subscription plan',
            value={
                'plan_id': 'uuid-here',
                'payment_gateway': 'sslcommerz',
                'success_url': 'https://yoursite.com/payment/success',
                'cancel_url': 'https://yoursite.com/payment/cancel'
            },
            request_only=True,
        ),
    ]
)
class SubscriptionPurchaseSerializer(serializers.Serializer):
    """
    Serializer for subscription purchase.
    """

    plan_id = serializers.UUIDField()
    payment_gateway = serializers.ChoiceField(
        choices=PaymentTransaction.GATEWAY_CHOICES, default="sslcommerz"
    )
    success_url = serializers.URLField()
    cancel_url = serializers.URLField()

    def validate_plan_id(self, value):
        """Validate plan exists and is active."""
        try:
            plan = SubscriptionPlan.objects.get(id=value, is_active=True)
            return value
        except SubscriptionPlan.DoesNotExist:
            raise serializers.ValidationError("Invalid or inactive subscription plan.")

    def create(self, validated_data):
        """Create subscription purchase request."""
        user = self.context["request"].user
        plan = SubscriptionPlan.objects.get(id=validated_data["plan_id"])

        # Generate transaction ID
        transaction_id = generate_transaction_id()

        # Calculate subscription dates
        start_date = timezone.now()
        end_date = start_date + timedelta(days=plan.duration_days)

        # Create pending subscription
        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            start_date=start_date,
            end_date=end_date,
            transaction_id=transaction_id,
            payment_method=validated_data["payment_gateway"],
            paid_amount=plan.price,
            is_active=False,  # Will be activated after payment
        )

        # Create payment transaction
        transaction = PaymentTransaction.objects.create(
            user=user,
            subscription=subscription,
            transaction_id=transaction_id,
            transaction_type="subscription",
            amount=plan.price,
            payment_gateway=validated_data["payment_gateway"],
        )

        logger.info(f"Subscription purchase initiated: {transaction_id}")

        return {
            "subscription": subscription,
            "transaction": transaction,
            "success_url": validated_data["success_url"],
            "cancel_url": validated_data["cancel_url"],
        }
@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Exam Result Example',
            summary='Complete exam result with analytics',
            value={
                'id': 'result-uuid',
                'exam_detail': {
                    'title': 'Mathematics Test',
                    'total_questions': 50
                },
                'total_questions': 50,
                'questions_attempted': 45,
                'correct_answers': 38,
                'wrong_answers': 7,
                'unanswered': 5,
                'percentage_score': 76.0,
                'is_passed': True,
                'grade': 'B+',
                'time_taken_minutes': 45,
                'accuracy_rate': 84.4,
                'subject_wise_scores': {
                    'Algebra': {'correct': 15, 'total': 20, 'percentage': 75.0},
                    'Geometry': {'correct': 23, 'total': 30, 'percentage': 76.7}
                },
                'weak_areas': ['Quadratic Equations'],
                'strong_areas': ['Linear Equations', 'Geometry Basics']
            },
            response_only=True,
        ),
    ]
)

class SubscriptionUsageSerializer(serializers.ModelSerializer):
    """
    Serializer for subscription usage.
    """

    exam_title = serializers.CharField(source="exam.title", read_only=True)

    class Meta:
        model = SubscriptionUsage
        fields = [
            "id",
            "exam",
            "exam_title",
            "exam_taken_at",
            "score_achieved",
            "time_spent_minutes",
        ]
        read_only_fields = ["id", "exam_taken_at"]
