from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Q
from django.core.cache import cache
from utils.mixins import CacheMixin
from utils.decorators import log_api_call
import logging

logger = logging.getLogger(__name__)


class BaseViewSet(CacheMixin, viewsets.ModelViewSet):
    """
    Base viewset with common functionality.
    """

    @log_api_call
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @log_api_call
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @log_api_call
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @log_api_call
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @log_api_call
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    def get_queryset(self):
        """
        Override to add search and filtering.
        """
        queryset = super().get_queryset()

        # Search functionality
        search = self.request.query_params.get("search")
        if search and hasattr(self, "search_fields"):
            query = Q()
            for field in self.search_fields:
                query |= Q(**{f"{field}__icontains": search})
            queryset = queryset.filter(query)

        return queryset

    @action(detail=False, methods=["get"])
    def count(self, request):
        """Get total count of objects"""
        count = self.get_queryset().count()
        return Response({"count": count})
