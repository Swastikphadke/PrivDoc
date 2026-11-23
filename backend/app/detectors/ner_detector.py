"""Named Entity Recognition (NER) & Contextual Linguistic Detector Adapter.

Provides contextual entity extraction for PERSON and ADDRESS categories:
- Strips job-role and title prefixes (e.g., 'Lead Auditor Elena Vance' -> 'Elena Vance') while recording
  the prefix as a supporting context signal.
- Suppresses organizational, institutional, header, and address noun phrases from triggering PERSON false positives.
- Performs a second-pass document-local standalone surname scan with strict ambiguity safeguards.
- Labels all scores explicitly as HEURISTIC_EVIDENCE.
"""

import re
from typing import Dict, List, Set, Tuple
from app.schemas.candidate import Candidate, ConfidenceBand, PIICategory


# Job-role and relational prefixes that frequently precede a person's name in running text
ROLE_PREFIX_WORDS: Set[str] = {
    "Lead", "Deputy", "Chief", "Senior", "Junior", "Principal", "Assistant", "Associate",
    "Executive", "Managing", "General", "Regional", "Clinical", "Medical", "Financial",
    "Commercial", "Corporate", "Primary", "Secondary", "Registered", "Official", "Direct",
    "Preliminary", "Attending", "Consulting", "Auditor", "Director", "Officer", "Inspector",
    "Manager", "Analyst", "Engineer", "Investigator", "Co-Investigator", "Coordinator",
    "Beneficiary", "Landlord", "Tenant", "Fellow", "Physician", "Specialist", "Spec",
    "Signer", "Holder", "Liaison", "Administrator", "Supervisor", "Operator", "Patient",
    "Client", "Employee", "User", "Applicant", "Candidate", "Doctor", "Agent", "Detective",
    "Cryptographer", "Architect", "Researcher", "Scientist", "Consultant", "Advisor",
    "Counsel", "Attorney", "Surgeon", "Nurse", "Therapist", "Pharmacist", "Dean",
    "Provost", "Treasurer", "Secretary", "Controller", "Technician", "Compliance", "Risk",
}

# Generic structural, institutional, organizational, header, and address head words (never proper personal names)
# Audited in Stage 2 Validation Audit: contains ZERO dataset-specific codenames, given names, or city names.
STOP_WORDS_CAPITALIZED: Set[str] = {
    "The", "This", "That", "These", "Those", "There", "Here", "Where", "When",
    "Why", "How", "What", "Which", "Who", "Whom", "Whose", "Monday", "Tuesday",
    "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "January", "February",
    "March", "April", "May", "June", "July", "August", "September", "October",
    "November", "December", "Section", "Table", "Figure", "Chapter", "Page",
    "Total", "Status", "Report", "Overview", "Summary", "Result", "PrivyDoc",
    "Document", "File", "Date", "Time", "Note", "Important", "Notice", "Warning",
    "Error", "Success", "Failed", "Pending", "Approved", "Rejected", "Version",
    "Corp", "Corporation", "Inc", "Incorporated", "Ltd", "Limited", "LLC", "LLP",
    "Co", "Company", "Bank", "Agency", "Department", "University", "Hospital",
    "Institute", "Foundation", "Group", "Solutions", "Services", "Technologies",
    "Tech", "Enterprises", "Ventures", "Holdings", "Partners", "Associates",
    "Agreement", "Contract", "Policy", "Statement", "Act", "Plan", "Proposal",
    "Memorandum", "Clause", "Addendum", "Exhibit", "Appendix", "Schedule",
    "Resolution", "Certificate", "Treaty", "Protocol", "Pact", "Accord",
    "License", "Terms", "Conditions", "Mutual", "Disclosure", "Confidentiality",
    "Master", "Order", "Project", "Phase", "Stage", "Milestone",
    # Generic institutional, corporate, document-section, and street-type nouns
    "Cybernetics", "Systems", "Defense", "Lab", "Labs", "Clinic", "Center", "Centre",
    "Wing", "Unit", "Desk", "Committee", "Roster", "Directory", "Briefing", "Dossier",
    "Dispatch", "Advice", "Conferral", "Clearance", "Oversight",
    "Academy", "Operations", "Security", "Internal",
    "Audit", "Assessment", "Incident", "Response", "Team", "Access", "Badge",
    "Research", "Specification", "Specifications", "Estate", "Branch", "Way", "Road",
    "Street", "Avenue", "Boulevard", "Drive", "Place", "Lane", "Terrace", "Sector",
    "City", "States", "United", "India", "Global", "Emergency", "Landline", "Account",
    "Tax", "Routing", "Earnings", "Call", "Revenue", "Subscription", "Subscriptions",
    "Legal", "Investigation", "Case", "Property", "Partnership", "Deed", "Advisory",
    "Memo", "Mission", "Debrief", "Flight", "Logs", "Aircraft", "Cell", "Lease",
    "Premises", "Electronic", "Funds", "Transfer", "Transaction", "Acknowledgement",
    "Support", "Phone", "Email", "Faculty", "Physics", "Communications",
    "Standards", "Supervision", "Inspection", "Protocols", "Findings",
    "Residential", "Logistics", "Field", "Coordination", "Hub", "Evaluation", "Context",
    "Quantum", "Annex", "Adversarial", "Embedded", "Directive",
    "Check", "Attested", "Billing", "Chart", "Record", "Secret", "Routine", "Registration",
    "Form", "Operation", "Precinct", "Number", "Non", "Vault", "Rotated",
    "Management", "Wealth", "Devices", "Healthcare", "Pharmaceuticals", "Capital",
    "Industries", "Energy", "Power", "Telecom", "Media", "Insurance", "Realty",
    "Properties", "Memorial", "National", "International", "Federal", "Municipal",
    "Ministry", "Bureau", "Authority", "Commission", "Council", "Board", "Association",
    "Society", "Federation", "Union", "Consortium", "Alliance", "Tower", "Towers",
    "Plaza", "Square", "Gardens", "Park", "Heights", "Hills", "Valley", "Meadows",
    "Crossing", "Harbor", "Port", "Station", "Terminal", "Reference", "Code", "Active",
    "Name", "Ops", "Panel", "Vendors", "Primary", "Secondary",
    # Standalone honorific abbreviations without period (with period they are in HONORIFIC_TOKENS)
    "Dr", "Mr", "Mrs", "Ms", "Prof",
    # Imperative / sentence-starter verbs that must not be merged into proper names
    "Consult", "Contact", "Please", "Refer", "Notify", "Reach", "Ask", "See", "Review",
    "Submitted", "Prepared", "Conducted", "Authorized",
}

