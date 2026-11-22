# 14 --- Risk Register

## 1. Risk scoring

Likelihood and impact are rated Low, Medium or High. Reassess after
implementation and testing.

  ------------------------------------------------------------------------------------
  ID             Risk               Likelihood     Impact         Mitigation /
                                                                  fallback
  -------------- ------------------ -------------- -------------- --------------------
  R-01           SLM too slow or    High           Medium         Quantized smaller
                 memory-heavy                                     model, on-demand
                                                                  loading, selective
                                                                  calls, deterministic
                                                                  fallback

  R-02           Person-name false  High           High           Combine NER, SLM,
                 negatives                                        rules,
                                                                  signatures/headers
                                                                  and manual add

  R-03           False positives on High           Medium         Context validation,
                 codes/dates                                      configurable rules
                                                                  and human review

  R-04           Incorrect alias    Medium         High           Conservative
                 linking                                          thresholds, evidence
                                                                  display, user
                                                                  confirmation

  R-05           PDF layout/offset  Medium         High           Page-coordinate
                 mismatch                                         mapping,
                                                                  representative PDF
                                                                  tests, conservative
                                                                  rebuild fallback

  R-06           PDF redaction      Medium         Critical       Actual redaction
                 leaves recoverable                               application,
                 content                                          reopen/export
                                                                  verification, reject
                                                                  unsupported
                                                                  structures

  R-07           Summary leaks      Medium         High           Quasi-identifier
                 indirect identity                                checks,
                                                                  generalization,
                                                                  human review and
                                                                  suppression

  R-08           Summary            Medium         Medium         Constrained prompts,
                 hallucinates facts                               source consistency
                                                                  checks and user
                                                                  warning

  R-09           Model emits        Medium         Medium         Strict schema
                 malformed or                                     validation, timeouts
                 unsafe output                                    and treat output as
                                                                  untrusted

  R-10           Private data       Medium         High           Redacted logging,
                 retained in                                      controlled
                 logs/temp files                                  workspace, cleanup
                                                                  tests

  R-11           Dependency/model   Low/Medium     High           Verify licenses and
                 license issue                                    record versions
                                                                  before distribution

  R-12           Scope expands      High           Medium         Freeze MVP scope;
                 beyond available                                 defer OCR, DOCX,
                 time                                             cloud and enterprise
                                                                  features

  R-13           Evaluation dataset Medium         High           Held-out documents,
                 too small or easy                                varied formats,
                                                                  manual annotation
                                                                  and transparent
                                                                  limitations

  R-14           Offline claim is   Medium         High           Network-disabled
                 inaccurate                                       end-to-end test
                                                                  after setup

  R-15           UI implies         Medium         High           Separate confidence
                 confidence equals                                and review status
                 approval                                         visually and in data
                                                                  model
  ------------------------------------------------------------------------------------

## 2. Fallback strategy

If local SLM integration is delayed: 1. Complete regex and NER
detection. 2. Keep the SLM adapter interface and mark it unavailable. 3.
Demonstrate local processing and human review. 4. Add contextual SLM
assistance when stable.

If PDF redaction is unreliable: 1. Do not ship visual-only masking. 2.
Rebuild a new PDF from sanitized text where feasible. 3. Disclose layout
loss. 4. Reject files whose structure cannot be safely handled.

If quasi-identifier detection is weak: 1. Use conservative
role/location/date combination rules. 2. Flag summaries for manual
review. 3. Suppress high-risk summaries rather than claiming safety.

## 3. Release blockers

The following are blockers: - Original document content sent to an
external service without explicit opt-in. - Summary generated from
original text. - Export marked safe when verification failed. -
Visual-only PDF masking presented as irreversible redaction. - Unhandled
parser failure that crashes the application. - Raw PII written to
routine logs.
