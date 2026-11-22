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

## Development Roadmap (P0 - P9)

| Phase | Description | Status |
|---|---|---|
| **P0** | Foundation: Repository, Backend/Frontend Scaffolding, Health Check | **Completed** |
| **P1** | Document Ingestion: Text/PDF/DOCX Extraction & Session Handling | Pending |
| **P2** | Hybrid PII Detection Engine (Regex, Presidio, Custom Pattern Bank) | Pending |
| **P3** | Global Entity Resolution & Cross-Document Consistency | Pending |
| **P4** | Interactive Human Review Interface (Review Queue, Overrides) | Pending |
| **P5** | Redaction Engine & Verifiable PDF True-Redaction / Fallback | Pending |
| **P6** | Privacy-Aware Summarization (Sanitized Only, Local SLM / Extractive) | Pending |
| **P7** | Export System (PDF, DOCX, TXT, JSON Audit Certificate) | Pending |
| **P8** | System Hardening, Local Security Audit, Privacy Guarantees | Pending |
| **P9** | Evaluation, Benchmarking (Recall >= 95%), Release Documentation | Pending |

---

## License

Internal Engineering Project — Strict Local Privacy Policy.
