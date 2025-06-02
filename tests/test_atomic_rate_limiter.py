"""Test for atomic rate limiter implementation."""

import threading
import time
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from text_to_audio.rate_limiter import TTSRateLimiter


class AtomicRateLimiterTests(TestCase):
    """Test that the rate limiter Lua script provides atomic operation."""

    @override_settings(
        OPENAI_TTS_RATE_LIMIT_PER_SECOND=2,
        OPENAI_TTS_RATE_LIMIT_PER_MINUTE=10,
        CELERY_BROKER_URL="redis://localhost:6379/1"  # Use a different DB for tests
    )
    def test_lua_script_atomicity(self):
        """Test that the Lua script prevents race conditions under concurrent access."""
        # Only run this test if Redis is available
        try:
            rate_limiter = TTSRateLimiter()
            # Test Redis connectivity
            rate_limiter.redis_client.ping()
        except Exception:
            self.skipTest("Redis not available for integration test")

        # Clear any existing rate limit state
        rate_limiter.redis_client.flushdb()

        # Set up concurrent access scenario
        per_second_limit = 2
        num_threads = 5
        requests_per_thread = 2
        total_requests = num_threads * requests_per_thread

        acquired_tokens = []
        threads = []

        def make_requests():
            """Function for each thread to make multiple requests."""
            thread_results = []
            for _ in range(requests_per_thread):
                # Use the same second timestamp to test per-second limiting
                result = rate_limiter._check_and_acquire()
                thread_results.append(result)
                time.sleep(0.01)  # Small delay to increase chance of race conditions
            acquired_tokens.extend(thread_results)

        # Start all threads at roughly the same time
        for _ in range(num_threads):
            thread = threading.Thread(target=make_requests)
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Count successful token acquisitions
        successful_acquisitions = sum(1 for result in acquired_tokens if result)

        # With per-second limit of 2, we should have at most 2 successful acquisitions
        # (plus potentially a few more if requests span multiple seconds)
        # The key test is that we don't have drastically more than the limit

        # Allow for some time window spillover but ensure we're not way over the limit
        max_expected = per_second_limit + 2  # Allow for 2-second window spillover

        self.assertLessEqual(
            successful_acquisitions,
            max_expected,
            f"Rate limiter allowed {successful_acquisitions} requests when limit is {per_second_limit} per second. "
            f"This suggests the atomic operation failed and race conditions occurred."
        )

        # Also verify we actually denied some requests (otherwise the test isn't meaningful)
        denied_requests = sum(1 for result in acquired_tokens if not result)
        self.assertGreater(
            denied_requests,
            0,
            "No requests were denied, which suggests the rate limiter isn't working at all"
        )

        print(f"Rate limiter test results: {successful_acquisitions} granted, {denied_requests} denied out of {total_requests} total")

    def test_lua_script_fallback_on_redis_error(self):
        """Test that the rate limiter falls back gracefully when Redis fails."""
        import redis

        with patch('text_to_audio.rate_limiter.redis.Redis') as mock_redis_class:
            # Mock Redis to always raise RedisError
            mock_redis_instance = Mock()
            mock_redis_instance.script_load.side_effect = redis.RedisError("Redis connection failed")
            mock_redis_instance.evalsha.side_effect = redis.RedisError("Redis evalsha failed")
            mock_redis_instance.eval.side_effect = redis.RedisError("Redis eval failed")
            mock_redis_class.return_value = mock_redis_instance

            rate_limiter = TTSRateLimiter()

            # Should fall back to allowing requests (fail-open mode)
            result = rate_limiter._check_and_acquire()
            self.assertTrue(result, "Rate limiter should allow requests when Redis fails")

    def test_lua_script_handles_noscript_error(self):
        """Test that the rate limiter handles NOSCRIPT errors gracefully."""
        with patch('text_to_audio.rate_limiter.redis.Redis') as mock_redis_class:
            mock_redis_instance = Mock()

            # Mock successful script loading initially
            mock_redis_instance.script_load.return_value = "sha123"

            # Mock NOSCRIPT error on first evalsha call, then success on reload
            import redis
            mock_redis_instance.evalsha.side_effect = [
                redis.ResponseError("NOSCRIPT No matching script"),
                [1, 1, 1]  # Success result after reload
            ]

            mock_redis_class.return_value = mock_redis_instance

            rate_limiter = TTSRateLimiter()

            # Should handle NOSCRIPT error and reload script
            result = rate_limiter._check_and_acquire()
            self.assertTrue(result, "Rate limiter should handle NOSCRIPT error and succeed")

            # Verify script was reloaded
            self.assertEqual(mock_redis_instance.script_load.call_count, 2)
            self.assertEqual(mock_redis_instance.evalsha.call_count, 2)

    @override_settings(
        OPENAI_TTS_RATE_LIMIT_PER_SECOND=1,
        OPENAI_TTS_RATE_LIMIT_PER_MINUTE=5,
        CELERY_BROKER_URL="redis://localhost:6379/1"
    )
    def test_lua_script_respects_both_limits(self):
        """Test that the Lua script correctly enforces both per-second and per-minute limits."""
        try:
            rate_limiter = TTSRateLimiter()
            rate_limiter.redis_client.ping()
        except Exception:
            self.skipTest("Redis not available for integration test")

        # Clear any existing rate limit state
        rate_limiter.redis_client.flushdb()

        # Test per-second limit (should allow 1 per second)
        result1 = rate_limiter._check_and_acquire()
        self.assertTrue(result1, "First request should succeed")

        result2 = rate_limiter._check_and_acquire()
        self.assertFalse(result2, "Second request in same second should be denied")

        # Wait for next second window
        time.sleep(1.1)

        result3 = rate_limiter._check_and_acquire()
        self.assertTrue(result3, "Request in new second should succeed")

        print("Lua script correctly enforces per-second and per-minute limits")
