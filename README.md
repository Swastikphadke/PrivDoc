# PrivyDoc (Privacy-Aware Document Redaction & Summary Tool)

PrivyDoc is an enterprise-grade, local-first document redaction and privacy-aware summarization platform designed to sanitize sensitive data (PII/PHI) and generate safe summaries entirely on local hardware.

---

## Key Guarantees & Privacy Architecture

- **100% Local-First Execution**: The backend binds exclusively to `127.0.0.1`. No external APIs, cloud inference services, or third-party trackers are utilized.
- **Strict Storage Separation**:
  - Ephemeral session files (original PDFs/DOCX, canonical extracted text, coordinate mappings) reside temporarily in `backend/data/sessions/{document_id}/` and are deleted upon session termination or TTL expiration.
  - SQLite (`backend/data/privydoc.db`) stores strictly metadata, review decisions, and privacy feedback—never raw document content.
- **Defense-in-Depth Verification**:
  - Extractive fallback summarization runs exclusively on verified sanitized text if local SLMs are unavailable.
  - Native PyMuPDF true redaction with output verification. Clean-text PDF reconstruction offered with explicit layout-loss warnings if native redaction cannot be verified.
  - Configurable quasi-identifier combination risk analysis.

---

## Repository Structure

```
PrivDoc/
├── Docs/                               # Approved architectural and specification docs
│   ├── 01_Project_Overview.md
│   ├── 02_System_Requirements_Document.md
│   ├── 03_Technology_Stack.md
│   ├── 04_System_Architecture.md
│   ├── 05_Processing_Pipeline.md
│   ├── 06_Implementation_Specification.md
│   ├── 07_Development_Phases.md
│   ├── 08_Evaluation_and_Test_Plan.md
│   ├── 09_Deliverables_and_Acceptance.md
│   ├── 10_Privacy_and_Security_Specification.md
│   ├── 11_Database_and_Data_Models.md
│   ├── 12_UI_UX_Specification.md
│   ├── 13_Setup_and_Deployment_Guide.md
│   ├── 14_Risk_Register.md
│   ├── 15_Documentation_Index.md
│   ├── IMPLEMENTATION_STATUS.md       # Phase tracking & task board
│   ├── TECHNICAL_DECISIONS.md         # Technical decision records (TDRs)
│   └── REQUIREMENTS_TRACEABILITY.md   # Requirement-to-test traceability matrix
├── backend/                            # FastAPI backend service (Python 3.11+)
│   ├── app/
│   │   ├── api/                       # API routes and endpoints
│   │   ├── core/                      # Configuration, security, CORS enforcement
│   │   ├── database/                  # SQLite models and connection management
│   │   ├── detectors/                 # PII/PHI detection engines (Regex, Presidio)
│   │   ├── processors/                # Document extraction and PDF redaction
│   │   ├── schemas/                   # Pydantic request and response schemas
│   │   ├── services/                  # Business logic and entity resolution
│   │   └── main.py                    # FastAPI application entry point
│   ├── data/                          # Local SQLite database and ephemeral sessions
│   ├── tests/                         # Pytest test suite
│   └── requirements.txt               # Pinned Python dependencies
├── frontend/                           # React + Vite frontend application
│   ├── src/
│   │   ├── assets/                    # Static assets
│   │   ├── components/                # Reusable UI components (Header, Footer, etc.)
│   │   ├── hooks/                     # Custom React hooks
│   │   ├── pages/                     # Application pages (Dashboard, etc.)
│   │   ├── services/                  # API clients and HTTP communication
│   │   ├── App.jsx                    # Root application component
│   │   ├── main.jsx                   # React DOM entry point
│   │   └── index.css                  # Tailwind CSS styling
│   ├── package.json                   # Pinned frontend dependencies
│   ├── tailwind.config.js             # Tailwind CSS configuration
│   └── vite.config.js                 # Vite development server and proxy config
├── .gitignore                          # Git ignore rules for node, python, sessions
└── README.md                           # Project guide and instructions
```

