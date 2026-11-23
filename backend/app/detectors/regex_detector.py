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
    # Landline formats with STD codes: 080-23456789, (022) 2345-6789, (080) 2345-6789
    LANDLINE_REGEX = re.compile(
        r'(?<!\d)(?:\(0\d{2,4}\)[\s.-]?|0\d{2,4}[\s.-])\d{3,4}[\s.-]?\d{3,4}(?!\d)'
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
        r'\b(?:EMP|EMPLOYEE|STAFF)[-_#]?[0-9][A-Z0-9_-]{1,9}\b',
        re.IGNORECASE
    )
    # Student IDs: STU-2024-881, STU123456
    STU_ID_REGEX = re.compile(
        r'\b(?:STU|STUDENT)[-_]?(?:[0-9]{4}[-_])?[0-9]{3,8}\b',
        re.IGNORECASE
    )
    # Account, Customer & Reference Numbers: explicit prefix with separator/digits (e.g., ACCT-904820, ACC-992014, CUST-774829, REF-2026-99481)
    # Never matches plain English words like "Account Holder" or "Account ID"
    ACC_NO_REGEX = re.compile(
        r'\b(?:(?:ACC|ACCT)[-_#]?[0-9][A-Z0-9_-]{2,14}|(?:CUST|REF|PAT|MRN)[-_#][0-9][A-Z0-9_-]{2,14})\b',
        re.IGNORECASE
    )
    # Partially masked sensitive identifiers: masked Aadhaar (XXXX-XXXX-4829) or masked SSN (XXX-XX-6789)
    MASKED_ID_REGEX = re.compile(
        r'\b(?:X{4}[-\s]X{4}[-\s]\d{4}|X{3}-X{2}-\d{4})\b',
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
    # Full street / building / plot / suite addresses with optional city, state, and postal/ZIP code tail
    STREET_ADDRESS_REGEX = re.compile(
        r'(?:(?<=\s)#\d{1,5}[A-Za-z/-]*,?[ \t]+|\b(?:(?:Flat|Apartment|Apt|Plot|House|Door|Suite|Ste|Room|Building|Unit)[ \t]*#?[0-9A-Za-z-]+,?[ \t]+|\d{1,5}[A-Za-z]?,?[ \t]+))'
        r'(?:[A-Z0-9][a-zA-Z0-9., \t\'-]{2,55}?[ \t]+)?'
        r'(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Boulevard|Blvd|Drive|Dr|Way|Place|Pl|Terrace|Court|Ct|Circle|Cir|Square|Sq|Park|Towers|Tower|Hills|Cross|Nagar|Marg|Sector(?:\s+\d+)?|Layout|Colony|Enclave|Apartments|City(?:\s+Phase\s+\d+)?)'
        r'(?:,[ \t]+(?:Apt|Suite|Ste|Unit|Fl|Floor)[ \t]*#?[0-9A-Za-z-]+)?'
        r'(?:,[ \t]+[A-Z][a-zA-Z]+(?:[ \t]+[A-Z][a-zA-Z0-9]+)*)*'
        r'(?:(?:,?[ \t]+(?:[A-Z]{2}[ \t]+)?|[ \t]*-[ \t]*)\d{5,6}(?:-\d{4})?)?\b'
    )
    # Postal code associations: Optional house/building number + Locality/Street + City/State + 5-or-6 digit PIN/ZIP
    POSTAL_PIN_REGEX = re.compile(
        r'(?:(?<=\s)#\d{1,5}[A-Za-z/-]*,[ \t]+|\b(?:(?:(?:Building|Plot|Suite|Flat|Block|Apt|Unit)[ \t]*#?[0-9A-Za-z-]+,[ \t]+)|(?:\d{1,5}[A-Za-z]?,?[ \t]+)))?'
        r'(?:[A-Z0-9][a-zA-Z0-9.\'-]+(?:[ \t]+[A-Z0-9][a-zA-Z0-9.\'-]+){0,3},[ \t]+)+'
        r'[A-Z][a-zA-Z]+(?:[ \t]+[A-Z][a-zA-Z]+)?(?:,?[ \t]+(?:[A-Z]{2}[ \t]+)?|[ \t]*-[ \t]*)(?:[1-9][0-9]{2}[ \t]?[0-9]{3}|\d{5}(?:-\d{4})?)\b'
    )
    # Known Indian locality / city pairs (with optional trailing 6-digit PIN)
    LOCALITY_CITY_REGEX = re.compile(
        r'\b(?:Koramangala|Indiranagar|Whitefield|Connaught Place|Bandra|Andheri|HSR Layout|Salt Lake|Jayanagar|Hadapsar|Kothrud),[ \t]*(?:Bangalore|Bengaluru|New Delhi|Delhi|Mumbai|Kolkata|Chennai|Hyderabad|Pune)(?:,?[ \t]+[1-9][0-9]{5})?\b',
        re.IGNORECASE
    )

    # -------------------------------------------------------------------------
    # 5. PERSON (Honorifics, Signatures, Initial Variants)
    # -------------------------------------------------------------------------
    ORG_SUFFIX_STOPWORDS = {
        "Systems", "Corp", "Corporation", "Inc", "Ltd", "Limited", "LLC", "LLP",
        "Group", "Solutions", "Services", "Technologies", "Enterprises", "Bank",
        "Agency", "University", "Hospital", "Institute", "Academy", "Lab", "Labs",
        "Center", "Centre", "Desk", "Committee", "Department", "Name", "Department",
        "Status", "Active", "Pending", "Ops", "Advisory",
    }

    # Header & signature patterns (requires word boundary on label; supports D'Artagnan, O'Brien, Jean-Luc, MacLeod)
    HEADER_PERSON_REGEX = re.compile(
        r'\b(?:(?i:Patient|Client|Employee|Candidate|Applicant|Customer|Name|Doctor|Beneficiary|Primary liaison|Trial coordinator|Account Holder|Secondary Signer|Lead Analyst|Co-Investigator|Property Manager|Facility Manager)[ \t]*:[ \t]*\n?[ \t]*|(?i:Regards|Sincerely|Signed by|Evaluated by|Approved by|Attested by)[: \t,]+\n?[ \t]*)'
        r'((?:(?:Dr\.|Mr\.|Mrs\.|Ms\.|Prof\.) )?(?:[A-Z]\. ?){0,2}[A-Z][a-z]*(?:[\'-][A-Z][a-z]+|[A-Z][a-z]+|[a-z]+)(?: [A-Z][a-z]*(?:[\'-][A-Z][a-z]+|[A-Z][a-z]+|[a-z]+)){0,2})\b'
    )
    # Title-based names: includes the honorific prefix (e.g. "Dr. Aris Thorne", "Dr. Jean-Luc Picard", "Prof. Siobhan O'Brien")
    TITLE_PERSON_REGEX = re.compile(
        r'\b(?:Dr\.|Mr\.|Mrs\.|Ms\.|Prof\.) [A-Z][a-z]*(?:[\'-][A-Z][a-z]+|[A-Z][a-z]+|[a-z]+)(?: [A-Z][a-z]*(?:[\'-][A-Z][a-z]+|[A-Z][a-z]+|[a-z]+)){0,2}\b'
    )
    # Initial-based names: R. Sharma, J. K. Rowling, S. K. Narayanan
    INITIAL_PERSON_REGEX = re.compile(
        r'\b(?:[A-Z]\. ?){1,3}[A-Z][a-z]*(?:[\'-][A-Z][a-z]+|[A-Z][a-z]+|[a-z]+)(?: [A-Z][a-z]+)?\b'
    )
    # Middle initial names: John H. Watson, Mary E. Jones
    MIDDLE_INITIAL_REGEX = re.compile(
        r'\b[A-Z][a-z]+ (?:[A-Z]\. )+[A-Z][a-z]+(?:[\'-]?[A-Z][a-z]+)?\b'
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

        def add_candidate(
            start: int,
            end: int,
            matched_text: str,
            pii_type: str,
            confidence: float,
            explanation: str = "",
            context_signal: str = "",
        ):
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
                    confidence_type="HEURISTIC_EVIDENCE",
                    sources=[cls.DETECTOR_NAME],
                    explanation=[explanation] if explanation else [f"Matched deterministic {pii_type} pattern"],
                    context_signals=[context_signal] if context_signal else [],
                    review_status="PENDING",
                )
            )

        # 1. Emails (Standard & Obfuscated)
        for match in cls.STANDARD_EMAIL_REGEX.finditer(text):
            add_candidate(
                match.start(), match.end(), match.group(), PIICategory.EMAIL.value, 0.96,
                explanation="Matched standard RFC-5322 email pattern",
                context_signal="email_format",
            )

        for match in cls.OBFUSCATED_EMAIL_REGEX.finditer(text):
            add_candidate(
                match.start(), match.end(), match.group(), PIICategory.EMAIL.value, 0.88,
                explanation="Matched obfuscated email pattern ([at]/[dot])",
                context_signal="obfuscated_email_format",
            )

        # 2. Phones (Indian Mobile, International, Landline)
        phone_matches: List[Tuple[int, int, str, str]] = []
        for match in cls.INDIAN_MOBILE_REGEX.finditer(text):
            raw = match.group().strip()
            if not cls.DATE_FILTER_REGEX.match(raw):
                digits = re.sub(r'\D', '', raw)
                if len(digits) >= 10:
                    phone_matches.append((match.start(), match.end(), raw, "Matched Indian mobile telephone pattern"))

        for match in cls.INTL_PHONE_REGEX.finditer(text):
            raw = match.group().strip()
            if not cls.DATE_FILTER_REGEX.match(raw):
                digits = re.sub(r'\D', '', raw)
                if len(digits) >= 9:
                    phone_matches.append((match.start(), match.end(), raw, "Matched international country-code telephone pattern"))

        for match in cls.LANDLINE_REGEX.finditer(text):
            raw = match.group().strip()
            if not cls.DATE_FILTER_REGEX.match(raw):
                digits = re.sub(r'\D', '', raw)
                if len(digits) >= 8:
                    phone_matches.append((match.start(), match.end(), raw, "Matched STD landline telephone pattern"))

        for start, end, matched, reason in phone_matches:
            add_candidate(
                start, end, matched, PIICategory.PHONE.value, 0.92,
                explanation=reason,
                context_signal="telephone_digits",
            )

        # 3. ID-Like Strings (PAN, Aadhaar, SSN, EMP, STU, ACC)
        for match in cls.PAN_CARD_REGEX.finditer(text):
            add_candidate(
                match.start(), match.end(), match.group(), PIICategory.ID_LIKE.value, 0.95,
                explanation="Matched 10-character Indian PAN tax identifier pattern",
                context_signal="pan_format",
            )

        for match in cls.AADHAAR_REGEX.finditer(text):
            add_candidate(
                match.start(), match.end(), match.group(), PIICategory.ID_LIKE.value, 0.94,
                explanation="Matched 12-digit Aadhaar identifier pattern",
                context_signal="aadhaar_format",
            )

        for match in cls.SSN_REGEX.finditer(text):
            add_candidate(
                match.start(), match.end(), match.group(), PIICategory.ID_LIKE.value, 0.95,
                explanation="Matched US Social Security Number (SSN) pattern",
                context_signal="ssn_format",
            )

        for match in cls.EMP_ID_REGEX.finditer(text):
            add_candidate(
                match.start(), match.end(), match.group(), PIICategory.ID_LIKE.value, 0.90,
                explanation="Matched employee badge/staff identifier pattern",
                context_signal="employee_id_prefix",
            )

        for match in cls.STU_ID_REGEX.finditer(text):
            add_candidate(
                match.start(), match.end(), match.group(), PIICategory.ID_LIKE.value, 0.90,
                explanation="Matched student enrollment identifier pattern",
                context_signal="student_id_prefix",
            )

        for match in cls.ACC_NO_REGEX.finditer(text):
            add_candidate(
                match.start(), match.end(), match.group(), PIICategory.ID_LIKE.value, 0.88,
                explanation="Matched financial/billing/reference account identifier pattern",
                context_signal="account_id_prefix",
            )

        for match in cls.MASKED_ID_REGEX.finditer(text):
            add_candidate(
                match.start(), match.end(), match.group(), PIICategory.ID_LIKE.value, 0.86,
                explanation="Matched partially masked national/tax identifier pattern",
                context_signal="masked_id_format",
            )

        # 4. Addresses
        for match in cls.STREET_ADDRESS_REGEX.finditer(text):
            add_candidate(
                match.start(), match.end(), match.group(), PIICategory.ADDRESS.value, 0.86,
                explanation="Matched street/building/suite address grammar",
                context_signal="street_address_structure",
            )

        for match in cls.POSTAL_PIN_REGEX.finditer(text):
            add_candidate(
                match.start(), match.end(), match.group(), PIICategory.ADDRESS.value, 0.88,
                explanation="Matched locality, city, and postal/ZIP code sequence",
                context_signal="postal_code_anchor",
            )

        for match in cls.LOCALITY_CITY_REGEX.finditer(text):
            add_candidate(
                match.start(), match.end(), match.group(), PIICategory.ADDRESS.value, 0.85,
                explanation="Matched known locality and city pair",
                context_signal="locality_city_pair",
            )

        # 5. Person Name Patterns
        for match in cls.HEADER_PERSON_REGEX.finditer(text):
            name_str = match.group(1).strip()
            if any(w in cls.ORG_SUFFIX_STOPWORDS for w in name_str.split()):
                continue
            grp_start = match.start(1)
            grp_end = grp_start + len(name_str)
            add_candidate(
                grp_start, grp_end, name_str, PIICategory.PERSON.value, 0.88,
                explanation="Matched person name anchored by role/signature header label",
                context_signal="header_or_signature_anchor",
            )

        for match in cls.TITLE_PERSON_REGEX.finditer(text):
            name_str = match.group(0).strip()
            if any(w in cls.ORG_SUFFIX_STOPWORDS for w in name_str.split()):
                continue
            grp_start = match.start(0)
            grp_end = grp_start + len(name_str)
            add_candidate(
                grp_start, grp_end, name_str, PIICategory.PERSON.value, 0.89,
                explanation="Matched honorific title and person name pattern",
                context_signal="honorific_title",
            )

        for match in cls.INITIAL_PERSON_REGEX.finditer(text):
            cand_str = match.group().strip()
            if len(cand_str.replace('.', '').replace(' ', '')) >= 3:
                add_candidate(
                    match.start(), match.end(), cand_str, PIICategory.PERSON.value, 0.82,
                    explanation="Matched initial-prefixed person name pattern",
                    context_signal="initial_surname_pattern",
                )

        for match in cls.MIDDLE_INITIAL_REGEX.finditer(text):
            add_candidate(
                match.start(), match.end(), match.group().strip(), PIICategory.PERSON.value, 0.86,
                explanation="Matched given-name, middle-initial, and surname pattern",
                context_signal="middle_initial_pattern",
            )

        return candidates