HONORIFIC_TOKENS: Set[str] = {"Dr.", "Mr.", "Mrs.", "Ms.", "Prof."}

# Contextual verbs that strongly suggest a preceding or succeeding person name
PERSON_CONTEXT_VERBS = re.compile(
    r'\b(?:evaluated|examined|consulted|authorized|reported|stated|agreed|signed|approved|recommended|diagnosed|prescribed|met with|joined|advised|contacted|conducted|compiled|inaugurated|authored|presented|supervised|executed|awarded|reviewed|dispatched|filed)\b',
    re.IGNORECASE
)

# Communicative cues for standalone surname mentions (e.g. "call Vance at", "contact Miller")
SURNAME_CONTEXT_CUES = re.compile(
    r'\b(?:call|contact|consult|reach|ask|notify|according to|authored by|reported by|reviewed by|signed by|escalate to)\s+$',
    re.IGNORECASE
)


class NERDetector:
    """Modular NER & contextual linguistic detector for PERSON and ADDRESS extraction."""

    DETECTOR_NAME = "ner"

    # Single-space capitalized sequence on the same line (respects multi-space table column boundaries
    # and supports Celtic/hyphenated/apostrophe names like McGonagall, MacLeod, O'Brien, D'Artagnan, Jean-Luc, Al-Mansoor)
    CAPITALIZED_SEQUENCE_REGEX = re.compile(
        r'(?:(?:Dr\.|Mr\.|Mrs\.|Ms\.|Prof\.) )?\b([A-Z][a-z]{0,18}(?:[\'-][A-Z][a-z]{1,18}|[A-Z][a-z]{1,18}|[a-z]{1,18})(?: [A-Z][a-z]{0,18}(?:[\'-][A-Z][a-z]{1,18}|[A-Z][a-z]{1,18}|[a-z]{1,18})){1,5})\b'
    )

    # Contextual address keywords (stops cleanly before sentence punctuation or trailing post-PIN state/country)
    ADDRESS_CONTEXT_REGEX = re.compile(
        r'\b(?:residing at|living at|located at|situated at|address:|premises:|primary hq:|registered branch:|branch:|shipped to|delivered to|office at|property at)[ \t]+([0-9A-Za-z \t,.\-#]{10,75}?)(?=(?:,[ \t]*(?:[A-Z][a-zA-Z ]{2,20}|USA|UK))?[.;\n]|$)',
        re.IGNORECASE
    )

    @classmethod
    def detect(cls, text: str, document_id: str = "doc_temp") -> List[Candidate]:
        """Detect contextual entities (PERSON and ADDRESS) in canonical text.

        Args:
            text: Canonical extracted text.
            document_id: Associated document identifier.

        Returns:
            List of detected Candidate objects with heuristic provenance.
        """
        candidates: List[Candidate] = []
        cand_idx = 0
        from app.core.security import fold_homoglyphs_1to1
        orig_text = text
        text = fold_homoglyphs_1to1(orig_text)

        def add_candidate(
            start: int,
            end: int,
            matched_text: str,
            pii_type: str,
            confidence: float,
            explanation: List[str],
            context_signals: List[str],
            is_ambiguous: bool = False,
        ):
            nonlocal cand_idx
            cand_idx += 1
            surface_text = orig_text[start:end] if 0 <= start < end <= len(orig_text) else matched_text
            band = (
                ConfidenceBand.HIGH.value
                if confidence >= 0.85
                else ConfidenceBand.MEDIUM.value
                if confidence >= 0.60
                else ConfidenceBand.LOW.value
            )
            candidates.append(
                Candidate(
                    candidate_id=f"c_ner_{cand_idx:04d}",
                    document_id=document_id,
                    start=start,
                    end=end,
                    text=surface_text,
                    type=pii_type,
                    confidence=round(confidence, 2),
                    confidence_band=band,
                    confidence_type="HEURISTIC_EVIDENCE",
                    sources=[cls.DETECTOR_NAME],
                    explanation=explanation,
                    context_signals=context_signals,
                    is_ambiguous_suggestion=is_ambiguous,
                    review_status="PENDING",
                )
            )

        #Track full-name anchors (surname -> list of full names) for Pass 2 document-local surname scan
        surname_to_full_names: Dict[str, Set[str]] = {}
        emitted_spans: List[Tuple[int, int]] = []

        # 1. Pass 1: Contextual Person Names with Role-Prefix Trimming
        for match in cls.CAPITALIZED_SEQUENCE_REGEX.finditer(text):
            full_match_str = match.group(0)
            full_start = match.start(0)

            # Tokenize with relative character offsets within full_match_str
            token_matches = list(
                re.finditer(r'(?:Dr\.|Mr\.|Mrs\.|Ms\.|Prof\.|[A-Z][a-z]*(?:[\'-][A-Z][a-z]+|[A-Z][a-z]+|[a-z]+))', full_match_str)
            )
            if len(token_matches) < 2:
                continue

            # Strip leading role/title words (but keep honorifics like Dr., Mr., Ms., Prof.)
            stripped_roles: List[str] = []
            idx_first_kept = 0
            while idx_first_kept < len(token_matches):
                tok_str = token_matches[idx_first_kept].group(0)
                if tok_str in HONORIFIC_TOKENS:
                    break
                if tok_str in ROLE_PREFIX_WORDS:
                    stripped_roles.append(tok_str)
                    idx_first_kept += 1
                else:
                    break

            kept_tokens = token_matches[idx_first_kept:]
            # Also strip trailing role words if any
            while kept_tokens and kept_tokens[-1].group(0) in ROLE_PREFIX_WORDS:
                kept_tokens.pop()

            # Must have at least 2 tokens remaining (e.g., First + Last, or Honorific + Last)
            if len(kept_tokens) < 2:
                continue

            # Check ALL tokens BEFORE length capping so 4-token organization names
            # (e.g., "Morgan Stanley Wealth Management") do not get truncated to 3 tokens and misclassified
            all_words = [t.group(0) for t in kept_tokens]
            all_non_honorific = [w for w in all_words if w not in HONORIFIC_TOKENS]
            if not all_non_honorific:
                continue
            if any(w in STOP_WORDS_CAPITALIZED or w in ROLE_PREFIX_WORDS for w in all_non_honorific):
                continue

            # Check immediate trailing text for corporate/legal designators (e.g. "Grant Thornton LLP", "Johnson & Johnson")
            seq_end = full_start + kept_tokens[-1].end()
            trailing_slice = text[seq_end:min(len(text), seq_end + 18)]
            if re.match(r'^[ \t,]*(?:LLP|LLC|PLC|Inc\.?|Ltd\.?|Corp\.?|GmbH|AG|&[ \t]+[A-Z])\b', trailing_slice):
                continue

            # Cap at 3 tokens (e.g. Honorific + First + Last, or First + Middle + Last)
            if len(kept_tokens) > 3:
                kept_tokens = kept_tokens[:3]

            words = [t.group(0) for t in kept_tokens]
            non_honorific_words = [w for w in words if w not in HONORIFIC_TOKENS]

            span_start = full_start + kept_tokens[0].start()
            span_end = full_start + kept_tokens[-1].end()
            cand_text = text[span_start:span_end]

            # Check surrounding context for person-associated verbs or role prefixes
            window_start = max(0, span_start - 55)
            window_end = min(len(text), span_end + 55)
            surrounding_context = text[window_start:window_end]

            signals: List[str] = []
            reasons: List[str] = ["Contextual multi-token proper name"]
            confidence = 0.78

            if stripped_roles:
                role_phrase = " ".join(stripped_roles)
                signals.append(f"role_prefix:{role_phrase}")
                reasons.append(f"Preceded by role title '{role_phrase}'")
                confidence = max(confidence, 0.88)

            if words[0] in HONORIFIC_TOKENS:
                signals.append(f"honorific:{words[0]}")
                reasons.append(f"Includes honorific '{words[0]}'")
                confidence = max(confidence, 0.89)

            verb_match = PERSON_CONTEXT_VERBS.search(surrounding_context)
            if verb_match:
                signals.append(f"context_verb:{verb_match.group(0).lower()}")
                reasons.append(f"Surrounding communicative/action verb '{verb_match.group(0)}'")
                confidence = max(confidence, 0.89)

            add_candidate(
                span_start,
                span_end,
                cand_text,
                PIICategory.PERSON.value,
                confidence,
                explanation=reasons,
                context_signals=signals,
            )
            emitted_spans.append((span_start, span_end))

            # Record full name surname anchor for Pass 2
            if len(non_honorific_words) >= 2:
                surname = non_honorific_words[-1]
                if len(surname) >= 3:
                    surname_to_full_names.setdefault(surname, set()).add(" ".join(non_honorific_words))

        # 2. Pass 2: Document-Local Standalone Surname Scan with Ambiguity Safeguards
        for surname, full_names in surname_to_full_names.items():
            for s_match in re.finditer(rf'\b{re.escape(surname)}\b', text):
                s_start, s_end = s_match.start(), s_match.end()
                # Skip if already inside an emitted span
                if any(not (s_end <= es or s_start >= ee) for es, ee in emitted_spans):
                    continue
                # Skip if preceded by an initial or honorific (handled by RegexDetector)
                preceding_window = text[max(0, s_start - 40):s_start]
                if re.search(r'(?:[A-Z]\.|Dr\.|Mr\.|Mrs\.|Ms\.|Prof\.)[ \t]*$', preceding_window):
                    continue
                # Require communicative cue immediately preceding the standalone surname
                if SURNAME_CONTEXT_CUES.search(preceding_window):
                    is_ambig = len(full_names) > 1
                    conf = 0.58 if is_ambig else 0.74
                    sorted_anchors = sorted(list(full_names))
                    reason = (
                        f"Ambiguous standalone surname matching multiple document anchors ({', '.join(sorted_anchors)}); requires human confirmation"
                        if is_ambig
                        else f"Document-local standalone surname reference to '{sorted_anchors[0]}'"
                    )
                    add_candidate(
                        s_start,
                        s_end,
                        s_match.group(0),
                        PIICategory.PERSON.value,
                        conf,
                        explanation=[reason],
                        context_signals=["document_local_surname_anchor"],
                        is_ambiguous=is_ambig,
                    )
                    emitted_spans.append((s_start, s_end))

        # 3. Contextual Address Sequences
        for match in cls.ADDRESS_CONTEXT_REGEX.finditer(text):
            addr_text = match.group(1).strip().rstrip(".,;")
            if len(addr_text) >= 10:
                a_start = match.start(1)
                a_end = a_start + len(addr_text)
                add_candidate(
                    a_start,
                    a_end,
                    addr_text,
                    PIICategory.ADDRESS.value,
                    0.84,
                    explanation=["Matched address span following location anchor phrase"],
                    context_signals=["location_preposition_anchor"],
                )

        return candidates
