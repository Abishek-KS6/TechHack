"""
Integration tests for Server-Sent Events (SSE) streaming analysis endpoint:
GET /api/v1/submissions/{id}/analyze/stream
"""

from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.domain.enums import UserRole, WorkflowState
from app.infrastructure.db.models import BrandProfile, DocumentRevision, Submission, User
from app.main import app


@pytest.fixture
def mock_auth_token():
    from datetime import timedelta
    from app.core.security import create_access_token
    uid = uuid.uuid4()
    wid = uuid.uuid4()
    token = create_access_token(
        user_id=uid,
        email="creator@enterprise.com",
        role=UserRole.CREATOR,
        workspace_id=wid,
        expires_delta=timedelta(hours=1),
    )
    return token, uid, wid


@pytest.mark.asyncio
async def test_sse_streaming_endpoint_success(mock_auth_token):
    token, uid, wid = mock_auth_token
    sub_id = uuid.uuid4()
    rev_id = uuid.uuid4()
    prof_id = uuid.uuid4()

    mock_user = MagicMock(spec=User)
    mock_user.id = uid
    mock_user.workspace_id = wid
    mock_user.role = UserRole.CREATOR
    mock_user.is_active = True

    mock_sub = MagicMock(spec=Submission)
    mock_sub.id = sub_id
    mock_sub.workspace_id = wid
    mock_sub.brand_profile_id = prof_id
    mock_sub.current_revision_id = rev_id
    mock_sub.workflow_state = WorkflowState.SUBMITTED

    mock_rev = MagicMock(spec=DocumentRevision)
    mock_rev.id = rev_id
    mock_rev.submission_id = sub_id
    mock_rev.content_text = "Acme guarantees 100% cure for headaches."

    mock_profile = MagicMock(spec=BrandProfile)
    mock_profile.id = prof_id
    mock_profile.workspace_id = wid
    mock_profile.brand_name = "Acme Corp"
    mock_profile.tone_guidelines = "Professional"

    mock_session = AsyncMock()

    async def mock_get(model, entity_id):
        if model == User:
            return mock_user
        if model == Submission:
            return mock_sub
        if model == DocumentRevision:
            return mock_rev
        if model == BrandProfile:
            return mock_profile
        return None

    mock_session.get.side_effect = mock_get

    # Mock execute for guidelines query
    mock_exec = MagicMock()
    mock_exec.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_exec

    from app.infrastructure.db.session import get_async_session
    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test authentication via query param (?token=) as supported by EventSource
            response = await client.get(
                f"/api/v1/submissions/{sub_id}/analyze/stream?token={token}",
            )
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")

            body = response.text
            assert "event: STAGE_1_DETERMINISTIC_COMPLETE" in body
            assert "event: STAGE_2_TEMPORAL_FACT_RAG_COMPLETE" in body
            assert "event: STAGE_3_PRIVACY_GATE_VERIFIED" in body
            assert "event: STAGE_4_TRIAGE_COMPLETE" in body
            assert "event: PIPELINE_COMPLETE" in body
    finally:
        app.dependency_overrides.pop(get_async_session, None)
