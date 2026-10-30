"""
BrandShield AI - Stage 1 Deterministic Rule Engine.
Implements O(N) multi-pattern Aho-Corasick automaton for brand terminology matrices,
trademark symbols, and algorithmic readability/accessibility metrics (Flesch-Kincaid,
passive voice, sentence length, and capitalization abuse).
"""

from collections import deque
from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Optional
import uuid

from app.domain.enums import DetectorSource, FindingCategory, SeverityLevel, TriageStatus
from app.infrastructure.db.models import BrandGuideline, BrandProfile

# Standard acronym whitelist for ALL-CAPS detector
ACRONYM_WHITELIST = {
    "FDA", "FTC", "SEC", "CEO", "CFO", "CTO", "CIO", "SLA", "API", "DAG",
    "REST", "HTTP", "HTTPS", "JSON", "XML", "HTML", "YAML", "B2B", "B2C",
    "ROI", "KPI", "GDPR", "HIPAA", "SOC2", "AWS", "GCP", "AI", "ML", "LLM",
    "RAG", "SQL", "NFC", "USA", "UK", "EU", "CAGR", "EBITDA", "ARR", "MRR",
    "SDK", "MIME", "SHA", "JWT", "RBAC", "OWASP", "VBA", "PDF", "DOCX",
}

# Passive voice regex pattern (supports optional adverbs like 'were painstakingly implemented')
PASSIVE_VOICE_REGEX = re.compile(
    r"\b(am|is|are|was|were|be|been|being)\s+(?:[a-zA-Z]+ly\s+)?([a-zA-Z]+(?:ed|en|t))\b",
    re.IGNORECASE,
)

# Irregular past participles commonly used in passive voice
IRREGULAR_PAST_PARTICIPLES = {
    "written", "chosen", "broken", "taken", "given", "seen", "done", "made",
    "built", "found", "lost", "sent", "kept", "held", "led", "left", "paid",
}


@dataclass
class PatternPayload:
    """Associated metadata for an Aho-Corasick dictionary entry."""
    term: str
    suggested_correction: Optional[str]
    reason: str
    category: FindingCategory
    severity: SeverityLevel
    match_type: str  # "BANNED", "PREFERRED", "TRADEMARK"
    guideline_clause: Optional[str] = None


class AhoCorasickNode:
    """Trie node for the Aho-Corasick automaton with failure and output links."""
    def __init__(self) -> None:
        self.children: dict[str, AhoCorasickNode] = {}
        self.fail: Optional[AhoCorasickNode] = None
        self.outputs: list[PatternPayload] = []


class AhoCorasickAutomaton:
    """
    O(N + M) Multi-Pattern String Matching Automaton.
    Constructs deterministic state transitions and failure links for dictionary scanning.
    """
    def __init__(self, case_sensitive: bool = False) -> None:
        self.root = AhoCorasickNode()
        self.case_sensitive = case_sensitive
        self._built = False

    def add_pattern(self, pattern: str, payload: PatternPayload) -> None:
        """Inserts a pattern into the Trie."""
        curr = self.root
        key = pattern if self.case_sensitive else pattern.lower()
        for char in key:
            if char not in curr.children:
                curr.children[char] = AhoCorasickNode()
            curr = curr.children[char]
        curr.outputs.append(payload)
        self._built = False

    def build(self) -> None:
        """Constructs failure transitions via Breadth-First Search (BFS)."""
        queue: deque[AhoCorasickNode] = deque()
        # Level 1 nodes fail back to root
        for child in self.root.children.values():
            child.fail = self.root
            queue.append(child)

        while queue:
            curr = queue.popleft()
            for char, next_node in curr.children.items():
                queue.append(next_node)
                # Trace failure link
                f = curr.fail
                while f is not None and char not in f.children:
                    f = f.fail
                next_node.fail = f.children[char] if f and char in f.children else self.root
                # Aggregate output matches from failure link
                if next_node.fail:
                    next_node.outputs.extend(next_node.fail.outputs)

        self._built = True

    def search(self, text: str) -> list[tuple[int, int, PatternPayload]]:
        """
        Scans text in O(len(text)) time and returns all matched (start_offset, end_offset, payload).
        Verifies whole-word boundaries to avoid false positives inside subwords.
        """
        if not self._built:
            self.build()

        matches: list[tuple[int, int, PatternPayload]] = []
        curr = self.root
        query_text = text if self.case_sensitive else text.lower()

        for idx, char in enumerate(query_text):
            while curr is not None and char not in curr.children:
                curr = curr.fail
            curr = curr.children[char] if curr and char in curr.children else self.root

            if curr.outputs:
                for payload in curr.outputs:
                    start_pos = idx - len(payload.term) + 1
                    end_pos = idx + 1

                    # Word boundary verification
                    is_start_boundary = (start_pos == 0) or not text[start_pos - 1].isalnum()
                    is_end_boundary = (end_pos == len(text)) or not text[end_pos].isalnum()

                    if is_start_boundary and is_end_boundary:
                        matches.append((start_pos, end_pos, payload))

        return matches


