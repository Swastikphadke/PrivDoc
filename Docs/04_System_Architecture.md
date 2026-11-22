# 04 --- System Architecture

## 1. Architectural style

A modular monolith is recommended for the MVP: one FastAPI backend with
clearly separated modules and a React frontend. Avoid microservices
until there is a measured need.

## 2. Trust boundaries

-   **Boundary A --- File intake:** untrusted uploaded file enters the
    local application.
-   **Boundary B --- Detection:** extractors and detectors process
    document content.
-   **Boundary C --- Human review:** candidate data is presented; user
    decisions are authoritative.
-   **Boundary D --- Sanitization:** approved spans are transformed into
    sanitized content.
-   **Boundary E --- Summary:** only sanitized content may cross into
    the summarizer.
-   **Boundary F --- Export:** sanitized output is verified before
    download.

The summary module should not have access to the original-document
object or raw source file.

## 3. Logical components

### Frontend

-   Upload screen.
-   Document workspace.
-   Text/PDF viewer.
-   Highlight overlay.
-   Candidate list and filters.
-   Entity group panel.
-   Review controls.
-   Export status and download.
-   Summary and privacy warning panel.

### Backend

-   Upload/API controller.
-   File validator.
-   TXT/PDF parser.
-   Detection orchestrator.
-   Regex detector.
-   NER detector.
-   SLM adapter.
-   Candidate normalizer/merger.
-   Entity resolver.
-   Review manager.
-   Redaction service.
-   Export verifier.
-   Summary service.
-   Summary privacy checker.
-   Feedback store and cleanup job.

## 4. Data flow

1.  Frontend uploads a file to the local backend.
2.  Backend validates type, size and parseability.
3.  Parser produces a normalized document representation with source
    offsets and PDF coordinates.
4.  Detection orchestrator runs regex, NER and selective SLM analysis.
5.  Candidate merger normalizes overlaps and records provenance.
6.  Entity resolver proposes links between occurrences.
7.  Frontend renders candidates for review.
8.  User decisions are stored in the session.
9.  Redaction service applies only approved decisions.
10. Export verifier checks the output.
11. Sanitized text is passed to the summary service.
12. Summary checker evaluates direct PII and quasi-identifier risk.
13. Frontend displays only verified output; otherwise it displays a
    warning or suppresses the summary.

## 5. Core design contracts

-   Every span uses a documented offset convention: Python Unicode
    code-point offsets in the canonical extracted text.
-   Each candidate retains original detector provenance.
-   Candidate confidence is not equivalent to approval.
-   User review decisions are explicit and auditable within the session.
-   PDF page coordinates are stored separately from text offsets.
-   The summarizer accepts a `SanitizedDocument` type, not a
    `RawDocument`.
-   Export verification is mandatory before marking an export complete.
-   Failure to verify means export status is failed or unverified, not
    safe.

## 6. Suggested architecture diagram

``` mermaid
flowchart TD
    A[React UI] --> B[FastAPI]
    B --> C[File Validation]
    C --> D[TXT / PDF Parser]
    D --> E[Detection Orchestrator]
    E --> F[Regex]
    E --> G[NER]
    E --> H[Local SLM]
    F --> I[Candidate Merge]
    G --> I
    H --> I
    I --> J[Entity Resolver]
    J --> K[Human Review]
    K --> L[Redaction Engine]
    L --> M[Export Verification]
    M --> N[Sanitized Document]
    N --> O[Summary Engine]
    O --> P[Summary Privacy Checks]
    P --> Q[Safe Summary / Suppress]
```

## 7. Failure handling

-   Unsupported file: reject before processing.
-   Empty extraction: explain that the PDF may be scanned or image-only.
-   Detector unavailable: disclose degraded mode and which detectors
    ran.
-   SLM timeout: continue with deterministic/NER candidates if
    configured; label the run as degraded.
-   Ambiguous entity link: do not auto-link; present separate candidates
    or ask the user.
-   Redaction error: do not provide an export marked successful.
-   Export verification failure: quarantine/delete failed output, block the export, and offer clean-text PDF reconstruction only as an explicit alternative with layout-loss warnings; re-verify the reconstructed output before offering download.
-   SLM unavailable for summary: execute a clearly labelled extractive fallback based exclusively on sanitized text; run identical summary privacy checks; never bypass verification.
-   Summary privacy failure: suppress summary or request manual review;
    never display it as safe; treat quasi-identifier alerts as risk flags, not definitive guarantees.

## 8. Deployment topology

The frontend and backend run on the same machine. Bind the backend to
localhost by default. Do not expose the service to a LAN or public
interface unless authentication, transport security and a separate
deployment threat model are implemented.
