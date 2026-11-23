# 10 --- Privacy and Security Specification

## 1. Security objective

Protect sensitive document content during processing and prevent
approved redactions from leaking through exported files or generated
summaries.

## 2. Threat model

### Assets

-   Original uploaded documents.
-   Extracted raw text.
-   Detected PII values.
-   Entity/alias mappings.
-   Review decisions.
-   Sanitized exports.
-   Summary outputs.
-   Local feedback database.

### Threats

-   Original content sent to external inference/API services.
-   Malicious or malformed uploaded files exploiting parsers.
-   PII exposed through logs, temporary files or crash reports.
-   Visual-only PDF masking leaving underlying text intact.
-   Metadata, annotations or hidden content retaining PII.
-   Summarizer accidentally receiving raw source text.
-   Summary reconstructing direct PII or indirect identity clues.
-   Incorrect entity linking causing under-redaction.
-   Incorrect candidate approval causing over-redaction.
-   Local service exposed to other devices on a network.

## 3. Security controls

  -----------------------------------------------------------------------
  Threat                              Control
  ----------------------------------- -----------------------------------
  Cloud leakage                       Local inference; no external API in
                                      baseline

  Malformed uploads                   File validation, size limits,
                                      parser errors handled

  Parser attack surface               Keep libraries updated; process
                                      untrusted files defensively

  Log leakage                         No raw text/PII in logs by default

  Temporary file leakage              Restricted local workspace and
                                      cleanup

  PDF text recovery                   Actual redaction and post-export
                                      verification

  Metadata leakage                    Inspect and sanitize metadata

  Summary leakage                     Sanitized-only input boundary and
                                      post-generation checks

  Entity mislinking                   Conservative links and human review

  LAN exposure                        Bind to localhost by default

  Model prompt injection              Treat document content and model
                                      output as untrusted data

  Unsafe output                       Fail closed when verification fails
  -----------------------------------------------------------------------

## 4. Data lifecycle

1.  Upload: file enters a local temporary workspace.
2.  Extraction: text exists in local process memory and temporary
    session state.
3.  Detection: candidates and offsets are generated locally.
4.  Review: decisions are stored in the local session/database.
5.  Redaction: a sanitized copy is created.
6.  Verification: exported artifact is reopened and inspected.
7.  Summary: sanitized text only is passed to the model.
8.  Cleanup: original temporary files and raw session content are
    deleted according to retention settings.

Define and test cleanup behavior for normal completion, cancellation,
errors and application shutdown.

## 5. Privacy boundary for summarization

The summary service must not accept a raw document object. Prefer a
separate sanitized input schema and function. Do not pass the original
filename if it contains a person's name. Do not include raw redaction
values in the summary prompt.

## 6. PDF security limitations

PDFs can contain text, images, annotations, metadata, attachments, forms
and other objects. The baseline verifier must document which structures
it inspects. If the implementation cannot safely sanitize a particular
structure, reject the export or rebuild a new PDF from sanitized text
and disclose layout loss. Do not claim complete forensic sanitization
without testing the relevant PDF structures.

## 7. Summary privacy limitations

Exact-match checks and PII detectors cannot guarantee prevention of all
re-identification. Quasi-identifier checks should flag suspicious
combinations for human review. When uncertain, suppress or generalize
the summary.

## 8. Local processing statement

The application may need internet access to install dependencies or
download model weights. After setup, normal document processing should
be offline. Verify this with network monitoring or a controlled offline
test before claiming fully offline operation.

## 9. Security test checklist

-   [x] Run a workflow with network disabled after setup.
-   [x] Confirm no outbound inference/API calls.
-   [x] Inspect logs for raw PII.
-   [x] Inspect temporary directory permissions and cleanup.
-   [x] Test malformed and oversized uploads.
-   [x] Test encrypted and image-only PDFs.
-   [x] Attempt to extract redacted text from output.
-   [x] Inspect metadata and annotations.
-   [x] Confirm summary module cannot access raw text.
-   [x] Test prompt injection text embedded in documents.
-   [x] Confirm local API binds to localhost by default.

## 10. Adversarial Resilience & Security Hardening (SEC-01 through SEC-07)

Following an internal Application Security & Privacy Red Team assessment, the following hardening controls are enforced and covered by automated regression tests (`backend/tests/test_security_adversarial.py`):

1.  **SEC-01 — Unicode Zero-Width, Bidi Control & Homoglyph Normalization:**
    -   `TXTProcessor` and `PDFProcessor` strip invisible zero-width characters (`\u200b`–`\u200f`, `\u2060`, `\ufeff`, `\u00ad`) and bidirectional override controls (`\u202a`–`\u202e`, `\u2066`–`\u2069`) and normalize exotic horizontal spaces (`\u00a0`, `\u2000`–`\u200a`, `\u3000`) to ASCII space during canonical extraction.
    -   `RegexDetector` and `NERDetector` evaluate a 1-to-1 homoglyph-folded projection (`fold_homoglyphs_1to1`) so Cyrillic/Greek confusable characters (`а`, `е`, `о`, `р`, `с`, `х`) inside names or emails are detected without shifting character offsets.
    -   `VerificationService` and `SummaryGuard` normalize text via `normalize_for_security_comparison` and scan for Base64, hex, and URL-encoded representations of approved sensitive entities.
2.  **SEC-02 — Complete Downstream Invalidation on Cluster Mutation:**
    -   Manual entity linking and unlinking (`EntityResolver.link_candidates`, `unlink_candidates`) atomically unlink `export_metadata.json`, `sanitized.txt`, `sanitized.pdf`, and `summary.json`, reset SQLite `documents.status` to `REVIEWING`, and validate that all candidate IDs belong to the active document session.
3.  **SEC-03 — PDF Annotation & Incremental Update Sanitization:**
    -   `RedactionService.apply_native_pdf_redaction` deletes non-redaction PDF annotations (`page.annots()`) whose content, title, or subject contains approved PII, scrubs metadata/XMP/TOC/widgets/links/attachments, and saves with `garbage=4, deflate=True, clean=True` to eliminate historical incremental update objects.
4.  **SEC-04 — Boundary Identifier Validation, Security Headers & Safe Error Handling:**
    -   Every `{document_id}` endpoint validates `^[a-zA-Z0-9_\-]{1,64}$` before any database or filesystem call, preventing unvalidated identifier reflection.
    -   All HTTP responses include `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `Referrer-Policy: no-referrer`.
    -   Unhandled HTTP 500 exceptions return generic operational messages without exposing host filesystem paths or raw exception strings.
5.  **SEC-05 — Decompression & Resource-Exhaustion Bounds:**
    -   `PDFProcessor` enforces `MAX_PDF_PAGES = 500` and `MAX_EXTRACTED_CHARS = 2_000_000`; `TXTProcessor` enforces `MAX_EXTRACTED_CHARS = 2_000_000`.
6.  **SEC-06 — Instruction-Hierarchy & Delimiter Escape Hardening:**
    -   `ModelService.sanitize_untrusted_input` neutralizes XML/ChatML/Llama/Markdown role markers and randomized boundary tags; `SummaryGuard.check_prompt_injection_artifacts` blocks instruction-hierarchy override phrases even when obfuscated.
7.  **SEC-07 — Frontend Session State Isolation:**
    -   `ReviewWorkspace`, `ExportView`, and `SummaryView` clear session state immediately upon route transitions or session-not-found errors so deleted or prior session data is never retained in memory.