---

## Prerequisites

- **Python**: 3.11+ (Python 3.12 supported)
- **Node.js**: v18+ (Node v20+ recommended)
- **Package Manager**: `npm` or `pnpm`

---

## Getting Started

### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create and activate a Python virtual environment
python -m venv venv
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run backend development server (binds to 127.0.0.1:8000)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Backend health checks can be verified at:
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/api/health`

### 2. Run Backend Tests

```bash
# Run backend test suite
python -m pytest backend/tests -v
```

### 3. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Run frontend development server (binds to 127.0.0.1:5173)
npm run dev
```

Frontend application will be accessible at:
- `http://127.0.0.1:5173`

### 4. Run Frontend Tests

```bash
cd frontend
npm test
```

---

## Human-in-the-Loop Review Workspace (Phase P4)

PrivyDoc features a minimalist, dark charcoal cybersecurity SaaS review interface built with React, Vite, and Tailwind CSS:

- **Canonical Text Viewer**: Interactive text viewer with exact half-open character offset highlights `[start, end)`. Supports mouse selection for arbitrary manual redactions.
- **Authoritative PDF Viewer**: Renders crisp PyMuPDF page PNG streams with page navigation, zoom, and visual candidate overlays.
- **Candidate Inspection Sidebar**:
  - Detailed metadata cards showing matched text (with mask/reveal toggle), PII category, confidence band (`High`, `Medium`, `Low`—strictly separated from review status), detector sources, and character offsets.
  - Review controls: **Approve**, **Reject**, **Undo**, and inline category reassignment.
  - **Redact All Similar**: Modal providing an explicit, transparent preview of all matching candidate occurrences across the document before bulk approval.
- **Entity Group Resolution**:
  - Entity cluster view displaying canonical identities, observed surface variants, link confidence, and evidence logs.
  - Ambiguity warning flags prevent automated merges between distinct individuals sharing surnames or ambiguous initials.
  - Single-click **Approve Linked Group**, **Reject Linked Group**, and occurrence **Unlink** actions.
- **Keyboard Shortcuts**:
  - `A`: Approve selected candidate for redaction.
  - `R`: Reject selected candidate (preserve text).
  - `M`: Open manual redaction dialog for highlighted text span.
  - *Shortcuts are automatically disabled when typing in text fields, inputs, or textareas.*
- **Export & Summary Previews**:
  - Export screen (Screen D): Format selection (.txt / .pdf), mask patterns (`[REDACTED]`, `[CATEGORY]`, `[ENTITY_N]`, Unicode black bars), approved vs pending verification status, and clean-text fallback options.
  - Privacy Summary screen (Screen E): Sanitized-only input guarantee, extractive fallback status, and post-summary zero-leak audit indicators.

---

## Redaction Engine & Verifiable Export (Phase P5)

PrivyDoc's redaction pipeline guarantees that sensitive data approved for removal is physically eliminated from exported files, rather than covered up visually:

- **Immutable Text Redaction**:
  - Source canonical text is treated as strictly read-only.
  - Approved character offset intervals `[start, end)` are merged to resolve overlaps and contiguous spans, then sorted in descending offset order to eliminate character offset drift.
  - Supports configurable placeholder formats: semantic category labels (`[PERSON]`, `[EMAIL]`, `[PHONE]`), generic privacy masks (`[REDACTED]`), or Unicode solid block characters (`████████`).
  - Unreviewed and rejected candidate spans remain completely untouched.
- **Physical PyMuPDF Stream Redaction**:
  - Approved text occurrences and coordinate bounding boxes are marked with native PDF redaction annotations (`page.add_redact_annot`).
  - Applying redactions (`page.apply_redactions`) physically purges characters and font subsets from the PDF byte stream.
  - Sanitization scrubs document metadata dictionaries, embedded file attachments, and active JavaScript scripts.
