"""
BrandShield AI - Distributed Observability, Telemetry & Structured Logging Middleware.
Provides RFC-compliant X-Correlation-ID propagation, high-precision latency instrumentation,
and contextual JSON logging across all API perimeter boundaries.
"""

from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import sys
import time
from typing import Any
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Request-scoped correlation ID context variable
CORRELATION_ID_HEADER = "X-Correlation-ID"
PROCESS_TIME_HEADER = "X-Process-Time-Ms"

_correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Retrieves current request correlation ID or generates a fallback identifier."""
    cid = _correlation_id_ctx.get()
    return cid if cid else uuid.uuid4().hex


def set_correlation_id(correlation_id: str) -> None:
    """Sets correlation ID for current async execution context."""
    _correlation_id_ctx.set(correlation_id)


class StructuredJsonFormatter(logging.Formatter):
    """
    High-performance JSON log formatter emitting structured telemetry events
    compatible with Datadog, Splunk, Elastic, and CloudWatch.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": _correlation_id_ctx.get() or None,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include custom extra attributes if supplied
        if hasattr(record, "props") and isinstance(record.props, dict):
            log_payload.update(record.props)

        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_payload, default=str)


def setup_telemetry_logging(level: int = logging.INFO) -> logging.Logger:
    """Configures root logger with JSON telemetry formatting."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers if already initialized
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter())
    root_logger.addHandler(handler)

    return logging.getLogger("brandshield.telemetry")


logger = logging.getLogger("brandshield.telemetry")


class TelemetryMiddleware(BaseHTTPMiddleware):
    """
    Enterprise ASGI Middleware:
    1. Extracts or synthesizes X-Correlation-ID for zero-loss tracing.
    2. Instruments sub-millisecond execution latency (X-Process-Time-Ms).
    3. Emits structured JSON access logs with HTTP metadata.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        inbound_cid = request.headers.get(CORRELATION_ID_HEADER)
        correlation_id = inbound_cid.strip() if inbound_cid and inbound_cid.strip() else uuid.uuid4().hex

        token = _correlation_id_ctx.set(correlation_id)
        start_time = time.perf_counter()

        client_host = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        method = request.method
        path = request.url.path

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            response.headers[CORRELATION_ID_HEADER] = correlation_id
            response.headers[PROCESS_TIME_HEADER] = f"{duration_ms:.2f}"

            # Structured audit access log
            logger.info(
                f"{method} {path} - {response.status_code} ({duration_ms}ms)",
                extra={
                    "props": {
                        "event": "http_request_complete",
                        "http_method": method,
                        "http_path": path,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                        "client_ip": client_host,
                        "user_agent": user_agent,
                        "correlation_id": correlation_id,
                    }
                },
            )
            return response

        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                f"Unhandled error processing {method} {path}: {str(exc)}",
                exc_info=True,
                extra={
                    "props": {
                        "event": "http_request_failed",
                        "http_method": method,
                        "http_path": path,
                        "duration_ms": duration_ms,
                        "client_ip": client_host,
                        "correlation_id": correlation_id,
                    }
                },
            )
            raise exc
        finally:
            _correlation_id_ctx.reset(token)
