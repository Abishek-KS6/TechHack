"""
BrandShield AI - RFC 7807 Problem Details and Telemetry Middleware Test Suite.
Validates standardized error structures, correlation ID propagation, and timing headers.
"""

from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient
import pytest

from app.core.exceptions import (
    PrivacyGateBlockProblem,
    StateMachineConflictProblem,
    ValidationErrorProblem,
    register_exception_handlers,
)
from app.core.telemetry import (
    CORRELATION_ID_HEADER,
    PROCESS_TIME_HEADER,
    TelemetryMiddleware,
    get_correlation_id,
)


@pytest.fixture
def app_with_controls() -> FastAPI:
    """Configures test FastAPI instance with Telemetry and Exception handlers."""
    app = FastAPI()
    app.add_middleware(TelemetryMiddleware)
    register_exception_handlers(app)

    @app.get("/test/success")
    async def sample_success():
        return {"status": "ok", "cid": get_correlation_id()}

    @app.get("/test/validation-error")
    async def sample_validation_error():
        raise ValidationErrorProblem(detail="Invalid clause_identifier format.")

    @app.get("/test/state-machine-conflict")
    async def sample_state_conflict():
        raise StateMachineConflictProblem(
            detail="Cannot transition from APPROVED to IN_CREATOR_REVISION without new revision.",
            current_state="APPROVED",
            attempted_state="IN_CREATOR_REVISION",
            allowed_transitions=["ARCHIVED"],
        )

    @app.get("/test/privacy-gate-block")
    async def sample_privacy_gate_block():
        raise PrivacyGateBlockProblem(
            detail="External LLM egress prohibited for unapproved provider 'UntrustedLLM'.",
            provider="UntrustedLLM",
            reason="UNAPPROVED_VENDOR",
        )

    return app


@pytest.mark.asyncio
async def test_telemetry_headers_injected_on_success(app_with_controls: FastAPI):
    """Verifies X-Correlation-ID and X-Process-Time-Ms headers are present in response."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_controls), base_url="http://test"
    ) as client:
        resp = await client.get("/test/success")
        assert resp.status_code == status.HTTP_200_OK
        assert CORRELATION_ID_HEADER in resp.headers
        assert len(resp.headers[CORRELATION_ID_HEADER]) >= 16
        assert PROCESS_TIME_HEADER in resp.headers
        duration = float(resp.headers[PROCESS_TIME_HEADER])
        assert duration >= 0.0


@pytest.mark.asyncio
async def test_inbound_correlation_id_propagated(app_with_controls: FastAPI):
    """Verifies client supplied correlation ID is preserved across boundary."""
    custom_cid = "enterprise-trace-xyz-98765"
    async with AsyncClient(
        transport=ASGITransport(app=app_with_controls), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/test/success", headers={CORRELATION_ID_HEADER: custom_cid}
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.headers[CORRELATION_ID_HEADER] == custom_cid
        assert resp.json()["cid"] == custom_cid


@pytest.mark.asyncio
async def test_rfc7807_validation_error_contract(app_with_controls: FastAPI):
    """Verifies 422 errors return RFC 7807 Problem Details contract."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_controls), base_url="http://test"
    ) as client:
        resp = await client.get("/test/validation-error")
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert resp.headers["content-type"] == "application/problem+json"

        body = resp.json()
        assert body["type"] == "https://brandshield.ai/errors/validation-error"
        assert body["title"] == "Validation Error"
        assert body["status"] == 422
        assert body["detail"] == "Invalid clause_identifier format."
        assert body["instance"] == "/test/validation-error"
        assert "correlation_id" in body
        assert "timestamp" in body


@pytest.mark.asyncio
async def test_rfc7807_state_machine_conflict_contract(app_with_controls: FastAPI):
    """Verifies 409 transition conflict returns RFC 7807 contract with diagnostic extensions."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_controls), base_url="http://test"
    ) as client:
        resp = await client.get("/test/state-machine-conflict")
        assert resp.status_code == status.HTTP_409_CONFLICT
        assert resp.headers["content-type"] == "application/problem+json"

        body = resp.json()
        assert body["type"] == "https://brandshield.ai/errors/state-machine-conflict"
        assert body["title"] == "State Machine Conflict"
        assert body["status"] == 409
        assert body["extensions"]["current_state"] == "APPROVED"
        assert body["extensions"]["attempted_state"] == "IN_CREATOR_REVISION"
        assert "ARCHIVED" in body["extensions"]["allowed_transitions"]


@pytest.mark.asyncio
async def test_rfc7807_privacy_gate_block_contract(app_with_controls: FastAPI):
    """Verifies 403 privacy gate block returns RFC 7807 contract with security extensions."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_controls), base_url="http://test"
    ) as client:
        resp = await client.get("/test/privacy-gate-block")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert resp.headers["content-type"] == "application/problem+json"

        body = resp.json()
        assert body["type"] == "https://brandshield.ai/errors/privacy-gate-block"
        assert body["title"] == "Privacy Gate Block"
        assert body["status"] == 403
        assert body["extensions"]["blocked_provider"] == "UntrustedLLM"
        assert body["extensions"]["policy_violation_reason"] == "UNAPPROVED_VENDOR"
