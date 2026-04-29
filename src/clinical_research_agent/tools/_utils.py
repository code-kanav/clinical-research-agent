from __future__ import annotations

import hashlib
import time
from threading import Lock
from typing import Any, Optional

import diskcache
import httpx

_cache_instance: Optional[diskcache.Cache] = None
_cache_lock = Lock()


def _get_cache() -> diskcache.Cache:
    global _cache_instance
    if _cache_instance is None:
        with _cache_lock:
            if _cache_instance is None:
                from clinical_research_agent.config import get_settings
                _cache_instance = diskcache.Cache(get_settings().cache_dir)
    return _cache_instance


def make_key(*parts: str) -> str:
    return hashlib.md5(":".join(parts).encode()).hexdigest()


def get_cached(key: str) -> Any:
    from clinical_research_agent.config import get_settings
    if get_settings().cache_ttl_seconds == 0:
        return None
    return _get_cache().get(key)


def set_cached(key: str, value: Any) -> None:
    from clinical_research_agent.config import get_settings
    settings = get_settings()
    if settings.cache_ttl_seconds == 0:
        return
    _get_cache().set(key, value, expire=settings.cache_ttl_seconds)


def http_get(
    url: str,
    *,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 30.0,
    retries: int = 3,
) -> httpx.Response:
    """GET with timeout and exponential-backoff retry on transient errors.

    Retries on: connection errors, timeouts, 429, 5xx.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(url, params=params, headers=headers)
            if resp.status_code == 429 or resp.status_code >= 500:
                last_exc = httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}", request=resp.request, response=resp
                )
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise last_exc or RuntimeError("http_get failed after retries")


class RateLimiter:
    def __init__(self, calls_per_second: float) -> None:
        self._interval = 1.0 / calls_per_second
        self._last = 0.0
        self._lock = Lock()

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last
            remaining = self._interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
            self._last = time.monotonic()
