"""
Rate limiting for OpenAI TTS API calls to prevent throttling.

Implements a two-level rate limiting strategy:
1. Per-second burst limiting
2. Per-minute sustained rate limiting

Uses Redis for distributed rate limiting across multiple workers.
"""

import logging
import time
from typing import Optional

import redis
from django.conf import settings

logger = logging.getLogger(__name__)


class TTSRateLimiter:
    """Rate limiter for OpenAI TTS API calls using sliding window algorithm."""

    def __init__(self):
        """Initialize rate limiter with Redis connection."""
        # Rate-limited warning tracking for Redis failures
        self._last_redis_warning = 0
        self._redis_warning_interval = 60  # Warn once per minute maximum
        # Get Redis connection from Celery broker URL or default
        broker_url = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")

        # Parse Redis URL (simple parsing for redis:// URLs)
        if broker_url.startswith("redis://"):
            # Extract host:port/db from redis://host:port/db
            url_parts = broker_url.replace("redis://", "").split("/")
            host_port = url_parts[0]
            db = int(url_parts[1]) if len(url_parts) > 1 else 0

            if ":" in host_port:
                host, port = host_port.split(":")
                port = int(port)
            else:
                host = host_port
                port = 6379

            self.redis_client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        else:
            # Fallback to localhost
            self.redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

        # Rate limiting configuration
        self.per_second_limit = getattr(settings, "OPENAI_TTS_RATE_LIMIT_PER_SECOND", 3)
        self.per_minute_limit = getattr(settings, "OPENAI_TTS_RATE_LIMIT_PER_MINUTE", 50)

        # Redis keys for rate limiting
        self.per_second_key = "tts_rate_limit:per_second"
        self.per_minute_key = "tts_rate_limit:per_minute"

    def acquire_tts_token(self, timeout: float = 30.0) -> bool:
        """
        Acquire a token to make a TTS API call, blocking until available.

        Args:
            timeout: Maximum time to wait for a token (seconds)

        Returns:
            True if token acquired, False if timeout reached
        """
        start_time = time.monotonic()

        while time.monotonic() - start_time < timeout:
            if self._check_and_acquire():
                return True

            # Wait a short time before checking again
            time.sleep(0.1)

        logger.warning(f"Rate limiter timeout after {timeout}s")
        return False

    def _check_and_acquire(self) -> bool:
        """
        Check if we can make a TTS call within rate limits and acquire token if possible.

        Uses sliding window counters for both per-second and per-minute limits.
        """
        current_time = time.time()

        try:
            # Use Redis pipeline for atomic operations
            pipe = self.redis_client.pipeline()

            # Check per-second limit using sliding window
            second_window_start = int(current_time)
            second_key = f"{self.per_second_key}:{second_window_start}"

            # Check per-minute limit using sliding window
            minute_window_start = int(current_time // 60) * 60
            minute_key = f"{self.per_minute_key}:{minute_window_start}"

            # Get current counts
            pipe.get(second_key)
            pipe.get(minute_key)
            results = pipe.execute()

            second_count = int(results[0]) if results[0] else 0
            minute_count = int(results[1]) if results[1] else 0

            # Check if we're within limits
            if second_count >= self.per_second_limit:
                logger.debug(f"Per-second rate limit hit: {second_count}/{self.per_second_limit}")
                return False

            if minute_count >= self.per_minute_limit:
                logger.debug(f"Per-minute rate limit hit: {minute_count}/{self.per_minute_limit}")
                return False

            # Acquire tokens atomically
            pipe = self.redis_client.pipeline()
            pipe.incr(second_key)
            pipe.expire(second_key, 2)  # Keep for 2 seconds to handle clock skew
            pipe.incr(minute_key)
            pipe.expire(minute_key, 120)  # Keep for 2 minutes to handle clock skew
            pipe.execute()

            logger.debug(f"Rate limiter token acquired: second={second_count+1}/{self.per_second_limit}, minute={minute_count+1}/{self.per_minute_limit}")
            return True

        except redis.RedisError as e:
            # Rate-limited warning to prevent log flooding
            current_time = time.time()
            if current_time - self._last_redis_warning >= self._redis_warning_interval:
                logger.warning(
                    f"Redis rate limiter failed, allowing requests (fail-open mode): {e}. "
                    f"Rate limiting is disabled until Redis is restored."
                )
                self._last_redis_warning = current_time
            else:
                # Log debug-level messages for subsequent failures within the interval
                logger.debug(f"Redis error in rate limiter (suppressed warning): {e}")

            # Fall back to allowing the request if Redis is unavailable
            # This prevents Redis outages from blocking all TTS generation
            return True

    def get_current_usage(self) -> dict:
        """
        Get current rate limiting usage for monitoring.

        Returns:
            Dictionary with current per-second and per-minute usage
        """
        current_time = time.time()

        try:
            second_window_start = int(current_time)
            minute_window_start = int(current_time // 60) * 60

            second_key = f"{self.per_second_key}:{second_window_start}"
            minute_key = f"{self.per_minute_key}:{minute_window_start}"

            pipe = self.redis_client.pipeline()
            pipe.get(second_key)
            pipe.get(minute_key)
            results = pipe.execute()

            return {
                "per_second": {
                    "current": int(results[0]) if results[0] else 0,
                    "limit": self.per_second_limit
                },
                "per_minute": {
                    "current": int(results[1]) if results[1] else 0,
                    "limit": self.per_minute_limit
                }
            }
        except redis.RedisError as e:
            logger.error(f"Redis error getting usage: {e}")
            return {
                "per_second": {"current": 0, "limit": self.per_second_limit},
                "per_minute": {"current": 0, "limit": self.per_minute_limit}
            }


# Global rate limiter instance
_rate_limiter: Optional[TTSRateLimiter] = None


def get_rate_limiter() -> TTSRateLimiter:
    """Get the global TTSRateLimiter instance (singleton pattern)."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = TTSRateLimiter()
    return _rate_limiter
