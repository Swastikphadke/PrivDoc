# 05 --- End-to-End Processing Pipeline

## 1. Pipeline overview

`Upload → Validate → Extract → Detect → Normalize → Link → Review → Redact → Verify → Summarize → Check → Export`

The order is mandatory. Summarization must occur only after redaction
and verification of the sanitized text.

## 2. Stage 1: Upload and validation

-   Accept `.txt` and `.pdf`.
-   Enforce configurable maximum file size.
-   Check extension and file signature/MIME where practical.
-   Generate a random document/session ID.
-   Store original uploaded files, canonical extracted text and PDF coordinate mappings in a temporary local session directory (`data/sessions/{document_id}/`). SQLite stores session metadata, review decisions and minimal feedback, not raw document content.
-   Reject encrypted PDFs unless password handling is explicitly
    implemented.
-   Never execute embedded content or scripts.

## 3. Stage 2: Extraction

### TXT

-   Decode UTF-8.
-   If decoding fails, show an explicit warning and ask the user to
    provide UTF-8 or choose a documented fallback.
-   Preserve exact extracted text and offsets.

### PDF

-   Use PyMuPDF to extract page text and word/span coordinates.
-   Preserve page index and bounding boxes.
-   Detect pages with no extractable text.
-   If the document is image-only, reject it as out of scope.
-   Warn when extraction appears incomplete or reading order is
    ambiguous.

## 4. Stage 3: Detection

### Regex detector

-   Email and supported obfuscated email variants.
-   Phone numbers using configurable country patterns and validation.
-   ID-like strings using configurable organization-specific patterns.
-   Postal codes only as supporting address evidence, not standalone
    proof of a home address.

### NER detector

-   Person names.
-   Address/location candidates.
-   Contextual entities from supported model labels.

### SLM detector

Use selective calls for: - Ambiguous name/person classification. -
Candidate context classification. - Relationship suggestions between
name variants. - Potential missed PII review suggestions.

The SLM must return schema-validated structured output. Treat model
output as untrusted data. It cannot alter system rules, approve
redactions or call tools.

## 5. Stage 4: Normalize and merge

-   Normalize Unicode consistently for comparison while retaining
    original text and offsets.
-   Merge exact duplicate spans.
-   Resolve overlapping spans according to a deterministic policy.
-   Retain all detector sources and confidence signals.
-   Do not discard a candidate merely because another detector
    disagrees; represent conflict for review.

## 6. Stage 5: Entity resolution

-   Create entity groups for person and identifier occurrences.
-   Use exact normalized matching first.
-   Use RapidFuzz only to propose similar strings.
-   Use contextual evidence and SLM suggestions as supporting evidence.
-   Do not automatically merge ambiguous initials or titles.
-   Expose link confidence and evidence in the review UI.
-   Allow users to link/unlink occurrences manually.
-   "Redact all similar" must operate on a visible, reviewable set of
    occurrences, not an unrestricted fuzzy search.

## 7. Stage 6: Human review

Each candidate has one of: - `PENDING` - `APPROVED` - `REJECTED` -
`MANUAL` - `NEEDS_REVIEW`

The user can: - Approve/reject a candidate. - Add a manual span. -
Change the type. - Review linked occurrences. - Approve a group of
linked occurrences. - Inspect low-confidence and conflicting candidates.

No original content is removed at this stage.

## 8. Stage 7: Redaction

### TXT

-   Sort approved spans by descending start offset.
-   Replace spans with type-specific placeholders.
-   Validate offsets and overlaps before mutation.
-   Preserve unapproved text.

### PDF

-   Map approved text spans to page coordinates.
-   Attempt native PyMuPDF redaction first by applying actual redaction annotations (`apply_redactions()`).
-   Save to a new file and immediately verify the output (Stage 8).
-   If verification fails, block the export completely.
-   Offer clean-text PDF reconstruction only as an explicit alternative to the user.
-   Re-verify the reconstructed output before allowing download.
-   Display prominent layout-loss warnings when reconstructed PDF is used.
-   Do not merely draw black rectangles or overlay text.

## 9. Stage 8: Export verification

For every approved value and known variant: - Search the exported text
extraction. - Search page-level extracted text. - Check that redaction
annotations have been applied rather than left pending. - Check metadata
for accidental sensitive values. - Record verifier result and any
limitations.

The verification report must not include raw sensitive values in normal
logs. Store hashes or masked diagnostics where practical.

## 10. Stage 9: Summarization

-   Construct a sanitized-only input object.
-   Ensure original document text is not passed to the summary module.
-   Summarize the sanitized content using the local SLM.
-   If the local SLM is unavailable or times out:
    - Use a clearly labelled extractive fallback based exclusively on sanitized text.
    - Run the identical summary privacy checks.
    - Never bypass verification.
-   Preserve key facts and uncertainty; do not invent missing values.
-   Use placeholders or generalized references where appropriate.

## 11. Stage 10: Summary privacy checks

1.  Compare against approved values and aliases.
2.  Run PII detection over the summary.
3.  Evaluate configurable quasi-identifier risk rules (e.g. role + department + location/date co-occurrences).
4.  Treat results as risk flags, not definitive anonymity guarantees.
4.  Check that removed facts have not been reconstructed from other
    remaining context.
5.  If risk is high or checks are uncertain, suppress the summary or
    require user revision.

A clean automated check is not a mathematical proof of anonymity. The UI
must describe it as a passed automated check, not a guarantee.

## 12. Pipeline outputs

-   Extracted document representation.
-   Candidate list and provenance.
-   Entity groups and link evidence.
-   Review decision set.
-   Sanitized text.
-   Redacted TXT/PDF.
-   Export verification result.
-   Summary and privacy-check result.
-   Local feedback records.
