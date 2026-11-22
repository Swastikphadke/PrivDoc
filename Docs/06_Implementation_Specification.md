# 06 --- Implementation Specification

## 1. Engineering approach

Build a modular monolith with FastAPI and React. Implement a working
vertical slice before optimizing models. Each module should have unit
tests and typed input/output contracts.

## 2. Repository structure

``` text
PrivyDoc/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Upload/
│   │   │   ├── DocumentViewer/
│   │   │   ├── CandidateList/
│   │   │   ├── EntityGroups/
│   │   │   └── SummaryPanel/
│   │   ├── pages/
│   │   ├── services/
│   │   └── App.jsx
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── processors/
│   │   ├── detectors/
│   │   ├── services/
│   │   ├── schemas/
│   │   ├── database/
│   │   └── main.py
│   ├── tests/
│   └── requirements.txt
├── datasets/
│   ├── sample_documents/
│   └── evaluation/
├── models/
├── Docs/
└── README.md
```

## 3. Backend module responsibilities

  ------------------------------------------------------------------------
  Module                               Responsibility
  ------------------------------------ -----------------------------------
  `processors/txt_processor.py`        Decode TXT and return canonical
                                       text

  `processors/pdf_processor.py`        Extract page text, words and
                                       coordinates

  `detectors/regex_detector.py`        Structured pattern detection

  `detectors/ner_detector.py`          NER model adapter

  `detectors/slm_detector.py`          Local SLM inference and JSON
                                       validation

  `detectors/entity_resolver.py`       Alias and occurrence grouping

  `services/detection_service.py`      Orchestrate detectors and merge
                                       candidates

  `services/review_service.py`         Validate and persist review
                                       decisions

  `services/redaction_service.py`      Create sanitized text and PDF

  `services/verification_service.py`   Verify exported artifact

  `services/summary_service.py`        Summarize sanitized-only input

  `services/summary_guard.py`          Direct PII and quasi-identifier
                                       checks

  `services/feedback_service.py`       Store corrections and feedback

  `core/security.py`                   File validation, IDs, cleanup and
                                       safe logging
  ------------------------------------------------------------------------

## 4. Canonical data contracts

### Document

``` json
{
  "document_id": "random-session-id",
  "filename": "report.pdf",
  "file_type": "pdf",
  "status": "EXTRACTED",
  "page_count": 3,
  "text_length": 5420
}
```

### Candidate

``` json
{
  "candidate_id": "c_001",
  "document_id": "random-session-id",
  "start": 0,
  "end": 12,
  "text": "Richa Sharma",
  "type": "PERSON",
  "confidence": 0.94,
  "confidence_band": "HIGH",
  "sources": ["ner", "slm"],
  "entity_id": "e_001",
  "review_status": "PENDING"
}
```

Offsets refer to the canonical extracted text, not PDF byte positions.
For PDF, retain page and bounding-box mapping separately.

### Review decision

``` json
{
  "candidate_id": "c_001",
  "decision": "APPROVED",
  "reviewed_at": "ISO-8601 timestamp",
  "scope": "OCCURRENCE"
}
```

### Sanitized document

``` json
{
  "document_id": "random-session-id",
  "sanitized_text": "The [PERSON] approved the report.",
  "approved_redaction_count": 1,
  "verification_status": "PASSED"
}
```

The summary service should receive this sanitized representation, not a
raw document object.

## 5. API contracts

  -----------------------------------------------------------------------------------------
  Method                  Route                                     Purpose
  ----------------------- ----------------------------------------- -----------------------
  POST                    `/api/documents/upload`                   Upload and extract file

  POST                    `/api/documents/{id}/detect`              Run detection

  GET                     `/api/documents/{id}`                     Get document
                                                                    status/metadata

  GET                     `/api/documents/{id}/candidates`          Get candidate spans

  POST                    `/api/documents/{id}/review`              Submit decisions

  POST                    `/api/documents/{id}/candidates/manual`   Add manual redaction

  POST                    `/api/documents/{id}/entities/link`       Link occurrences

  POST                    `/api/documents/{id}/redact`              Create sanitized export

  GET                     `/api/documents/{id}/export`              Download verified
                                                                    output

  POST                    `/api/documents/{id}/summary`             Summarize sanitized
                                                                    text

  GET                     `/api/documents/{id}/summary`             Retrieve summary/check
                                                                    status

  POST                    `/api/feedback`                           Store correction
                                                                    feedback

  DELETE                  `/api/documents/{id}`                     Delete session and
                                                                    temporary data
  -----------------------------------------------------------------------------------------

Use Pydantic request/response models. Validate IDs and ownership/session
scope. Add request-size limits and consistent error responses.

## 6. Implementation rules

-   Use half-open offsets `[start, end)`.
-   Keep canonical source text immutable during review.
-   Apply replacements from highest offset to lowest.
-   Reject invalid, out-of-range or conflicting spans.
-   Preserve detector provenance.
-   Never equate confidence with approval.
-   Never summarize original text.
-   Never report an export as safe before verification.
-   Do not log raw document contents or full PII values.
-   Use random session IDs and local-only binding by default.
-   Add unit tests for every offset transformation.

## 7. Recommended build order

1.  TXT parser and regex detector.
2.  PDF parser and coordinate mapping.
3.  Candidate schema and merge logic.
4.  NER adapter.
5.  SLM adapter with schema validation and timeout.
6.  Entity resolution.
7.  Review API and frontend.
8.  TXT redaction.
9.  PDF redaction and verifier.
10. Sanitized-only summary service.
11. Summary privacy guard.
12. Feedback, cleanup and integration tests.
