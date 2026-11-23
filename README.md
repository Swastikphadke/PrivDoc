# PrivyDoc

### Privacy-Aware Document Redaction & Summarization

**"Review. Redact. Verify. Summarize — without exposing the original."**

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI 0.162](https://img.shields.io/badge/FastAPI-0.162-009688?logo=fastapi&logoColor=white)
![React 18.3](https://img.shields.io/badge/React-18.3-61DAFB?logo=react&logoColor=black)
![Tests 201 Passing](https://img.shields.io/badge/Tests-159%20Backend%20%7C%2042%20Frontend-2EA043)
![Runtime Local-First](https://img.shields.io/badge/Runtime-127.0.0.1%20Local--First-F59E0B)

**PrivyDoc** is a local-first document privacy workstation that detects sensitive personal information in **UTF-8 `.txt`** and **text-based `.pdf`** documents, resolves multi-mention entity variants, enforces human-in-the-loop review before physical redaction, independently verifies exported files, and generates structured summaries exclusively from verified sanitized text.

It targets five core Personally Identifiable Information (PII) categories—**`PERSON`**, **`EMAIL`**, **`PHONE`**, **`ADDRESS`**, and **`ID_LIKE`**—while keeping document parsing, entity linking, stream sanitization, and optional Small Language Model (SLM) inference strictly on the local machine (`127.0.0.1`).

---

## Product Preview

![PrivyDoc 3-Panel Document Review Workspace](Docs/screenshots/02_review_workspace_3panel.png)

| Operational Telemetry & Session Launchpad | Entity Coreference & Link Evidence |
| :---: | :---: |
| ![Dashboard](Docs/screenshots/01_dashboard.png) | ![Entity Inspector](Docs/screenshots/03_entity_inspector_clusters.png) |
| **Irreversible Redaction & 8-Point Export Audit** | **Verified Sanitized Summary & SummaryGuard** |
| ![Export Verification](Docs/screenshots/04_export_verification.png) | ![Summary Verified](Docs/screenshots/05_summary_verified.png) |

---

## Why PrivyDoc?

Organizations routinely share audit reports, legal filings, HR records, and incident summaries with external reviewers, vendors, and regulators. Sanitizing these documents reliably is difficult for five reasons:

1. **Manual redaction misses variants:** A reviewer may remove `"Dr. Marcus Vance"` on page 1 while overlooking `"M. Vance"` or `"Mr. Vance"` in a later paragraph.
2. **Cosmetic PDF masking is reversible:** Drawing black rectangles over PDF text leaves underlying character glyphs, annotations, and metadata intact and recoverable via copy-paste or stream extraction.
3. **Purely automated scanners over- or under-redact:** Aggressive regex rules corrupt legitimate business terms (such as `"Project Apollo"` or `"ISO-9001:2015"`), while rigid rules miss contextual names or lightly obfuscated contact details.
4. **Cloud document AI introduces external exposure:** Uploading unredacted files to third-party APIs creates a new data-custody boundary before sanitization even begins.
5. **Unsanitized summarization leaks identity:** Generating summaries from raw source text allows language models to reproduce names, aliases, or identifying context in the summary output.

**Core Engineering Principle:** Finding sensitive information is only part of the problem. PrivyDoc preserves human authority over every redaction decision, physically removes approved spans from the underlying file stream, independently verifies the exported artifact, and guarantees that the summarizer never sees the original document.

---

## Core Capabilities

### 1. Hybrid PII Detection & Explainable Entity Resolution
- **Three-Stage Detection Pipeline:** Combines deterministic regular expressions (`RegexDetector`), two-pass contextual Named Entity Recognition (`NERDetector`), and optional locally executed SLM assistance (`SLMDetector` via Ollama) across five categories: `PERSON`, `EMAIL`, `PHONE`, `ADDRESS`, and `ID_LIKE`.
- **Variant & Coreference Linking:** Groups surface variations of the same identity within a document—such as full names (`"Dr. Richa K. Sharma"`), initials (`"R. K. Sharma"`), honorifics (`"Ms. Sharma"`), obfuscated emails (`user [at] domain [dot] org`), and phonetic transliterations—using cycle-safe Union-Find clustering with structured `link_reasons`.
- **Ambiguity Safeguards:** Refuses to auto-merge ambiguous initials (e.g., `"J. Smith"` when both `"John Smith"` and `"James Smith"` appear) or distinct individuals sharing a surname, flagging them as `AMBIGUOUS_CONFLICT` for human review.
- **Constrained SLM Role:** The local SLM never authorizes redaction independently. Novel SLM detections are held at `PENDING` status (`confidence = 0.65`) for human approval, while corroborating spans contribute to `MULTI_DETECTOR_CONSENSUS`.

### 2. Human-in-the-Loop Review Workstation
- **Three-Panel Review Interface:** Pair an interactive canonical text viewer or synchronized PyMuPDF page renderer with a filterable candidate sidebar and a contextual evidence inspector.
- **Granular & Bulk Controls:** Approve (`A`), Reject (`R`), undo to `PENDING`, reassign PII categories, approve entire linked entity clusters, or trigger **Redact All Similar** across matching strings.
- **Manual Span Selection:** Highlight any unflagged text range in the viewer and press `M` to register a manual redaction candidate with exact Unicode code-point offsets `[start, end)` and PDF bounding boxes.

### 3. Irreversible Physical Redaction & Independent Verification
- **Occurrence-Safe TXT & PDF Sanitization:** Plain-text files are sanitized via descending-offset string replacement (`[CATEGORY]`, `[PERSON_1]`, `[REDACTED]`, or `████`). PDF files undergo native PyMuPDF redaction (`add_redact_annot` + `apply_redactions`) to purge character glyphs from the content stream while preserving rejected identical strings on the same page.
- **Metadata & Hidden-Structure Scrubbing:** Cleanses PDF metadata dictionaries, XMP XML packets, table-of-contents bookmarks, form widgets, links, embedded attachments, and sensitive annotations, saving with `garbage=4, deflate=True, clean=True`.
- **Explicit Clean-Text PDF Reconstruction:** If a complex PDF structure cannot pass native stream verification, export fails closed (`FAILED`) and offers an explicit, user-triggered clean-text PDF rebuild (`POST /api/documents/{id}/reconstruct-pdf`) with layout-change disclosures.
- **Independent 8-Point Audit:** `VerificationService` re-opens every exported `.txt` or `.pdf` from disk to verify file readability, zero residual approved substrings, zero known aliases, annotation/metadata hygiene, and SHA-256 byte integrity before unlocking download.

### 4. Privacy-Safe Summarization (`SanitizedDocument` + `SummaryGuard`)
- **Hard Input Isolation:** `SummaryService` accepts only a validated `SanitizedDocument` containing verified sanitized text and placeholders (`P5-VERIFIED`). It has no access to raw source files, unredacted text, candidate values, or coordinate maps.
- **Local SLM & Extractive Fallback:** Generates structured JSON summaries (narrative, key points, findings, grounded `[§1]` source citations) via local Ollama, or falls back automatically to a deterministic extractive summarizer when Ollama is offline.
- **Six-Tier `SummaryGuard`:** Inspects every generated summary for (A) direct & Base64/hex/URL-encoded leaks, (B) entity alias variants, (C) regex + NER residual PII re-detection, (D) rule-based quasi-identifier co-occurrence risks, (E) source date/figure grounding, and (F) reflected prompt-injection artifacts. Unsafe outputs fail closed to `SUPPRESSED`.

### 5. Privacy-Preserving Feedback & Active Learning
- **Zero-PII Feedback Records:** Reviewer actions are logged in SQLite using pseudonymous IDs, categories, detector provenance, and confidence scores—never raw document text or sensitive substrings.
- **Quorum-Gated Structural Prefix Learning:** When reviewers manually add an organization-specific `ID_LIKE` pattern (e.g., `BDG-99201`) at least twice (`quorum >= 2`), `FeedbackService` learns only the non-PII uppercase prefix (`BDG-*`, filtered against a standard-code blocklist) to flag future occurrences as `PENDING`.
- **Bounded Confidence Calibration & Opt-In Encrypted Aliases:** Adjusts category/source confidence within `[-0.15, +0.10]` after $\ge 3$ review decisions, and supports optional cross-session alias retention encrypted locally with **AES-256-GCM** (`opt_in_consent=true`). Feedback never auto-mutates model weights or production code.

---

## How It Works

```mermaid
flowchart LR
    A["1. Upload\n(.txt / .pdf)"] --> B["2. Canonical Extract\nOffsets & BBoxes"]
    B --> C["3. Hybrid Detect\nRegex + NER + SLM"]
    C --> D["4. Entity Resolution\nVariant Clustering"]
    D --> E["5. Human Review\nApprove / Reject / Add"]
    E --> F["6. Physical Redaction\nStream & Metadata Scrub"]
    F --> G{"7. Verification\n8-Point Audit"}
    G -- "Pass (VERIFIED)" --> H["8. SanitizedDocument\nHard Privacy Boundary"]
    G -- "Fail" --> X["Block Download\n(Fail-Closed)"]
    H --> I["9. Summary + SummaryGuard\nVerified Output Only"]
```

1. **Upload:** Ingest a UTF-8 `.txt` or text-based `.pdf` ($\le 20\text{ MB}$, $\le 500\text{ pages}$).
2. **Extract:** Strip zero-width/bidirectional control characters and map Unicode code-point offsets `[start, end)` and PDF word bounding boxes `[x0, y0, x1, y1]`.
3. **Detect:** Run `RegexDetector`, `NERDetector`, optional `SLMDetector`, and active-learned prefix rules.
4. **Resolve:** Cluster within-document entity variants and isolate ambiguous mentions.
5. **Review:** Inspect evidence in the 3-panel workstation and finalize approvals, rejections, or manual additions.
6. **Redact:** Scrub approved spans from the TXT string or PDF content stream while preserving rejected spans.
7. **Verify:** Re-open the exported artifact from disk and execute the independent verification suite.
8. **Summarize:** Pass only the verified `SanitizedDocument` to `SummaryService` (local SLM or extractive fallback).
9. **Guard & Deliver:** Run `SummaryGuard` checks and expose only verified downloads and leak-checked summaries.

---

## Architecture Overview

| Layer | Primary Components | Responsibility |
| :--- | :--- | :--- |
| **Frontend** | `Dashboard`, `ReviewWorkspace`, `ExportView`, `SummaryView` | 3-panel review workstation, PDF/text highlighting, keyboard shortcuts, verification & summary views |
| **API** | FastAPI (`/api/documents/*`, `/api/feedback/*`, `/health`) | Localhost request routing, strict ID validation (`^[a-zA-Z0-9_\-]{1,64}$`), security headers, CORS |
| **Ingestion** | `TXTProcessor`, `PDFProcessor` | UTF-8 normalization, zero-width/bidi stripping, PyMuPDF word coordinate & rotation/CropBox mapping |
| **Detection** | `DetectionService`, `RegexDetector`, `NERDetector`, `SLMDetector` | Hybrid candidate extraction, 1-to-1 homoglyph folding, role-prefix trimming, span unioning |
| **Entity Resolution** | `EntityResolver` | Category-aware normalization, Union-Find clustering, phonetic matching, ambiguity safeguards |
| **Review & Feedback** | `ReviewService`, `FeedbackService` | Decision state management, downstream artifact invalidation, quorum prefix learning, AES-256-GCM aliases |
| **Redaction** | `RedactionService` | Descending-offset TXT replacement, PyMuPDF stream/metadata/annotation scrubbing, clean-text PDF rebuild |
| **Verification** | `VerificationService` | Independent disk re-extraction, 8-point residual PII & structure audit, SHA-256 digest computation |
| **Summarization** | `SummaryService`, `SummaryGuard`, `ModelService` | `SanitizedDocument` enforcement, `<UNTRUSTED_DOCUMENT_CONTENT>` isolation, 6-tier leak & injection shield |
| **Storage** | SQLite (`privydoc.db`) + `data/sessions/{id}/` | Zero-PII relational metadata separated from ephemeral session files (purged on delete or 24h TTL) |

```mermaid
flowchart TD
    subgraph RawZone ["Untrusted Source & Review Zone (Ephemeral Session)"]
        In["Uploaded .txt / .pdf"] --> Det["Ingestion + Hybrid Detection + Entity Resolution"]
        Det --> Rev["Human-in-the-Loop Review Workspace"]
        Rev --> Red["RedactionService (TXT & PyMuPDF Stream Scrub)"]
        Red --> Ver["VerificationService (8-Point Independent Audit)"]
    end

    subgraph SafeZone ["Sanitized-Only Zone (Zero Raw Text Access)"]
        San["SanitizedDocument Contract (P5-VERIFIED)"]
        Sum["SummaryService (Local Ollama / Extractive Fallback)"]
        Grd["SummaryGuard (6-Tier Privacy & Injection Shield)"]
        Out["Verified Export (.pdf / .txt) & Safe Summary"]
        San --> Sum --> Grd --> Out
    end

    Ver -- "Passes All Checks" --> San
    Rev -. "Any Review Edit Invalidates & Unlinks" .-> San
```

---

## Privacy and Security

- **Localhost Network Binding:** The FastAPI backend binds strictly to `127.0.0.1:8000` (`validate_local_host`) and restricts CORS to local origins (`127.0.0.1:5173`, `localhost:5173`). Optional SLM requests target only local Ollama (`http://127.0.0.1:11434`).
- **Offline Execution Path:** After dependency installation and optional model download, the complete ingestion, detection, review, redaction, verification, and summarization pipeline executes without external network calls (validated by socket-blocked integration tests).
- **Storage Separation & Session Hygiene:** SQLite (`backend/data/privydoc.db`) stores operational metadata, review decisions, and data-minimized feedback records with zero raw document text. Uploaded files and extracted text live in `backend/data/sessions/{document_id}/` and are deleted on manual session purge (`DELETE /api/documents/{id}`) or startup TTL cleanup (`SESSION_TTL_HOURS=24`).
- **Optional Encrypted Aliases:** Cross-session alias retention is disabled by default; when explicitly enabled (`opt_in_consent=true`), alias ciphertexts are encrypted with **AES-256-GCM** using a local 256-bit key (`backend/data/.alias_encryption.key`).
- **Stale Artifact Invalidation:** Any review mutation (approving, rejecting, manual addition, category change, or entity linking/unlinking) atomically deletes existing `sanitized.txt`, `sanitized.pdf`, `export_metadata.json`, and `summary.json` files and resets session status to `REVIEWING`.
- **Adversarial Input Hardening (`SEC-01`–`SEC-07`):** Normalizes zero-width/bidirectional characters and single-codepoint Cyrillic/Greek homoglyphs, enforces file/page/character bounds (`20 MB`, `500 pages`, `2,000,000 chars`), wraps summarizer input in randomized `<UNTRUSTED_DOCUMENT_CONTENT_{nonce}>` delimiters, and fails closed when verification or `SummaryGuard` checks fail.
- **Host Trust Boundary:** Localhost binding prevents LAN exposure and cloud egress, but does not protect against a compromised host OS or malicious local processes running under the same user account. See [Privacy and Security Specification](Docs/10_Privacy_and_Security_Specification.md) for the complete threat model.

---

## Supported Inputs and Limitations

| Capability / Input Type | Support Status | Operational Behavior & Notes |
| :--- | :---: | :--- |
| **UTF-8 Plain Text (`.txt`)** | **Supported** | Up to 20 MB / 2,000,000 characters; exact Unicode code-point offset redaction |
| **Text-Based Digital PDF (`.pdf`)** | **Supported** | Up to 20 MB / 500 pages; native PyMuPDF glyph stream & metadata redaction |
| **Scanned / Image-Only PDF** | **Unsupported** | Rejected at ingestion (`IMAGE_ONLY_PDF_NOT_SUPPORTED`); run OCR beforehand |
| **Password-Protected / Encrypted PDF** | **Unsupported** | Rejected at ingestion (`ENCRYPTED_FILE_REJECTED`) |
| **Rasterized Text in Embedded Images** | **Unsupported** | Embedded bitmap images inside hybrid PDFs are not OCR-scanned |
| **Vector Glyph Outlines / Dynamic XFA** | **Reconstruction Only** | Native stream verification fails closed; explicit clean-text PDF rebuild offered |
| **Supported PII Categories** | **5 Categories** | `PERSON`, `EMAIL`, `PHONE`, `ADDRESS`, `ID_LIKE` |

**Disclosed Operational Limitations:**
- **Lowercase & Diacritic Names:** Heuristic contextual NER relies on capitalization cues and ASCII character ranges; lowercase names in informal notes (e.g., `"rohit verma"`) or names with non-ASCII diacritics (e.g., `"Renée Müller"`) without header labels may require manual selection (`M`).
- **Unconfigured Identifier Prefixes:** Out-of-the-box `ID_LIKE` regex targets standard patterns (`EMP-`, `STU-`, `ACC-`, `CUST-`, `PAN`, `Aadhaar`, `SSN`). Custom organizational prefixes (`BDG-`, `TRK-`) require manual selection or activation via the quorum-gated active-learning loop ($\ge 2$ manual additions).
- **Pseudonymization vs. Mathematical Anonymity:** Entity-indexed placeholders (`[PERSON_1]`) and rule-based quasi-identifier checks improve readability and flag high-risk co-occurrences, but do not provide mathematical $k$-anonymity or differential privacy.
- **Single-User Workstation Scope:** Designed for local single-user execution without multi-tenant authentication or RBAC. See [Known Limitations](Docs/KNOWN_LIMITATIONS.md) for full details.

---

## Technology Stack

| Layer | Technology | Version | Engineering Rationale |
| :--- | :--- | :--- | :--- |
| **Frontend UI** | React, Vite, Tailwind CSS, React Router, Axios, Lucide | React `^18.3.1`, Vite `^6.0.3`, Tailwind `^3.4.16` | Fast local SPA workstation with responsive 3-panel inspection and keyboard-driven review |
| **Backend API** | Python, FastAPI, Pydantic v2, Uvicorn | Python `3.11+` (`3.12`), FastAPI `0.162.0`, Pydantic `2.14.2` | Strict schema validation (`SanitizedDocument`, `SLMAnalysisResponse`) at every service boundary |
| **Document Engine** | PyMuPDF (`fitz`) | `>=1.24.0` (`1.25.x`) | Word-level PDF bounding-box extraction, page derotation, and physical stream redaction |
| **Detection & Linking** | Regex, Custom NER / spaCy, RapidFuzz | `spacy>=3.7.0`, `rapidfuzz>=3.9.0` | High-precision structured pattern matching paired with fuzzy and phonetic entity coreference |
| **Local SLM Runtime** | Ollama (`qwen2.5:1.5b-instruct`) | Local HTTP (`127.0.0.1:11434`) | Zero-egress contextual candidate proposals and summarization with deterministic offline fallback |
| **Storage & Crypto** | SQLite 3, `cryptography` (`AESGCM`), `hashlib` | SQLite `3`, AES-256-GCM, SHA-256 | Zero-PII metadata persistence, authenticated alias encryption, and post-export byte integrity |
| **Testing & Profiling** | Pytest, HTTPX, Vitest, React Testing Library, `psutil` | Pytest `9.2.0`, Vitest `^2.1.8` | 159 backend and 42 frontend automated tests across unit, adversarial, and E2E workflows |

---

## Installation and Quick Start

### Prerequisites
- **Python:** `3.11+` (`3.12` recommended)
- **Node.js:** `18.0+` (with `npm`)
- **Optional Local SLM:** [Ollama](https://ollama.com) running locally on `127.0.0.1:11434`

### 1. Clone the Repository
```bash
git clone https://github.com/Swastikphadke/PrivDoc.git
cd PrivDoc
```

### 2. Backend Setup
```powershell
cd backend
python -m venv venv

# Activate on Windows PowerShell:
.\venv\Scripts\Activate.ps1

# Or activate on macOS / Linux:
# source venv/bin/activate

pip install -r requirements.txt
```

### 3. Frontend Setup
```bash
cd ../frontend
npm install
```

### 4. Optional: Local Ollama Model Setup
PrivyDoc works out of the box without Ollama using its deterministic `Regex + NER` detection pipeline and extractive summary fallback. To enable local SLM candidate assistance and generative summarization:
```bash
ollama pull qwen2.5:1.5b-instruct
ollama serve
```
*(Optional configuration overrides can be placed in `backend/.env` for `HOST`, `PORT`, `MAX_UPLOAD_SIZE_MB`, `SESSION_TTL_HOURS`, `LOCAL_SLM_URL`, `SLM_MODEL_NAME`, and `SLM_TIMEOUT_SECONDS`; see [`backend/app/core/config.py`](backend/app/core/config.py).)*

### 5. Start the Workstation
Run the backend and frontend in two separate terminals:

**Terminal 1 — Backend (`http://127.0.0.1:8000`):**
```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 — Frontend (`http://127.0.0.1:5173`):**
```bash
cd frontend
npm run dev
```

- **Workstation UI:** `http://127.0.0.1:5173`
- **Health Check Endpoints:** `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/api/health`

---

## Usage Walkthrough

1. **Upload a Document:** Open `http://127.0.0.1:5173` and upload a `.txt` or `.pdf` file (or use the synthetic fixtures in `datasets/demo/demo_sample_report.pdf`).
2. **Inspect Candidates & Evidence:** In the **Review Workspace**, switch between **Canonical Text** and **PDF View**. Click any highlighted span to inspect detector provenance, confidence weight, and why the span was flagged.
3. **Approve, Reject, or Link Entities:** Press `A` to approve sensitive items for removal or `R` to reject false positives (preserving them in the output). Switch to the **Entities** tab to approve entire linked name clusters (`"Dr. Marcus Vance"` $\leftrightarrow$ `"M. Vance"`) or manually link/unlink mentions.
4. **Add Manual Redactions:** Highlight any unflagged text with your cursor and press `M` to add a custom redaction span.
5. **Redact & Verify Export:** Open **2. Redact & Verify**, choose a placeholder pattern (`[CATEGORY]`, `[CATEGORY_#]`, `[REDACTED]`, or block mask), and click **Execute Redaction & Verify Output**. Inspect the 8-point verification audit and SHA-256 digest before downloading the verified `.pdf` or `.txt`.
6. **Generate a Safe Summary:** Open **3. Safe Summary** to generate a structured summary from the `SanitizedDocument` payload, complete with `[§1]` source evidence grounding, `SummaryGuard` check results, and quasi-identifier risk assessment.
7. **Purge Session:** Click the session delete action to wipe all temporary session files and metadata rows.

For detailed operating instructions and a scripted 15-minute walkthrough, see the [User Guide](Docs/USER_GUIDE.md) and [Demo Guide](Docs/DEMO_GUIDE.md).

---

## Evaluation and Performance

PrivyDoc is evaluated on two frozen synthetic benchmarks totaling **61 documents (122 TXT and PDF files, 305 gold PII spans, and 3 negative 0-PII documents)**: **Suite V1** (`datasets/evaluation`, 25 docs) and **Suite V2** (`datasets/evaluation_stage4`, 36 docs across 17 challenge categories).

| Evaluation Dimension | Benchmark / Scope | Measured Result | Context & Notes |
| :--- | :--- | :---: | :--- |
| **Suite V2 Held-Out Micro F1 (Exact)** | `datasets/evaluation_stage4/test` (12 docs, 56 spans) | **90.74%** | `P = 94.23%`, `R = 87.50%` (`TP = 49, FP = 3, FN = 7`); Overlap Micro F1: **92.59%** |
| **Suite V2 Held-Out Macro F1 (Exact)** | `datasets/evaluation_stage4/test` (5 categories) | **92.62%** | `EMAIL: 100%` · `ID_LIKE: 96.30%` · `PHONE: 93.33%` · `ADDRESS: 85.71%` · `PERSON: 85.11%` |
| **Suite V1 Held-Out Micro F1 (Exact)** | `datasets/evaluation/test` (8 docs, 45 spans) | **89.89%** | `P = 90.91%`, `R = 88.89%` (`TP = 40, FP = 4, FN = 5`); Overlap Micro F1: **92.13%** |
| **Negative (0-PII) False Positives** | 3 negative vendor/regulatory documents | **0 FPs** | Zero false alarms on non-PII corporate and ISO compliance documents |
| **Within-Document Entity Resolution** | Suite V1 (`5` pos / `775` neg pairs) & V2 (`8` pos / `1,168` neg) | **1.0000 Pairwise F1** | `0` false merges; `100%` ambiguity safeguard rate on conflicting initials/surnames |
| **Approved-Item Physical Removal** | 35 redaction verification scenarios (`38` unit/adversarial tests) | **100.0%** | `100.0%` rejected span preservation (including identical strings on the same PDF page) |
| **Summary Privacy Safety** | 19 automated `SummaryGuard` scenarios | **0.0% PII Leakage** | `100%` fail-closed suppression on injected leaks and prompt-injection payloads |
| **Automated Test Suites** | Backend (`pytest`) + Frontend (`vitest`) | **159 + 42 Passed** | `201` total automated tests passing (`0` failures) |
| **End-to-End Pipeline Latency** | 4-core / 8-thread CPU, 7.85 GB RAM (Windows 11) | **~1.29 s (TXT) / ~1.39 s (PDF)** | Upload through verified export and extractive summary (`2.01 ms/doc` warm hybrid detection) |
| **Application Process Memory** | OS Resident Set Size (`psutil` RSS) | **~87.33 MB** | Python + PyMuPDF process RSS (excludes external Ollama process; Python heap delta: `1.58 MB`) |

**Evaluation Scope & SLM Distinction:**
- All benchmark scores reflect controlled synthetic datasets and do not guarantee identical accuracy on arbitrary real-world documents.
- On the held-out benchmark suites, `90.74%` exact micro F1 (Suite V2) and `89.89%` (Suite V1) were achieved by the deterministic `Regex + NER` pipeline without requiring Ollama online. In controlled ablation tests on untitled narrative aliases (`test_stage2_audit_slm_ablation_and_failure_safety`), local SLM proposals increased recall from `0.50` to `1.00` while keeping all novel SLM suggestions in `PENDING` review state.

```bash
# Run backend & frontend test suites
python -m pytest backend/tests -v
npm --prefix frontend test

# Run held-out benchmark evaluations and hardware profiler
python scripts/evaluate.py --dataset-dir datasets/evaluation --split test --matching exact
python scripts/evaluate.py --dataset-dir datasets/evaluation_stage4 --split all --matching exact
python scripts/profile_pipeline.py
```

Full methodology, confusion matrices, and failure analyses are documented in [Docs/EVALUATION_REPORT.md](Docs/EVALUATION_REPORT.md) and [Docs/EVALUATION_METRICS.json](Docs/EVALUATION_METRICS.json).

---

## Documentation Index

| Document | Path | Purpose |
| :--- | :--- | :--- |
| **System Architecture** | [`Docs/ARCHITECTURE.md`](Docs/ARCHITECTURE.md) | Layered system design, pipeline stages, storage layout, and privacy boundaries |
| **Privacy & Security Specification** | [`Docs/10_Privacy_and_Security_Specification.md`](Docs/10_Privacy_and_Security_Specification.md) | Threat model, data lifecycle, and adversarial hardening controls (`SEC-01`–`SEC-07`) |
| **Evaluation & Benchmark Report** | [`Docs/EVALUATION_REPORT.md`](Docs/EVALUATION_REPORT.md) | Suite V1/V2 metrics, ablations, entity resolution, latency, and error analysis |
| **Evaluation Metrics Artifact** | [`Docs/EVALUATION_METRICS.json`](Docs/EVALUATION_METRICS.json) | Machine-readable benchmark outputs and dataset integrity SHA-256 hashes |
| **Known Limitations** | [`Docs/KNOWN_LIMITATIONS.md`](Docs/KNOWN_LIMITATIONS.md) | Supported input scope, format boundaries, and residual re-identification risks |
| **User Guide** | [`Docs/USER_GUIDE.md`](Docs/USER_GUIDE.md) | Step-by-step workstation operating instructions, shortcuts, and troubleshooting |
| **Demonstration Guide** | [`Docs/DEMO_GUIDE.md`](Docs/DEMO_GUIDE.md) | Reproducible 4-part walkthrough using synthetic fixtures in [`datasets/demo/`](datasets/demo/DEMO_FIXTURES_SPECIFICATION.md) |
| **Technical Decisions Record** | [`Docs/TECHNICAL_DECISIONS.md`](Docs/TECHNICAL_DECISIONS.md) | Architectural decision records (`TDR-001` through `TDR-021`) |
| **Requirements Traceability** | [`Docs/REQUIREMENTS_TRACEABILITY.md`](Docs/REQUIREMENTS_TRACEABILITY.md) | End-to-end mapping of functional and non-functional requirements to tests |

---

## Project Status and Licensing

- **Project Status:** Completed academic engineering and privacy-workstation release baseline (`v1.0.0`, Problem Statement `PS3`).
- **License:** No open-source license file is currently attached to this repository. All rights are reserved by the author for academic evaluation and portfolio review unless otherwise specified.
