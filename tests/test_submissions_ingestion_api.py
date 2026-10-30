"""
BrandShield AI - Submissions Ingestion & AST API Test Suite.
Validates raw text ingestion, multipart document upload, Genesis revision creation,
and RBAC enforcement on /api/v1/submissions.
"""

from datetime import datetime, timezone
import io
from unittest.mock import AsyncMock
import uuid
import zipfile
import fitz
from httpx import ASGITransport, AsyncClient
import pytest

from app.core.security import create_access_token, hash_password
from app.domain.enums import UserRole
from app.infrastructure.db.models import BrandProfile, User
from app.infrastructure.db.session import get_async_session
from app.main import app


@pytest.fixture
def workspace_id():
    return uuid.uuid4()


@pytest.fixture
def brand_profile_id():
    return uuid.uuid4()


@pytest.fixture
def creator_user(workspace_id):
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        email="creator@brandshield.ai",
        hashed_password=hash_password("CreatorSecure123!"),
        full_name="Enterprise Creator",
        role=UserRole.CREATOR,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def reviewer_user(workspace_id):
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        email="reviewer@brandshield.ai",
        hashed_password=hash_password("ReviewerSecure123!"),
        full_name="Compliance Reviewer",
        role=UserRole.REVIEWER,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def brand_profile(workspace_id, brand_profile_id):
    now = datetime.now(timezone.utc)
    return BrandProfile(
        id=brand_profile_id,
        workspace_id=workspace_id,
        name="Global B2B SaaS Profile",
        description="Profile for enterprise B2B",
        tone_parameters={},
        banned_terminology_map={},
        preferred_terminology_map={},
        messaging_rules={},
        privacy_gate_config={"allow_external_llm": False, "approved_providers": [], "retention_days": 30},
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def creator_token(creator_user):
    return create_access_token(
        user_id=creator_user.id,
        email=creator_user.email,
        role=creator_user.role,
        workspace_id=creator_user.workspace_id,
    )


@pytest.fixture
def reviewer_token(reviewer_user):
    return create_access_token(
        user_id=reviewer_user.id,
        email=reviewer_user.email,
        role=reviewer_user.role,
        workspace_id=reviewer_user.workspace_id,
    )


@pytest.mark.asyncio
async def test_text_submission_creates_genesis_revision(
    creator_user, brand_profile, creator_token, brand_profile_id
):
    """
    Validates POST /api/v1/submissions/text:
    Normalizes text, creates Submission & DocumentRevision v1 with AST span map.
    """
    mock_session = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return creator_user
        if model == BrandProfile:
            return brand_profile
        return None

    mock_session.get.side_effect = mock_get
    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/submissions/text",
                headers={"Authorization": f"Bearer {creator_token}"},
                json={
                    "title": "Q3 Marketing Campaign",
                    "brand_profile_id": str(brand_profile_id),
                    "content": "Leading enterprise AI platform.\n\nGuarantees 99.99% compliance SLA.",
                    "document_type": "TEXT",
                },
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["title"] == "Q3 Marketing Campaign"
            assert data["workflow_state"] == "SUBMITTED"
            assert resp.headers.get("X-Correlation-ID") is not None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_pdf_upload_submission_success(
    creator_user, brand_profile, creator_token, brand_profile_id
):
    """
    Validates POST /api/v1/submissions/upload with valid PDF:
    Verifies magic bytes, tokenizes blocks with bounding boxes, establishes Revision v1.
    """
    # Create in-memory PDF
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Official Quarterly Press Release.")
    pdf_bytes = doc.tobytes()
    doc.close()

    mock_session = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return creator_user
        if model == BrandProfile:
            return brand_profile
        return None

    mock_session.get.side_effect = mock_get
    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            files = {"file": ("press_release.pdf", pdf_bytes, "application/pdf")}
            data = {
                "title": "Q3 Press Release PDF",
                "brand_profile_id": str(brand_profile_id),
            }
            resp = await client.post(
                "/api/v1/submissions/upload",
                headers={"Authorization": f"Bearer {creator_token}"},
                data=data,
                files=files,
            )
            assert resp.status_code == 201
            res_data = resp.json()
            assert res_data["title"] == "Q3 Press Release PDF"
            assert res_data["document_type"] == "PDF"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_upload_malicious_macro_docx_rejected(
    creator_user, brand_profile, creator_token, brand_profile_id
):
    """
    Validates that uploading a DOCX containing VBA macro payload triggers 422 RFC 7807 error.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "<w:document><w:body></w:body></w:document>")
        zf.writestr("word/vbaProject.bin", b"MALICIOUS_VBA_BIN")

    macro_bytes = buf.getvalue()

    mock_session = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return creator_user
        if model == BrandProfile:
            return brand_profile
        return None

    mock_session.get.side_effect = mock_get
    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            files = {"file": ("malicious.docx", macro_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
            data = {
                "title": "Infected Document",
                "brand_profile_id": str(brand_profile_id),
            }
            resp = await client.post(
                "/api/v1/submissions/upload",
                headers={"Authorization": f"Bearer {creator_token}"},
                data=data,
                files=files,
            )
            assert resp.status_code == 422
            assert resp.headers["content-type"] == "application/problem+json"
            err = resp.json()
            assert "macro" in err["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_reviewer_cannot_submit_content(
    reviewer_user, reviewer_token, brand_profile_id
):
    """
    Validates RBAC: REVIEWER persona cannot submit content (only CREATOR or ADMINISTRATOR allowed).
    """
    mock_session = AsyncMock()
    mock_session.get.return_value = reviewer_user
    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/submissions/text",
                headers={"Authorization": f"Bearer {reviewer_token}"},
                json={
                    "title": "Reviewer Attempt",
                    "brand_profile_id": str(brand_profile_id),
                    "content": "Trying to submit as reviewer.",
                },
            )
            assert resp.status_code == 403
            err = resp.json()
            assert err["type"] == "https://brandshield.ai/errors/forbidden"
    finally:
        app.dependency_overrides.clear()
