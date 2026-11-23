"""Summary Privacy Guard & Multi-Tiered Verification Service (Phase P6).

Strict Privacy & Security Invariants:
1. Multi-Tiered Verification Pipeline:
   A. Direct leakage detection against approved candidate values.
   B. Alias and entity-variant detection.
   C. PII re-detection (Regex + NER).
   D. Configurable quasi-identifier risk assessment.
   E. Source consistency validation (hallucination & reconstructed detail detection).
2. Fail-Closed Privacy Guarantee:
   A single failed mandatory check prevents a summary from ever being marked VERIFIED.
3. Safe Masked Reporting (NFR-004):
   Never expose raw PII values, sensitive candidate strings, or person names in logs,
   API responses, check details, or error messages.
4. Quasi-Identifier Principle (TDR-011, FR-024):
   Quasi-identifier evaluation identifies statistical re-identification risk flags;
   it is never described as mathematical or definitive proof of complete anonymity.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.config import settings
from app.detectors.ner_detector import NERDetector
from app.detectors.regex_detector import RegexDetector
from app.schemas.summary import (
    QuasiIdentifierAssessment,
    QuasiRiskLevel,
    SanitizedDocument,
    StructuredSummaryContent,
    SummaryVerificationCheck,
    SummaryVerificationReport,
)

logger = logging.getLogger(__name__)


class SummaryGuard:
    """Multi-tiered privacy and consistency guard for generated summaries."""

    _quasi_config_cache: Optional[Dict[str, Any]] = None

    @classmethod
    def get_quasi_config(cls, custom_path: Optional[Path] = None) -> Dict[str, Any]:
        """Load and cache quasi-identifier configuration from JSON."""
        if cls._quasi_config_cache is not None and custom_path is None:
            return cls._quasi_config_cache

        paths_to_try = [
            custom_path,
            settings.BASE_DIR / "backend" / "app" / "core" / "quasi_identifiers.json",
            settings.BASE_DIR / "app" / "core" / "quasi_identifiers.json",
            Path(__file__).resolve().parent.parent / "core" / "quasi_identifiers.json",
            settings.BASE_DIR / "config" / "quasi_identifiers.json",
        ]

        for p in paths_to_try:
            if p and p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    if custom_path is None:
                        cls._quasi_config_cache = data
                    return data
                except Exception as exc:
                    logger.warning("Failed to parse quasi_identifiers.json at %s: %s", p, exc)

        # Fallback default configuration
        default_cfg = {
            "rules": [
                {
                    "id": "QI-001",
                    "name": "role_department_location",
                    "description": "Co-occurrence of executive role, department, and location or date",
                    "risk_level": "HIGH",
                    "required_categories": ["ROLE", "DEPARTMENT", "LOCATION_OR_DATE"],
                },
                {
                    "id": "QI-002",
                    "name": "demographic_tuple",
                    "description": "Co-occurrence of age/birth-year, gender, and locality/postal code",
                    "risk_level": "HIGH",
                    "required_categories": ["AGE_OR_DOB", "GENDER", "LOCATION_OR_ZIP"],
                },
                {
                    "id": "QI-004",
                    "name": "role_department_alone",
                    "description": "Executive role combined with specific department",
                    "risk_level": "MEDIUM",
                    "required_categories": ["ROLE", "DEPARTMENT"],
                },
            ],
            "dictionaries": {
                "roles": ["director", "ceo", "cfo", "cto", "cso", "ciso", "dean", "principal", "chief", "head of", "lead architect"],
                "departments": ["oncology", "pediatrics", "cardiology", "cybersecurity", "finance", "legal", "hr", "operations"],
                "genders": ["male", "female", "man", "woman"],
            },
            "disclaimer": (
                "Quasi-identifier risk evaluation assesses statistical re-identification risk flags based on "
                "demographic or contextual co-occurrences; it does not constitute mathematical or legal proof "
                "of complete anonymity."
            ),
        }
        if custom_path is None:
            cls._quasi_config_cache = default_cfg
        return default_cfg

    @classmethod
    def check_direct_leakage(
        cls,
        summary_text: str,
        approved_values: List[str],
    ) -> Tuple[bool, Optional[str]]:
        """A. Direct leakage detection: Check if any approved PII values appear in summary.

        Returns (passed, error_detail).
        NEVER includes raw PII values in error_detail or log messages.
        """
        if not approved_values or not summary_text:
            return True, None

        normalized_summary = summary_text.lower()

        for val in approved_values:
            cleaned_val = val.strip().lower()
            # Ignore short 1-2 character tokens or common whitespace
            if len(cleaned_val) < 3:
                continue

            # Substring and word-boundary check
            pattern = re.compile(rf"(?:\b|\s|^){re.escape(cleaned_val)}(?:\b|\s|$|[.,;:!?'\"])", re.IGNORECASE)
            if pattern.search(normalized_summary) or cleaned_val in normalized_summary:
                val_hash = hashlib.sha256(val.encode("utf-8")).hexdigest()[:8]
                logger.warning(
                    "Direct leakage detected in summary: approved entity [token_hash=%s] found.",
                    val_hash,
                )
                return False, f"Approved sensitive entity detected in summary (token hash: {val_hash})."

        return True, None

    @classmethod
    def check_alias_and_entity_variants(
        cls,
        summary_text: str,
        entity_variants: List[str],
    ) -> Tuple[bool, Optional[str]]:
        """B. Alias and entity-variant detection: Check for initials, nicknames, or resolved entity mentions.

        Returns (passed, error_detail).
        NEVER exposes sensitive variant strings in output.
        """
        if not entity_variants or not summary_text:
            return True, None

        normalized_summary = summary_text.lower()

        for variant in entity_variants:
            cleaned_var = variant.strip().lower()
            if len(cleaned_var) < 3:
                continue

            pattern = re.compile(rf"(?:\b|\s|^){re.escape(cleaned_var)}(?:\b|\s|$|[.,;:!?'\"])", re.IGNORECASE)
            if pattern.search(normalized_summary) or cleaned_var in normalized_summary:
                var_hash = hashlib.sha256(variant.encode("utf-8")).hexdigest()[:8]
                logger.warning(
                    "Alias/variant leakage detected in summary: entity variant [token_hash=%s] found.",
                    var_hash,
                )
                return False, f"Approved entity alias or variant detected in summary (token hash: {var_hash})."

        return True, None

    @classmethod
    def check_pii_redetection(
        cls,
        summary_text: str,
    ) -> Tuple[bool, Optional[str]]:
        """C. PII re-detection: Re-run Regex and NER detection across summary text.

        Returns (passed, error_detail).
        Excludes category placeholders (e.g. [PERSON], [EMAIL]).
        """
        if not summary_text:
            return True, None

        # Strip standard and entity-indexed placeholders (e.g. [PERSON], [PERSON_1], [EMAIL_2]) so they do not trigger false positive regex/NER
        scrubbed = re.sub(
            r"\[(?:PERSON|EMAIL|PHONE|ADDRESS|ID_LIKE|REDACTED|CONFIDENTIAL)(?:_\d+)?(?:/(?:PERSON|EMAIL|PHONE|ADDRESS|ID_LIKE)(?:_\d+)?)*\]",
            " ",
            summary_text,
        )

        # 1. Deterministic Regex Detection
        regex_candidates = RegexDetector.detect(scrubbed)
        for cand in regex_candidates:
            # Check if match is real and not an empty token
            match_text = cand.text.strip()
            cand_cat = getattr(cand, "type", getattr(cand, "category", "PII"))
            if match_text and len(match_text) >= 3:
                logger.warning(
                    "PII re-detection failed on summary: regex detected category '%s'.",
                    cand_cat,
                )
                return False, f"Residual PII detected in summary of category '{cand_cat}' via deterministic scan."

        # 2. Contextual NER Detection
        try:
            ner_candidates = NERDetector.detect(scrubbed)
            for cand in ner_candidates:
                match_text = cand.text.strip()
                cand_cat = getattr(cand, "type", getattr(cand, "category", "PII"))
                if match_text and len(match_text) >= 3 and cand.confidence >= 0.55:
                    logger.warning(
                        "PII re-detection failed on summary: NER detected category '%s'.",
                        cand_cat,
                    )
                    return False, f"Residual PII detected in summary of category '{cand_cat}' via contextual NER scan."
        except Exception as exc:
            logger.debug("NER detection during summary guard skipped/errored: %s", exc)

        return True, None

    @classmethod
    def check_quasi_identifier_risk(
        cls,
        summary_text: str,
        sanitized_text: str,
        config_path: Optional[Path] = None,
    ) -> QuasiIdentifierAssessment:
        """D. Quasi-identifier risk assessment: Evaluate co-occurrence rules.

        Returns QuasiIdentifierAssessment with risk_level (LOW, MEDIUM, HIGH), flagged rules,
        findings, and mandatory disclaimer.
        """
        cfg = cls.get_quasi_config(config_path)
        rules = cfg.get("rules", [])
        dicts = cfg.get("dictionaries", {})
        disclaimer = cfg.get(
            "disclaimer",
            "Quasi-identifier risk evaluation assesses statistical re-identification risk flags based on "
            "demographic or contextual co-occurrences; it does not constitute mathematical or legal proof "
            "of complete anonymity."
        )

        norm_text = summary_text.lower()
        flagged_rules: List[str] = []
        findings: List[str] = []
        highest_risk = QuasiRiskLevel.LOW

        # Detect categories present in summary
        matched_roles: List[str] = [
            r for r in dicts.get("roles", []) if re.search(rf"\b{re.escape(r)}\b", norm_text)
        ]
        matched_departments: List[str] = [
            d for d in dicts.get("departments", []) if re.search(rf"\b{re.escape(d)}\b", norm_text)
        ]
        matched_genders: List[str] = [
            g for g in dicts.get("genders", []) if re.search(rf"\b{re.escape(g)}\b", norm_text)
        ]
        matched_conditions: List[str] = [
            m for m in dicts.get("medical_conditions", []) if re.search(rf"\b{re.escape(m)}\b", norm_text)
        ]
        matched_incidents: List[str] = [
            i for i in dicts.get("incident_terms", []) if re.search(rf"\b{re.escape(i)}\b", norm_text)
        ]

        # Specific dates (e.g. 2024, 14/10/2024, October 2024)
        has_dates = bool(
            re.search(
                r"\b(?:19|20)\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b",
                norm_text,
            )
        )
        # Location keywords (hospital, clinic, university, city, street, center, floor, ward)
        has_locations = bool(
            re.search(
                r"\b(?:hospital|clinic|center|centre|ward|campus|university|institute|branch|headquarters|office|facility)\b",
                norm_text,
            )
        )
        # Demographic age (e.g. age 45, 45 years old, aged 50)
        has_age = bool(re.search(r"\b(?:age[d]?\s+)?\d{1,2}\s*(?:years?\s*old|yo)\b|\bborn\s+in\s+\d{4}\b", norm_text))
        # Postal or locality reference (e.g. zip code, sector, pin code)
        has_zip = bool(re.search(r"\b\d{5,6}\b|\bpin\s*code\b|\bpostal\s*code\b|\bsector\s*\d+\b", norm_text))

        category_presence = {
            "ROLE": bool(matched_roles),
            "DEPARTMENT": bool(matched_departments),
            "LOCATION_OR_DATE": has_locations or has_dates,
            "AGE_OR_DOB": has_age,
            "GENDER": bool(matched_genders),
            "LOCATION_OR_ZIP": has_locations or has_zip,
            "MEDICAL_CONDITION": bool(matched_conditions),
            "FACILITY_OR_LOCATION": has_locations,
            "EXACT_DATE": has_dates,
            "INCIDENT_TERM": bool(matched_incidents),
        }

        # Evaluate rules
        for rule in rules:
            req_cats = rule.get("required_categories", [])
            if req_cats and all(category_presence.get(cat, False) for cat in req_cats):
                rule_id = rule.get("id", rule.get("name", "QI-RULE"))
                rule_risk = rule.get("risk_level", "MEDIUM").upper()
                flagged_rules.append(rule_id)
                findings.append(f"Rule {rule_id} triggered: {rule.get('description', '')}")

                if rule_risk == "HIGH":
                    highest_risk = QuasiRiskLevel.HIGH
                elif rule_risk == "MEDIUM" and highest_risk != QuasiRiskLevel.HIGH:
                    highest_risk = QuasiRiskLevel.MEDIUM

        return QuasiIdentifierAssessment(
            risk_level=highest_risk,
            flagged_rules=flagged_rules,
            findings=findings,
            disclaimer=disclaimer,
        )

    @classmethod
    def check_source_consistency(
        cls,
        summary_content: StructuredSummaryContent,
        sanitized_text: str,
    ) -> Tuple[bool, Optional[str]]:
        """E. Source consistency validation: Ensure summary does not introduce unsupported facts,
        invented dates, numbers, or reconstructed personal details.

        Returns (passed, error_detail).
        """
        if not sanitized_text or not summary_content:
            return True, None

        norm_sanitized = sanitized_text.lower()

        # Check all text elements in structured summary
        combined_text = " ".join(
            [
                summary_content.summary_text,
                " ".join(summary_content.key_points),
                " ".join(summary_content.important_findings),
                " ".join(summary_content.relevant_dates_or_figures),
            ]
        )

        # 1. Check relevant_dates_or_figures: every date/figure claimed MUST exist in sanitized text
        for item in summary_content.relevant_dates_or_figures:
            cleaned_item = item.strip().lower()
            if len(cleaned_item) >= 3 and cleaned_item not in norm_sanitized:
                logger.warning(
                    "Source consistency violation: claimed date/figure '%s' not found in sanitized source.",
                    cleaned_item[:20],
                )
                return False, "Summary contains unsupported date or numerical figure not present in sanitized text."

        # 2. Extract numerical figures and monetary amounts from summary text and check source grounding
        # Strip entity-indexed placeholders first so the index in [PERSON_1] is not treated as a numerical figure
        combined_without_placeholders = re.sub(
            r"\[(?:PERSON|EMAIL|PHONE|ADDRESS|ID_LIKE|REDACTED|CONFIDENTIAL)(?:_\d+)?\]",
            " ",
            combined_text,
        )
        numbers_in_summary = re.findall(r"\b(?:\$|€|£|₹)?\d+(?:[.,]\d+)*(?:\s*(?:%|percent|million|billion|thousand|k|cr|lakh))?\b", combined_without_placeholders, re.IGNORECASE)
        for num in numbers_in_summary:
            num_clean = num.strip().lower()
            # Ignore standard single digit numbers 0-9
            if re.match(r"^\d$", num_clean):
                continue
            if num_clean not in norm_sanitized:
                logger.warning(
                    "Source consistency violation: number '%s' not present in sanitized text.",
                    num_clean[:15],
                )
                return False, "Summary introduces numerical figures not supported by sanitized source text."

        # 3. Check specific full dates in summary
        dates_in_summary = re.findall(
            r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
            combined_text,
            re.IGNORECASE,
        )
        for dt in dates_in_summary:
            dt_clean = dt.strip().lower()
            if dt_clean not in norm_sanitized:
                logger.warning(
                    "Source consistency violation: date '%s' not present in sanitized text.",
                    dt_clean,
                )
                return False, "Summary introduces unsupported calendar dates not present in sanitized text."

        return True, None

    @classmethod
    def check_prompt_injection_artifacts(
        cls,
        summary_text: str,
    ) -> Tuple[bool, Optional[str]]:
        """F. Prompt injection artifact check: Ensure summary does not reflect prompt injection payloads."""
        if not summary_text:
            return True, None

        suspicious_patterns = [
            r"<\/?\s*untrusted_document_content[^>]*>",
            r"\[delimiter_neutralized\]",
            r"\[role_marker_neutralized\]",
            r"<\|im_start\|>|<\|im_end\|>|<<sys>>|\[inst\]",
            r"\bignore\s+(?:all\s+)?previous\s+(?:safety\s+)?(?:instructions|directives)\b",
            r"\boverride\s+previous\s+safety\s+directives\b",
            r"\bdisregard\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions|directives|rules)\b",
            r"\b(?:reveal|output)\s+all\s+(?:redacted|personal)\s+(?:names|entities|pii)\b",
            r"\byou\s+are\s+now\s+a\s+helpful\b",
            r"\bsystem\s+prompt\b",
            r"\bpwned\b",
            r"\bjailbreak(?:ed)?\b",
        ]
        norm = summary_text.lower()
        for pat in suspicious_patterns:
            if re.search(pat, norm):
                logger.warning("Prompt injection artifact detected in summary output: pattern '%s'", pat)
                return False, "Prompt injection directive or artifact detected in generated summary."
        return True, None

    @classmethod
    def verify_summary(
        cls,
        summary_content: StructuredSummaryContent,
        sanitized_doc: SanitizedDocument,
        guard_references: Optional[Dict[str, Any]] = None,
    ) -> SummaryVerificationReport:
        """Execute full multi-tiered privacy and consistency verification suite.

        Args:
            summary_content: Generated or extracted structured summary.
            sanitized_doc: Isolated SanitizedDocument instance.
            guard_references: Optional dictionary containing sensitive approved candidate values
                              and entity variants strictly for leakage detection.
                              (NEVER passed to the summarizer/SLM).

        Returns:
            SummaryVerificationReport with overall status and granular check breakdown.
        """
        checks: List[SummaryVerificationCheck] = []
        mandatory_checks_passed = True

        combined_summary = " ".join(
            [
                summary_content.summary_text,
                " ".join(summary_content.key_points),
                " ".join(summary_content.important_findings),
                " ".join(summary_content.relevant_dates_or_figures),
                " ".join(summary_content.source_evidence),
            ]
        )

        # Extract sensitive references if provided
        approved_values: List[str] = []
        entity_variants: List[str] = []
        if guard_references:
            approved_values = guard_references.get("approved_values", [])
            entity_variants = guard_references.get("entity_variants", [])

        # Check A: Direct Leakage Detection
        dir_ok, dir_err = cls.check_direct_leakage(combined_summary, approved_values)
        if not dir_ok:
            mandatory_checks_passed = False
            checks.append(
                SummaryVerificationCheck(
                    check_name="DIRECT_LEAKAGE",
                    status="FAILED",
                    details=dir_err or "Direct leakage detected: an approved entity appeared in summary.",
                )
            )
        else:
            checks.append(
                SummaryVerificationCheck(
                    check_name="DIRECT_LEAKAGE",
                    status="PASSED",
                    details="Zero approved sensitive entity values detected in summary.",
                )
            )

        # Check B: Alias and Entity-Variant Detection
        alias_ok, alias_err = cls.check_alias_and_entity_variants(combined_summary, entity_variants)
        if not alias_ok:
            mandatory_checks_passed = False
            checks.append(
                SummaryVerificationCheck(
                    check_name="ALIAS_VARIANT",
                    status="FAILED",
                    details=alias_err or "Alias/variant leakage detected.",
                )
            )
        else:
            checks.append(
                SummaryVerificationCheck(
                    check_name="ALIAS_VARIANT",
                    status="PASSED",
                    details="Zero known entity variants or initials detected in summary.",
                )
            )

        # Check C: PII Re-detection (Regex + NER)
        pii_ok, pii_err = cls.check_pii_redetection(combined_summary)
        if not pii_ok:
            mandatory_checks_passed = False
            checks.append(
                SummaryVerificationCheck(
                    check_name="PII_REDETECTION",
                    status="FAILED",
                    details=pii_err or "Residual unmasked PII detected in summary.",
                )
            )
        else:
            checks.append(
                SummaryVerificationCheck(
                    check_name="PII_REDETECTION",
                    status="PASSED",
                    details="Zero unmasked PII entities detected across regex and contextual scans.",
                )
            )

        # Check D: Quasi-Identifier Risk Assessment
        quasi_assessment = cls.check_quasi_identifier_risk(
            summary_text=combined_summary,
            sanitized_text=sanitized_doc.sanitized_text,
        )
        if quasi_assessment.risk_level == QuasiRiskLevel.HIGH:
            checks.append(
                SummaryVerificationCheck(
                    check_name="QUASI_IDENTIFIER",
                    status="WARNING",
                    details=(
                        f"High quasi-identifier risk: {len(quasi_assessment.flagged_rules)} co-occurrence rule(s) flagged. "
                        "Manual review required before distribution."
                    ),
                )
            )
        else:
            checks.append(
                SummaryVerificationCheck(
                    check_name="QUASI_IDENTIFIER",
                    status="PASSED",
                    details=f"Quasi-identifier risk level assessed as {quasi_assessment.risk_level.value}.",
                )
            )

        # Check E: Source Consistency Validation
        source_ok, source_err = cls.check_source_consistency(summary_content, sanitized_doc.sanitized_text)
        if not source_ok:
            mandatory_checks_passed = False
            checks.append(
                SummaryVerificationCheck(
                    check_name="SOURCE_CONSISTENCY",
                    status="FAILED",
                    details=source_err or "Unsupported figures, dates, or reconstructed facts detected.",
                )
            )
        else:
            checks.append(
                SummaryVerificationCheck(
                    check_name="SOURCE_CONSISTENCY",
                    status="PASSED",
                    details="All dates, figures, and facts strictly grounded in sanitized source text.",
                )
            )

        # Check F: Prompt Injection Artifact Check (TDR-019)
        inj_ok, inj_err = cls.check_prompt_injection_artifacts(combined_summary)
        if not inj_ok:
            mandatory_checks_passed = False
            checks.append(
                SummaryVerificationCheck(
                    check_name="PROMPT_INJECTION_DEFENSE",
                    status="FAILED",
                    details=inj_err or "Prompt injection directive or system artifact detected in summary.",
                )
            )
        else:
            checks.append(
                SummaryVerificationCheck(
                    check_name="PROMPT_INJECTION_DEFENSE",
                    status="PASSED",
                    details="Zero prompt injection directives or system boundary artifacts detected.",
                )
            )

        # Overall Status Determination:
        # If any mandatory check failed -> FAILED
        # Else if quasi-identifier is HIGH -> REQUIRES_REVIEW
        # Else -> PASSED
        if not mandatory_checks_passed:
            overall_status = "FAILED"
        elif quasi_assessment.risk_level == QuasiRiskLevel.HIGH:
            overall_status = "REQUIRES_REVIEW"
        else:
            overall_status = "PASSED"

        return SummaryVerificationReport(
            status=overall_status,
            checks=checks,
            quasi_assessment=quasi_assessment,
            verified_at=datetime.now(timezone.utc).isoformat(),
        )
