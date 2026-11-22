# 01 --- Project Overview / Product Definition (PD)

## 1. Project identity

**Name:** PrivyDoc (working name)\
**Title:** Privacy-Aware Document Redaction and Summary Tool\
**Domain:** Cybersecurity, Applied AI/NLP and Privacy-Preserving
Computing

## 2. Problem statement

Organizations share reports, forms and records with auditors, vendors,
partners and the public. These documents may contain names, email
addresses, telephone numbers, home addresses and ID-like strings. Manual
redaction is slow and error-prone. Fully automated redaction can
silently miss sensitive content or remove legitimate content. Cloud
processing can expose the very documents users are trying to protect.
Summaries can also leak information removed from the source.

PrivyDoc will provide a local-first workflow that detects possible PII,
lets a human review and approve candidates, exports a sanitized copy,
and generates a summary only from sanitized content.

## 3. Product vision

Enable a user to prepare a document for safe sharing with transparent,
reviewable and verifiable redaction, without routinely sending the
original document to a third-party service.

## 4. Goals

1.  Accept TXT and text-based PDF files.
2.  Identify five required PII categories.
3.  Use an SLM alongside deterministic rules and/or NER.
4.  Link likely name variants into entities while exposing uncertainty.
5.  Provide highlighted candidates and user approval/rejection.
6.  Support manual redaction and bulk redaction of linked occurrences.
7.  Export a copy in which approved source content is not recoverable
    through ordinary text extraction or PDF annotation reversal.
8.  Generate summaries from sanitized text only.
9.  Check summaries for direct PII and plausible indirect identification
    risks.
10. Run on ordinary consumer hardware and document resource
    requirements.

## 5. Non-goals for the baseline

-   OCR of scanned or image-only PDFs.
-   Legal certification or a guarantee of regulatory compliance.
-   Fully autonomous redaction without user approval.
-   Perfect detection of every possible identifier or quasi-identifier.
-   Cloud document processing or third-party hosted inference.
-   Enterprise identity management, collaboration, audit integrations or
    role-based administration.
-   Automatic training or fine-tuning of a model from private documents.

## 6. Target users and use cases

### Primary users

-   Staff preparing reports for external sharing.
-   Students/researchers handling sample records.
-   Auditors or analysts reviewing documents before disclosure.
-   Small organizations needing a local document hygiene workflow.

### Main use cases

-   UC-01: Upload a supported document.
-   UC-02: Inspect extracted text and processing warnings.
-   UC-03: Review PII candidates by type and confidence.
-   UC-04: Approve, reject or manually add a redaction.
-   UC-05: Apply a decision to all linked occurrences.
-   UC-06: Export a sanitized document.
-   UC-07: Verify that approved content is absent from the export.
-   UC-08: Generate a summary from sanitized text.
-   UC-09: Inspect summary privacy warnings and suppress unsafe output.
-   UC-10: Save local feedback to improve future suggestions.

## 7. Product principles

-   Privacy by design and local-first processing.
-   Human-in-the-loop control.
-   Conservative handling of ambiguity.
-   Clear separation of detection confidence and user approval.
-   Sanitization as a hard boundary before summarization.
-   Reproducible evaluation and transparent limitations.

## 8. Success criteria

The project is successful when a user can complete the full workflow on
a representative TXT and text-based PDF, review candidates, approve
redactions, export and verify the sanitized file, and receive a summary
that has passed the configured privacy checks.

Quantitative thresholds are defined in `08_Evaluation_and_Test_Plan.md`.
These are proposed project targets and must be validated against the
actual test corpus.

## 9. Assumptions and constraints

-   Users can install Python dependencies and a local model runtime.
-   Model downloads may require internet access during setup; document
    processing and inference should work offline after setup.
-   PDF text extraction may not preserve reading order in complex
    layouts.
-   Detection performance depends on language, formatting and the
    evaluation corpus.
-   Hardware varies; model selection must be benchmarked on the target
    machine.
