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

## Development Roadmap (P0 - P9)

| Phase | Description | Status |
|---|---|---|
| **P0** | Foundation: Repository Scaffolding, SQLite Foundation, Health Check | **Completed** |
| **P1** | Document Ingestion: TXT & PyMuPDF Text/Bbox Extraction, Canonical Offsets | **Completed** |
| **P2** | Hybrid PII Detection Engine (Deterministic Regex + Contextual NER) | **Completed** |
| **P3** | Entity Resolution: Canonical Identity Clustering, Ambiguity Guard | **Completed** |
| **P4** | Human-in-the-Loop Review UI: Workspace, Modals, Shortcuts, Audit Log | **Completed** |
| **P5** | Redaction Engine & Verifiable PDF True-Redaction / Layout-Loss Fallback | **Completed** |
| **P6** | Privacy-Aware Summarization (Sanitized Only, Local SLM / Extractive Fallback) | Planned |
| **P7** | Local Feedback System & Evaluation Metrics Framework | Planned |
| **P8** | System Hardening, Local Security Audit, Privacy Boundary Verification | Planned |
| **P9** | Final Benchmarking (Recall >= 95%), Demo & Production Release | Planned |

---

## License

Internal Engineering Project — Strict Local Privacy Policy.
