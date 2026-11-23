"""Named Entity Recognition (NER) Detector Adapter.

Provides contextual entity extraction for PERSON and ADDRESS categories.
Implements a modular adapter pattern allowing spaCy / GLiNER models or lightweight
contextual linguistic extraction when heavy model weights are omitted.
"""

import re
from typing import List, Set
from app.schemas.candidate import Candidate, ConfidenceBand, PIICategory


# Common English capitalized words that are not person names
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
    "Master", "Order", "Project", "Phase", "Stage", "Milestone"
}

# Contextual verbs that strongly suggest a preceding or succeeding person name
PERSON_CONTEXT_VERBS = re.compile(
    r'\b(?:evaluated|examined|consulted|authorized|reported|stated|agreed|signed|approved|recommended|diagnosed|prescribed|met with|joined|advised|contacted)\b',
    re.IGNORECASE
)


class NERDetector:
    """Modular NER detector for contextual PERSON and ADDRESS extraction."""

    DETECTOR_NAME = "ner"

    # Pattern for capitalized 2-to-3 word names: e.g. "Vikram Malhotra", "Sarah Jenkins", "Dr. David Banner"
    CAPITALIZED_NAME_REGEX = re.compile(
        r'\b([A-Z][a-z]{2,15}\s+[A-Z][a-z]{2,15}(?:\s+[A-Z][a-z]{2,15})?)\b'
    )

    # Contextual Indian / Global address keywords
    ADDRESS_CONTEXT_REGEX = re.compile(
        r'\b(?:residing at|living at|located at|address:|shipped to|delivered to|office at)\s+([0-9A-Za-z\s,.-]{10,60}?)(?=[.;\n]|$)',
        re.IGNORECASE
    )

    @classmethod
    def detect(cls, text: str, document_id: str = "doc_temp") -> List[Candidate]:
        """Detect contextual entities (PERSON and ADDRESS) in canonical text.

        Args:
            text: Canonical extracted text.
            document_id: Associated document identifier.

        Returns:
            List of detected Candidate objects.
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
                    candidate_id=f"c_ner_{cand_idx:04d}",
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

        # 1. Contextual Person Names
        for match in cls.CAPITALIZED_NAME_REGEX.finditer(text):
            cand_text = match.group(1).strip()
            words = cand_text.split()

            # Filter out non-person capitalized sequences
            if any(w in STOP_WORDS_CAPITALIZED for w in words):
                continue

            # Check surrounding context for person-associated verbs or markers
            window_start = max(0, match.start() - 50)
            window_end = min(len(text), match.end() + 50)
            surrounding_context = text[window_start:window_end]

            confidence = 0.78  # Baseline for capitalized 2-3 word entity
            if PERSON_CONTEXT_VERBS.search(surrounding_context):
                confidence = 0.89  # Boosted by surrounding communicative / action verb

            add_candidate(match.start(1), match.end(1), cand_text, PIICategory.PERSON.value, confidence)

        # 2. Contextual Address Sequences
        for match in cls.ADDRESS_CONTEXT_REGEX.finditer(text):
            addr_text = match.group(1).strip()
            if len(addr_text) >= 10:
                add_candidate(
                    match.start(1),
                    match.end(1),
                    addr_text,
                    PIICategory.ADDRESS.value,
                    0.80
                )

        return candidates
