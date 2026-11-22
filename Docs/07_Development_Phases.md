# 07 --- Development Phases and Milestones

## 1. Execution strategy

Build a reliable end-to-end workflow first, then improve model quality
and UX. The schedule below is a suggested 14-day focused plan; adjust
for team size and hardware.

## 2. Phase plan

  -----------------------------------------------------------------------------
  Phase             Indicative timing Main outcome         Exit condition
  ----------------- ----------------- -------------------- --------------------
  P0 --- Planning   Day 1             Repo, environment,   Backend and frontend
  and setup                           requirements and     start locally
                                      sample data          

  P1 --- Document   Day 2             TXT/PDF extraction   Text and PDF
  ingestion                                                coordinates can be
                                                           inspected

  P2 --- Baseline   Days 3--4         Regex + NER          Unit tests pass on
  detection                           candidates           annotated examples

  P3 --- SLM and    Day 5             Contextual           Ambiguous links are
  entity linking                      suggestions and      reviewable, not
                                      alias groups         silently merged

  P4 --- Human      Days 6--7         Highlighting and     User can
  review UI                           approval workflow    approve/reject/add
                                                           candidates

  P5 --- Redaction  Day 8             Sanitized TXT/PDF    Approved values fail
  and verification                                         extraction checks on
                                                           output

  P6 --- Safe       Day 9             Sanitized-only       Original text is not
  summary                             summarization and    accessible to
                                      guard                summary module

  P7 --- Feedback   Day 10            Local feedback and   Evaluation report
  and evaluation                      metrics              generated

  P8 ---            Days 11--12       Complete stable      End-to-end
  Integration and                     application          regression tests
  hardening                                                pass

  P9 --- Demo and   Days 13--14       Presentation-ready   Demo script and
  documentation                       release              deliverables
                                                           complete
  -----------------------------------------------------------------------------

## 3. Detailed phase exit criteria

### P0 --- Setup

-   Repository and branch strategy established.
-   Python virtual environment and frontend dependencies installed.
-   Configuration and `.gitignore` created.
-   Sample synthetic documents prepared.
-   No real personal data committed.

### P1 --- Ingestion

-   TXT parsing works.
-   Text-based PDF parsing works.
-   Image-only PDFs are detected/rejected.
-   Offsets and page coordinates are stable.
-   Unsupported and malformed files return useful errors.

### P2 --- Detection

-   Regex rules cover baseline email, phone and configured ID patterns.
-   NER returns person and address candidates.
-   Candidate schema includes source and confidence.
-   False-positive examples are included in tests.

### P3 --- SLM/entity linking

-   SLM runs locally.
-   Output is JSON/schema validated.
-   Timeout/failure is handled.
-   Similarity alone does not automatically merge ambiguous people.
-   User can inspect proposed entity links.

### P4 --- Review

-   Highlights map to correct text.
-   Approve/reject/manual add work.
-   Group review and "redact all similar" work.
-   Keyboard shortcuts do not interfere with text input.
-   Review decisions persist for the session.

### P5 --- Redaction

-   TXT offsets are replaced correctly.
-   PDF content is actually redacted.
-   Export is reopened and verified.
-   Failed verification blocks the safe-export state.

### P6 --- Summary

-   Summary input is sanitized-only.
-   Exact-value and alias checks run.
-   PII scan runs.
-   Quasi-identifier warnings/suppression work.
-   Summary cannot be marked safe when checks fail.

### P7--P9 --- Quality and release

-   Precision, recall, F1 and per-category results reported.
-   Performance and resource use measured.
-   Cleanup and privacy controls tested.
-   Documentation and demo are reproducible.

## 4. Team allocation suggestion

For a team of three: - Developer A: backend, document parsing, redaction
and verification. - Developer B: detection, SLM, entity resolution and
evaluation. - Developer C: frontend, review UX, integration and demo.

All team members should review privacy boundaries and test the full
workflow. For an individual project, complete phases sequentially.

## 5. Change management

Do not add OCR, DOCX, cloud inference, accounts or enterprise features
until the baseline acceptance criteria pass. Any scope change must
include implementation effort and new tests.
