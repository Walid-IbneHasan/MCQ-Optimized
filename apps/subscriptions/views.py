from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from .models import (
    SubscriptionPlan,
    Subscription,
    PaymentTransaction,
    SubscriptionUsage,
)
from .serializers import (
    SubscriptionPlanSerializer,
    SubscriptionSerializer,
    PaymentTransactionSerializer,
    SubscriptionPurchaseSerializer,
    SubscriptionUsageSerializer,
)
from utils.permissions import IsAdminOrModerator, HasActiveSubscription
from utils.sslcommerz import SSLCommerzGateway
from utils.decorators import log_api_call
from apps.core.views import BaseViewSet
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class SubscriptionPlanViewSet(BaseViewSet):
    """
    ViewSet for subscription plans.
    """

    queryset = SubscriptionPlan.objects.filter(is_active=True)
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.AllowAny]  # Plans are public

    def get_permissions(self):
        """Set permissions based on action."""
        if self.action in ["create", "update", "partial_update", "destroy"]:
            self.permission_classes = [IsAdminOrModerator]
        return [permission() for permission in self.permission_classes]

    @log_api_call
    def list(self, request, *args, **kwargs):
        """List all active subscription plans."""
        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    def popular(self, request):
        """Get popular subscription plans."""
        popular_plans = self.get_queryset().order_by("-sort_order")[:3]
        serializer = self.get_serializer(popular_plans, many=True)
        return Response({"success": True, "plans": serializer.data})


class SubscriptionViewSet(BaseViewSet):
    """
    ViewSet for user subscriptions.
    """

    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Get user's subscriptions."""
        return Subscription.objects.filter(user=self.request.user)

    @log_api_call
    def list(self, request, *args, **kwargs):
        """List user's subscriptions."""
        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    def active(self, request):
        """Get user's active subscription."""
        try:
            active_subscription = Subscription.objects.get(
                user=request.user, is_active=True, end_date__gt=timezone.now()
            )
            serializer = self.get_serializer(active_subscription)
            return Response({"success": True, "subscription": serializer.data})
        except Subscription.DoesNotExist:
            return Response(
                {"success": False, "message": "No active subscription found"},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=False, methods=["post"])
    def purchase(self, request):
        """Purchase a subscription."""
        serializer = SubscriptionPurchaseSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            with transaction.atomic():
                purchase_data = serializer.save()
                subscription = purchase_data["subscription"]
                payment_transaction = purchase_data["transaction"]

                # Initialize payment gateway
                gateway = SSLCommerzGateway()

                # Prepare payment data
                payment_data = {
                    "amount": float(subscription.paid_amount),
                    "transaction_id": payment_transaction.transaction_id,
                    "customer_name": request.user.full_name,
                    "customer_email": request.user.email
                    or f"{request.user.phone_number}@temp.com",
                    "customer_phone": request.user.phone_number,
                    "product_name": f"Subscription: {subscription.plan.name}",
                    "success_url": purchase_data["success_url"],
                    "fail_url": purchase_data["cancel_url"],
                    "cancel_url": purchase_data["cancel_url"],
                }

                # Create payment session
                payment_result = gateway.create_payment_session(payment_data)

                if payment_result["success"]:
                    return Response(
                        {
                            "success": True,
                            "payment_url": payment_result["gateway_url"],
                            "transaction_id": payment_transaction.transaction_id,
                            "subscription_id": subscription.id,
                        },
                        status=status.HTTP_201_CREATED,
                    )
                else:
                    # Delete the created records on payment failure
                    subscription.delete()
                    payment_transaction.delete()

                    return Response(
                        {"success": False, "error": payment_result["error"]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel a subscription."""
        subscription = get_object_or_404(Subscription, pk=pk, user=request.user)

        if not subscription.is_active:
            return Response(
                {"success": False, "error": "Subscription is not active"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        subscription.is_active = False
        subscription.save()

        logger.info(f"Subscription cancelled: {subscription.transaction_id}")

        return Response(
            {"success": True, "message": "Subscription cancelled successfully"}
        )

    @action(detail=False, methods=["get"])
    def usage(self, request):
        """Get subscription usage details."""
        try:
            active_subscription = Subscription.objects.get(
                user=request.user, is_active=True
            )

            usage_records = SubscriptionUsage.objects.filter(
                subscription=active_subscription
            ).select_related("exam")

            serializer = SubscriptionUsageSerializer(usage_records, many=True)

            return Response(
                {
                    "success": True,
                    "subscription": SubscriptionSerializer(active_subscription).data,
                    "usage": serializer.data,
                }
            )
        except Subscription.DoesNotExist:
            return Response(
                {"success": False, "message": "No active subscription found"},
                status=status.HTTP_404_NOT_FOUND,
            )


class PaymentTransactionViewSet(BaseViewSet):
    """
    ViewSet for payment transactions.
    """

    serializer_class = PaymentTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Get user's payment transactions."""
        return PaymentTransaction.objects.filter(user=self.request.user)

    @action(detail=False, methods=["post"])
    def webhook(self, request):
        """Handle payment gateway webhooks."""
        # This endpoint should be called by SSLCommerz
        transaction_id = request.data.get("tran_id")
        status_code = request.data.get("status")
        amount = request.data.get("amount")

        if not transaction_id:
            return Response(
                {"success": False, "error": "Transaction ID required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment_transaction = PaymentTransaction.objects.get(
                transaction_id=transaction_id
            )
            subscription = payment_transaction.subscription

            # Verify payment with gateway
            gateway = SSLCommerzGateway()
            verification_result = gateway.validate_payment(
                transaction_id, float(payment_transaction.amount)
            )

            if verification_result["success"] and status_code in ["VALID", "VALIDATED"]:
                # Payment successful
                with transaction.atomic():
                    payment_transaction.status = "completed"
                    payment_transaction.gateway_transaction_id = request.data.get(
                        "val_id", ""
                    )
                    payment_transaction.gateway_response = request.data
                    payment_transaction.processed_at = timezone.now()
                    payment_transaction.save()

                    # Activate subscription
                    subscription.is_active = True
                    subscription.payment_status = "completed"
                    subscription.save()

                    logger.info(f"Payment completed for transaction: {transaction_id}")

                    # Send confirmation email/SMS
                    from .tasks import send_subscription_confirmation

                    send_subscription_confirmation.delay(subscription.id)

            else:
                # Payment failed
                payment_transaction.status = "failed"
                payment_transaction.failure_reason = request.data.get(
                    "error", "Payment validation failed"
                )
                payment_transaction.gateway_response = request.data
                payment_transaction.save()

                logger.warning(f"Payment failed for transaction: {transaction_id}")

            return Response({"success": True})

        except PaymentTransaction.DoesNotExist:
            logger.error(f"Transaction not found: {transaction_id}")
            return Response(
                {"success": False, "error": "Transaction not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.error(f"Webhook processing error: {str(e)}")
            return Response(
                {"success": False, "error": "Processing error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        """Manually verify a payment transaction."""
        if not request.user.is_staff:
            return Response(
                {"success": False, "error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN,
            )

        payment_transaction = get_object_or_404(PaymentTransaction, pk=pk)

        # Verify with gateway
        gateway = SSLCommerzGateway()
        result = gateway.validate_payment(
            payment_transaction.transaction_id, float(payment_transaction.amount)
        )

        return Response({"success": True, "verification_result": result})
