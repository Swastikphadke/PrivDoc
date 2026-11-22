# 12 --- UI/UX Specification

## 1. Design objective

Provide a calm, professional document-security workspace. The interface
should make the review decision obvious and prevent users from mistaking
model confidence for approval.

## 2. Main screens

### Screen A --- Dashboard / Upload

-   Product identity and local-processing indicator.
-   Drag-and-drop upload.
-   Supported formats and size limit.
-   Recent local sessions, if retention is enabled.
-   Clear privacy note: files are processed locally in the configured
    mode.

### Screen B --- Processing

-   Current stage: parsing, detection, entity linking.
-   Progress and elapsed time.
-   Detector status and degraded-mode warnings.
-   Cancel action.

### Screen C --- Document Review

Recommended layout: - Left: page/document navigation. - Center: document
text or PDF preview with highlights. - Right: candidate list and entity
groups. - Top: document status, detected count, approved count and
filters. - Bottom/toolbar: approve, reject, add manually, redact all
similar.

### Screen D --- Export

-   Export format.
-   Placeholder configuration.
-   Approved redaction count.
-   Verification status.
-   Download only after verification passes.
-   Clear warning if output is unverified or layout reconstruction was
    used.

### Screen E --- Summary

-   Safe summary.
-   Summary verification status.
-   Direct PII check result.
-   Quasi-identifier warnings.
-   Regenerate/generalize or suppress action.

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
