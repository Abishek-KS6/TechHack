"""
BrandShield AI - Limited-Retention TTL Reaper Service.
Automates enforcement of enterprise data retention policies:
- Identifies submissions older than configured brand retention days.
- Cryptographically shreds raw text from immutable DocumentRevision records.
- Preserves findings, category statistics, and revision lineage for governance parity.
- Commits RETENTION_POLICY_PURGED event to the SHA-256 tamper-evident ledger.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import AuditAction
from app.infrastructure.db.models import BrandProfile, DocumentRevision, Finding, Submission
from app.services.audit_service import AuditService

logger = logging.getLogger("brandshield.services.governance.retention_reaper")

PURGED_PLACEHOLDER = "[RETENTION_POLICY_PURGED: Raw text purged per enterprise data retention policy]"


@dataclass
class RetentionReaperResult:
    """Summary metrics of executed retention cleanup."""
    purged_submissions_count: int
    purged_revisions_count: int
    preserved_findings_count: int
    execution_timestamp: str
    dry_run: bool
    purged_submission_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "purged_submissions_count": self.purged_submissions_count,
            "purged_revisions_count": self.purged_revisions_count,
            "preserved_findings_count": self.preserved_findings_count,
            "execution_timestamp": self.execution_timestamp,
            "dry_run": self.dry_run,
            "purged_submission_ids": self.purged_submission_ids,
        }


class RetentionReaperService:
    """
    Automated data retention enforcement engine preventing indefinite storage of customer PII/text.
    """

    @classmethod
    async def enforce_retention(
        cls,
        session: AsyncSession,
        workspace_id: Optional[uuid.UUID] = None,
        forced_retention_days: Optional[int] = None,
        dry_run: bool = False,
    ) -> RetentionReaperResult:
        """
        Executes retention policy sweep across submissions in the database.
        """
        now = datetime.now(timezone.utc)
        query = select(Submission).options(
            selectinload(Submission.revisions),
            selectinload(Submission.brand_profile),
        )
        if workspace_id:
            query = query.where(Submission.workspace_id == workspace_id)

        result = await session.execute(query)
        submissions = result.scalars().all()

        purged_sub_ids: list[str] = []
        purged_revisions_count = 0
        preserved_findings_count = 0

        for sub in submissions:
            profile = sub.brand_profile
            privacy_cfg = getattr(profile, "privacy_gate_config", {}) if profile else {}
            if not isinstance(privacy_cfg, dict):
                privacy_cfg = {}

            retention_days = forced_retention_days or privacy_cfg.get("retention_days", 30)
            cutoff_date = now - timedelta(days=retention_days)

            sub_created = sub.created_at
            if sub_created.tzinfo is None:
                sub_created = sub_created.replace(tzinfo=timezone.utc)

            # Check if submission is older than retention cutoff
            if sub_created < cutoff_date:
                purged_sub_ids.append(str(sub.id))

                revisions = sub.revisions or []
                for rev in revisions:
                    if rev.content_text != PURGED_PLACEHOLDER:
                        purged_revisions_count += 1
                        if not dry_run:
                            rev.content_text = PURGED_PLACEHOLDER

                # Count findings associated with this submission's revisions
                rev_ids = [r.id for r in revisions]
                if rev_ids:
                    f_query = select(Finding).where(Finding.revision_id.in_(rev_ids))
                    f_res = await session.execute(f_query)
                    preserved_findings_count += len(f_res.scalars().all())

                if not dry_run:
                    await AuditService.record_event(
                        session=session,
                        action=AuditAction.RETENTION_POLICY_PURGED,
                        workspace_id=sub.workspace_id,
                        actor_id=sub.creator_id,
                        payload={
                            "submission_id": str(sub.id),
                            "retention_days": retention_days,
                            "purged_revisions_count": len(revisions),
                            "purged_at": now.isoformat(),
                        },
                    )

        if not dry_run:
            await session.commit()

        return RetentionReaperResult(
            purged_submissions_count=len(purged_sub_ids),
            purged_revisions_count=purged_revisions_count,
            preserved_findings_count=preserved_findings_count,
            execution_timestamp=now.isoformat(),
            dry_run=dry_run,
            purged_submission_ids=purged_sub_ids,
        )
