"""
BrandShield AI - RFC 7807 Problem Details for HTTP APIs.
Standardizes machine-readable error contracts across all security, validation,
governance, state machine, and privacy gate subsystems.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.telemetry import get_correlation_id

PROBLEM_JSON_MEDIA_TYPE = "application/problem+json"


class InvalidParam(BaseModel):
    """Specification of an invalid parameter field in RFC 7807 format."""
    name: str = Field(..., description="Field path or query parameter name")
    reason: str = Field(..., description="Human-readable reason for invalidity")
    error_type: Optional[str] = Field(None, description="Pydantic validation error code")


class ProblemDetail(BaseModel):
    """
    RFC 7807 Standardized Problem Details for HTTP APIs:
    - type: URI reference identifying the problem type
    - title: Short, human-readable summary of the problem type
    - status: HTTP status code
    - detail: Human-readable explanation specific to this occurrence
    - instance: URI reference that identifies the specific occurrence
    - correlation_id: Distributed tracing correlation identifier
    """
    type: str = Field(
        default="about:blank",
        description="URI reference resolving problem specification"
    )
    title: str = Field(..., description="High-level category title")
    status: int = Field(..., description="HTTP status code")
    detail: str = Field(..., description="Detailed contextual message")
    instance: str = Field(..., description="Request URI where the problem occurred")
    correlation_id: str = Field(..., description="Distributed tracing identifier")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC timestamp of occurrence"
    )
    invalid_params: Optional[list[InvalidParam]] = Field(
        default=None,
        description="Granular field validation errors if status is 422"
    )
    extensions: Optional[dict[str, Any]] = Field(
        default=None,
        description="Domain-specific contextual diagnostic attributes"
    )


class ProblemDetailException(Exception):
    """Base application exception mapped directly to RFC 7807 contracts."""

    def __init__(
        self,
        status_code: int,
        title: str,
        detail: str,
        type_uri: str = "about:blank",
        instance: Optional[str] = None,
        invalid_params: Optional[list[InvalidParam]] = None,
        extensions: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.title = title
        self.detail = detail
        self.type_uri = type_uri
        self.instance = instance
        self.invalid_params = invalid_params
        self.extensions = extensions or {}


# ------------------------------------------------------------------------------
# Concrete Enterprise Problem Exceptions
# ------------------------------------------------------------------------------

class ValidationErrorProblem(ProblemDetailException):
    """RFC 7807 422 validation failure."""

    def __init__(
        self,
        detail: str = "Request payload failed semantic or structural validation.",
        invalid_params: Optional[list[InvalidParam]] = None,
        extensions: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            title="Validation Error",
            detail=detail,
            type_uri="https://brandshield.ai/errors/validation-error",
            invalid_params=invalid_params,
            extensions=extensions,
        )


class StateMachineConflictProblem(ProblemDetailException):
    """RFC 7807 409 transition collision across Submission/Reviewer DAG states."""

    def __init__(
        self,
        detail: str,
        current_state: Optional[str] = None,
        attempted_state: Optional[str] = None,
        allowed_transitions: Optional[list[str]] = None,
    ) -> None:
        extensions: dict[str, Any] = {}
        if current_state:
            extensions["current_state"] = current_state
        if attempted_state:
            extensions["attempted_state"] = attempted_state
        if allowed_transitions:
            extensions["allowed_transitions"] = allowed_transitions

        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            title="State Machine Conflict",
            detail=detail,
            type_uri="https://brandshield.ai/errors/state-machine-conflict",
            extensions=extensions,
        )


class PrivacyGateBlockProblem(ProblemDetailException):
    """RFC 7807 403 Privacy Gate Egress Block."""

    def __init__(
        self,
        detail: str = "Privacy gate blocked external egress or data retention violation.",
        provider: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        extensions: dict[str, Any] = {}
        if provider:
            extensions["blocked_provider"] = provider
        if reason:
            extensions["policy_violation_reason"] = reason

        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            title="Privacy Gate Block",
            detail=detail,
            type_uri="https://brandshield.ai/errors/privacy-gate-block",
            extensions=extensions,
        )


class UnauthorizedProblem(ProblemDetailException):
    """RFC 7807 401 Credential or Token failure."""

    def __init__(
        self,
        detail: str = "Missing, invalid, or expired authentication token.",
        realm: str = "Bearer",
    ) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            title="Unauthorized",
            detail=detail,
            type_uri="https://brandshield.ai/errors/unauthorized",
            extensions={"realm": realm},
        )


class ForbiddenProblem(ProblemDetailException):
    """RFC 7807 403 RBAC authorization violation."""

    def __init__(
        self,
        detail: str = "Actor lacks requisite role permission for this operation.",
        required_roles: Optional[list[str]] = None,
        current_role: Optional[str] = None,
    ) -> None:
        extensions: dict[str, Any] = {}
        if required_roles:
            extensions["required_roles"] = required_roles
        if current_role:
            extensions["current_role"] = current_role

        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            title="Forbidden Access",
            detail=detail,
            type_uri="https://brandshield.ai/errors/forbidden",
            extensions=extensions,
        )


class NotFoundProblem(ProblemDetailException):
    """RFC 7807 404 Resource Not Found."""

    def __init__(
        self,
        detail: str = "Requested resource was not found.",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> None:
        extensions: dict[str, Any] = {}
        if resource_type:
            extensions["resource_type"] = resource_type
        if resource_id:
            extensions["resource_id"] = resource_id

        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            title="Resource Not Found",
            detail=detail,
            type_uri="https://brandshield.ai/errors/not-found",
            extensions=extensions,
        )


class ConflictProblem(ProblemDetailException):
    """RFC 7807 409 Resource Conflict."""

    def __init__(
        self,
        detail: str = "A conflict occurred with an existing resource.",
        conflicting_field: Optional[str] = None,
        conflicting_value: Optional[str] = None,
    ) -> None:
        extensions: dict[str, Any] = {}
        if conflicting_field:
            extensions["conflicting_field"] = conflicting_field
        if conflicting_value:
            extensions["conflicting_value"] = conflicting_value

        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            title="Conflict",
            detail=detail,
            type_uri="https://brandshield.ai/errors/conflict",
            extensions=extensions,
        )


class StateTransitionConflictProblem(ProblemDetailException):
    """RFC 7807 409 State Machine Conflict / Invalid Transition."""

    def __init__(
        self,
        detail: str,
        from_state: str,
        to_state: str,
        actor_role: Optional[str] = None,
    ) -> None:
        extensions: dict[str, Any] = {
            "from_state": from_state,
            "to_state": to_state,
        }
        if actor_role:
            extensions["actor_role"] = actor_role

        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            title="Invalid State Transition",
            detail=detail,
            type_uri="https://brandshield.ai/errors/state-transition-conflict",
            extensions=extensions,
        )


class InternalServerErrorProblem(ProblemDetailException):
    """RFC 7807 500 Unhandled system fault."""

    def __init__(
        self,
        detail: str = "An unexpected internal server error occurred.",
    ) -> None:
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Internal Server Error",
            detail=detail,
            type_uri="https://brandshield.ai/errors/internal-server-error",
        )


# ------------------------------------------------------------------------------
# FastAPI Exception Handlers
# ------------------------------------------------------------------------------

def _create_problem_response(
    status_code: int,
    title: str,
    detail: str,
    type_uri: str,
    instance: str,
    invalid_params: Optional[list[InvalidParam]] = None,
    extensions: Optional[dict[str, Any]] = None,
) -> JSONResponse:
    cid = get_correlation_id()
    problem = ProblemDetail(
        type=type_uri,
        title=title,
        status=status_code,
        detail=detail,
        instance=instance,
        correlation_id=cid,
        invalid_params=invalid_params,
        extensions=extensions,
    )
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_JSON_MEDIA_TYPE,
        headers={"X-Correlation-ID": cid},
    )


async def problem_detail_exception_handler(
    request: Request, exc: ProblemDetailException
) -> JSONResponse:
    """Translates domain ProblemDetailException to standardized RFC 7807 response."""
    instance = exc.instance or request.url.path
    return _create_problem_response(
        status_code=exc.status_code,
        title=exc.title,
        detail=exc.detail,
        type_uri=exc.type_uri,
        instance=instance,
        invalid_params=exc.invalid_params,
        extensions=exc.extensions,
    )


async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Transforms FastAPI / Pydantic validation errors into RFC 7807 response."""
    invalid_params: list[InvalidParam] = []
    for err in exc.errors():
        loc = ".".join(str(item) for item in err.get("loc", []))
        msg = err.get("msg", "Invalid value")
        err_type = err.get("type", "value_error")
        invalid_params.append(
            InvalidParam(name=loc, reason=msg, error_type=err_type)
        )

    return _create_problem_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        title="Unprocessable Entity",
        detail="The request body or parameters failed schema validation.",
        type_uri="https://brandshield.ai/errors/validation-error",
        instance=request.url.path,
        invalid_params=invalid_params,
    )


async def starlette_http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Translates standard HTTPExceptions into RFC 7807 responses."""
    detail_msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    title = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden Access",
        404: "Resource Not Found",
        405: "Method Not Allowed",
        409: "Conflict",
        422: "Unprocessable Entity",
        500: "Internal Server Error",
    }.get(exc.status_code, "HTTP Error")

    return _create_problem_response(
        status_code=exc.status_code,
        title=title,
        detail=detail_msg,
        type_uri=f"https://brandshield.ai/errors/{exc.status_code}",
        instance=request.url.path,
    )


async def generic_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Fallback handler catching unhandled exceptions to prevent stack trace leaks."""
    return _create_problem_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        title="Internal Server Error",
        detail="An unexpected internal server error occurred. Please reference the correlation_id for support.",
        type_uri="https://brandshield.ai/errors/internal-server-error",
        instance=request.url.path,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Registers all RFC 7807 Problem Details exception handlers on FastAPI instance."""
    app.add_exception_handler(ProblemDetailException, problem_detail_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
