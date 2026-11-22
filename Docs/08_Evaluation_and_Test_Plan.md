# 08 --- Evaluation and Test Plan

## 1. Purpose

Measure detection quality, human review usability, redaction integrity,
summary safety, robustness and efficiency. Report results honestly with
dataset size and limitations.

## 2. Evaluation dataset

Create a small, manually annotated corpus using synthetic or properly
de-identified documents. Do not use real sensitive records without
authorization and a suitable handling plan.

Recommended corpus: - 20--30 TXT documents. - 20--30 text-based PDFs. -
At least 5 documents per major difficulty class. - A separate held-out
set not used to tune patterns/prompts.

Difficulty classes: 1. Clean business reports. 2. Names in headers,
signatures and running text. 3. Initials and name variants. 4.
International and locally formatted phone numbers. 5. Addresses with
varied formatting. 6. Employee/student/account ID formats. 7. Borderline
examples: product codes, dates, invoice numbers and generic numeric
strings. 8. Multi-column and multi-page PDFs.

Each document needs a gold annotation file with exact spans and entity
types. Record annotation guidelines and adjudicate disagreements.

## 3. Metrics

### Detection

-   Precision = TP / (TP + FP)
-   Recall = TP / (TP + FN)
-   F1 = 2 × Precision × Recall / (Precision + Recall)

Report: - Overall precision, recall and F1. - Per-category
precision/recall/F1. - Exact-span match and overlap-based match
separately. - False positives per document. - Results on held-out
documents.

### Entity linking

-   Pairwise precision/recall/F1 for same-entity links.
-   False-merge rate.
-   Missed-link rate.
-   Human correction rate.

### Redaction integrity

-   Approved source span recovery attempts.
-   Text extraction from output.
-   PDF annotation inspection.
-   Metadata checks.
-   Tests with copy/search/extract operations.
-   Count of approved spans remaining: target zero within the supported
    verification scope.

### Summary safety and quality

-   Exact approved-value leakage count.
-   Known-alias leakage count.
-   PII detector flags in summary.
-   Quasi-identifier risk flags and human adjudication.
-   Factual consistency review against sanitized source.
-   Unsupported claims/hallucination count.

### Performance

-   Processing time by stage.
-   Total end-to-end time.
-   Peak RAM and CPU.
-   Model load time and inference time.
-   Document length/page count.
-   Hardware and model revision used.

## 4. Proposed MVP targets

These are engineering targets, not claimed results. Revise them after
baseline measurement.

  Measure                                             Initial target
  --------------------------------------------------- ----------------------------------------
  Email precision                                     ≥ 98%
  Email recall                                        ≥ 98%
  Phone precision                                     ≥ 95%
  Phone recall                                        ≥ 95%
  Person-name F1                                      ≥ 85%
  Address F1                                          ≥ 80%
  ID-like F1                                          ≥ 90% on documented configured formats
  Entity-link false merges                            ≤ 2% on held-out pair set
  Approved PII remaining in verified export           0 detected instances
  Exact approved-value leakage in displayed summary   0
  Critical workflow completion                        100% of defined acceptance scenarios

Do not combine all categories into one number that hides weak
performance. If a target is not met, report the result and limitation.

## 5. Functional test cases

  -----------------------------------------------------------------------
  Test ID                 Scenario                Expected result
  ----------------------- ----------------------- -----------------------
  T-001                   Upload valid TXT        Text extracted

  T-002                   Upload text-based PDF   Page text and
                                                  coordinates extracted

  T-003                   Upload scanned PDF      Clear
                                                  unsupported-format
                                                  warning

  T-004                   Upload malformed PDF    Safe error; no crash

  T-005                   Detect standard email   Correct email candidate

  T-006                   Detect supported        Candidate flagged with
                          obfuscated email        appropriate confidence

  T-007                   Detect phone with       Correct candidate
                          separators/country code 

  T-008                   Product code resembles  Contextual
                          ID                      false-positive handling

  T-009                   Same person appears as  Link proposed with
                          full name and initial   evidence

  T-010                   Ambiguous initial could No silent merge
                          refer to two people     

  T-011                   Reject candidate        Content remains in
                                                  export

  T-012                   Approve candidate       Content replaced in
                                                  export

  T-013                   Approve linked group    All selected linked
                                                  occurrences replaced

  T-014                   Manually add span       Span appears in
                                                  redaction set

  T-015                   Overlapping approved    Deterministic handling
                          spans                   or explicit conflict

  T-016                   Extract exported PDF    Approved source text
                          text                    absent

  T-017                   Inspect output metadata No known source PII
                                                  remains in checked
                                                  metadata

  T-018                   Summary contains        Summary blocked or
                          approved name           regenerated

  T-019                   Summary has PII not in  PII guard flags it
                          source redaction list   

  T-020                   Summary reveals unique  Quasi-identifier guard
                          role/location           flags for review
                          combination             

  T-021                   SLM unavailable         Degraded mode is
                                                  disclosed

  T-022                   Delete document session Temporary files and
                                                  session data cleaned
                                                  per policy
  -----------------------------------------------------------------------

## 6. Robustness tests

-   Empty document.
-   Very long document.
-   Unicode and non-ASCII names.
-   Repeated names.
-   Multiple people with similar names.
-   Header/footer text.
-   Multi-page PDFs.
-   Multi-column PDFs.
-   Text split across PDF spans.
-   Different phone formats.
-   Dates and product codes resembling PII.
-   Invalid offsets and overlapping spans.
-   SLM malformed JSON, timeout and refusal.
-   Export interrupted or disk unavailable.

## 7. Human review usability

Run at least five representative review sessions if feasible. Observe: -
Time to review a document. - Missed candidates. - Incorrect
approvals/rejections. - Ease of identifying linked variants. - Keyboard
shortcut discoverability. - Clarity of confidence and warning labels.

## 8. Evaluation report format

Include: 1. Hardware and software environment. 2. Dataset composition
and annotation method. 3. Model and ruleset versions. 4. Overall and
per-category metrics. 5. Entity-linking results. 6. Redaction integrity
test results. 7. Summary safety results. 8. Runtime and memory
measurements. 9. Failure examples and limitations. 10. Planned
improvements.
