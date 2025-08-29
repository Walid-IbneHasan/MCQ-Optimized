from django.core.cache import cache
from rest_framework.response import Response
from rest_framework import status
from .redis_client import redis_client


class CacheMixin:
    """
    Mixin for caching API responses.
    """

    cache_timeout = 300  # 5 minutes default
    cache_key_prefix = "api"

    def get_cache_key(self, *args):
        """Generate cache key"""
        return f"{self.cache_key_prefix}:{':'.join(str(arg) for arg in args)}"

    def get_cached_data(self, cache_key):
        """Get data from cache"""
        return redis_client.get(cache_key)

    def set_cached_data(self, cache_key, data, timeout=None):
        """Set data in cache"""
        timeout = timeout or self.cache_timeout
        return redis_client.set(cache_key, data, timeout)


class BulkCreateMixin:
    """
    Mixin for bulk create operations.
    """

    def bulk_create(self, serializer_class, data_list):
        """Bulk create objects"""
        serializer = serializer_class(data=data_list, many=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
