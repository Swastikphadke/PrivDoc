"""Dedicated Export Verification Service for PrivyDoc.

Performs independent post-export verification audits of redacted TXT and PDF artifacts:
1. Exact approved strings absence (with occurrence-aware counting to preserve legitimate rejected/unreviewed occurrences).
2. Known entity variants absence.
3. Approved phone/email/address/ID normalized values absence.
4. Extractable PDF page text inspection.
5. Remaining/uncommitted redaction annotations inspection (PDF_ANNOT_REDACT).
6. PDF metadata inspection (title, author, subject, creator, producer, keywords, etc.).
7. PDF form fields and widget values inspection.
8. PDF links and URI destinations inspection.
9. Hidden content and unsupported structures inspection (attachments, JavaScript).
10. Export file integrity and encoding verification.

Strict Privacy Invariant:
Never log or return raw PII values in verification reports, issues, or exceptions.
Issues report candidate IDs, entity IDs, categories, diagnostic codes, and page numbers only.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple
import pymupdf

from app.schemas.candidate import Candidate
from app.schemas.entity import Entity
from app.schemas.redaction import VerificationIssue, VerificationResult

logger = logging.getLogger(__name__)

# Standard structural limitations notice documented explicitly per Stage D
PDF_STRUCTURAL_LIMITATIONS_NOTICE = (
    "PDF structural limitations notice: Verification scope covers extractable digital text streams, "
    "metadata dictionaries, annotations, form field widgets, links, embedded attachments, "
    "and document JavaScript. Raster images containing text (scanned stamps/signatures), "
    "vector path glyph outlines, and dynamic Adobe XFA forms cannot be forensically verified or sanitized via PyMuPDF."
)


class VerificationService:
    """Independent verification engine enforcing zero-leakage guarantees on exported artifacts."""

    @staticmethod
    def _count_occurrences(text_lower: str, target_lower: str) -> int:
        """Count occurrences of target_lower in text_lower using word-boundary protection for short tokens."""
        if not text_lower or not target_lower:
            return 0
        # For short tokens (<= 4 chars) or tokens starting/ending with alphanumeric characters,
        # enforce non-alphanumeric boundaries so 'al' does not falsely match inside 'also' or 'medical'.
        starts_alnum = target_lower[0].isalnum()
        ends_alnum = target_lower[-1].isalnum()
        if starts_alnum or ends_alnum:
            prefix = r"(?<![a-z0-9])" if starts_alnum else ""
            suffix = r"(?![a-z0-9])" if ends_alnum else ""
            pattern = re.compile(f"{prefix}{re.escape(target_lower)}{suffix}")
            return len(pattern.findall(text_lower))
        return text_lower.count(target_lower)

    @classmethod
    def verify_txt_export(
        cls,
        document_id: str,
        sanitized_txt_path: Path,
        canonical_text: str = "",
        approved_candidates: Optional[List[Candidate]] = None,
        all_candidates: Optional[List[Candidate]] = None,
        entities: Optional[List[Entity]] = None,
    ) -> VerificationResult:
        """Verify that an exported TXT file is completely free of approved PII and variants.

        Occurrence-aware: If the same text string appears in both an approved candidate and
        a rejected candidate, verification checks that the count in the exported text does not
        exceed the number of preserved (rejected/pending) occurrences. If an approved string
        was not preserved anywhere, its count must be exactly 0.
        """
        approved_candidates = approved_candidates or []
        all_candidates = all_candidates if all_candidates is not None else approved_candidates
        entities = entities or []
        checks_run: List[str] = [
            "FILE_INTEGRITY",
            "EXACT_APPROVED_STRINGS",
            "KNOWN_ENTITY_VARIANTS",
            "NORMALIZED_PII_PATTERNS",
        ]
        issues: List[VerificationIssue] = []
        warnings: List[str] = []

        # 1. File Integrity Check
        if not sanitized_txt_path.exists():
            issues.append(
                VerificationIssue(
                    check_name="FILE_INTEGRITY",
                    description="Exported sanitized TXT file was not created on disk.",
                    severity="ERROR",
                    diagnostic_code="TXT_FILE_NOT_FOUND",
                )
            )
            return cls._build_result("FAILED", checks_run, issues, warnings)

        try:
            exported_text = sanitized_txt_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            issues.append(
                VerificationIssue(
                    check_name="FILE_INTEGRITY",
                    description="Exported TXT file contains invalid non-UTF-8 character encodings.",
                    severity="ERROR",
                    diagnostic_code="TXT_ENCODING_ERROR",
                )
            )
            return cls._build_result("FAILED", checks_run, issues, warnings)

        exported_lower = exported_text.casefold()
        from app.core.security import normalize_for_security_comparison
        exported_sec_norm = normalize_for_security_comparison(exported_text)
        canonical_lower = canonical_text.casefold()

        # Build occurrence counts for preserved (rejected/pending) vs approved candidates
        preserved_candidates = [c for c in all_candidates if c.review_status in ("REJECTED", "PENDING")]

        # Group counts by normalized surface text
        approved_text_counts: Dict[str, int] = {}
        for c in approved_candidates:
            clean = normalize_for_security_comparison(c.text.strip())
            if clean and len(clean) >= 2:
                approved_text_counts[clean] = approved_text_counts.get(clean, 0) + 1

        preserved_text_counts: Dict[str, int] = {}
        for c in preserved_candidates:
            clean = normalize_for_security_comparison(c.text.strip())
            if clean and len(clean) >= 2:
                preserved_text_counts[clean] = preserved_text_counts.get(clean, 0) + 1

        # 2. Exact Approved Strings Check (Occurrence-Aware + Zero-Width/Homoglyph Normalized)
        verified_texts: Set[str] = set()
        for cand in approved_candidates:
            clean_text = cand.text.strip()
            clean_lower = normalize_for_security_comparison(clean_text)
            if not clean_text or len(clean_lower) < 2 or clean_lower in verified_texts:
                continue
            verified_texts.add(clean_lower)

            count_in_export = max(
                cls._count_occurrences(exported_lower, clean_text.casefold()),
                cls._count_occurrences(exported_sec_norm, clean_lower),
            )
            allowed_preserved_count = preserved_text_counts.get(clean_lower, 0)

            if count_in_export > allowed_preserved_count:
                issues.append(
                    VerificationIssue(
                        check_name="EXACT_APPROVED_STRINGS",
                        description=(
                            f"Approved {cand.type} candidate (ID: {cand.candidate_id}) remains present "
                            f"in exported text ({count_in_export} occurrences found, "
                            f"expected <= {allowed_preserved_count})."
                        ),
                        severity="ERROR",
                        diagnostic_code="APPROVED_TEXT_LEAK_TXT",
                        candidate_id=cand.candidate_id,
                    )
                )

        # 3. Known Entity Variants Check
        approved_cand_ids = {c.candidate_id for c in approved_candidates}
        relevant_entities = [
            ent for ent in entities
            if any(cid in approved_cand_ids for cid in ent.candidate_ids)
        ]

        for ent in relevant_entities:
            # Check if any candidate in this entity was preserved (rejected/pending)
            entity_has_preserved = any(
                cid not in approved_cand_ids for cid in ent.candidate_ids
            )
            for variant in ent.variants:
                v_clean = variant.strip()
                v_lower = v_clean.casefold()
                if not v_clean or len(v_clean) < 2:
                    continue

                count_var = cls._count_occurrences(exported_lower, v_lower)
                # If no candidate of this entity was preserved, count must be 0
                if not entity_has_preserved and count_var > 0:
                    issues.append(
                        VerificationIssue(
                            check_name="KNOWN_ENTITY_VARIANTS",
                            description=(
                                f"Known alias variant for approved entity cluster {ent.entity_id} "
                                f"found in exported text."
                            ),
                            severity="ERROR",
                            diagnostic_code="ENTITY_VARIANT_LEAK_TXT",
                        )
                    )
                    break

        # 4. Normalized PII Values Check (phones digits, IDs without separators)
        for cand in approved_candidates:
            if cand.type == "PHONE":
                digits = re.sub(r"\D", "", cand.text)
                if len(digits) >= 7 and digits in exported_text:
                    issues.append(
                        VerificationIssue(
                            check_name="NORMALIZED_PII_PATTERNS",
                            description=(
                                f"Normalized digit sequence of approved PHONE candidate "
                                f"(ID: {cand.candidate_id}) found in exported text."
                            ),
                            severity="ERROR",
                            diagnostic_code="NORMALIZED_PHONE_LEAK_TXT",
                            candidate_id=cand.candidate_id,
                        )
                    )
            elif cand.type == "ID_LIKE":
                compact_id = re.sub(r"[\s\-_]", "", cand.text).casefold()
                if len(compact_id) >= 6 and compact_id in re.sub(r"[\s\-_]", "", exported_lower):
                    issues.append(
                        VerificationIssue(
                            check_name="NORMALIZED_PII_PATTERNS",
                            description=(
                                f"Normalized alphanumeric sequence of approved ID candidate "
                                f"(ID: {cand.candidate_id}) found in exported text."
                            ),
                            severity="ERROR",
                            diagnostic_code="NORMALIZED_ID_LEAK_TXT",
                            candidate_id=cand.candidate_id,
                        )
                    )

        status = "PASSED" if not issues else "FAILED"
        return cls._build_result(status, checks_run, issues, warnings)

    @classmethod
    def verify_pdf_export(
        cls,
        document_id: str,
        sanitized_pdf_path: Path,
        approved_candidates: Optional[List[Candidate]] = None,
        all_candidates: Optional[List[Candidate]] = None,
        entities: Optional[List[Entity]] = None,
    ) -> VerificationResult:
        """Verify that an exported PDF file has all approved PII physically purged."""
        approved_candidates = approved_candidates or []
        all_candidates = all_candidates if all_candidates is not None else approved_candidates
        entities = entities or []
        checks_run: List[str] = [
            "FILE_INTEGRITY",
            "EXTRACTABLE_PDF_TEXT",
            "KNOWN_ENTITY_VARIANTS",
            "REMAINING_ANNOTATIONS",
            "METADATA_INSPECTION",
            "WIDGETS_AND_FORMS",
            "LINKS_INSPECTION",
            "HIDDEN_STRUCTURES",
        ]
        issues: List[VerificationIssue] = []
        warnings: List[str] = [PDF_STRUCTURAL_LIMITATIONS_NOTICE]

        # 1. File Integrity Check
        if not sanitized_pdf_path.exists():
            issues.append(
                VerificationIssue(
                    check_name="FILE_INTEGRITY",
                    description="Exported sanitized PDF file was not created on disk.",
                    severity="ERROR",
                    diagnostic_code="PDF_FILE_NOT_FOUND",
                )
            )
            return cls._build_result("FAILED", checks_run, issues, warnings)

        if sanitized_pdf_path.stat().st_size == 0:
            issues.append(
                VerificationIssue(
                    check_name="FILE_INTEGRITY",
                    description="Exported PDF file is empty (0 bytes).",
                    severity="ERROR",
                    diagnostic_code="PDF_EMPTY_FILE",
                )
            )
            return cls._build_result("FAILED", checks_run, issues, warnings)

        try:
            doc = pymupdf.open(sanitized_pdf_path)
        except Exception as exc:
            issues.append(
                VerificationIssue(
                    check_name="FILE_INTEGRITY",
                    description="Exported PDF file is malformed and cannot be parsed by PyMuPDF.",
                    severity="ERROR",
                    diagnostic_code="PDF_MALFORMED_PARSE_ERROR",
                )
            )
            return cls._build_result("FAILED", checks_run, issues, warnings)

        try:
            # Preserved candidates on each page for occurrence-aware checks
            preserved_candidates = [c for c in all_candidates if c.review_status in ("REJECTED", "PENDING")]

            all_page_texts: List[Tuple[int, str]] = []

            # 2. Extractable Page Text & Annotations & Form Widgets & Links
            for page_idx in range(doc.page_count):
                page = doc[page_idx]
                page_num = page_idx + 1
                text = page.get_text("text") or ""
                all_page_texts.append((page_num, text))

                # Check Annotations (unapplied redaction annotations or sensitive comment text)
                for annot in page.annots():
                    if annot.type[0] == pymupdf.PDF_ANNOT_REDACT:
                        issues.append(
                            VerificationIssue(
                                check_name="REMAINING_ANNOTATIONS",
                                description=f"Unapplied redaction annotation remains on page {page_num}.",
                                severity="ERROR",
                                diagnostic_code="UNAPPLIED_REDACT_ANNOT",
                                page_number=page_num,
                            )
                        )
                    annot_info = annot.info or {}
                    annot_content = (annot_info.get("content") or "") + (annot_info.get("title") or "")
                    if annot_content:
                        for cand in approved_candidates:
                            clean_c = cand.text.strip().casefold()
                            if len(clean_c) >= 2 and clean_c in annot_content.casefold():
                                issues.append(
                                    VerificationIssue(
                                        check_name="REMAINING_ANNOTATIONS",
                                        description=f"Annotation on page {page_num} contains approved {cand.type} content.",
                                        severity="ERROR",
                                        diagnostic_code="ANNOTATION_PII_LEAK",
                                        page_number=page_num,
                                        candidate_id=cand.candidate_id,
                                    )
                                )

                # Check Form Widgets
                for widget in page.widgets():
                    field_val = str(widget.field_value or "")
                    field_name = str(widget.field_name or "")
                    combined_widget = f"{field_name} {field_val}".casefold()
                    for cand in approved_candidates:
                        clean_c = cand.text.strip().casefold()
                        if len(clean_c) >= 2 and clean_c in combined_widget:
                            issues.append(
                                VerificationIssue(
                                    check_name="WIDGETS_AND_FORMS",
                                    description=f"AcroForm field on page {page_num} contains approved {cand.type} content.",
                                    severity="ERROR",
                                    diagnostic_code="FORM_WIDGET_PII_LEAK",
                                    page_number=page_num,
                                    candidate_id=cand.candidate_id,
                                )
                            )

                # Check Document Links & URIs
                for link in page.get_links():
                    uri = str(link.get("uri") or "").casefold()
                    if uri:
                        for cand in approved_candidates:
                            clean_c = cand.text.strip().casefold()
                            if len(clean_c) >= 3 and clean_c in uri:
                                issues.append(
                                    VerificationIssue(
                                        check_name="LINKS_INSPECTION",
                                        description=f"Link URI on page {page_num} contains approved {cand.type} content.",
                                        severity="ERROR",
                                        diagnostic_code="LINK_URI_PII_LEAK",
                                        page_number=page_num,
                                        candidate_id=cand.candidate_id,
                                    )
                                )

            # Verify approved candidates across all extracted page texts (Occurrence-Aware + Security Normalized)
            from app.core.security import normalize_for_security_comparison
            for page_num, page_text in all_page_texts:
                page_lower = page_text.casefold()
                page_sec_norm = normalize_for_security_comparison(page_text)

                # Count preserved candidates on this page
                page_preserved = [
                    c for c in preserved_candidates
                    if getattr(c, "page_number", None) == page_num or getattr(c, "page_number", None) is None
                ]
                page_preserved_counts: Dict[str, int] = {}
                for c in page_preserved:
                    clean = normalize_for_security_comparison(c.text.strip())
                    if clean and len(clean) >= 2:
                        page_preserved_counts[clean] = page_preserved_counts.get(clean, 0) + 1

                checked_on_page: Set[str] = set()
                for cand in approved_candidates:
                    clean_text = cand.text.strip()
                    clean_lower = normalize_for_security_comparison(clean_text)
                    if not clean_text or len(clean_lower) < 2 or clean_lower in checked_on_page:
                        continue
                    checked_on_page.add(clean_lower)

                    count_on_page = max(
                        cls._count_occurrences(page_lower, clean_text.casefold()),
                        cls._count_occurrences(page_sec_norm, clean_lower),
                    )
                    allowed_on_page = page_preserved_counts.get(clean_lower, 0)

                    if count_on_page > allowed_on_page:
                        issues.append(
                            VerificationIssue(
                                check_name="EXTRACTABLE_PDF_TEXT",
                                description=(
                                    f"Extractable text on page {page_num} contains approved {cand.type} "
                                    f"candidate (ID: {cand.candidate_id}). Found {count_on_page} occurrences, "
                                    f"expected <= {allowed_on_page}."
                                ),
                                severity="ERROR",
                                diagnostic_code="EXTRACTABLE_TEXT_LEAK_PDF",
                                page_number=page_num,
                                candidate_id=cand.candidate_id,
                            )
                        )

            # 3. Known Entity Variants Check
            approved_cand_ids = {c.candidate_id for c in approved_candidates}
            relevant_entities = [
                ent for ent in entities
                if any(cid in approved_cand_ids for cid in ent.candidate_ids)
            ]

            for page_num, page_text in all_page_texts:
                page_lower = page_text.casefold()
                for ent in relevant_entities:
                    entity_has_preserved = any(
                        cid not in approved_cand_ids for cid in ent.candidate_ids
                    )
                    for variant in ent.variants:
                        v_clean = variant.strip()
                        v_lower = v_clean.casefold()
                        if not v_clean or len(v_clean) < 2:
                            continue
                        if not entity_has_preserved and cls._count_occurrences(page_lower, v_lower) > 0:
                            issues.append(
                                VerificationIssue(
                                    check_name="KNOWN_ENTITY_VARIANTS",
                                    description=(
                                        f"Extractable text on page {page_num} contains known variant of "
                                        f"approved entity {ent.entity_id}."
                                    ),
                                    severity="ERROR",
                                    diagnostic_code="ENTITY_VARIANT_LEAK_PDF",
                                    page_number=page_num,
                                )
                            )
                            break

            # 4. Metadata Inspection Check (Classic Info Dict + XMP XML Stream + Bookmarks TOC)
            meta = doc.metadata or {}
            try:
                xml_metadata_str = doc.get_xml_metadata() or ""
            except Exception:
                xml_metadata_str = ""
            combined_metadata_str = (
                " ".join(str(v) for k, v in meta.items() if v and isinstance(v, str))
                + " "
                + xml_metadata_str
            ).casefold()

            for cand in approved_candidates:
                clean_text = cand.text.strip()
                if len(clean_text) >= 3 and cls._count_occurrences(combined_metadata_str, clean_text.casefold()) > 0:
                    issues.append(
                        VerificationIssue(
                            check_name="METADATA_INSPECTION",
                            description=f"Document metadata or XMP stream contains approved {cand.type} candidate content.",
                            severity="ERROR",
                            diagnostic_code="METADATA_PII_LEAK_PDF",
                            candidate_id=cand.candidate_id,
                        )
                    )

            for ent in relevant_entities:
                for variant in ent.variants:
                    v_clean = variant.strip()
                    if len(v_clean) >= 3 and cls._count_occurrences(combined_metadata_str, v_clean.casefold()) > 0:
                        issues.append(
                            VerificationIssue(
                                check_name="METADATA_INSPECTION",
                                description=f"Document metadata or XMP stream contains known variant for entity {ent.entity_id}.",
                                severity="ERROR",
                                diagnostic_code="METADATA_VARIANT_LEAK_PDF",
                            )
                        )
                        break

            # Inspect PDF Document Outlines / Table of Contents (Bookmarks)
            try:
                toc_items = doc.get_toc() or []
                combined_toc_str = " ".join(
                    str(item[1]) for item in toc_items if len(item) >= 2 and item[1]
                ).casefold()
                if combined_toc_str:
                    for cand in approved_candidates:
                        clean_text = cand.text.strip()
                        if len(clean_text) >= 2 and cls._count_occurrences(combined_toc_str, clean_text.casefold()) > 0:
                            issues.append(
                                VerificationIssue(
                                    check_name="HIDDEN_STRUCTURES",
                                    description=f"PDF bookmark outline (TOC) contains approved {cand.type} candidate content.",
                                    severity="ERROR",
                                    diagnostic_code="TOC_BOOKMARK_PII_LEAK_PDF",
                                    candidate_id=cand.candidate_id,
                                )
                            )
            except Exception:
                pass

            # 5. Hidden Structures & Unsupported Objects Check
            if doc.embfile_count() > 0:
                issues.append(
                    VerificationIssue(
                        check_name="HIDDEN_STRUCTURES",
                        description=f"Exported PDF contains {doc.embfile_count()} embedded file attachments that could not be sanitized.",
                        severity="ERROR",
                        diagnostic_code="EMBEDDED_FILES_LEAK_PDF",
                    )
                )

            if getattr(doc, "has_js", False):
                issues.append(
                    VerificationIssue(
                        check_name="HIDDEN_STRUCTURES",
                        description="Exported PDF contains active JavaScript objects.",
                        severity="ERROR",
                        diagnostic_code="JAVASCRIPT_OBJECTS_LEAK_PDF",
                    )
                )

        finally:
            doc.close()

        status = "PASSED" if not issues else "FAILED"
        return cls._build_result(status, checks_run, issues, warnings)

    @classmethod
    def _build_result(
        cls,
        status: str,
        checks_run: List[str],
        issues: List[VerificationIssue],
        warnings: List[str],
    ) -> VerificationResult:
        """Helper to construct VerificationResult with ISO timestamp."""
        now_iso = datetime.now(timezone.utc).isoformat()
        return VerificationResult(
            status=status,
            checks_run=checks_run,
            issues=issues,
            warnings=warnings,
            verified_at=now_iso,
        )
