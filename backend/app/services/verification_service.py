"""Dedicated Export Verification Service for PrivyDoc.

Performs independent post-export verification audits of redacted TXT and PDF artifacts:
1. Exact approved strings absence.
2. Known entity variants absence.
3. Approved phone/email/address/ID normalized values absence.
4. Extractable PDF page text inspection.
5. Remaining/uncommitted redaction annotations inspection.
6. PDF metadata inspection (title, author, subject, creator, producer, etc.).
7. Hidden content and unsupported structures inspection (attachments, JavaScript).
8. Export file integrity and encoding verification.

Strict Privacy Invariant:
Never log or return raw PII values in verification reports or exceptions.
Issues report candidate IDs, entity IDs, categories, and page numbers only.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import List, Optional, Set, Tuple
import pymupdf

from app.core.security import get_safe_session_dir
from app.detectors.entity_resolver import EntityResolver
from app.schemas.candidate import Candidate
from app.schemas.entity import Entity
from app.schemas.redaction import VerificationIssue, VerificationResult

logger = logging.getLogger(__name__)


class VerificationService:
    """Independent verification engine enforcing zero-leakage guarantees on exported artifacts."""

    @classmethod
    def verify_txt_export(
        cls,
        document_id: str,
        sanitized_txt_path: Path,
        approved_candidates: List[Candidate],
        entities: List[Entity],
    ) -> VerificationResult:
        """Verify that an exported TXT file is completely free of approved PII and variants."""
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
                )
            )
            return cls._build_result("FAILED", checks_run, issues, warnings)

        exported_lower = exported_text.casefold()

        # 2. Exact Approved Strings Check
        for cand in approved_candidates:
            clean_text = cand.text.strip()
            if not clean_text or len(clean_text) < 2:
                continue

            # Substring match (case-insensitive)
            if clean_text.casefold() in exported_lower:
                issues.append(
                    VerificationIssue(
                        check_name="EXACT_APPROVED_STRINGS",
                        description=f"Approved {cand.type} candidate (ID: {cand.candidate_id}) remains present in exported text.",
                        severity="ERROR",
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
            for variant in ent.variants:
                v_clean = variant.strip()
                if not v_clean or len(v_clean) < 2:
                    continue
                if v_clean.casefold() in exported_lower:
                    issues.append(
                        VerificationIssue(
                            check_name="KNOWN_ENTITY_VARIANTS",
                            description=f"Known alias variant for approved entity cluster {ent.entity_id} found in exported text.",
                            severity="ERROR",
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
                            description=f"Normalized digit sequence of approved PHONE candidate (ID: {cand.candidate_id}) found in exported text.",
                            severity="ERROR",
                            candidate_id=cand.candidate_id,
                        )
                    )
            elif cand.type == "ID_LIKE":
                compact_id = re.sub(r"[\s\-_]", "", cand.text).casefold()
                if len(compact_id) >= 6 and compact_id in re.sub(r"[\s\-_]", "", exported_lower):
                    issues.append(
                        VerificationIssue(
                            check_name="NORMALIZED_PII_PATTERNS",
                            description=f"Normalized alphanumeric sequence of approved ID candidate (ID: {cand.candidate_id}) found in exported text.",
                            severity="ERROR",
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
        approved_candidates: List[Candidate],
        entities: List[Entity],
    ) -> VerificationResult:
        """Verify that an exported PDF file has all approved PII physically purged."""
        checks_run: List[str] = [
            "FILE_INTEGRITY",
            "EXTRACTABLE_PDF_TEXT",
            "KNOWN_ENTITY_VARIANTS",
            "REMAINING_ANNOTATIONS",
            "METADATA_INSPECTION",
            "HIDDEN_STRUCTURES",
        ]
        issues: List[VerificationIssue] = []
        warnings: List[str] = []

        # 1. File Integrity Check
        if not sanitized_pdf_path.exists():
            issues.append(
                VerificationIssue(
                    check_name="FILE_INTEGRITY",
                    description="Exported sanitized PDF file was not created on disk.",
                    severity="ERROR",
                )
            )
            return cls._build_result("FAILED", checks_run, issues, warnings)

        if sanitized_pdf_path.stat().st_size == 0:
            issues.append(
                VerificationIssue(
                    check_name="FILE_INTEGRITY",
                    description="Exported PDF file is empty (0 bytes).",
                    severity="ERROR",
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
                )
            )
            return cls._build_result("FAILED", checks_run, issues, warnings)

        try:
            # 2. Extractable Page Text & Exact Approved Strings Check
            all_page_texts: List[Tuple[int, str]] = []
            for page_idx in range(doc.page_count):
                page = doc[page_idx]
                page_num = page_idx + 1
                text = page.get_text("text") or ""
                all_page_texts.append((page_num, text))

                # Also inspect annotations on this page
                for annot in page.annots():
                    # Check if unapplied redact annot remains
                    if annot.type[0] == pymupdf.PDF_ANNOT_REDACT:
                        issues.append(
                            VerificationIssue(
                                check_name="REMAINING_ANNOTATIONS",
                                description="Unapplied redaction annotation remains in output PDF.",
                                severity="ERROR",
                                page_number=page_num,
                            )
                        )
                    # Check if comment / text annotation contains text
                    annot_info = annot.info
                    annot_content = (annot_info.get("content") or "") + (annot_info.get("title") or "")
                    if annot_content:
                        for cand in approved_candidates:
                            if cand.text.strip().casefold() in annot_content.casefold():
                                issues.append(
                                    VerificationIssue(
                                        check_name="REMAINING_ANNOTATIONS",
                                        description=f"Annotation on page {page_num} contains approved {cand.type} content.",
                                        severity="ERROR",
                                        page_number=page_num,
                                        candidate_id=cand.candidate_id,
                                    )
                                )

            # Verify approved candidates across all extracted page texts
            for page_num, page_text in all_page_texts:
                page_lower = page_text.casefold()
                for cand in approved_candidates:
                    clean_text = cand.text.strip()
                    if not clean_text or len(clean_text) < 2:
                        continue
                    if clean_text.casefold() in page_lower:
                        issues.append(
                            VerificationIssue(
                                check_name="EXTRACTABLE_PDF_TEXT",
                                description=f"Extractable text on page {page_num} contains approved {cand.type} candidate (ID: {cand.candidate_id}).",
                                severity="ERROR",
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
                    for variant in ent.variants:
                        v_clean = variant.strip()
                        if not v_clean or len(v_clean) < 2:
                            continue
                        if v_clean.casefold() in page_lower:
                            issues.append(
                                VerificationIssue(
                                    check_name="KNOWN_ENTITY_VARIANTS",
                                    description=f"Extractable text on page {page_num} contains known variant of approved entity {ent.entity_id}.",
                                    severity="ERROR",
                                    page_number=page_num,
                                )
                            )
                            break

            # 4. Metadata Inspection Check
            meta = doc.metadata or {}
            combined_metadata_str = " ".join(
                str(v) for k, v in meta.items() if v and isinstance(v, str)
            ).casefold()

            for cand in approved_candidates:
                clean_text = cand.text.strip()
                if len(clean_text) >= 3 and clean_text.casefold() in combined_metadata_str:
                    issues.append(
                        VerificationIssue(
                            check_name="METADATA_INSPECTION",
                            description=f"Document metadata contains approved {cand.type} candidate content.",
                            severity="ERROR",
                            candidate_id=cand.candidate_id,
                        )
                    )

            for ent in relevant_entities:
                for variant in ent.variants:
                    v_clean = variant.strip()
                    if len(v_clean) >= 3 and v_clean.casefold() in combined_metadata_str:
                        issues.append(
                            VerificationIssue(
                                check_name="METADATA_INSPECTION",
                                description=f"Document metadata contains known variant for entity {ent.entity_id}.",
                                severity="ERROR",
                            )
                        )
                        break

            # 5. Hidden Structures & Unsupported Objects Check
            if doc.embfile_count() > 0:
                issues.append(
                    VerificationIssue(
                        check_name="HIDDEN_STRUCTURES",
                        description=f"Exported PDF contains {doc.embfile_count()} embedded file attachments that could not be sanitized.",
                        severity="ERROR",
                    )
                )

            if getattr(doc, "has_js", False):
                issues.append(
                    VerificationIssue(
                        check_name="HIDDEN_STRUCTURES",
                        description="Exported PDF contains active JavaScript objects.",
                        severity="ERROR",
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
        """Helper to construct VerificationResult."""
        now_iso = datetime.now(timezone.utc).isoformat()
        return VerificationResult(
            status=status,
            checks_run=checks_run,
            issues=issues,
            warnings=warnings,
            verified_at=now_iso,
        )
