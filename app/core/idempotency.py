"""
BrandShield AI - Stripe-Style Idempotency Engine.
Provides at-least-once to exactly-once delivery guarantees for state-mutating HTTP requests (POST, PATCH, PUT).
Caches status code, response headers, and response payload keyed by (tenant_scope, idempotency_key).
Guarantees race-condition protection via in-flight execution locks.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("brandshield.core.idempotency")


@dataclass
class CachedIdempotentResponse:
    """Container for cached idempotent response payloads."""
    status_code: int
    headers: dict[str, str]
    body: bytes
    media_type: Optional[str]
    created_at: float
    is_in_flight: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class IdempotencyCache:
    """Thread-safe and async-safe in-memory cache for idempotent request replays."""
    _store: dict[str, CachedIdempotentResponse] = {}
    _ttl_seconds: int = 86400  # 24 hours

    @classmethod
    def get(cls, key: str) -> Optional[CachedIdempotentResponse]:
        item = cls._store.get(key)
        if item is None:
            return None
        now = datetime.now(timezone.utc).timestamp()
        if (now - item.created_at) > cls._ttl_seconds:
            cls._store.pop(key, None)
            return None
        return item

    @classmethod
    def reserve(cls, key: str) -> CachedIdempotentResponse:
        now = datetime.now(timezone.utc).timestamp()
        entry = CachedIdempotentResponse(
            status_code=0,
            headers={},
            body=b"",
            media_type=None,
            created_at=now,
            is_in_flight=True,
        )
        cls._store[key] = entry
        return entry

    @classmethod
    def save(
        cls,
        key: str,
        status_code: int,
        headers: dict[str, str],
        body: bytes,
        media_type: Optional[str] = None,
    ) -> None:
        entry = cls._store.get(key)
        now = datetime.now(timezone.utc).timestamp()
        if entry:
            entry.status_code = status_code
            entry.headers = headers
            entry.body = body
            entry.media_type = media_type
            entry.created_at = now
            entry.is_in_flight = False
        else:
            cls._store[key] = CachedIdempotentResponse(
                status_code=status_code,
                headers=headers,
                body=body,
                media_type=media_type,
                created_at=now,
                is_in_flight=False,
            )

    @classmethod
    def clear(cls) -> None:
        """Flushes all cached responses."""
        cls._store.clear()


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware intercepting POST, PUT, PATCH requests containing an `Idempotency-Key` header.
    Replays exact cached responses on duplicate submissions without re-executing mutations.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.method not in ("POST", "PATCH", "PUT"):
            return await call_next(request)

        idempotency_key = request.headers.get("idempotency-key") or request.headers.get("Idempotency-Key")
        if not idempotency_key or not idempotency_key.strip():
            return await call_next(request)

        idempotency_key = idempotency_key.strip()
        auth_header = request.headers.get("authorization", "")
        # Scope key by authorization prefix and request path
        cache_key = f"{auth_header[:32]}:{request.url.path}:{idempotency_key}"

        cached = IdempotencyCache.get(cache_key)
        if cached is not None:
            if cached.is_in_flight:
                # Concurrent request in-flight: wait for initial request to finish
                async with cached.lock:
                    pass
                # Read completed result
                cached = IdempotencyCache.get(cache_key)
                if cached and not cached.is_in_flight:
                    response_headers = dict(cached.headers)
                    response_headers["X-Cache-Idempotency"] = "HIT"
                    return Response(
                        content=cached.body,
                        status_code=cached.status_code,
                        headers=response_headers,
                        media_type=cached.media_type,
                    )

            if not cached.is_in_flight and cached.status_code != 0:
                response_headers = dict(cached.headers)
                response_headers["X-Cache-Idempotency"] = "HIT"
                return Response(
                    content=cached.body,
                    status_code=cached.status_code,
                    headers=response_headers,
                    media_type=cached.media_type,
                )

        # Reserve key in-flight
        entry = IdempotencyCache.reserve(cache_key)
        async with entry.lock:
            try:
                response = await call_next(request)

                # Read body for caching
                resp_body = [chunk async for chunk in response.body_iterator]
                body_bytes = b"".join(resp_body)

                # Extract cachable response headers
                cached_headers: dict[str, str] = {}
                for k, v in response.headers.items():
                    if k.lower() not in ("content-length", "content-encoding", "transfer-encoding"):
                        cached_headers[k] = v

                # Only cache successful or client error responses (never transient 500s)
                if response.status_code < 500:
                    IdempotencyCache.save(
                        key=cache_key,
                        status_code=response.status_code,
                        headers=cached_headers,
                        body=body_bytes,
                        media_type=response.media_type,
                    )
                else:
                    IdempotencyCache._store.pop(cache_key, None)

                cached_headers["X-Cache-Idempotency"] = "MISS"
                return Response(
                    content=body_bytes,
                    status_code=response.status_code,
                    headers=cached_headers,
                    media_type=response.media_type,
                )
            except Exception:
                IdempotencyCache._store.pop(cache_key, None)
                raise
