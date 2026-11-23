"""Privacy-Preserving Summarization Service (Phase P6).

Strict Privacy & Security Invariants:
1. Architectural Isolation (TDR-010, FR-021):
   The summarizer receives an isolated SanitizedDocument instance ONLY.
   Zero access to original document objects, original extracted text, original PDFs,
   unredacted candidate values, or coordinate mappings.
2. Structured Output Guarantee:
   Generates strictly structured summaries conforming to StructuredSummaryContent
   (summary text, key points, findings, grounded dates/figures, and source evidence).
3. Degraded Mode & Fallback (DEC-003, TDR-008):
   If local SLM is unavailable, times out, or returns malformed output, the system seamlessly
   falls back to a deterministic extractive summary generated exclusively from sanitized text.
   The extractive fallback undergoes the IDENTICAL multi-tiered privacy verification checks.
4. Fail-Safe Bounded Retry & Suppression (NFR-012, FR-024):
   Max 2 retries on privacy failure. Re-runs all checks after each retry.
   If verification remains failed or unsafe, output is SUPPRESSED and never displayed as verified.
"""

import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.security import get_safe_session_dir
from app.schemas.summary import (
    QuasiRiskLevel,
    SanitizedDocument,
    StructuredSummaryContent,
    SummaryEngine,
    SummaryRequest,
    SummaryResponse,
    SummaryState,
    SummaryVerificationReport,
)
from app.services.model_service import ModelService
from app.services.summary_guard import SummaryGuard

logger = logging.getLogger(__name__)

STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves",
}


