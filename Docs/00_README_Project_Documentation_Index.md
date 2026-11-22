# PrivyDoc --- Project Documentation Index

**Project:** Privacy-Aware Document Redaction and Summary Tool\
**Domain:** Cybersecurity \| Applied AI / NLP \| Privacy-Preserving
Computing\
**Documentation status:** Baseline v1.0\
**Implementation approach:** Local-first, human-in-the-loop,
SLM-assisted

## 1. Purpose of this documentation pack

This pack is the working source of truth for planning, implementing,
testing, demonstrating and maintaining PrivyDoc. Requirements in the SRD
take precedence over informal feature ideas. Architecture and
implementation documents describe how those requirements are to be
realized.

## 2. Document index

  --------------------------------------------------------------------------------
  File                                         Purpose
  -------------------------------------------- -----------------------------------
  `01_Project_Overview_PD.md`                  Product vision, problem, goals,
                                               scope and users

  `02_SRD.md`                                  Functional and non-functional
                                               requirements

  `03_Technology_Stack.md`                     Selected technologies and decision
                                               rationale

  `04_System_Architecture.md`                  Components, boundaries and system
                                               architecture

  `05_Processing_Pipeline.md`                  End-to-end document processing and
                                               privacy gates

  `06_Implementation_Specification.md`         Modules, API contracts and
                                               engineering rules

  `07_Development_Phases.md`                   Ordered development plan and
                                               milestones

  `08_Evaluation_and_Test_Plan.md`             Dataset, metrics, test cases and
                                               acceptance criteria

  `09_Deliverables_and_Acceptance.md`          Final outputs and definition of
                                               done

  `10_Privacy_and_Security_Specification.md`   Threat model, data lifecycle and
                                               security controls

  `11_Database_and_Data_Models.md`             Internal data structures and
                                               persistence

  `12_UI_UX_Specification.md`                  Screens, interactions and review
                                               workflow

  `13_Setup_and_Deployment_Guide.md`           Local installation and operation

  `14_Risk_Register.md`                        Risks, mitigations and fallback
                                               options
  --------------------------------------------------------------------------------

## 3. Product principles

1.  **Local-first:** document content should remain on the user's
    machine during normal operation.
2.  **Human approval:** detection produces candidates; it does not
    authorize removal.
3.  **Fail visibly:** uncertain or unsupported processing must be
    reported, not silently treated as safe.
4.  **Redact before summarize:** the summarizer receives sanitized text
    only.
5.  **Verify outputs:** exported files and summaries are checked after
    generation.
6.  **Trace decisions:** each candidate has a type, source, confidence,
    offsets and review status.
7.  **No false guarantees:** automated checks reduce risk but cannot
    prove that every indirect identification risk has been eliminated.

## 4. Baseline scope

-   Input: UTF-8 TXT and text-based PDF.
-   Out of scope for baseline: scanned/image-only PDF OCR, DOCX,
    spreadsheets, image files, cloud processing and multi-user
    enterprise deployment.
-   PII classes: person names and variants, email addresses, phone
    numbers, postal/street addresses, and configurable ID-like strings.
-   Outputs: redacted TXT/PDF, safe summary, review metadata and
    evaluation report.

## 5. Terminology

-   **PII:** personally identifiable information.
-   **Candidate:** a possible sensitive span returned by one or more
    detectors.
-   **Occurrence:** one appearance of a string in a document.
-   **Entity:** a real-world person or identifier to which one or more
    occurrences may belong.
-   **Alias/variant:** another textual reference believed to identify
    the same entity.
-   **Approved redaction:** a candidate or occurrence explicitly
    approved by the user.
-   **Sanitized text:** text produced after approved replacements and
    validated for removal.
-   **Quasi-identifier:** information that may identify a person when
    combined with other facts.
-   **SLM:** small language model used for contextual assistance.

## 6. Requirement and change control

Assign stable IDs to requirements and tests. A requirement change must
be reflected in the SRD, implementation specification, tests and
acceptance checklist. Do not treat a feature as complete solely because
its UI exists.

## 7. Recommended build order

Follow `07_Development_Phases.md`. Build a working vertical slice early:
upload → extract → detect → review → redact → verify. Add model
sophistication only after this path is reliable.