@dataclass
class CachedBrandAutomatonBundle:
    """Compiled in-memory automaton and guideline indices for a specific profile version."""
    ci_automaton: AhoCorasickAutomaton
    cs_automaton: AhoCorasickAutomaton
    guidelines_by_clause: dict[str, uuid.UUID]
    guidelines: list[BrandGuideline]
    profile_version_hash: str

    def resolve_guideline(self, clause: str, category: FindingCategory) -> Optional[uuid.UUID]:
        if clause in self.guidelines_by_clause:
            return self.guidelines_by_clause[clause]
        if self.guidelines:
            for g in self.guidelines:
                if hasattr(g, "category"):
                    cat_val = g.category.value if hasattr(g.category, "value") else str(g.category)
                    if cat_val == category.value:
                        return g.id
            if hasattr(self.guidelines[0], "id"):
                return self.guidelines[0].id
        return None


class BrandAutomatonCache:
    """
    L1 In-Memory Versioned Cache for Compiled Brand Automatons.
    Maintains pre-compiled Aho-Corasick state machines and Regex ASTs
    keyed by (brand_profile_id, updated_at_hash).
    Enables sub-millisecond document scanning by avoiding re-compilation on every request.
    """
    _cache: dict[tuple[Any, str], CachedBrandAutomatonBundle] = {}
    _hits: int = 0
    _misses: int = 0

    @classmethod
    def get_version_hash(cls, profile: BrandProfile, guidelines: Optional[list[BrandGuideline]] = None) -> str:
        h = hashlib.sha256()
        h.update(str(getattr(profile, "updated_at", "")).encode())
        h.update(str(getattr(profile, "banned_terminology_map", {})).encode())
        h.update(str(getattr(profile, "preferred_terminology_map", {})).encode())
        h.update(str(getattr(profile, "messaging_rules", {})).encode())
        if guidelines:
            for g in sorted(guidelines, key=lambda x: str(getattr(x, "id", ""))):
                h.update(f"{getattr(g, 'id', '')}:{getattr(g, 'updated_at', '')}".encode())
        return h.hexdigest()[:16]

    @classmethod
    def get_or_compile(
        cls,
        profile: BrandProfile,
        guidelines: Optional[list[BrandGuideline]] = None,
    ) -> CachedBrandAutomatonBundle:
        prof_id = getattr(profile, "id", None) or "default_profile"
        v_hash = cls.get_version_hash(profile, guidelines)
        cache_key = (prof_id, v_hash)

        if cache_key in cls._cache:
            cls._hits += 1
            return cls._cache[cache_key]

        cls._misses += 1
        bundle = cls._compile_bundle(profile, guidelines, v_hash)
        cls._cache[cache_key] = bundle
        return bundle

    @classmethod
    def _compile_bundle(
        cls,
        brand_profile: BrandProfile,
        guidelines: Optional[list[BrandGuideline]],
        v_hash: str,
    ) -> CachedBrandAutomatonBundle:
        # Case-Insensitive Automaton (Banned & Preferred terms)
        ci_automaton = AhoCorasickAutomaton(case_sensitive=False)
        banned_map = brand_profile.banned_terminology_map if isinstance(getattr(brand_profile, "banned_terminology_map", None), dict) else {}
        for term, details in banned_map.items():
            if isinstance(details, dict):
                reason = details.get("reason", f"Term '{term}' is prohibited by brand guidelines.")
                sev_str = details.get("violation_severity", details.get("severity", "HIGH"))
                severity = SeverityLevel(sev_str) if sev_str in SeverityLevel._value2member_map_ else SeverityLevel.HIGH
                replacements = details.get("suggested_replacements", [])
                suggested = ", ".join(replacements) if isinstance(replacements, list) and replacements else details.get("suggested_correction")
            else:
                reason = f"Prohibited term: '{term}'."
                severity = SeverityLevel.HIGH
                suggested = str(details) if details else None

            ci_automaton.add_pattern(
                pattern=term,
                payload=PatternPayload(
                    term=term,
                    suggested_correction=suggested,
                    reason=reason,
                    category=FindingCategory.TERMINOLOGY,
                    severity=severity,
                    match_type="BANNED",
                ),
            )

        pref_map = brand_profile.preferred_terminology_map if isinstance(getattr(brand_profile, "preferred_terminology_map", None), dict) else {}
        for deprecated, approved in pref_map.items():
            if isinstance(approved, dict):
                clean_term = (
                    approved.get("approved_term")
                    or approved.get("suggested_correction")
                    or approved.get("term")
                    or approved.get("preferred")
                )
                suggested = str(clean_term) if clean_term is not None else None
                reason = approved.get("reason") or f"Deprecated term '{deprecated}'. Corporate standard is '{suggested or deprecated}'."
                sev_str = approved.get("violation_severity", approved.get("severity", "MEDIUM"))
                severity = SeverityLevel(sev_str) if sev_str in SeverityLevel._value2member_map_ else SeverityLevel.MEDIUM
            elif isinstance(approved, list) and approved:
                suggested = ", ".join(str(x) for x in approved)
                reason = f"Deprecated term '{deprecated}'. Corporate standard is '{suggested}'."
                severity = SeverityLevel.MEDIUM
            elif approved is not None:
                suggested = str(approved)
                reason = f"Deprecated term '{deprecated}'. Corporate standard is '{suggested}'."
                severity = SeverityLevel.MEDIUM
            else:
                suggested = None
                reason = f"Deprecated term: '{deprecated}'."
                severity = SeverityLevel.MEDIUM

            ci_automaton.add_pattern(
                pattern=deprecated,
                payload=PatternPayload(
                    term=deprecated,
                    suggested_correction=suggested,
                    reason=reason,
                    category=FindingCategory.TERMINOLOGY,
                    severity=severity,
                    match_type="PREFERRED",
                ),
            )
        ci_automaton.build()

        # Case-Sensitive Automaton (Trademarks)
        cs_automaton = AhoCorasickAutomaton(case_sensitive=True)
        raw_msg_rules = getattr(brand_profile, "messaging_rules", None)
        messaging_rules = raw_msg_rules if isinstance(raw_msg_rules, dict) else {}
        raw_trademarks = messaging_rules.get("required_trademarks", {})
        trademarks = raw_trademarks if isinstance(raw_trademarks, dict) else {}

        for product_name, required_symbol_form in trademarks.items():
            cs_automaton.add_pattern(
                pattern=product_name,
                payload=PatternPayload(
                    term=product_name,
                    suggested_correction=required_symbol_form,
                    reason=f"Trademark compliance requires legal symbol for '{product_name}'. Use '{required_symbol_form}'.",
                    category=FindingCategory.TERMINOLOGY,
                    severity=SeverityLevel.HIGH,
                    match_type="TRADEMARK",
                ),
            )
        cs_automaton.build()

        g_list = list(guidelines) if guidelines else []
        g_by_clause = {g.clause_identifier: g.id for g in g_list if hasattr(g, "clause_identifier")}

        return CachedBrandAutomatonBundle(
            ci_automaton=ci_automaton,
            cs_automaton=cs_automaton,
            guidelines_by_clause=g_by_clause,
            guidelines=g_list,
            profile_version_hash=v_hash,
        )

    @classmethod
    def get_metrics(cls) -> dict[str, Any]:
        """Telemetry metrics for the L1 in-memory automaton cache."""
        total = cls._hits + cls._misses
        ratio = round((cls._hits / total * 100), 2) if total > 0 else 0.0
        return {
            "hits": cls._hits,
            "misses": cls._misses,
            "hit_ratio_pct": ratio,
            "cached_profiles_count": len(cls._cache),
            "memory_footprint_approx_bytes": len(cls._cache) * 4096,
        }

    @classmethod
    def clear(cls) -> None:
        """Flushes cache."""
        cls._cache.clear()
        cls._hits = 0
        cls._misses = 0


