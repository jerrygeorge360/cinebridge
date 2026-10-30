from __future__ import annotations

import unittest

from app.rate_limit import RateLimiter


class RateLimiterTests(unittest.TestCase):
    def test_active_random_keys_stay_within_the_memory_bound(self) -> None:
        limiter = RateLimiter()

        for index in range(limiter.MAX_KEYS + 100):
            allowed, _ = limiter.allow(f"random-token-{index}", limit=1, window_seconds=3600)
            self.assertTrue(allowed)

        self.assertLessEqual(len(limiter._entries), limiter.MAX_KEYS)


if __name__ == "__main__":
    unittest.main()
