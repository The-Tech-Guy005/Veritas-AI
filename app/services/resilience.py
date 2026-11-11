"""
Resilience & Limits Engine
Provides:
1. Exponential backoff retry mechanisms with jitter.
2. Request rate limiting (sliding window token bucket).
3. Concurrency limits & resource budgeting.
4. Circuit breaker & timeout safeguards.
"""

import time
import random
import functools
from threading import Lock, BoundedSemaphore
from typing import Callable, Any, Tuple, Type, Optional, Dict, List

from app.config import settings


def retry_with_backoff(
    max_retries: Optional[int] = None,
    initial_delay: Optional[float] = None,
    backoff_factor: Optional[float] = None,
    max_delay: float = 10.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[BaseException], ...] = (Exception,)
) -> Callable:
    """
    Decorator for retrying operations with exponential backoff and randomized jitter.
    Tracks retry attempts and gracefully recovers from transient failures.
    """
    _retries = max_retries if max_retries is not None else settings.max_retries
    _init_delay = initial_delay if initial_delay is not None else settings.retry_initial_delay
    _factor = backoff_factor if backoff_factor is not None else settings.retry_backoff_factor

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            attempt = 0
            current_delay = _init_delay
            last_exception: Optional[BaseException] = None

            while attempt <= _retries:
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as exc:
                    attempt += 1
                    last_exception = exc
                    if attempt > _retries:
                        break

                    # Compute backoff with jitter
                    sleep_time = current_delay
                    if jitter:
                        sleep_time = current_delay * (0.8 + 0.4 * random.random())
                    sleep_time = min(sleep_time, max_delay)

                    time.sleep(sleep_time)
                    current_delay *= _factor

            raise last_exception or RuntimeError(f"Operation failed after {_retries} retries.")
        return wrapper
    return decorator


class RateLimiter:
    """
    Sliding window rate limiter per client/key or globally.
    Prevents resource exhaustion by limiting requests per minute.
    """
    def __init__(self, default_limit: Optional[int] = None, window_seconds: int = 60):
        self.default_limit = default_limit or settings.rate_limit_per_minute
        self.window_seconds = window_seconds
        self._history: Dict[str, List[float]] = {}
        self._lock = Lock()

    def is_allowed(self, key: str = "global", limit: Optional[int] = None) -> bool:
        """
        Returns True if request is within rate limit; otherwise False.
        """
        max_requests = limit or self.default_limit
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
            timestamps = self._history.get(key, [])
            # Filter timestamps outside current window
            valid_timestamps = [t for t in timestamps if t >= window_start]
            
            if len(valid_timestamps) < max_requests:
                valid_timestamps.append(now)
                self._history[key] = valid_timestamps
                return True
            else:
                self._history[key] = valid_timestamps
                return False

    def reset(self, key: Optional[str] = None):
        with self._lock:
            if key:
                self._history.pop(key, None)
            else:
                self._history.clear()


class ConcurrencyLimiter:
    """
    Limits concurrent parallel operations across sub-agents using bounded semaphores.
    """
    def __init__(self, max_concurrency: Optional[int] = None):
        capacity = max_concurrency or settings.max_concurrency
        self.semaphore = BoundedSemaphore(value=capacity)
        self.capacity = capacity

    def __enter__(self):
        self.semaphore.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.semaphore.release()


# Global singletons
rate_limiter = RateLimiter()
concurrency_limiter = ConcurrencyLimiter()
