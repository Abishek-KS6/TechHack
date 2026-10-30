"""
BrandShield AI - Enterprise Guarantees Verification Test Suite.
Verifies critical non-negotiable enterprise architectural guarantees:
a) Creators cannot call Reviewer approval endpoints (403 Forbidden + audit log entry).
b) Submitting a revision creates a new DocumentRevision node and preserves the original content hash (zero silent overwriting).
c) Disabling allow_external_llm in privacy_gate_config strictly blocks external LLM calls and logs to audit_ledger.
d) Expired facts are deterministically flagged for re-verification.
e) Claims without supporting facts are marked "Needs verification" and never claimed as violations.
f) Visual Asset Matcher strictly compares against approved organizational assets and detects distorted, outdated, and unapproved logos.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import io
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.core.security import create_access_token
from app.domain.enums import (
    AuditAction,
    DetectorSource,
    FindingCategory,
    ReviewSignOff,
    SeverityLevel,
    TriageStatus,
    UserRole,
    WorkflowState,
)
from app.domain.schemas.asset import AssetMatchStatus
from app.domain.schemas.submission import ReviewDecisionCreate
from app.infrastructure.db.models import (
    ApprovedFact,
    BrandProfile,
    DocumentRevision,
    Finding,
    Submission,
    User,
)
from app.infrastructure.db.session import get_async_session
from app.main import app
from app.services.analysis.asset_matcher import VisualAssetMatcher
from app.services.analysis.privacy_gate import PrivacyGateRouter
from app.services.analysis.temporal_fact_engine import TemporalFactEngine
from app.services.audit_service import AuditService
from app.services.submission_service import SubmissionService


# ==============================================================================
# Guarantee A: Creators cannot call Reviewer approval endpoints
# ==============================================================================

@pytest.mark.asyncio
async def test_guarantee_a_creator_cannot_approve_submission():
    """
    Guarantee A:
    Creators attempting to execute Reviewer approval endpoints MUST receive
    an RFC 7807 403 Forbidden response and trigger an UNAUTHORIZED_ROLE_ACCESS
    audit log entry in the audit_ledger.
    """
    creator_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    submission_id = uuid.uuid4()

    creator_token = create_access_token(
        user_id=creator_id,
        email="creator@enterprise.com",
        role=UserRole.CREATOR,
        workspace_id=workspace_id,
    )

    creator_user = MagicMock(spec=User)
    creator_user.id = creator_id
    creator_user.workspace_id = workspace_id
    creator_user.role = UserRole.CREATOR
    creator_user.is_active = True

    mock_session = AsyncMock()
    mock_session.get.return_value = creator_user

    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch.object(AuditService, "record_event", new_callable=AsyncMock) as mock_audit:
                response = await client.post(
                    f"/api/v1/submissions/{submission_id}/decisions",
                    headers={"Authorization": f"Bearer {creator_token}"},
                    json={
                        "decision": "APPROVED",
                        "comments": "Attempting creator self-approval",
                    },
                )
                assert response.status_code == 403
                problem = response.json()
                assert problem["status"] == 403
                assert "Required role(s)" in problem["detail"] or "Forbidden" in problem["title"]

                # Guarantee audit entry logged
                mock_audit.assert_awaited()
                call_kwargs = mock_audit.call_args.kwargs
                assert call_kwargs["action"] == AuditAction.UNAUTHORIZED_ACCESS_ATTEMPT
                assert call_kwargs["actor_id"] == creator_id
    finally:
        app.dependency_overrides.pop(get_async_session, None)


# ==============================================================================
# Guarantee B: Immutable DocumentRevision DAG & Content Hash Preservation
# ==============================================================================

@pytest.mark.asyncio
async def test_guarantee_b_revision_commit_preserves_parent_hash():
    """
    Guarantee B:
    Submitting a revision creates a new DocumentRevision node and preserves
    the original parent content text and SHA-256 hash (zero silent overwriting).
    """
    submission_id = uuid.uuid4()
    creator_id = uuid.uuid4()
    workspace_id = uuid.uuid4()

    initial_content = "Version 1 content: Enterprise brand guidelines are mandatory."
    initial_hash = hashlib.sha256(initial_content.encode("utf-8")).hexdigest()

    genesis_rev = DocumentRevision(
        id=uuid.uuid4(),
        submission_id=submission_id,
        revision_number=1,
        parent_revision_id=None,
        content_text=initial_content,
        ast_span_map=[],
        sha256_content_hash=initial_hash,
    )

    submission = Submission(
        id=submission_id,
        workspace_id=workspace_id,
        brand_profile_id=uuid.uuid4(),
        creator_id=creator_id,
        title="Policy Document",
        document_type="TEXT",
        workflow_state=WorkflowState.CHANGES_REQUESTED,
        current_revision_id=genesis_rev.id,
    )
    submission.current_revision = genesis_rev

    mock_session = AsyncMock()

    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = submission
    mock_session.execute.return_value = mock_exec

    async def mock_get(model, entity_id):
        if model == Submission and entity_id == submission_id:
            return submission
        if model == DocumentRevision and entity_id == genesis_rev.id:
            return genesis_rev
        return None

    mock_session.get.side_effect = mock_get

    new_content = "Version 2 content: Enterprise brand guidelines are mandatory and strictly monitored."
    new_spans = [{"start_char": 0, "end_char": len(new_content), "block_type": "PARAGRAPH"}]

    with patch.object(AuditService, "record_event", new_callable=AsyncMock) as mock_audit:
        rev_v2 = await SubmissionService.commit_revision(
            session=mock_session,
            submission_id=submission_id,
            new_content=new_content,
            ast_span_map=new_spans,
            creator_id=creator_id,
        )

        # Verification of append-only DAG properties
        assert rev_v2.revision_number == 2
        assert rev_v2.parent_revision_id == genesis_rev.id
        assert rev_v2.content_text == new_content
        assert rev_v2.sha256_content_hash != initial_hash

        # Verification of Genesis Revision Immutability
        assert genesis_rev.content_text == initial_content
        assert genesis_rev.sha256_content_hash == initial_hash
        assert genesis_rev.revision_number == 1

        # Submission tip pointer updated
        assert submission.current_revision_id == rev_v2.id
        assert submission.workflow_state == WorkflowState.ANALYZING

        # Audit ledger event recorded
        mock_audit.assert_awaited()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["action"] == AuditAction.REVISION_COMMITTED
        assert call_kwargs["payload"]["parent_revision_id"] == str(genesis_rev.id)
        assert call_kwargs["payload"]["sha256_hash"] == rev_v2.sha256_content_hash


# ==============================================================================
# Guarantee C: Privacy Gate External LLM Blocking & Audit
# ==============================================================================

@pytest.mark.asyncio
async def test_guarantee_c_privacy_gate_blocks_external_llm_and_audits():
    """
    Guarantee C:
    Disabling allow_external_llm in privacy_gate_config strictly blocks
    external LLM network calls and commits an audit log entry.
    """
    workspace_id = uuid.uuid4()
    brand_profile = MagicMock(spec=BrandProfile)
    brand_profile.id = uuid.uuid4()
    brand_profile.workspace_id = workspace_id
    brand_profile.privacy_gate_config = {
        "allow_external_llm": False,  # Strict block
        "contract_verified_at": "2026-01-01T00:00:00Z",
        "retention_days": 14,
        "approved_providers": ["Azure OpenAI"],
    }

    is_cleared, reason = PrivacyGateRouter.evaluate_privacy_clearance(
        brand_profile=brand_profile,
        requested_provider="Azure OpenAI",
    )
    assert is_cleared is False
    assert "strictly prohibits external LLM" in reason

    # Test full analyze_tone_and_messaging execution under disabled gate
    mock_session = AsyncMock()
    with patch.object(AuditService, "record_event", new_callable=AsyncMock) as mock_audit:
        findings = await PrivacyGateRouter.analyze_tone_and_messaging(
            content_text="Confidential internal corporate strategy details.",
            brand_profile=brand_profile,
            workspace_id=workspace_id,
            session=mock_session,
            requested_provider="Azure OpenAI",
        )
        assert len(findings) == 0

        # Audit verification
        mock_audit.assert_awaited()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["action"] == AuditAction.PRIVACY_GATE_BLOCKED_EXTERNAL_AI
        assert call_kwargs["workspace_id"] == workspace_id


# ==============================================================================
# Guarantee D: Expired facts deterministically flagged for re-verification
# ==============================================================================

@pytest.mark.asyncio
async def test_guarantee_d_expired_facts_flagged_for_reverification():
    """
    Guarantee D:
    Expired approved facts are deterministically flagged for re-verification
    (STALE_FACT_REVERIFY) and not silently treated as valid ground truth.
    """
    workspace_id = uuid.uuid4()
    fact_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Fact expired 30 days ago
    expired_fact = MagicMock(spec=ApprovedFact)
    expired_fact.id = fact_id
    expired_fact.fact_statement = "Our legacy database engine delivers 99.9% uptime."
    expired_fact.valid_from = now - timedelta(days=365)
    expired_fact.valid_until = now - timedelta(days=30)
    expired_fact.expiry_date = now - timedelta(days=30)
    expired_fact.is_active = True

    mock_session = AsyncMock()

    content = "Our legacy database engine delivers 99.9% uptime according to our SLA."

    hits = await TemporalFactEngine.evaluate_claims(
        content_text=content,
        workspace_id=workspace_id,
        session=mock_session,
        preloaded_facts=[expired_fact],
    )

    stale_hits = [h for h in hits if h.triage_status == TriageStatus.STALE_FACT_REVERIFY]
    assert len(stale_hits) >= 1
    hit = stale_hits[0]
    assert hit.issue_category == FindingCategory.STALE_FACT
    assert hit.linked_fact_id == fact_id
    assert "expired" in hit.explanation_reason.lower()


# ==============================================================================
# Guarantee E: Claims without facts marked "Needs verification"
# ==============================================================================

@pytest.mark.asyncio
async def test_guarantee_e_ungrounded_claims_marked_needs_verification():
    """
    Guarantee E:
    Claims lacking supporting facts are marked 'Needs verification'
    (NEEDS_VERIFICATION_MISSING_EVIDENCE) and NEVER claimed as violations.
    """
    workspace_id = uuid.uuid4()
    mock_session = AsyncMock()

    # Content with numerical / quantitative claim but zero approved facts in catalog
    content = "Our patented algorithm boosts client revenue by 342% in just two weeks."

    hits = await TemporalFactEngine.evaluate_claims(
        content_text=content,
        workspace_id=workspace_id,
        session=mock_session,
        preloaded_facts=[],  # Empty catalog
    )

    ungrounded_hits = [
        h for h in hits if h.triage_status == TriageStatus.NEEDS_VERIFICATION_MISSING_EVIDENCE
    ]
    assert len(ungrounded_hits) >= 1
    hit = ungrounded_hits[0]
    assert hit.issue_category == FindingCategory.UNSUBSTANTIATED_CLAIM
    assert hit.severity == SeverityLevel.MEDIUM
    assert "needs verification" in hit.explanation_reason.lower() or "supporting evidence unavailable" in hit.explanation_reason.lower()
    assert hit.linked_fact_id is None


# ==============================================================================
# Guarantee F: Approved Brand Asset Matcher Visual Inspection
# ==============================================================================

@pytest.mark.asyncio
async def test_guarantee_f_asset_matcher_visual_inspection():
    """
    Guarantee F:
    Visual Asset Matcher strictly compares against approved organizational
    brand assets, detecting approved matches, distorted logos, outdated logos,
    and unapproved visual assets.
    """
    brand_id = uuid.uuid4()
    approved_logo_id = uuid.uuid4()
    deprecated_logo_id = uuid.uuid4()

    # 1. Create native approved reference image (200x100, left half white, right half black, ratio = 2.0)
    ref_image = Image.new("RGB", (200, 100), color=(0, 0, 0))
    for x in range(100):
        for y in range(100):
            ref_image.putpixel((x, y), (255, 255, 255))

    ref_dhash = VisualAssetMatcher.compute_dhash(ref_image)
    ref_ratio = 2.0

    # 2. Approved catalog setup
    approved_catalog = [
        {
            "id": approved_logo_id,
            "name": "Official Corporate Shield Logo",
            "dhash": ref_dhash,
            "aspect_ratio": ref_ratio,
            "is_deprecated": False,
        },
        {
            "id": deprecated_logo_id,
            "name": "2020 Heritage Brand Logo",
            "dhash": "aaaaaaaaaaaaaaaa",
            "aspect_ratio": 1.5,
            "is_deprecated": True,
        },
    ]

    # Test Case 1: Compliant Match
    finding_clean = VisualAssetMatcher.evaluate_image(
        image=ref_image,
        image_index=0,
        source_format="PNG",
        approved_catalog=approved_catalog,
    )
    assert finding_clean.match_status == AssetMatchStatus.APPROVED_MATCH
    assert finding_clean.is_compliant is True
    assert finding_clean.matched_approved_asset_id == approved_logo_id
    assert finding_clean.comparison_scope == "ORGANIZATIONAL_APPROVED_ASSETS_ONLY"

    # Test Case 2: Stretched / Distorted Logo (non-uniform scaling to 400x100, aspect ratio = 4.0, > 8% distortion)
    stretched_image = ref_image.resize((400, 100), Image.Resampling.BILINEAR)
    finding_stretched = VisualAssetMatcher.evaluate_image(
        image=stretched_image,
        image_index=1,
        source_format="PNG",
        approved_catalog=approved_catalog,
    )
    assert finding_stretched.match_status == AssetMatchStatus.STRETCHED_OR_DISTORTED
    assert finding_stretched.is_compliant is False
    assert finding_stretched.aspect_ratio_distortion_percent > 8.0
    assert "Distorted brand logo" in finding_stretched.explanation

    # Test Case 3: Outdated / Deprecated Logo
    heritage_image = Image.new("RGB", (150, 100), color=(180, 83, 9))
    with patch.object(VisualAssetMatcher, "compute_dhash", return_value="aaaaaaaaaaaaaaaa"):
        finding_outdated = VisualAssetMatcher.evaluate_image(
            image=heritage_image,
            image_index=2,
            source_format="PNG",
            approved_catalog=approved_catalog,
        )
        assert finding_outdated.match_status == AssetMatchStatus.OUTDATED_LOGO
        assert finding_outdated.is_compliant is False
        assert "Outdated brand logo" in finding_outdated.explanation

    # Test Case 4: Unapproved / Unknown Visual Asset
    random_image = Image.new("RGB", (100, 100), color=(0, 0, 0))
    for x in range(0, 100, 10):
        for y in range(100):
            for dx in range(5):
                random_image.putpixel((x + dx, y), (255, 255, 255))

    finding_unknown = VisualAssetMatcher.evaluate_image(
        image=random_image,
        image_index=3,
        source_format="PNG",
        approved_catalog=approved_catalog,
    )
    assert finding_unknown.match_status == AssetMatchStatus.UNAPPROVED_ASSET
    assert finding_unknown.is_compliant is False
    assert "Unapproved visual asset" in finding_unknown.explanation