- **Clean-Text PDF Reconstruction (DEC-004)**:
  - Native PDF stream redaction is always attempted first by default. If verification fails, export state is set to `FAILED`, temporary artifacts are purged, and download is blocked.
  - Clean-text PDF reconstruction is **never automatically initiated**; it is offered strictly as an explicit, separate user-triggered alternative (`POST /api/documents/{id}/reconstruct-pdf`).
  - Generates a brand-new, clean A4 PDF rendered purely from sanitized text with prominent layout-loss disclosures, and runs the complete independent verification suite before promoting to `VERIFIED`.
- **Post-Export Verification Service**:
  - Re-opens every exported file independently and executes an 8-point audit check:
    1. Export file integrity and readability.
    2. Direct text scan for exact approved PII substrings.
    3. Detection of known surface name variants and aliases.
    4. Normalized pattern scan (digits-only phone numbers, compact IDs).
    5. Annotation hygiene (verifying zero remaining redaction markup or sensitive comments).
    6. PDF metadata cleansing (author, title, producer, subject).
    7. Embedded file attachment audit.
    8. JavaScript and active content purging.
  - **Zero-PII Audit Logging**: Invariant enforcement guarantees verification failure reports never log or expose raw PII strings.
- **Fail-Safe Gatekeeper**:
  - Only exports attaining verified safe status (`VERIFIED`) can be downloaded (`GET /api/documents/{id}/export`). Any unverified or failed export is strictly blocked.

---

## Privacy-Preserving Summarization Engine (Phase P6)

PrivyDoc's summarization pipeline is built with strict architectural boundaries ensuring zero raw data leakage:

- **Strict Sanitized-Only Data Contract (`SanitizedDocument`)**:
  - The summarization engine accepts exclusively a typed `SanitizedDocument` containing verified sanitized text (with `[CATEGORY]` placeholders) and an export verification reference (`P5-VERIFIED`).
  - The summarizer has zero access to raw original documents, original extracted text, original PDF streams, candidate PII objects, or coordinate mappings.
  - Non-verified P5 exports are rejected at the API boundary with HTTP 400.
- **Privacy Guard Architecture (`SummaryGuard`)**:
  - Approved redaction values and entity variants are passed strictly to `SummaryGuard` for post-generation leakage analysis and are never exposed to the summarizer model.
  - Executes a multi-tier safety pipeline:
    1. **Direct Leakage Check**: Scans for exact approved sensitive values and generates token-hashed audit logs (never logs raw PII).
    2. **Alias and Entity Variants Check**: Scans for resolved entity variants and aliases.
    3. **Residual PII Re-detection**: Runs both deterministic regex and contextual NER scans over the summary text to detect hallucinated or residual PII.
    4. **Quasi-Identifier Risk Assessment**: Rule-based evaluation of demographic, departmental, and role-based co-occurrences (`config/quasi_identifiers.json`) with an explicit non-anonymity disclaimer.
    5. **Source Evidence Consistency**: Verifies grounded dates and figures against sanitized text to eliminate hallucinated details.
- **Structured Summary Schema**:
  - Summaries are generated according to a strict JSON schema (`StructuredSummaryContent`) containing narrative summary text, key points, important findings, grounded dates/figures, and source evidence.
- **Deterministic Extractive Fallback**:
  - If the local SLM is unreachable, offline, or times out, the engine seamlessly falls back to a deterministic sentence-scoring algorithm operating strictly on sanitized text while preserving category placeholders.
  - Extractive summaries undergo 100% of the identical privacy verification checks as SLM summaries.
- **Fail-Safe State Machine & Suppression**:
  - Supported lifecycle states: `PENDING`, `GENERATING`, `VERIFYING`, `VERIFIED`, `SUPPRESSED`, `FAILED`, `REQUIRES_REVIEW`.
  - If verification checks fail after a bounded retry loop (max 2 retries = 3 attempts), the summary is transitioned to `SUPPRESSED`.
  - Suppressed summaries are completely blocked from display in the UI, presenting a clear security alert without leaking sensitive text.

