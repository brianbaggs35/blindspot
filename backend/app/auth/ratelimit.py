"""A sliding-window counter for failures, per key (an address, in practice). It lives in memory:
the container runs one API process, and a restart that clears it is no help to an attacker who
cannot cause one."""

import time
from collections import deque
from collections.abc import Callable

_MAX_KEYS = 10_000


class FailureLimiter:
    """Blocks a key that has failed `limit` times within `window` seconds."""

    def __init__(
        self, limit: int, window: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window = window
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}

    def _recent(self, key: str) -> deque[float]:
        failures = self._failures.get(key)
        if failures is None:
            return deque()
        cutoff = self._clock() - self.window
        while failures and failures[0] <= cutoff:
            failures.popleft()
        return failures

    def blocked_for(self, key: str) -> float:
        """Seconds until the key may try again; 0 when it may try now."""
        failures = self._recent(key)
        if len(failures) < self.limit:
            return 0.0
        return max(0.0, failures[0] + self.window - self._clock())

    def record_failure(self, key: str) -> None:
        """Count a failed attempt."""
        if len(self._failures) >= _MAX_KEYS:
            self._forget_quiet_keys()
        self._failures.setdefault(key, deque()).append(self._clock())

    def tracked(self) -> set[str]:
        """The keys with a failure on record (for the tests and for diagnosing)."""
        return set(self._failures)

    def _forget_quiet_keys(self) -> None:
        self._failures = {key: seen for key, seen in self._failures.items() if self._recent(key)}
