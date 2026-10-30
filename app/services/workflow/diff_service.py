"""
BrandShield AI - Revision Lineage & Side-by-Side Token Diff Engine.
Calculates unified diff patches and fine-grained token-level side-by-side diffs across the revision DAG.
"""

import difflib
import re
from typing import Any, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundProblem, ValidationErrorProblem
from app.domain.schemas.submission import DocumentRevisionRead, RevisionDiffResponse, TokenDiffChunk
from app.infrastructure.db.models import DocumentRevision, Submission


class DiffService:
    """
    Service responsible for computing unified line diffs, token-level side-by-side
    comparisons, and assembling complete revision lineage DAGs.
    """

    @staticmethod
    def tokenize_with_spans(text: str) -> list[tuple[str, int, int]]:
        """
        Tokenizes text into words, whitespace, and punctuation while tracking exact character offsets.
        Returns list of (token_str, start_char, end_char).
        """
        token_pattern = re.compile(r"\w+|\s+|[^\w\s]", re.UNICODE)
        tokens: list[tuple[str, int, int]] = []
        for match in token_pattern.finditer(text):
            tokens.append((match.group(0), match.start(), match.end()))
        return tokens

    @classmethod
    def compute_token_diff(cls, old_text: str, new_text: str) -> list[TokenDiffChunk]:
        """
        Computes granular side-by-side token-level diff chunks using SequenceMatcher opcodes.
        Produces equal, replace, insert, and delete operations mapped to exact character offsets.
        """
        old_token_tuples = cls.tokenize_with_spans(old_text)
        new_token_tuples = cls.tokenize_with_spans(new_text)

        old_words = [t[0] for t in old_token_tuples]
        new_words = [t[0] for t in new_token_tuples]

        matcher = difflib.SequenceMatcher(None, old_words, new_words)
        chunks: list[TokenDiffChunk] = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            old_slice = "".join(old_words[i1:i2])
            new_slice = "".join(new_words[j1:j2])

            old_start = old_token_tuples[i1][1] if i1 < len(old_token_tuples) else len(old_text)
            old_end = old_token_tuples[i2 - 1][2] if (i2 > 0 and i2 - 1 < len(old_token_tuples)) else old_start

            new_start = new_token_tuples[j1][1] if j1 < len(new_token_tuples) else len(new_text)
            new_end = new_token_tuples[j2 - 1][2] if (j2 > 0 and j2 - 1 < len(new_token_tuples)) else new_start

            chunks.append(
                TokenDiffChunk(
                    op=tag,
                    old_text=old_slice,
                    new_text=new_slice,
                    old_start=old_start,
                    old_end=old_end,
                    new_start=new_start,
                    new_end=new_end,
                )
            )

        return chunks

    @staticmethod
    def compute_line_diff(old_text: str, new_text: str) -> dict[str, Any]:
        """
        Computes standard unified line diff summary between two revision snapshots.
        """
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        diff = list(difflib.unified_diff(old_lines, new_lines, fromfile="base_revision", tofile="target_revision"))
        lines_added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
        lines_removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))

        return {
            "diff_lines": diff,
            "lines_added": lines_added,
            "lines_removed": lines_removed,
        }

    @classmethod
    async def get_revision_diff(
        cls,
        session: AsyncSession,
        submission_id: uuid.UUID,
        from_revision: int = 1,
        to_revision: Optional[int] = None,
    ) -> RevisionDiffResponse:
        """
        Retrieves submission revision lineage and computes exact side-by-side token and unified diffs.
        """
        # 1. Verify submission
        submission = await session.get(Submission, submission_id)
        if not submission:
            raise NotFoundProblem(
                detail=f"Submission '{submission_id}' not found.",
                resource_type="Submission",
                resource_id=str(submission_id),
            )

        # 2. Query full revision lineage ordered by revision number
        query = (
            select(DocumentRevision)
            .where(DocumentRevision.submission_id == submission_id)
            .order_by(DocumentRevision.revision_number.asc())
        )
        result = await session.execute(query)
        revisions = list(result.scalars().all())

        if not revisions:
            raise NotFoundProblem(
                detail=f"Submission '{submission_id}' contains no committed revisions.",
                resource_type="DocumentRevision",
                resource_id=str(submission_id),
            )

        # 3. Resolve target revision boundary
        max_rev = revisions[-1].revision_number
        target_rev_num = to_revision if to_revision is not None else max_rev

        if from_revision < 1 or from_revision > max_rev:
            raise ValidationErrorProblem(
                detail=f"from_revision {from_revision} is invalid. Available range: 1 to {max_rev}."
            )
        if target_rev_num < from_revision or target_rev_num > max_rev:
            raise ValidationErrorProblem(
                detail=f"to_revision {target_rev_num} is invalid. Available range: {from_revision} to {max_rev}."
            )

        rev_map = {r.revision_number: r for r in revisions}
        base_node = rev_map[from_revision]
        target_node = rev_map[target_rev_num]

        # 4. Compute line and token diffs
        line_diff_summary = cls.compute_line_diff(base_node.content_text, target_node.content_text)
        token_diff_chunks = cls.compute_token_diff(base_node.content_text, target_node.content_text)

        lineage_reads = [DocumentRevisionRead.model_validate(r) for r in revisions]

        return RevisionDiffResponse(
            submission_id=submission_id,
            from_revision=from_revision,
            to_revision=target_rev_num,
            from_revision_id=base_node.id,
            to_revision_id=target_node.id,
            lineage=lineage_reads,
            unified_diff=line_diff_summary["diff_lines"],
            token_diff=token_diff_chunks,
            lines_added=line_diff_summary["lines_added"],
            lines_removed=line_diff_summary["lines_removed"],
        )
