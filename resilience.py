import time
import threading
import functools
import asyncio
from typing import Callable


def retry(times: int = 3, delay: float = 0.2, backoff: float = 2.0, exceptions=(Exception,)):
    def deco(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            _tries = times
            _delay = delay
            while _tries > 0:
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    _tries -= 1
                    if _tries <= 0:
                        raise
                    time.sleep(_delay)
                    _delay *= backoff
        return wrapper
    return deco


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_time: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self._failures = 0
        self._state = 'CLOSED'
        self._opened_at = None
        self._lock = threading.RLock()

    def call_allowed(self) -> bool:
        with self._lock:
            if self._state == 'OPEN':
                if (time.time() - self._opened_at) > self.recovery_time:
                    self._state = 'HALF'
                    return True
                return False
            return True

    def record_success(self):
        with self._lock:
            self._failures = 0
            self._state = 'CLOSED'

    def record_failure(self):
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._state = 'OPEN'
                self._opened_at = time.time()

    def protect(self, func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not self.call_allowed():
                raise RuntimeError('Circuit open')
            try:
                res = func(*args, **kwargs)
                self.record_success()
                return res
            except Exception:
                self.record_failure()
                raise
        return wrapper


class AsyncCircuitBreaker(CircuitBreaker):
    async def protect_async(self, func: Callable):
        async def wrapper(*args, **kwargs):
            if not self.call_allowed():
                raise RuntimeError('Circuit open')
            try:
                res = await func(*args, **kwargs)
                self.record_success()
                return res
            except Exception:
                self.record_failure()
                raise
        return wrapper


def async_retry(times: int = 3, delay: float = 0.2, backoff: float = 2.0, exceptions=(Exception,)):
    def deco(func: Callable):
        async def wrapper(*args, **kwargs):
            _tries = times
            _delay = delay
            while _tries > 0:
                try:
                    return await func(*args, **kwargs)
                except exceptions:
                    _tries -= 1
                    if _tries <= 0:
                        raise
                    await asyncio.sleep(_delay)
                    _delay *= backoff
        return wrapper
    return deco