@dataclass
class DeterministicFinding:
    """Standardized finding structure generated by deterministic checks."""
    issue_category: FindingCategory
    severity: SeverityLevel
    confidence_score: float = 1.0
    triage_status: TriageStatus = TriageStatus.FLAGGED_HIGH_CONFIDENCE
    start_offset: int = 0
    end_offset: int = 0
    explanation_reason: str = ""
    suggested_correction: Optional[str] = None
    detector_source: DetectorSource = DetectorSource.DETERMINISTIC_RULE
    linked_guideline_id: Optional[uuid.UUID] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class DeterministicRuleEngine:
    """
    Stage 1 Engine:
    Executes O(N) multi-pattern dictionary checks and algorithmic accessibility rules.
    Provides deterministic, evidence-linked compliance enforcement.
    """

    @classmethod
    def analyze_document(
        cls,
        content_text: str,
        brand_profile: BrandProfile,
        guidelines: Optional[list[BrandGuideline]] = None,
    ) -> list[DeterministicFinding]:
        """
        Executes all deterministic rules against document content:
        1. Banned terminology matrix via Aho-Corasick.
        2. Preferred vocabulary replacements via Aho-Corasick.
        3. Required trademark symbols via Case-Sensitive Aho-Corasick.
        4. Flesch-Kincaid readability & passive voice analysis.
        5. Sentence length ceilings & ALL-CAPS abuse.
        """
        findings: list[DeterministicFinding] = []

        # Acquire pre-compiled L1 cached bundle (< 0.05ms on cache hit)
        bundle = BrandAutomatonCache.get_or_compile(brand_profile, guidelines)

        # 1. Scan Case-Insensitive Automaton (Banned & Preferred terms)
        ci_matches = bundle.ci_automaton.search(content_text)
        for start_pos, end_pos, payload in ci_matches:
            matched_slice = content_text[start_pos:end_pos]
            suggested = payload.suggested_correction or f"Remove or replace prohibited term '{matched_slice}'."
            findings.append(
                DeterministicFinding(
                    issue_category=payload.category,
                    severity=payload.severity,
                    confidence_score=1.0,
                    triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
                    start_offset=start_pos,
                    end_offset=end_pos,
                    explanation_reason=f"{payload.reason} (Detected: '{matched_slice}')",
                    suggested_correction=suggested,
                    detector_source=DetectorSource.DETERMINISTIC_RULE,
                    linked_guideline_id=bundle.resolve_guideline("TERM-01", payload.category),
                )
            )

        # 2. Trademark & Case-Sensitive Automaton
        cs_matches = bundle.cs_automaton.search(content_text)
        for start_pos, end_pos, payload in cs_matches:
            matched_slice = content_text[start_pos:end_pos]
            if payload.suggested_correction and matched_slice != payload.suggested_correction:
                # Check if symbol already follows immediately
                following_slice = content_text[end_pos : end_pos + 3]
                if not any(sym in following_slice for sym in ("™", "®", "©")):
                    findings.append(
                        DeterministicFinding(
                            issue_category=payload.category,
                            severity=payload.severity,
                            confidence_score=1.0,
                            triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
                            start_offset=start_pos,
                            end_offset=end_pos,
                            explanation_reason=payload.reason,
                            suggested_correction=payload.suggested_correction,
                            detector_source=DetectorSource.DETERMINISTIC_RULE,
                            linked_guideline_id=bundle.resolve_guideline("LEGAL-TRADEMARK-01", payload.category),
                        )
                    )

        # 3. Readability, Sentence Length & Passive Voice Checks
        findings.extend(
            cls._evaluate_readability_and_style(
                content_text, brand_profile, bundle.guidelines_by_clause, bundle.guidelines
            )
        )

        return findings

    @classmethod
    def _evaluate_readability_and_style(
        cls,
        content_text: str,
        brand_profile: BrandProfile,
        guidelines_by_clause: dict[str, uuid.UUID],
        guidelines: Optional[list[BrandGuideline]] = None,
    ) -> list[DeterministicFinding]:
        """
        Executes readability, passive voice, sentence length, and ALL-CAPS analysis.
        """
        findings: list[DeterministicFinding] = []

        def _resolve(clause: str, category: FindingCategory) -> Optional[uuid.UUID]:
            if clause in guidelines_by_clause:
                return guidelines_by_clause[clause]
            if guidelines:
                for g in guidelines:
                    cat_val = g.category.value if hasattr(g.category, "value") else str(g.category)
                    if cat_val == category.value:
                        return g.id
                return guidelines[0].id
            return None
        raw_tone_params = getattr(brand_profile, "tone_parameters", None)
        tone_params = raw_tone_params if isinstance(raw_tone_params, dict) else {}
        max_sentence_words = tone_params.get("max_sentence_length", 35) if isinstance(tone_params, dict) else 35
        target_max_fkgl = tone_params.get("max_grade_level", 13.0) if isinstance(tone_params, dict) else 13.0

        # Segment sentences with exact positions
        sentence_pattern = re.compile(r"((?:[^\.\?!]|\.(?=\d))+[\.\?!]*(?:\s+|$))")
        for match in sentence_pattern.finditer(content_text):
            raw_sentence = match.group(0)
            clean_sentence = raw_sentence.strip()
            if not clean_sentence:
                continue

            rel_offset = raw_sentence.find(clean_sentence)
            s_start = match.start() + rel_offset
            s_end = s_start + len(clean_sentence)

            words = clean_sentence.split()
            word_count = len(words)

            # A. Sentence Length Threshold
            if word_count > max_sentence_words:
                findings.append(
                    DeterministicFinding(
                        issue_category=FindingCategory.ACCESSIBILITY,
                        severity=SeverityLevel.LOW,
                        confidence_score=1.0,
                        triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
                        start_offset=s_start,
                        end_offset=s_end,
                        explanation_reason=(
                            f"Sentence exceeds readability threshold ({word_count} words > {max_sentence_words} max). "
                            "Consider splitting for clarity."
                        ),
                        suggested_correction="Split into shorter, concise sentences.",
                        detector_source=DetectorSource.DETERMINISTIC_RULE,
                        linked_guideline_id=_resolve("READ-LEN-01", FindingCategory.ACCESSIBILITY),
                    )
                )

            # B. Flesch-Kincaid Grade Level per sentence (if sentence is substantial)
            if word_count >= 10:
                fkgl = cls.calculate_fkgl(clean_sentence)
                if fkgl > target_max_fkgl:
                    findings.append(
                        DeterministicFinding(
                            issue_category=FindingCategory.ACCESSIBILITY,
                            severity=SeverityLevel.MEDIUM,
                            confidence_score=1.0,
                            triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
                            start_offset=s_start,
                            end_offset=s_end,
                            explanation_reason=(
                                f"Flesch-Kincaid grade level ({fkgl:.1f}) exceeds target ceiling ({target_max_fkgl:.1f}). "
                                "Vocabulary and sentence structure are excessively complex."
                            ),
                            suggested_correction="Simplify multi-syllable jargon and shorten sentence clauses.",
                            detector_source=DetectorSource.DETERMINISTIC_RULE,
                            linked_guideline_id=_resolve("READ-FKGL-01", FindingCategory.ACCESSIBILITY),
                            metadata={"fkgl": round(fkgl, 1)},
                        )
                    )

            # C. Excessive Passive Voice Regex
            for pv_match in PASSIVE_VOICE_REGEX.finditer(clean_sentence):
                participle = pv_match.group(2).lower()
                if participle.endswith("ed") or participle in IRREGULAR_PAST_PARTICIPLES:
                    pv_start = s_start + pv_match.start()
                    pv_end = s_start + pv_match.end()
                    findings.append(
                        DeterministicFinding(
                            issue_category=FindingCategory.TONE,
                            severity=SeverityLevel.LOW,
                            confidence_score=1.0,
                            triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
                            start_offset=pv_start,
                            end_offset=pv_end,
                            explanation_reason=(
                                f"Passive voice detected ('{pv_match.group(0)}'). "
                                "Active voice reinforces corporate authority and conviction."
                            ),
                            suggested_correction=f"Rewrite '{pv_match.group(0)}' in active voice attributing direct action to subject.",
                            detector_source=DetectorSource.DETERMINISTIC_RULE,
                            linked_guideline_id=_resolve("TONE-ACTIVE-01", FindingCategory.TONE),
                        )
                    )

            # D. ALL-CAPS Abuse Check
            for word_match in re.finditer(r"\b[A-Z]{4,}\b", clean_sentence):
                cap_word = word_match.group(0)
                if cap_word not in ACRONYM_WHITELIST:
                    cap_start = s_start + word_match.start()
                    cap_end = s_start + word_match.end()
                    findings.append(
                        DeterministicFinding(
                            issue_category=FindingCategory.ACCESSIBILITY,
                            severity=SeverityLevel.LOW,
                            confidence_score=1.0,
                            triage_status=TriageStatus.FLAGGED_HIGH_CONFIDENCE,
                            start_offset=cap_start,
                            end_offset=cap_end,
                            explanation_reason=(
                                f"Excessive uppercase formatting ('{cap_word}') degrades readability "
                                "and violates visual brand accessibility guidelines."
                            ),
                            suggested_correction=cap_word.capitalize(),
                            detector_source=DetectorSource.DETERMINISTIC_RULE,
                            linked_guideline_id=_resolve("ACC-CAPS-01", FindingCategory.ACCESSIBILITY),
                        )
                    )

        return findings

    @classmethod
    def calculate_fkgl(cls, text: str) -> float:
        """
        Calculates Flesch-Kincaid Grade Level formula:
        FKGL = 0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59
        """
        words = re.findall(r"[a-zA-Z0-9]+", text)
        if not words:
            return 0.0

        num_words = len(words)
        # Sentence count (at least 1)
        num_sentences = max(1, len(re.findall(r"[\.\?!]+", text)))

        num_syllables = sum(cls._count_syllables(w) for w in words)
        fkgl = 0.39 * (num_words / num_sentences) + 11.8 * (num_syllables / num_words) - 15.59
        return max(0.0, fkgl)

    @staticmethod
    def _count_syllables(word: str) -> int:
        """Heuristic English syllable counter with vowel grouping and silent 'e' handling."""
        w = word.lower().strip()
        if len(w) <= 3:
            return 1
        # Remove terminal silent e
        if w.endswith("e") and not w.endswith("le"):
            w = w[:-1]
        vowels = "aeiouy"
        count = 0
        prev_was_vowel = False
        for char in w:
            is_vowel = char in vowels
            if is_vowel and not prev_was_vowel:
                count += 1
            prev_was_vowel = is_vowel
        return max(1, count)
