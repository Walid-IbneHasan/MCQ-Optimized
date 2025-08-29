import redis
from django.conf import settings
import json
import logging
from typing import Any, Optional, Dict, List

logger = logging.getLogger(__name__)


class RedisClient:
    def __init__(self):
        self.client = redis.from_url(settings.CACHES["default"]["LOCATION"])

    def set(self, key: str, value: Any, timeout: Optional[int] = None) -> bool:
        """Set a key-value pair in Redis"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            return self.client.set(key, value, ex=timeout)
        except Exception as e:
            logger.error(f"Redis SET error: {e}")
            return False

    def get(self, key: str) -> Any:
        """Get value from Redis"""
        try:
            value = self.client.get(key)
            if value:
                try:
                    return json.loads(value.decode("utf-8"))
                except (json.JSONDecodeError, AttributeError):
                    return value.decode("utf-8") if isinstance(value, bytes) else value
            return None
        except Exception as e:
            logger.error(f"Redis GET error: {e}")
            return None

    def delete(self, *keys: str) -> int:
        """Delete keys from Redis"""
        try:
            return self.client.delete(*keys)
        except Exception as e:
            logger.error(f"Redis DELETE error: {e}")
            return 0

    def exists(self, key: str) -> bool:
        """Check if key exists in Redis"""
        try:
            return self.client.exists(key)
        except Exception as e:
            logger.error(f"Redis EXISTS error: {e}")
            return False

    def expire(self, key: str, timeout: int) -> bool:
        """Set expiration for a key"""
        try:
            return self.client.expire(key, timeout)
        except Exception as e:
            logger.error(f"Redis EXPIRE error: {e}")
            return False

    def hset(self, name: str, key: str, value: Any) -> int:
        """Set hash field"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            return self.client.hset(name, key, value)
        except Exception as e:
            logger.error(f"Redis HSET error: {e}")
            return 0

    def hget(self, name: str, key: str) -> Any:
        """Get hash field"""
        try:
            value = self.client.hget(name, key)
            if value:
                try:
                    return json.loads(value.decode("utf-8"))
                except (json.JSONDecodeError, AttributeError):
                    return value.decode("utf-8") if isinstance(value, bytes) else value
            return None
        except Exception as e:
            logger.error(f"Redis HGET error: {e}")
            return None

    def hgetall(self, name: str) -> Dict:
        """Get all hash fields"""
        try:
            data = self.client.hgetall(name)
            result = {}
            for key, value in data.items():
                key = key.decode("utf-8") if isinstance(key, bytes) else key
                try:
                    result[key] = json.loads(value.decode("utf-8"))
                except (json.JSONDecodeError, AttributeError):
                    result[key] = (
                        value.decode("utf-8") if isinstance(value, bytes) else value
                    )
            return result
        except Exception as e:
            logger.error(f"Redis HGETALL error: {e}")
            return {}

    def zadd(self, name: str, mapping: Dict[str, float]) -> int:
        """Add to sorted set"""
        try:
            return self.client.zadd(name, mapping)
        except Exception as e:
            logger.error(f"Redis ZADD error: {e}")
            return 0

    def zrevrange(
        self, name: str, start: int = 0, end: int = -1, withscores: bool = False
    ) -> List:
        """Get sorted set in reverse order"""
        try:
            return self.client.zrevrange(name, start, end, withscores=withscores)
        except Exception as e:
            logger.error(f"Redis ZREVRANGE error: {e}")
            return []


# Global Redis client instance
redis_client = RedisClient()