class SummaryService:
    """Orchestrates privacy-preserving document summarization with strict boundary enforcement."""

    MAX_RETRIES: int = 2

    @classmethod
    def generate_summary(
        cls,
        sanitized_doc: SanitizedDocument,
        request: Optional[SummaryRequest] = None,
        guard_references: Optional[Dict[str, Any]] = None,
    ) -> SummaryResponse:
        """Generate, verify, and persist a privacy-preserving summary.

        Args:
            sanitized_doc: Strict SanitizedDocument contract containing ONLY verified sanitized text.
            request: Optional configuration (max_length, force_extractive).
            guard_references: Optional reference data (approved values, aliases) passed strictly
                              to SummaryGuard for leakage detection. (NEVER passed to the SLM).

        Returns:
            SummaryResponse with verified content or safe suppression.
        """
        if not isinstance(sanitized_doc, SanitizedDocument):
            raise TypeError("SummaryService requires a typed SanitizedDocument contract.")

        if not sanitized_doc.sanitized_text or not sanitized_doc.sanitized_text.strip():
            raise ValueError("Sanitized text is empty; cannot generate summary.")

        if not sanitized_doc.export_verification_ref:
            raise ValueError("SanitizedDocument lacks export verification reference; non-verified exports are rejected.")

        if request is None:
            request = SummaryRequest()

        document_id = sanitized_doc.document_id
        session_dir = get_safe_session_dir(document_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        engine_used = SummaryEngine.SLM
        summary_content: Optional[StructuredSummaryContent] = None
        verification_report: Optional[SummaryVerificationReport] = None
        retry_count = 0
        state = SummaryState.GENERATING

        # Check if local SLM is available or if extractive mode is forced
        use_extractive = request.force_extractive
        if not use_extractive:
            if not ModelService.check_availability():
                logger.info("Local SLM is offline. Seamlessly utilizing extractive fallback on sanitized text.")
                use_extractive = True

        # Generation & Bounded Retry Loop
        if not use_extractive:
            # Attempt SLM generation with retries
            for attempt in range(cls.MAX_RETRIES + 1):
                retry_count = attempt
                retry_guidance = None
                if attempt > 0:
                    retry_guidance = (
                        "Previous attempt contained unsupported terms or residual identifiers. "
                        "Adhere strictly and exclusively to facts in the sanitized text without inventing details."
                    )

                raw_slm = ModelService.generate_structured_summary(
                    sanitized_text=sanitized_doc.sanitized_text,
                    max_length=request.max_length or 250,
                    retry_guidance=retry_guidance,
                )

                if raw_slm is None:
                    # Model failed, timed out, or returned invalid JSON
                    logger.warning("SLM generation attempt %d failed. Falling back to extractive engine.", attempt + 1)
                    use_extractive = True
                    break

                # Verify SLM output with SummaryGuard
                state = SummaryState.VERIFYING
                report = SummaryGuard.verify_summary(raw_slm, sanitized_doc, guard_references)
                verification_report = report

                if report.status == "PASSED":
                    summary_content = raw_slm
                    state = SummaryState.VERIFIED
                    engine_used = SummaryEngine.SLM
                    break
                elif report.status == "REQUIRES_REVIEW":
                    # High quasi-identifier risk without direct leaks
                    summary_content = raw_slm
                    state = SummaryState.REQUIRES_REVIEW
                    engine_used = SummaryEngine.SLM
                    break
                else:
                    # FAILED checks
                    logger.warning(
                        "SLM summary failed privacy verification on attempt %d: %s",
                        attempt + 1,
                        [c.check_name for c in report.checks if c.status == "FAILED"],
                    )
                    if attempt == cls.MAX_RETRIES:
                        logger.info("SLM retries exhausted. Switching to extractive fallback.")
                        use_extractive = True

        # Extractive Fallback Path
        if use_extractive:
            engine_used = SummaryEngine.EXTRACTIVE_FALLBACK
            state = SummaryState.GENERATING
            extractive_content = cls.generate_extractive_summary(
                sanitized_text=sanitized_doc.sanitized_text,
                max_length=request.max_length or 250,
            )

            # Subject extractive fallback to IDENTICAL privacy verification
            state = SummaryState.VERIFYING
            report = SummaryGuard.verify_summary(extractive_content, sanitized_doc, guard_references)
            verification_report = report

            if report.status == "PASSED":
                summary_content = extractive_content
                state = SummaryState.VERIFIED
            elif report.status == "REQUIRES_REVIEW":
                summary_content = extractive_content
                state = SummaryState.REQUIRES_REVIEW
            else:
                summary_content = None
                state = SummaryState.SUPPRESSED

        # Final state check and fail-safe suppression
        warning_message: Optional[str] = None
        if state == SummaryState.SUPPRESSED:
            summary_content = None
            warning_message = (
                "Summary output has been suppressed because it failed one or more mandatory privacy checks. "
                "No unsafe or unverified content will be displayed."
            )
        elif state == SummaryState.REQUIRES_REVIEW:
            warning_message = (
                "Summary flagged for human review: plausible quasi-identifier co-occurrences were detected. "
                "Quasi-identifier flags reflect potential statistical re-identification risk and do not guarantee anonymity."
            )
        elif state == SummaryState.VERIFIED and engine_used == SummaryEngine.EXTRACTIVE_FALLBACK:
            warning_message = "Generated using deterministic extractive fallback operating exclusively on sanitized text."

        response = SummaryResponse(
            document_id=document_id,
            state=state,
            engine_used=engine_used,
            content=summary_content,
            verification_report=verification_report,
            retry_count=retry_count,
            warning_message=warning_message,
        )

        # Persist summary response to session directory
        summary_path = session_dir / "summary.json"
        summary_path.write_text(response.model_dump_json(indent=2), encoding="utf-8")

        return response

    @classmethod
    def generate_extractive_summary(
        cls,
        sanitized_text: str,
        max_length: int = 250,
    ) -> StructuredSummaryContent:
        """Deterministic extractive summarization operating exclusively on sanitized text.

        Guarantees:
        - Never introduces outside words, names, dates, or figures.
        - Preserves redaction placeholders intact.
        - Scores sentences using term-frequency and document position.
        """
        # Split into sentences
        raw_sentences = re.split(r"(?<=[.!?])\s+|\n+", sanitized_text.strip())
        sentences: List[str] = [s.strip() for s in raw_sentences if len(s.strip()) >= 15]

        if not sentences:
            # Fallback for very short text
            single_s = sanitized_text.strip() or "No content available."
            return StructuredSummaryContent(
                summary_text=single_s,
                key_points=[single_s],
                important_findings=[],
                relevant_dates_or_figures=[],
                source_evidence=[single_s[:100]],
            )

        # Calculate word frequency weights
        words = re.findall(r"\b[a-zA-Z]{3,}\b", sanitized_text.lower())
        word_freq: Dict[str, int] = {}
        for w in words:
            if w not in STOPWORDS:
                word_freq[w] = word_freq.get(w, 0) + 1

        # Score sentences
        sentence_scores: List[Tuple[float, int, str]] = []
        for idx, sent in enumerate(sentences):
            sent_words = re.findall(r"\b[a-zA-Z]{3,}\b", sent.lower())
            if not sent_words:
                continue
            score = sum(word_freq.get(w, 0) for w in sent_words) / (len(sent_words) ** 0.5)

            # Bonus for sentences containing contractual or project keywords
            if re.search(r"\b(agree|policy|contract|deliverable|scope|requirement|confidential|status|finding|report)\b", sent, re.IGNORECASE):
                score *= 1.3

            sentence_scores.append((score, idx, sent))

        # Select top 2-4 sentences based on word budget
        sentence_scores.sort(key=lambda x: x[0], reverse=True)
        target_count = min(4, max(2, len(sentences) // 3))
        selected = sentence_scores[:target_count]

        # Re-sort into original document order
        selected.sort(key=lambda x: x[1])
        selected_sentences = [item[2] for item in selected]

        summary_text = " ".join(selected_sentences)
        # Enforce max word limit if necessary
        words_summary = summary_text.split()
        if len(words_summary) > max_length:
            summary_text = " ".join(words_summary[:max_length]) + "..."

        # Extract key points from selected sentences
        key_points = [s for s in selected_sentences[:3]]

        # Extract important findings (sentences matching findings keywords)
        findings = [
            s for s in selected_sentences
            if re.search(r"\b(agree|require|deliver|complete|finding|policy|compliance|obligation)\b", s, re.IGNORECASE)
        ]
        if not findings and selected_sentences:
            findings = [selected_sentences[0]]

        # Extract dates or figures from selected sentences only
        dates_and_figures = re.findall(
            r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b(?:\$|€|£|₹)?\d+(?:[.,]\d+)*(?:\s*(?:%|percent|million|billion|thousand))?\b",
            summary_text,
            re.IGNORECASE,
        )
        unique_dates_and_figures = list(dict.fromkeys([item.strip() for item in dates_and_figures if len(item.strip()) >= 2]))

        # Source evidence references
        source_evidence = [s[:120] + ("..." if len(s) > 120 else "") for s in selected_sentences[:2]]

        return StructuredSummaryContent(
            summary_text=summary_text,
            key_points=key_points,
            important_findings=findings,
            relevant_dates_or_figures=unique_dates_and_figures[:5],
            source_evidence=source_evidence,
        )

    @classmethod
    def get_existing_summary(cls, document_id: str) -> Optional[SummaryResponse]:
        """Retrieve previously saved summary for document session, if present."""
        session_dir = get_safe_session_dir(document_id)
        summary_path = session_dir / "summary.json"
        if not summary_path.exists():
            return None

        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
            return SummaryResponse.model_validate(data)
        except Exception as exc:
            logger.warning("Failed to parse existing summary for %s: %s", document_id, exc)
            return None
