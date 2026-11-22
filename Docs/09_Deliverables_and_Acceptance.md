# 09 --- Deliverables and Acceptance Criteria

## 1. Software deliverables

  -----------------------------------------------------------------------
  ID                      Deliverable             Required contents
  ----------------------- ----------------------- -----------------------
  D-01                    Source repository       Frontend, backend,
                                                  tests, configuration
                                                  and `.gitignore`

  D-02                    Working application     Local upload, review,
                                                  redaction, export and
                                                  summary workflow

  D-03                    Detection engine        Regex, NER and
                                                  SLM-assisted candidate
                                                  detection

  D-04                    Entity resolution       Name variant grouping
                                                  and reviewable links

  D-05                    Redaction engine        TXT and PDF
                                                  sanitization

  D-06                    Verification engine     Export and summary
                                                  checks

  D-07                    Feedback mechanism      Local corrections and
                                                  review feedback

  D-08                    Evaluation corpus       Synthetic/authorized
                                                  documents and gold
                                                  annotations

  D-09                    Evaluation report       Metrics, test results
                                                  and limitations

  D-10                    Documentation           Setup, architecture,
                                                  requirements, model and
                                                  user guides

  D-11                    Demo package            Demo documents,
                                                  walkthrough and
                                                  screenshots

  D-12                    Presentation            Problem, approach,
                                                  architecture,
                                                  implementation,
                                                  evaluation and future
                                                  work
  -----------------------------------------------------------------------

## 2. Required documentation

-   Project overview / product definition.
-   Software requirements document.
-   Technology stack and rationale.
-   System architecture.
-   Processing pipeline.
-   Implementation specification.
-   Development phases.
-   Evaluation and test plan.
-   Privacy/security specification.
-   Database/data model.
-   UI/UX specification.
-   Setup/deployment guide.
-   Risk register.
-   User guide and limitations.

## 3. Acceptance checklist

### Input and detection

-   [ ] TXT upload works.
-   [ ] Text-based PDF upload works.
-   [ ] Image-only PDFs are rejected clearly.
-   [ ] All five PII categories have a detection path.
-   [ ] Candidate spans and offsets are accurate.
-   [ ] Detection provenance and confidence are visible.
-   [ ] Name variants are linked conservatively.

### Human review

-   [ ] Highlights map to correct source text.
-   [ ] Approve and reject work.
-   [ ] Manual redaction works.
-   [ ] Bulk/group redaction works.
-   [ ] Keyboard shortcuts work.
-   [ ] No removal occurs before approval.

### Redaction

-   [ ] TXT export contains placeholders for approved spans.
-   [ ] PDF export applies actual redaction.
-   [ ] Approved text cannot be recovered by supported extraction
    checks.
-   [ ] Metadata and annotations are inspected.
-   [ ] Failed verification blocks a safe-export claim.

### Summary

-   [ ] Summarizer receives sanitized text only.
-   [ ] Exact values and known aliases are checked.
-   [ ] Summary PII scan runs.
-   [ ] Quasi-identifier checks run.
-   [ ] Unsafe or uncertain summaries are suppressed or flagged.
-   [ ] Summary is factually consistent with sanitized source.

### Privacy and usability

-   [ ] No external API receives original document content.
-   [ ] Temporary file cleanup works.
-   [ ] Logs do not expose raw PII.
-   [ ] Errors are clear and recoverable.
-   [ ] Evaluation report includes per-category metrics.
-   [ ] Demo can be reproduced from setup instructions.

## 4. Definition of done

The project is not complete merely because the UI renders or the model
returns candidates. It is complete when the primary end-to-end workflow
passes the acceptance tests, exports are verified, the summary boundary
is enforced, and limitations are documented.

## 5. Demo deliverables

Prepare: - One ordinary business report. - One document with multiple
name variants. - One document with tricky false positives. - One
text-based PDF. - One unsafe summary example that is blocked. - A short
demonstration of extraction verification. - A recorded evaluation result
with actual measured values.
