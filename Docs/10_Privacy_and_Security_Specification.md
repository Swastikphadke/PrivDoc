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

-   [ ] Run a workflow with network disabled after setup.
-   [ ] Confirm no outbound inference/API calls.
-   [ ] Inspect logs for raw PII.
-   [ ] Inspect temporary directory permissions and cleanup.
-   [ ] Test malformed and oversized uploads.
-   [ ] Test encrypted and image-only PDFs.
-   [ ] Attempt to extract redacted text from output.
-   [ ] Inspect metadata and annotations.
-   [ ] Confirm summary module cannot access raw text.
-   [ ] Test prompt injection text embedded in documents.
-   [ ] Confirm local API binds to localhost by default.
