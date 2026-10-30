"""
BrandShield AI - Governance Reporting, Traceability & Evaluation Test Suite.
Validates:
1. Governance Reporting (GET /api/v1/governance/reports):
   Single-pass PostgreSQL CUBE aggregations matching findings with 100% precision.
2. Evidence Traceability Audit (GET /api/v1/governance/traceability-metrics):
   Calculation of evidence grounding percentage and zero ungrounded claim validation.
3. Automated Benchmark Evaluator (POST /api/v1/governance/evaluate-testset):
   15-sample ground-truth corporate benchmark, TP, FP, FN, Precision, Recall, F1, and P95 latency.
4. Idempotent Database Seeder:
   Acme FinTech Global workspace, 3 RBAC users, 20 guidelines, 15 facts (4 expired), and fallback cache.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid

from httpx import ASGITransport, AsyncClient
import pytest

from app.core.security import create_access_token, hash_password
from app.domain.enums import UserRole
from app.domain.schemas.governance import (
    EvaluationBenchmarkResponse,
    GovernanceReportResponse,
    TraceabilityMetricsResponse,
)
from app.infrastructure.db.models import (
    ApprovedFact,
    BrandGuideline,
    BrandProfile,
    User,
    Workspace,
)
from app.infrastructure.db.seed import seed_database
from app.infrastructure.db.session import get_async_session
from app.main import app
from app.services.governance.evaluator import BENCHMARK_TESTSET, GovernanceEvaluator
from app.services.governance.reporting_service import GovernanceReportService
from app.services.governance.traceability_service import TraceabilityAuditService


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
        email="author@acmefintech.com",
        hashed_password=hash_password("DemoSecure2026!"),
        full_name="Alex Creator",
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
        email="reviewer@acmefintech.com",
        hashed_password=hash_password("DemoSecure2026!"),
        full_name="Morgan Reviewer",
        role=UserRole.REVIEWER,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def admin_user(workspace_id):
    now = datetime.now(timezone.utc)
    return User(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        email="admin@acmefintech.com",
        hashed_password=hash_password("DemoSecure2026!"),
        full_name="Sam Admin",
        role=UserRole.ADMINISTRATOR,
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


@pytest.fixture
def admin_token(admin_user):
    return create_access_token(
        user_id=admin_user.id,
        email=admin_user.email,
        role=admin_user.role,
        workspace_id=admin_user.workspace_id,
    )


# ==============================================================================
# 1. Governance Reporting Unit Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_governance_reporting_service_cube_aggregation(workspace_id, brand_profile_id):
    """
    Validates GovernanceReportService parses single-pass CUBE/CTE aggregation rows
    into category counts, severity distributions, and multi-dimensional cross-cells with 100% precision.
    """
    mock_session = AsyncMock()

    # Mock CUBE result rows
    mock_rows = [
        # Grand total
        MagicMock(_mapping={"metric_type": "CUBE", "issue_category": None, "severity": None, "dimension_val": None, "count": 10}),
        # Category subtotals
        MagicMock(_mapping={"metric_type": "CUBE", "issue_category": "TONE", "severity": None, "dimension_val": None, "count": 3}),
        MagicMock(_mapping={"metric_type": "CUBE", "issue_category": "TERMINOLOGY", "severity": None, "dimension_val": None, "count": 4}),
        MagicMock(_mapping={"metric_type": "CUBE", "issue_category": "STALE_FACT", "severity": None, "dimension_val": None, "count": 2}),
        MagicMock(_mapping={"metric_type": "CUBE", "issue_category": "UNSUBSTANTIATED_CLAIM", "severity": None, "dimension_val": None, "count": 1}),
        # Severity subtotals
        MagicMock(_mapping={"metric_type": "CUBE", "issue_category": None, "severity": "HIGH", "dimension_val": None, "count": 5}),
        MagicMock(_mapping={"metric_type": "CUBE", "issue_category": None, "severity": "MEDIUM", "dimension_val": None, "count": 3}),
        MagicMock(_mapping={"metric_type": "CUBE", "issue_category": None, "severity": "LOW", "dimension_val": None, "count": 2}),
        # Multi-dimensional cells
        MagicMock(_mapping={"metric_type": "CUBE", "issue_category": "TERMINOLOGY", "severity": "HIGH", "dimension_val": None, "count": 3}),
        MagicMock(_mapping={"metric_type": "CUBE", "issue_category": "TONE", "severity": "MEDIUM", "dimension_val": None, "count": 2}),
        # Triage status
        MagicMock(_mapping={"metric_type": "TRIAGE", "issue_category": None, "severity": None, "dimension_val": "FLAGGED_HIGH_CONFIDENCE", "count": 7}),
        MagicMock(_mapping={"metric_type": "TRIAGE", "issue_category": None, "severity": None, "dimension_val": "ROUTED_TO_HUMAN_LOW_CONFIDENCE", "count": 3}),
        # Detector source
        MagicMock(_mapping={"metric_type": "DETECTOR", "issue_category": None, "severity": None, "dimension_val": "DETERMINISTIC_RULE", "count": 7}),
        MagicMock(_mapping={"metric_type": "DETECTOR", "issue_category": None, "severity": None, "dimension_val": "TEMPORAL_FACT_MATCHER", "count": 3}),
        # Creator action
        MagicMock(_mapping={"metric_type": "ACTION", "issue_category": None, "severity": None, "dimension_val": "PENDING", "count": 8}),
        MagicMock(_mapping={"metric_type": "ACTION", "issue_category": None, "severity": None, "dimension_val": "ACCEPTED", "count": 2}),
    ]

    mock_exec_result = MagicMock()
    mock_exec_result.fetchall.return_value = mock_rows
    mock_session.execute.return_value = mock_exec_result

    report: GovernanceReportResponse = await GovernanceReportService.generate_report(
        session=mock_session,
        workspace_id=workspace_id,
        brand_profile_id=brand_profile_id,
    )

    assert report.total_findings == 10
    assert report.category_counts["TONE"] == 3
    assert report.category_counts["TERMINOLOGY"] == 4
    assert report.category_counts["STALE_FACT"] == 2
    assert report.category_counts["UNSUBSTANTIATED_CLAIM"] == 1
    assert report.category_counts["UNSUPPORTED_CLAIM"] == 1  # Alias verification
    assert report.category_counts["ACCESSIBILITY"] == 0

    assert report.severity_counts["HIGH"] == 5
    assert report.severity_counts["MEDIUM"] == 3
    assert report.severity_counts["LOW"] == 2
    assert report.severity_counts["CRITICAL"] == 0

    assert report.triage_status_counts["FLAGGED_HIGH_CONFIDENCE"] == 7
    assert report.detector_source_counts["DETERMINISTIC_RULE"] == 7
    assert report.creator_action_counts["ACCEPTED"] == 2

    assert len(report.category_severity_cube) == 2
    cell = next(c for c in report.category_severity_cube if c.issue_category == "TERMINOLOGY")
    assert cell.severity == "HIGH"
    assert cell.count == 3


@pytest.mark.asyncio
async def test_governance_reporting_empty_findings(workspace_id):
    """Validates GovernanceReportService handles empty workspaces with zeroed metrics."""
    mock_session = AsyncMock()
    mock_exec_result = MagicMock()
    mock_exec_result.fetchall.return_value = []
    mock_session.execute.return_value = mock_exec_result

    report = await GovernanceReportService.generate_report(
        session=mock_session,
        workspace_id=workspace_id,
    )

    assert report.total_findings == 0
    assert report.category_counts["TONE"] == 0
    assert report.category_counts["UNSUPPORTED_CLAIM"] == 0
    assert len(report.category_severity_cube) == 0


# ==============================================================================
# 2. Evidence Traceability Unit Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_traceability_metrics_perfect_grounding(workspace_id):
    """Validates 100% evidence traceability when all findings have guideline or fact references."""
    mock_session = AsyncMock()
    mock_row = MagicMock(_mapping={
        "total_findings": 15,
        "grounded_findings_count": 15,
        "ungrounded_findings_count": 0,
        "guideline_linked_count": 10,
        "fact_linked_count": 5,
        "both_linked_count": 0,
        "unsubstantiated_claims_count": 0,
    })
    mock_exec_result = MagicMock()
    mock_exec_result.fetchone.return_value = mock_row
    mock_session.execute.return_value = mock_exec_result

    metrics: TraceabilityMetricsResponse = await TraceabilityAuditService.compute_metrics(
        session=mock_session,
        workspace_id=workspace_id,
    )

    assert metrics.total_findings == 15
    assert metrics.grounded_findings_count == 15
    assert metrics.ungrounded_findings_count == 0
    assert metrics.traceability_percentage == 100.0
    assert metrics.is_zero_ungrounded_verified is True
    assert metrics.guideline_linked_count == 10
    assert metrics.fact_linked_count == 5


@pytest.mark.asyncio
async def test_traceability_metrics_partial_grounding(workspace_id):
    """Validates exact calculation when some findings lack evidence citations."""
    mock_session = AsyncMock()
    mock_row = MagicMock(_mapping={
        "total_findings": 20,
        "grounded_findings_count": 16,
        "ungrounded_findings_count": 4,
        "guideline_linked_count": 12,
        "fact_linked_count": 4,
        "both_linked_count": 0,
        "unsubstantiated_claims_count": 4,
    })
    mock_exec_result = MagicMock()
    mock_exec_result.fetchone.return_value = mock_row
    mock_session.execute.return_value = mock_exec_result

    metrics = await TraceabilityAuditService.compute_metrics(
        session=mock_session,
        workspace_id=workspace_id,
    )

    assert metrics.total_findings == 20
    assert metrics.grounded_findings_count == 16
    assert metrics.ungrounded_findings_count == 4
    assert metrics.traceability_percentage == 80.0
    assert metrics.is_zero_ungrounded_verified is False


# ==============================================================================
# 3. Labelled Test Set Evaluator Benchmark Tests
# ==============================================================================

def test_benchmark_testset_dataset_composition():
    """Confirms the labelled evaluation test set contains exactly 15 samples covering all required domains."""
    assert len(BENCHMARK_TESTSET) == 15

    categories_present = set()
    for s in BENCHMARK_TESTSET:
        categories_present.update(s.ground_truth_categories)

    # Required categories present in testset
    assert "STALE_FACT" in categories_present
    assert "TERMINOLOGY" in categories_present
    assert "TONE" in categories_present
    assert "ACCESSIBILITY" in categories_present

    # Clean baselines present
    clean_baselines = [s for s in BENCHMARK_TESTSET if len(s.ground_truth_categories) == 0]
    assert len(clean_baselines) == 3


@pytest.mark.asyncio
async def test_governance_evaluator_benchmark_execution(workspace_id):
    """
    Executes the analysis pipeline across all 15 ground-truth samples and validates
    True Positives, False Positives, False Negatives, Precision, Recall, F1, and P95 latency.
    """
    mock_session = AsyncMock()

    # Preloaded brand profile and facts
    profile = GovernanceEvaluator.create_default_benchmark_profile(workspace_id)
    facts = GovernanceEvaluator.create_default_benchmark_facts(workspace_id)

    async def mock_get(model, ident):
        if model == BrandProfile:
            return profile
        return None

    mock_session.get.side_effect = mock_get

    def mock_eval_execute(statement, *args, **kwargs):
        stmt_str = str(statement).lower()
        mock_r = MagicMock()
        mock_s = MagicMock()
        if "from brand_profiles" in stmt_str:
            mock_s.first.return_value = profile
            mock_s.all.return_value = [profile]
        elif "from brand_guidelines" in stmt_str:
            mock_s.all.return_value = []
        elif "from approved_facts" in stmt_str:
            mock_s.all.return_value = facts
        else:
            mock_s.first.return_value = None
            mock_s.all.return_value = []
        mock_r.scalars.return_value = mock_s
        return mock_r

    mock_session.execute.side_effect = mock_eval_execute

    benchmark: EvaluationBenchmarkResponse = await GovernanceEvaluator.run_benchmark(
        session=mock_session,
        workspace_id=workspace_id,
        brand_profile_id=profile.id,
    )

    assert benchmark.total_samples == 15
    assert len(benchmark.samples) == 15

    # True positives must be detected across the corporate samples
    assert benchmark.true_positives >= 10
    assert benchmark.precision > 0.60
    assert benchmark.recall > 0.60
    assert benchmark.f1_score > 0.60

    # Latency verification
    assert benchmark.p95_latency_ms >= 0.0
    assert benchmark.avg_latency_ms >= 0.0

    # Clean baseline samples (BENCH-13, 14, 15) must pass without false positive flags
    baseline_samples = [s for s in benchmark.samples if s.sample_id in {"BENCH-13", "BENCH-14", "BENCH-15"}]
    for b in baseline_samples:
        assert b.false_positives == 0
        assert b.status == "CLEAN_PASS"


# ==============================================================================
# 4. Database Seeder Idempotency Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_seed_database_idempotent():
    """
    Validates that the database seeder populates the Acme FinTech Global workspace,
    3 RBAC users, 20 guidelines, 15 facts (including 4 expired), and pre-warms the fallback cache.
    Running repeatedly must not raise unique constraint errors.
    """
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()

    # First run (clean DB)
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = None  # Entities do not exist yet
    mock_res = MagicMock()
    mock_res.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_res

    res1 = await seed_database(mock_session)

    assert res1["status"] == "SUCCESS"
    assert res1["workspace"]["slug"] == "acme-fintech"
    assert len(res1["users"]) == 3
    assert res1["guidelines_count"] == 20
    assert res1["newly_seeded_guidelines"] == 20
    assert res1["facts_count"] == 15
    assert res1["newly_seeded_facts"] == 15
    assert res1["expired_facts_count"] == 4
    assert res1["prewarmed_cache_entries"] >= 3

    # Second run (all entities already exist)
    ws_id = uuid.uuid4()
    existing_ws = Workspace(id=ws_id, name="Acme FinTech Global", slug="acme-fintech")
    existing_users = {
        UserRole.CREATOR: User(id=uuid.uuid4(), workspace_id=ws_id, email="creator@acmefintech.com", role=UserRole.CREATOR, full_name="Alex Creator", hashed_password="h"),
        UserRole.REVIEWER: User(id=uuid.uuid4(), workspace_id=ws_id, email="reviewer@acmefintech.com", role=UserRole.REVIEWER, full_name="Morgan Reviewer", hashed_password="h"),
        UserRole.ADMINISTRATOR: User(id=uuid.uuid4(), workspace_id=ws_id, email="admin@acmefintech.com", role=UserRole.ADMINISTRATOR, full_name="Sam Admin", hashed_password="h"),
    }
    existing_bp = BrandProfile(id=uuid.uuid4(), workspace_id=ws_id, name="Acme FinTech Global Profile")
    existing_g = BrandGuideline(id=uuid.uuid4(), brand_profile_id=existing_bp.id, clause_identifier="ACME-TONE-01", clause_text="Text")
    existing_f = ApprovedFact(id=uuid.uuid4(), workspace_id=ws_id, fact_statement="Fact stmt", expiry_date=datetime.now(timezone.utc))

    def mock_seed_execute_run2(statement, *args, **kwargs):
        stmt_str = str(statement).lower()
        mock_r = MagicMock()
        mock_s = MagicMock()
        if "from workspaces" in stmt_str:
            mock_s.first.return_value = existing_ws
        elif "from users" in stmt_str:
            if "creator" in stmt_str:
                mock_s.first.return_value = existing_users[UserRole.CREATOR]
            elif "admin" in stmt_str:
                mock_s.first.return_value = existing_users[UserRole.ADMINISTRATOR]
            else:
                mock_s.first.return_value = existing_users[UserRole.REVIEWER]
        elif "from brand_profiles" in stmt_str:
            mock_s.first.return_value = existing_bp
        elif "from brand_guidelines" in stmt_str:
            mock_s.first.return_value = existing_g
        elif "from approved_facts" in stmt_str:
            mock_s.first.return_value = existing_f
        else:
            mock_s.first.return_value = None
        mock_r.scalars.return_value = mock_s
        return mock_r

    mock_session.execute.side_effect = mock_seed_execute_run2

    res2 = await seed_database(mock_session)
    assert res2["status"] == "SUCCESS"
    # Idempotence: No new entities inserted
    assert res2["newly_seeded_guidelines"] == 0
    assert res2["newly_seeded_facts"] == 0


# ==============================================================================
# 5. FastAPI Endpoints HTTP Integration Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_api_governance_report_reviewer_success(reviewer_user, reviewer_token):
    """Validates HTTP GET /api/v1/governance/reports for authenticated Reviewer."""
    mock_session = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return reviewer_user
        return None

    mock_session.get.side_effect = mock_get

    mock_rows = [
        MagicMock(_mapping={"metric_type": "CUBE", "issue_category": None, "severity": None, "dimension_val": None, "count": 5}),
        MagicMock(_mapping={"metric_type": "CUBE", "issue_category": "TERMINOLOGY", "severity": None, "dimension_val": None, "count": 5}),
        MagicMock(_mapping={"metric_type": "CUBE", "issue_category": None, "severity": "HIGH", "dimension_val": None, "count": 5}),
    ]
    mock_exec_res = MagicMock()
    mock_exec_res.fetchall.return_value = mock_rows
    mock_session.execute.return_value = mock_exec_res

    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get(
                "/api/v1/governance/reports",
                headers={"Authorization": f"Bearer {reviewer_token}"},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["total_findings"] == 5
            assert data["category_counts"]["TERMINOLOGY"] == 5
            assert data["severity_counts"]["HIGH"] == 5
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_governance_report_creator_forbidden(creator_user, creator_token):
    """Guarantees Creators are forbidden from accessing executive governance reports."""
    mock_session = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return creator_user
        return None

    mock_session.get.side_effect = mock_get
    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get(
                "/api/v1/governance/reports",
                headers={"Authorization": f"Bearer {creator_token}"},
            )

            assert resp.status_code == 403
            assert resp.json()["title"] == "Forbidden Access"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_governance_traceability_metrics_success(admin_user, admin_token):
    """Validates HTTP GET /api/v1/governance/traceability-metrics."""
    mock_session = AsyncMock()

    async def mock_get(model, ident):
        if model == User:
            return admin_user
        return None

    mock_session.get.side_effect = mock_get

    mock_row = MagicMock(_mapping={
        "total_findings": 10,
        "grounded_findings_count": 10,
        "ungrounded_findings_count": 0,
        "guideline_linked_count": 8,
        "fact_linked_count": 2,
        "both_linked_count": 0,
        "unsubstantiated_claims_count": 0,
    })
    mock_exec_res = MagicMock()
    mock_exec_res.fetchone.return_value = mock_row
    mock_session.execute.return_value = mock_exec_res

    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get(
                "/api/v1/governance/traceability-metrics",
                headers={"Authorization": f"Bearer {admin_token}"},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["total_findings"] == 10
            assert data["traceability_percentage"] == 100.0
            assert data["is_zero_ungrounded_verified"] is True
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_governance_evaluate_testset_success(reviewer_user, reviewer_token):
    """Validates HTTP POST /api/v1/governance/evaluate-testset."""
    mock_session = AsyncMock()

    profile = GovernanceEvaluator.create_default_benchmark_profile(reviewer_user.workspace_id)
    facts = GovernanceEvaluator.create_default_benchmark_facts(reviewer_user.workspace_id)

    async def mock_get(model, ident):
        if model == User:
            return reviewer_user
        if model == BrandProfile:
            return profile
        return None

    mock_session.get.side_effect = mock_get

    def mock_eval_api_execute(statement, *args, **kwargs):
        stmt_str = str(statement).lower()
        mock_r = MagicMock()
        mock_s = MagicMock()
        if "from brand_profiles" in stmt_str:
            mock_s.first.return_value = profile
            mock_s.all.return_value = [profile]
        elif "from brand_guidelines" in stmt_str:
            mock_s.all.return_value = []
        elif "from approved_facts" in stmt_str:
            mock_s.all.return_value = facts
        else:
            mock_s.first.return_value = None
            mock_s.all.return_value = []
        mock_r.scalars.return_value = mock_s
        return mock_r

    mock_session.execute.side_effect = mock_eval_api_execute

    app.dependency_overrides[get_async_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/api/v1/governance/evaluate-testset",
                headers={"Authorization": f"Bearer {reviewer_token}"},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["total_samples"] == 15
            assert "precision" in data
            assert "recall" in data
            assert "f1_score" in data
            assert "p95_latency_ms" in data
            assert len(data["samples"]) == 15
    finally:
        app.dependency_overrides.clear()
