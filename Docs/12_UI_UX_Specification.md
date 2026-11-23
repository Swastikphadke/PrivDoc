# 12 --- UI/UX Specification

## 1. Design objective

Provide a calm, professional document-security workspace. The interface
should make the review decision obvious and prevent users from mistaking
model confidence for approval.

## 2. Main screens

### Screen A --- Dashboard / Upload

-   Product identity and local-processing indicator (`127.0.0.1:8000`).
-   Live operational telemetry strip backed by real SQLite and session metadata (`GET /api/documents`): Documents Processed, Awaiting Review, Verified Exports, and Suppressed Summaries.
-   Active-session PII category distribution bars and 5-stage fail-closed lifecycle indicator.
-   Drag-and-drop upload with supported formats (`.TXT`, `.PDF`) and 20MB size limit.
-   Active & Recent Local Document Sessions table with live verification badges and direct navigation.

### Screen B --- Processing

-   Current stage: parsing, detection, entity linking.
-   Progress and elapsed time.
-   Detector status and degraded-mode warnings.
-   Cancel action.

### Screen C --- 3-Panel Document Review Workstation

Three-panel technical layout:
-   **Panel 1 (Left):** Authoritative Document Viewer (Canonical Text with `[start, end)` offset highlights or PyMuPDF page PNG preview with synchronized bounding-box overlays).
-   **Panel 2 (Center):** Detected Candidates & Entity Clusters sidebar with search, category/status filters, and bulk review controls.
-   **Panel 3 (Right):** Contextual Evidence & Coreference Inspector displaying why the selected candidate was flagged, detector provenance and consensus/conflict status, heuristic evidence weight (with explicit non-calibration notice), interactive hub-and-spoke entity cluster graph, structured `link_reasons`, and clickable occurrence navigation.
-   **Top Workspace Bar:** Document metadata, review progress counters, keyboard shortcut legend (`A`, `R`, `M`), view mode toggle, and Inspector toggle.

### Screen D --- Export & Verification

-   Export format (`.pdf` or `.txt`) and placeholder configuration (`[CATEGORY]`, `[REDACTED]`, or mask characters).
-   Approved redaction count and pending-candidate review gatekeeper.
-   Explicit visual distinction between `PENDING`, `PROCESSING`, `VERIFIED`, `FAILED`, `RECONSTRUCTED`, and `UNVERIFIED`.
-   8-point independent verification audit checklist, verification timestamp, and exported file SHA-256 integrity digest (with explicit notice that a hash verifies file byte integrity only and does not prove redaction completeness).
-   Download enabled strictly after verification passes; explicit layout-loss warning badge (`RECONSTRUCTED PDF`) when DEC-004 clean-text reconstruction is used.

### Screen E --- Privacy-Safe Summary

-   Explicit visual distinction between `VERIFIED`, `REQUIRES_REVIEW`, `SUPPRESSED`, and `FAILED`.
-   Sanitized-only input contract badge (`P5-VERIFIED`) and generation engine indicator (`SLM` vs `EXTRACTIVE_FALLBACK`).
-   Structured summary sections (Executive Narrative, Key Points, Important Findings, Grounded Dates & Figures, and Source Evidence with `[§1]` grounded quote traceability).
-   Persistent Quasi-Identifier Re-Identification Risk card and non-anonymity disclaimer.
-   Unmistakable security suppression alert when `SummaryGuard` blocks an unsafe summary.

## 3. Candidate visual system

Use both color and text labels: - Person: red. - Email: blue. - Phone:
amber. - Address: purple. - ID-like: teal. - Uncertain/conflict: neutral
warning style.

Colors are illustrative; maintain sufficient contrast and do not rely on
color alone.

## 4. Candidate card fields

-   Text snippet, masked by default where appropriate.
-   PII type.
-   Confidence band and score if calibrated.
-   Detector sources.
-   Page/position.
-   Linked entity and occurrence count.
-   Review status.
-   Approve/reject controls.

## 5. Interaction rules

-   Approve: mark candidate/selected occurrence for redaction.
-   Reject: preserve text.
-   Manual add: select text and assign category.
-   Redact all similar: preview exact affected occurrences before
    applying.
-   Entity group: show evidence and allow link/unlink.
-   Undo: allow reversal before export.
-   Keyboard shortcuts: A approve, R reject, M manual add, with
    shortcuts disabled while typing in text inputs.
-   Bulk actions should show the number of affected occurrences and
    require confirmation.

## 6. Confidence and review language

Use `High`, `Medium`, `Low` or `Uncertain` bands. Do not display a model
score as a calibrated probability unless calibration has been measured.
Show a separate status such as `Pending`, `Approved` or `Rejected`.

## 7. Accessibility and usability

-   Keyboard navigation.
-   Visible focus states.
-   Screen-reader labels for controls.
-   Text labels in addition to highlight colors.
-   Zoom support and readable typography.
-   Clear error and empty states.
-   Confirmation before destructive actions.
-   Responsive layout for laptop screens; desktop-first is acceptable
    for MVP.

## 8. Primary user journey

Upload → processing → review candidates → inspect entity links →
approve/reject/add → preview redaction → export and verify → view safe
summary → delete session.
