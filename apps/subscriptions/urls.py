from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SubscriptionPlanViewSet,
    SubscriptionViewSet,
    PaymentTransactionViewSet,
)

router = DefaultRouter()
router.register(r"plans", SubscriptionPlanViewSet, basename="subscription-plans")
router.register(r"subscriptions", SubscriptionViewSet, basename="subscriptions")
router.register(
    r"transactions", PaymentTransactionViewSet, basename="payment-transactions"
)

urlpatterns = [
    path("", include(router.urls)),
]
