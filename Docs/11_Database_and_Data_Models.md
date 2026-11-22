# 11 --- Database and Data Models

## 1. Persistence approach

Use SQLite strictly for local session metadata, candidate references, review decisions and minimal feedback.
Never store raw document contents, canonical extracted text, or PDF coordinate mappings in the database; store these ephemeral artifacts in the temporary local session directory (`data/sessions/{document_id}/`) with explicit cleanup upon session termination or TTL expiration.

## 2. Core entities

### Document

-   `id`: random opaque ID.
-   `original_filename`: sanitized display name.
-   `file_type`: TXT or PDF.
-   `status`: uploaded, extracted, detected, reviewed, redacted,
    verified, failed.
-   `created_at`, `expires_at`.
-   `page_count`, `text_length`.
-   `parser_version`.

### Candidate

-   `id`, `document_id`.
-   `start_offset`, `end_offset`.
-   `page_index` and bounding boxes for PDF.
-   `entity_type`.
-   `confidence`, `confidence_band`.
-   `detector_sources`.
-   `entity_id` (nullable).
-   `review_status`.
-   `normalized_match_key` where safe and necessary.

### Entity

-   `id`, `document_id`.
-   `entity_type`.
-   `display_label` (mask where appropriate).
-   `link_confidence`.
-   `link_evidence_summary`.
-   `review_status`.

### EntityOccurrence

-   `entity_id`, `candidate_id`.
-   `relationship_type`: exact, alias, initial, contextual, user-linked.
-   `link_confidence`.

### ReviewDecision

-   `id`, `candidate_id` or `entity_id`.
-   `decision`: approved, rejected, manual.
-   `scope`: occurrence or group.
-   `timestamp`.
-   `decision_source`: user.

### ExportRecord

-   `id`, `document_id`.
-   `output_type`.
-   `verification_status`.
-   `created_at`.
-   `verification_summary`.
-   `output_path` stored only within controlled workspace.

### FeedbackRecord

-   `id`, `candidate_type`.
-   `action`: approved, rejected, corrected, manually added.
-   `detector_version`.
-   `context_policy`: avoid storing raw context by default.
-   `created_at`.

## 3. Data handling rules

-   Use random IDs; do not use names or email addresses in IDs.
-   Do not store raw PII in analytics or logs.
-   Restrict database and workspace file permissions.
-   Define expiration and deletion behavior.
-   Avoid retaining original text after session cleanup.
-   Feedback records should store minimal information; raw snippets
    require explicit justification and local-only retention.
-   Never use private user documents for model training by default.

## 4. State transitions

``` text
UPLOADED
   ↓
EXTRACTED
   ↓
DETECTED
   ↓
REVIEWED
   ↓
REDACTED
   ↓
VERIFIED
   ↓
SUMMARIZED
```

Any stage may transition to `FAILED` with a safe error. A summary can
only be created from a verified sanitized representation.

## 5. Offset and coordinate model

-   Canonical text offsets are half-open `[start, end)` Python Unicode
    code-point indices.
-   PDF coordinates use page index plus rectangle coordinates in the
    coordinate system documented by PyMuPDF.
-   Keep the original extracted text immutable for the duration of
    review.
-   Store a mapping from canonical text spans to PDF word/span
    rectangles.
-   Validate every span before applying a redaction.