---

## Local Feedback System & Evaluation Metrics Framework (Phase P7)

PrivyDoc includes a local-first, privacy-minimized continuous improvement mechanism and rigorous evaluation metrics framework:

- **Feedback Storage with Data Minimization (TDR-015)**:
  - Captures human review interactions (`APPROVE`, `REJECT`, `MANUAL_ADD`, `CATEGORY_CHANGE`, `LINK_ENTITIES`, `UNLINK_ENTITIES`, `MERGE_ENTITIES`) in SQLite `feedback_records`.
  - **Zero Raw Data Retention Guarantee**: Strictly prohibits storing raw document text, surrounding text snippets, original PDF content, or sensitive candidate strings in feedback tables or application logs. Only pseudonymous identifiers, entity IDs, PII categories, detector sources, and confidence scores are recorded.
- **Opt-In Locally Encrypted Aliases**:
  - When users manually link name variants or aliases, relationship events and pseudonymous entity references are stored by default.
  - If actual alias values are required for cross-session matching, users must explicitly opt in (`POST /api/documents/{id}/aliases` with `opt_in_consent=true`).
  - Stored in `opt_in_encrypted_aliases` protected by machine-local **AES-256-GCM** authenticated encryption (`data/.alias_encryption.key`).
  - Supports configurable TTL retention (default 30 days), explicit deletion (`DELETE /api/documents/{id}/aliases`), and automatic cascade deletion when documents are deleted.
- **Controlled Feedback Workflow (TDR-016)**:
  - User feedback **never automatically mutates** active detection regex patterns, classifier weights, or SLM prompts in production.
  - Aggregated feedback patterns produce structured `FeedbackProposal` records (`GET /api/feedback/analysis`) requiring explicit human inspection, code review, and promotion.
- **Synthetic Evaluation Corpus & Quarantined Isolation (TDR-017)**:
  - 100% synthetic, locally generated dataset across 8 realistic difficulty classes (standard business, high-density contact, informal correspondence, multi-page legal agreements, structured invoices, mixed medical summaries, ambiguous initials, and edge formatting).
  - Split into three distinct subsets:
    - `dev/`: 10 documents (development tuning)
    - `val/`: 7 documents (validation and threshold selection)
    - `test/`: 8 documents (quarantined held-out evaluation set, strictly isolated from regex heuristics)
  - Both searchable TXT and PyMuPDF-generated PDFs with validated exact character offsets in `gold_annotations.json`.
- **Reproducible Evaluation Framework**:
  - Exact-span and partial-overlap matching for token-level precision, recall, and F1.
  - Zero-denominator protection: Returns 0.0 with `has_zero_denominator=True` when TP+FP=0 or TP+FN=0 to avoid artificial scores or division-by-zero crashes.
  - Pairwise coreference evaluation engine (B-cubed style Precision, Recall, F1, False Merge Rate, Missed Link Rate).
  - Post-redaction residual leakage verification rate (100% verification target) and post-summary leakage rate.
  - Performance profiling measuring per-phase latency and peak memory allocation using `tracemalloc`.
- **CLI Commands**:
  ```bash
  # Regenerate synthetic evaluation corpus (seed=42)
  python scripts/generate_synthetic_corpus.py

  # Run evaluation harness on quarantined test split
  python scripts/evaluate.py --split test --matching exact --output-md Docs/EVALUATION_REPORT.md --output-json Docs/EVALUATION_METRICS.json

  # Run full evaluation across all splits
  python scripts/evaluate.py --split all --matching overlap
  ```
- **Evaluation Integrity Disclaimer**:
  > [!NOTE]
  > All reported benchmark metrics reflect controlled evaluation on the synthetic test corpus and do not constitute an unconditional guarantee of 100% accuracy on arbitrary, unstructured real-world documents.

---

## System Hardening & Release-Readiness Quality Gates (Phase P8)

