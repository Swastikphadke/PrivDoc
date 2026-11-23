"""Deterministic Regex-based PII Detector for PrivyDoc.

Detects structured PII entities with high precision and low false positives:
- EMAIL (standard RFC formats and obfuscated variants)
- PHONE (Indian mobile, international formats, landlines, separators)
- ID_LIKE (employee, student, account IDs, PAN, Aadhaar, SSN)
- ADDRESS (street addresses, localities, postal codes)
- PERSON (honorifics, header/signature contexts, initial-based name variants)
"""

import re
from typing import List, Tuple
from app.schemas.candidate import Candidate, ConfidenceBand, PIICategory


class RegexDetector:
    """Deterministic regex detector for structured PII categories."""

    DETECTOR_NAME = "regex"

    # -------------------------------------------------------------------------
    # 1. EMAIL Patterns
    # -------------------------------------------------------------------------
    STANDARD_EMAIL_REGEX = re.compile(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
    )
    # Obfuscated: user [at] example [dot] com, user (at) domain (dot) net, user at domain dot com
    OBFUSCATED_EMAIL_REGEX = re.compile(
        r'\b([A-Za-z0-9._%+-]+)\s*(?:\[\s*at\s*\]|\(\s*at\s*\)|\bat\b)\s*([A-Za-z0-9.-]+)\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\bdot\b)\s*([A-Za-z]{2,})\b',
        re.IGNORECASE
    )

    # -------------------------------------------------------------------------
    # 2. PHONE Patterns
    # -------------------------------------------------------------------------
    # Indian mobile: starting with 6,7,8,9 with optional +91, 91, or 0
    INDIAN_MOBILE_REGEX = re.compile(
        r'(?<!\d)(?:(?:\+?91[\s.-]?|0)?[6-9]\d{4}[\s.-]?\d{5})(?!\d)'
    )
    # International phone with explicit country code (+1-800-555-0199, +44 20 7946 0958)
    INTL_PHONE_REGEX = re.compile(
        r'(?<!\d)\+(?:[1-9]\d{0,2})[\s.-]?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}(?!\d)'
    )
    # Landline formats with STD codes: 080-23456789, (022) 2345-6789
    LANDLINE_REGEX = re.compile(
        r'(?<!\d)(?:\(?0\d{2,4}\)?[\s.-]?)\d{6,8}(?!\d)'
    )
    # False positive date patterns: YYYY-MM-DD, DD-MM-YYYY, YYYY/MM/DD
    DATE_FILTER_REGEX = re.compile(
        r'^(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}$|^\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}$'
    )

    # -------------------------------------------------------------------------
    # 3. ID_LIKE Patterns
    # -------------------------------------------------------------------------
    # Employee IDs: EMP-10294, EMP_9921, STAFF_881
    EMP_ID_REGEX = re.compile(
        r'\b(?:EMP|EMPLOYEE|STAFF)[-_#]?[A-Z0-9]{3,10}\b',
        re.IGNORECASE
    )
    # Student IDs: STU-2024-881, STU123456
    STU_ID_REGEX = re.compile(
        r'\b(?:STU|STUDENT)[-_]?(?:[0-9]{4}[-_])?[0-9]{3,8}\b',
        re.IGNORECASE
    )
    # Account Numbers with explicit keywords: ACC-992014, ACCT: 44910283, ACC-88291
    ACC_NO_REGEX = re.compile(
        r'\b(?:ACC|ACCT|ACCOUNT)[-_#:\s]*([A-Z0-9]{4,16})\b',
        re.IGNORECASE
    )
    # Indian PAN card: 5 letters, 4 digits, 1 letter
    PAN_CARD_REGEX = re.compile(
        r'\b[A-Z]{5}[0-9]{4}[A-Z]\b'
    )
    # Indian Aadhaar: 12 digits, format XXXX XXXX XXXX (cannot start with 0 or 1)
    AADHAAR_REGEX = re.compile(
        r'\b[2-9]\d{3}\s\d{4}\s\d{4}\b'
    )
    # US Social Security Number: XXX-XX-XXXX
    SSN_REGEX = re.compile(
        r'\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b'
    )

    # -------------------------------------------------------------------------
    # 4. ADDRESS Patterns
    # -------------------------------------------------------------------------
    # Street addresses with house/flat numbers and street identifiers
    STREET_ADDRESS_REGEX = re.compile(
        r'\b(?:Flat|Apartment|Plot|House|Door|Suite|Room|Building)?\s*#?\d{1,4}[A-Za-z]?,?\s+(?:[A-Z][a-zA-Z0-9\s.-]+?)\s+(?:Street|St|Road|Rd|Avenue|Ave|Lane|Boulevard|Blvd|Drive|Dr|Nagar|Marg|Sector|Layout|Colony|Enclave|Apartments|Tower)\b',
        re.IGNORECASE
    )
    # Postal code associations: City/State + 6-digit Indian PIN (e.g. Bangalore, Karnataka 560001)
    POSTAL_PIN_REGEX = re.compile(
        r'\b(?:[A-Z][a-zA-Z]+(?:[\s,]+[A-Z][a-zA-Z]+)?)[,\s]+[1-9][0-9]{2}\s?[0-9]{3}\b'
    )
    # Known Indian locality / city pairs
    LOCALITY_CITY_REGEX = re.compile(
        r'\b(?:Koramangala|Indiranagar|Whitefield|Connaught Place|Bandra|Andheri|HSR Layout|Salt Lake|Jayanagar|Hadapsar|Kothrud),\s*(?:Bangalore|Bengaluru|New Delhi|Delhi|Mumbai|Kolkata|Chennai|Hyderabad|Pune)\b',
        re.IGNORECASE
    )

    # -------------------------------------------------------------------------
    # 5. PERSON (Honorifics, Signatures, Initial Variants)
    # -------------------------------------------------------------------------
    # Header & signature patterns: Patient: John Doe, Regards,\nDr. Suresh Menon
    HEADER_PERSON_REGEX = re.compile(
        r'(?i:Patient|Client|Employee|Candidate|Applicant|Customer|Name|Subject|Regards|Sincerely|Signed by|Evaluated by|Doctor|Approved by)[:\s,]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b'
    )
    # Title-based names: Dr. Richa Sharma, Mr. John Doe, Prof. Alice Smith
    TITLE_PERSON_REGEX = re.compile(
        r'\b(?:Dr\.|Mr\.|Mrs\.|Ms\.|Prof\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b'
    )
    # Initial-based names: R. Sharma, J. K. Rowling, A. P. J. Abdul Kalam
    INITIAL_PERSON_REGEX = re.compile(
        r'\b(?:[A-Z]\.\s*){1,3}[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b'
    )
    # Middle initial names: John H. Watson, Mary E. Jones
    MIDDLE_INITIAL_REGEX = re.compile(
        r'\b[A-Z][a-z]+\s+(?:[A-Z]\.\s*)+[A-Z][a-z]+\b'
    )

    PATTERNS = {
        "STANDARD_EMAIL": STANDARD_EMAIL_REGEX,
        "OBFUSCATED_EMAIL": OBFUSCATED_EMAIL_REGEX,
        "INDIAN_MOBILE": INDIAN_MOBILE_REGEX,
        "INTL_PHONE": INTL_PHONE_REGEX,
        "LANDLINE": LANDLINE_REGEX,
        "EMP_ID": EMP_ID_REGEX,
        "STU_ID": STU_ID_REGEX,
        "ACC_NO": ACC_NO_REGEX,
        "PAN_CARD": PAN_CARD_REGEX,
        "AADHAAR": AADHAAR_REGEX,
        "SSN": SSN_REGEX,
        "STREET_ADDRESS": STREET_ADDRESS_REGEX,
        "POSTAL_PIN": POSTAL_PIN_REGEX,
        "LOCALITY_CITY": LOCALITY_CITY_REGEX,
        "HEADER_PERSON": HEADER_PERSON_REGEX,
        "TITLE_PERSON": TITLE_PERSON_REGEX,
        "INITIAL_PERSON": INITIAL_PERSON_REGEX,
        "MIDDLE_INITIAL": MIDDLE_INITIAL_REGEX,
    }

    @classmethod
    def detect(cls, text: str, document_id: str = "doc_temp") -> List[Candidate]:
        """Run all deterministic regex detectors over canonical text.

        Args:
            text: Canonical extracted text.
            document_id: Associated document session ID.

        Returns:
            List of Candidate objects.
        """
        candidates: List[Candidate] = []
        cand_idx = 0

        def add_candidate(start: int, end: int, matched_text: str, pii_type: str, confidence: float):
            nonlocal cand_idx
            cand_idx += 1
            band = (
                ConfidenceBand.HIGH.value
                if confidence >= 0.85
                else ConfidenceBand.MEDIUM.value
                if confidence >= 0.60
                else ConfidenceBand.LOW.value
            )
            candidates.append(
                Candidate(
                    candidate_id=f"c_reg_{cand_idx:04d}",
                    document_id=document_id,
                    start=start,
                    end=end,
                    text=matched_text,
                    type=pii_type,
                    confidence=round(confidence, 2),
                    confidence_band=band,
                    sources=[cls.DETECTOR_NAME],
                    review_status="PENDING",
                )
            )

        # 1. Emails (Standard & Obfuscated)
        for match in cls.STANDARD_EMAIL_REGEX.finditer(text):
            add_candidate(match.start(), match.end(), match.group(), PIICategory.EMAIL.value, 0.96)

        for match in cls.OBFUSCATED_EMAIL_REGEX.finditer(text):
            add_candidate(match.start(), match.end(), match.group(), PIICategory.EMAIL.value, 0.88)

        # 2. Phones (Indian Mobile, International, Landline)
        phone_matches: List[Tuple[int, int, str]] = []
        for match in cls.INDIAN_MOBILE_REGEX.finditer(text):
            raw = match.group().strip()
            # Verify not a date or false positive
            if not cls.DATE_FILTER_REGEX.match(raw):
                digits = re.sub(r'\D', '', raw)
                if len(digits) >= 10:
                    phone_matches.append((match.start(), match.end(), raw))

        for match in cls.INTL_PHONE_REGEX.finditer(text):
            raw = match.group().strip()
            if not cls.DATE_FILTER_REGEX.match(raw):
                digits = re.sub(r'\D', '', raw)
                if len(digits) >= 9:
                    phone_matches.append((match.start(), match.end(), raw))

        for match in cls.LANDLINE_REGEX.finditer(text):
            raw = match.group().strip()
            if not cls.DATE_FILTER_REGEX.match(raw):
                digits = re.sub(r'\D', '', raw)
                if len(digits) >= 8:
                    phone_matches.append((match.start(), match.end(), raw))

        for start, end, matched in phone_matches:
            add_candidate(start, end, matched, PIICategory.PHONE.value, 0.92)

        # 3. ID-Like Strings (PAN, Aadhaar, SSN, EMP, STU, ACC)
        for match in cls.PAN_CARD_REGEX.finditer(text):
            add_candidate(match.start(), match.end(), match.group(), PIICategory.ID_LIKE.value, 0.95)

        for match in cls.AADHAAR_REGEX.finditer(text):
            add_candidate(match.start(), match.end(), match.group(), PIICategory.ID_LIKE.value, 0.94)

        for match in cls.SSN_REGEX.finditer(text):
            add_candidate(match.start(), match.end(), match.group(), PIICategory.ID_LIKE.value, 0.95)

        for match in cls.EMP_ID_REGEX.finditer(text):
            add_candidate(match.start(), match.end(), match.group(), PIICategory.ID_LIKE.value, 0.90)

        for match in cls.STU_ID_REGEX.finditer(text):
            add_candidate(match.start(), match.end(), match.group(), PIICategory.ID_LIKE.value, 0.90)

        for match in cls.ACC_NO_REGEX.finditer(text):
            add_candidate(match.start(), match.end(), match.group(), PIICategory.ID_LIKE.value, 0.88)

        # 4. Addresses
        for match in cls.STREET_ADDRESS_REGEX.finditer(text):
            add_candidate(match.start(), match.end(), match.group(), PIICategory.ADDRESS.value, 0.86)

        for match in cls.POSTAL_PIN_REGEX.finditer(text):
            add_candidate(match.start(), match.end(), match.group(), PIICategory.ADDRESS.value, 0.88)

        for match in cls.LOCALITY_CITY_REGEX.finditer(text):
            add_candidate(match.start(), match.end(), match.group(), PIICategory.ADDRESS.value, 0.85)

        # 5. Person Name Patterns
        for match in cls.HEADER_PERSON_REGEX.finditer(text):
            # Capture group 1 has the name
            name_str = match.group(1).strip()
            # Calculate offset of group 1
            grp_start = match.start(1)
            grp_end = grp_start + len(name_str)
            add_candidate(grp_start, grp_end, name_str, PIICategory.PERSON.value, 0.88)

        for match in cls.TITLE_PERSON_REGEX.finditer(text):
            name_str = match.group(1).strip()
            grp_start = match.start(1)
            grp_end = grp_start + len(name_str)
            add_candidate(grp_start, grp_end, name_str, PIICategory.PERSON.value, 0.89)

        for match in cls.INITIAL_PERSON_REGEX.finditer(text):
            # Avoid single letters at sentence start
            cand_str = match.group().strip()
            if len(cand_str.replace('.', '').replace(' ', '')) >= 3:
                add_candidate(match.start(), match.end(), cand_str, PIICategory.PERSON.value, 0.82)

        for match in cls.MIDDLE_INITIAL_REGEX.finditer(text):
            add_candidate(match.start(), match.end(), match.group().strip(), PIICategory.PERSON.value, 0.86)

        return candidates