Phase P8 enforces rigorous integration, end-to-end reliability, security boundaries, and local hardware profiling:

- **End-to-End Workflow Verification**:
  - Full automated lifecycle tests covering ingestion, detection, candidate review, manual redaction, entity linking, native and fallback redaction, export verification, summarization, privacy guard, export download, and complete session deletion (`backend/tests/test_integration_p8.py`).
  - Supports both `.txt` and text-based `.pdf` documents with coordinate-accurate redactions and physical stream scrubbing.
- **Stale Export Invalidation (TDR-018)**:
  - Any review mutation (`submit_review`, `add_manual_candidate`, `redact_all_similar`, `apply_entity_action`) atomically purges all downstream export files (`sanitized.txt`, `sanitized.pdf`, `export_metadata.json`) and structured summaries (`summary.json`), resetting the document state to `REVIEWING`.
- **Reflected Prompt-Injection Defense (TDR-019)**:
  - Sanitized text passed to SLM summarization is strictly enclosed in `<UNTRUSTED_DOCUMENT_CONTENT>` boundary tags.
  - `SummaryGuard` incorporates Check F to scan for reflected boundary tokens and prompt escape directives, immediately suppressing unsafe output.
- **Entity Resolution Accuracy Root-Cause Resolution (TDR-020)**:
  - Investigated the historical P7 held-out precision score (0.0435) and proved it was an evaluation harness cross-document pooling artifact rather than an algorithmic failure.
  - Document-scoped intra-document coreference precision is **1.0000** (Pairwise F1: 1.0000, False Merge Rate: 0.0000) on the held-out test split. Both scoped and unscoped baseline metrics are preserved side-by-side.
- **Zero Outbound Network Traffic Guarantee**:
  - Verified with network-disabled integration tests: the complete end-to-end pipeline executes with zero outbound external network connections.
- **Complete Deletion Cascade**:
  - `DELETE /api/documents/{id}` and session cleanup purges ephemeral session folders, canonical text, SQLite document records, candidates, decisions, feedback events, and opt-in AES-256-GCM encrypted aliases.
- **Performance Profiling on Local Hardware**:
  - Automated benchmark harness (`scripts/profile_pipeline.py`) profiled on Windows 11 (Intel 4-core / 8-thread, 7.85 GB RAM):
    - Cold Startup: **1094.8 ms** | Warm Startup: **0.7 ms**
    - Complete TXT Pipeline: **969.2 ms** (< 1.0 s)
    - Complete PDF Pipeline: **1024.5 ms** (~1.0 s)
    - Peak Memory Consumption: **1.55 MB** (via `tracemalloc`)

---

## Development Roadmap (P0 - P9)

| Phase | Description | Status |
|---|---|---|
| **P0** | Foundation: Repository Scaffolding, SQLite Foundation, Health Check | **Completed** |
| **P1** | Document Ingestion: TXT & PyMuPDF Text/Bbox Extraction, Canonical Offsets | **Completed** |
| **P2** | Hybrid PII Detection Engine (Deterministic Regex + Contextual NER) | **Completed** |
| **P3** | Entity Resolution: Canonical Identity Clustering, Ambiguity Guard | **Completed** |
| **P4** | Human-in-the-Loop Review UI: Workspace, Modals, Shortcuts, Audit Log | **Completed** |
| **P5** | Redaction Engine & Verifiable PDF True-Redaction / Layout-Loss Fallback | **Completed** |
| **P6** | Privacy-Aware Summarization (Sanitized Only, Local SLM / Extractive Fallback) | **Completed** |
| **P7** | Local Feedback System & Evaluation Metrics Framework | **Completed** |
| **P8** | System Hardening, Local Security Audit, Privacy Boundary Verification | **Completed** |
| **P9** | Final Benchmarking (Recall >= 95%), Demo & Production Release | Planned |

---

## License

Internal Engineering Project — Strict Local Privacy Policy.
