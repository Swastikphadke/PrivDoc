# PrivyDoc

### Privacy-Aware Document Redaction & Summarization

**"Review. Redact. Verify. Summarize — without exposing the original."**

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI 0.162](https://img.shields.io/badge/FastAPI-0.162-009688?logo=fastapi&logoColor=white)
![React 18.3](https://img.shields.io/badge/React-18.3.1-61DAFB?logo=react&logoColor=black)
![Tests 201 Passing](https://img.shields.io/badge/Tests-159%20Backend%20%7C%2042%20Frontend-2EA043)
![Runtime Localhost](https://img.shields.io/badge/Runtime-127.0.0.1%20Localhost-F59E0B)

**PrivyDoc** is a local-first document privacy workstation for **UTF-8 `.txt`** and **text-based `.pdf`** files. It detects sensitive personal information across five categories (**`PERSON`**, **`EMAIL`**, **`PHONE`**, **`ADDRESS`**, and **`ID_LIKE`**), links multi-mention entity variants, requires human-in-the-loop approval before redaction, independently verifies exported artifacts, and generates structured summaries exclusively from verified sanitized text.

In its standard configuration, document parsing, entity resolution, stream sanitization, and optional Small Language Model (SLM) inference via **Ollama** run locally on `127.0.0.1` without sending document content to external cloud APIs.

---

## Product Preview

![PrivyDoc 3-Panel Document Review Workspace](Docs/screenshots/02_review_workspace_3panel.png)
*Three-panel Review Workspace: canonical text and PDF viewer (left), filterable candidate & entity list (center), and contextual evidence inspector (right).*

| Operational Dashboard & Session Launchpad | Entity Coreference & Link Explanations |
| :---: | :---: |
| ![Dashboard](Docs/screenshots/01_dashboard.png) | ![Entity Inspector](Docs/screenshots/03_entity_inspector_clusters.png) |
| **Redaction Configuration & Post-Export Audit** | **Sanitized-Only Summary & SummaryGuard** |
| ![Export Verification](Docs/screenshots/04_export_verification.png) | ![Summary Verified](Docs/screenshots/05_summary_verified.png) |

---

## Why PrivyDoc?

Organizations regularly share audit reports, legal filings, HR records, and incident summaries with external reviewers, vendors, and regulators. Sanitizing these documents reliably involves five recurring failure modes:

1. **Missed name variants:** Removing `"Dr. Marcus Vance"` on page 1 while overlooking `"M. Vance"` or `"Mr. Vance"` in later paragraphs leaks identity.
2. **Cosmetic PDF masking:** Drawing black rectangles over PDF text leaves the underlying character glyphs, annotations, and metadata intact and recoverable via copy-paste or stream extraction.
3. **Static scanner over- and under-redaction:** Aggressive regex rules corrupt legitimate business terms (`"Project Apollo"`, `"ISO-9001:2015"`), while rigid rules miss contextual names or lightly obfuscated contact details.
4. **Cloud document AI exposure:** Uploading unredacted files to third-party hosted APIs introduces an external data-custody boundary prior to sanitization.
5. **Summary leakage:** Generating summaries from raw source text allows language models to reproduce names, aliases, or identifying context in the summary output.

**Core Design Principle:** Finding sensitive information is only part of the problem. The system must preserve reviewer control, remove approved spans from the exported document stream, verify the resulting artifact before download, and isolate summarization to verified sanitized content.

---

## Core Capabilities

### 1. Hybrid PII Detection & Explainable Entity Resolution
- **Three-Stage Detection Pipeline:** Combines deterministic regular expressions (`RegexDetector`), a two-pass contextual linguistic NER detector (`NERDetector`), and optional locally executed SLM assistance (`SLMDetector` via Ollama) across `PERSON`, `EMAIL`, `PHONE`, `ADDRESS`, and `ID_LIKE`.
- **Variant & Coreference Linking:** Clusters within-document surface variations—such as full names (`"Dr. Richa K. Sharma"`), initials (`"R. K. Sharma"`), honorifics (`"Ms. Sharma"`), obfuscated emails (`user [at] domain [dot] org`), and phonetic transliterations—using Union-Find transitive closure with structured `link_reasons`.
- **Ambiguity Safeguards:** Refuses to auto-merge ambiguous initials (e.g., `"J. Smith"` when both `"John Smith"` and `"James Smith"` appear) or distinct individuals sharing a surname, flagging them as `AMBIGUOUS_CONFLICT` for human review.
- **Constrained SLM Role:** The local SLM never authorizes redaction independently. Novel SLM detections remain in `PENDING` status (`confidence = 0.65`) until reviewed by a human, while corroborating spans contribute to `MULTI_DETECTOR_CONSENSUS`.

### 2. Human-in-the-Loop Review Workstation
- **Three-Panel Review Interface:** Combines a canonical text viewer and synchronized PyMuPDF page renderer with a filterable candidate sidebar and a contextual evidence inspector.
- **Granular & Bulk Actions:** Approve (`A`), Reject (`R`), reset to `PENDING`, reassign PII categories, approve entire linked entity clusters, or apply **Redact All Similar** across matching normalized strings.
- **Manual Span Selection:** Highlight any unflagged text range in the viewer and press `M` to register a manual redaction candidate with exact Unicode code-point offsets `[start, end)` and PDF bounding boxes.

### 3. Physical Redaction & Independent Export Verification
- **Occurrence-Safe TXT & PDF Sanitization:** Plain-text files are sanitized via descending-offset string replacement (`[CATEGORY]`, `[PERSON_1]`, `[REDACTED]`, or `████████`). Digital PDFs undergo native PyMuPDF redaction (`add_redact_annot` + `apply_redactions`) to remove extractable character glyphs intersecting approved bounding boxes while preserving rejected identical strings on the same page.
- **Metadata & Structure Scrubbing:** Cleanses PDF metadata dictionaries, XMP XML packets, table-of-contents bookmarks, form widget values, link URIs, embedded attachments, and non-redaction annotations containing approved PII, saving with `garbage=4, deflate=True, clean=True`.
- **Explicit Clean-Text PDF Reconstruction:** If a PDF contains unsupported structures or fails native verification, export fails closed (`FAILED`) and offers an explicit, user-triggered clean-text PDF rebuild (`POST /api/documents/{id}/reconstruct-pdf`) with layout-change disclosures.
- **Independent Post-Export Audit:** `VerificationService` re-opens every exported `.txt` (4 checks) or `.pdf` (8 checks) from disk to verify file readability, absence of approved extractable text and known variants, metadata/annotation hygiene, and SHA-256 byte integrity before unlocking download.

### 4. Privacy-Safe Summarization (`SanitizedDocument` + `SummaryGuard`)
- **Hard Input Isolation:** `SummaryService` accepts only a validated `SanitizedDocument` containing verified sanitized text and placeholders (`export_verification_ref="P5-VERIFIED"`). It has no access to raw source files, unredacted text, candidate values, or coordinate maps.
- **Local SLM & Extractive Fallback:** Generates structured JSON summaries (narrative, key points, findings, grounded `[§1]` source citations) via local Ollama, or falls back automatically to a deterministic extractive summarizer when Ollama is offline.
- **Six-Tier `SummaryGuard`:** Inspects every generated summary for (A) direct & Base64/hex/URL-encoded leaks, (B) entity alias variants, (C) regex + NER residual PII re-detection, (D) rule-based quasi-identifier co-occurrence risks, (E) source date/figure grounding, and (F) reflected prompt-injection artifacts. Unsafe outputs fail closed to `SUPPRESSED`.

### 5. Privacy-Preserving Feedback & Active Learning
- **Data-Minimized Feedback Records:** Reviewer decisions are logged in SQLite (`feedback_records`) using pseudonymous IDs, categories, detector sources, and confidence scores—without storing raw document text or sensitive substrings.
- **Quorum-Gated Structural Prefix Learning:** When reviewers manually add an organization-specific `ID_LIKE` pattern (`<ALPHA_PREFIX>-<DIGITS>`, e.g., `BDG-99201`) at least twice (`quorum >= 2`), `FeedbackService` learns only the non-PII uppercase prefix (`BDG-*`, filtered against a standard-code blocklist) to flag future occurrences as `PENDING`.
- **Bounded Confidence Calibration & Optional Encrypted Aliases:** Adjusts category/source confidence within `[-0.15, +0.10]` after $\ge 3$ review decisions, and supports optional cross-session alias retention encrypted locally with **AES-256-GCM** (`opt_in_consent=true`). Feedback never auto-mutates model weights or production code.

---

## How It Works

```mermaid
flowchart LR
    A["1. Upload\n(.txt / .pdf)"] --> B["2. Canonical Extract\nOffsets & BBoxes"]
    B --> C["3. Hybrid Detect\nRegex + NER + SLM"]
    C --> D["4. Entity Resolution\nVariant Clustering"]
    D --> E["5. Human Review\nApprove / Reject / Add"]
    E --> F["6. Physical Redaction\nTXT & PDF Stream Scrub"]
    F --> G{"7. Verification\nPost-Export Audit"}
    G -- "Pass (VERIFIED)" --> H["8. SanitizedDocument\nHard Privacy Boundary"]
    G -- "Fail" --> X["Block Download\n(Fail-Closed)"]
    H --> I["9. Summary + SummaryGuard\nVerified Output Only"]
```

1. **Upload:** Ingest a UTF-8 `.txt` or text-based `.pdf` ($\le 20\text{ MB}$, $\le 500\text{ pages}$).
2. **Extract:** Strip zero-width/bidirectional control characters and map Unicode code-point offsets `[start, end)` and PDF word bounding boxes `[x0, y0, x1, y1]`.
3. **Detect:** Run `RegexDetector`, `NERDetector`, optional `SLMDetector`, and active-learned prefix rules.
4. **Resolve:** Cluster within-document entity variants and flag ambiguous mentions for review.
5. **Review:** Inspect evidence in the 3-panel workstation and finalize approvals, rejections, or manual additions.
6. **Redact:** Remove approved spans from the TXT string or PDF content stream while preserving rejected spans.
7. **Verify:** Re-open the exported artifact from disk and execute the independent verification checks.
8. **Summarize:** Pass only the verified `SanitizedDocument` to `SummaryService` (local Ollama or extractive fallback).
9. **Guard & Deliver:** Run `SummaryGuard` checks and expose only verified downloads and leak-checked summaries.

---

## Architecture Overview

| Layer | Primary Components | Responsibility |
| :--- | :--- | :--- |
| **Frontend** | `Dashboard`, `ReviewWorkspace`, `ExportView`, `SummaryView` | React 18.3 review workstation, PDF/text highlighting, keyboard shortcuts, verification & summary views |
| **API** | FastAPI (`/api/documents/*`, `/api/feedback/*`, `/health`) | Localhost request routing, strict ID validation (`^[a-zA-Z0-9_\-]{1,64}$`), security headers, CORS |
| **Ingestion** | `TXTProcessor`, `PDFProcessor` | UTF-8 normalization, zero-width/bidi stripping, PyMuPDF word coordinate & rotation/CropBox mapping |
| **Detection** | `DetectionService`, `RegexDetector`, `NERDetector`, `SLMDetector` | Hybrid candidate extraction, 1-to-1 homoglyph folding, role-prefix trimming, span unioning |
| **Entity Resolution** | `EntityResolver` | Category-aware normalization, Union-Find clustering, phonetic matching, ambiguity safeguards |
| **Review & Feedback** | `ReviewService`, `FeedbackService` | Decision state management, downstream artifact invalidation, quorum prefix learning, AES-256-GCM aliases |
| **Redaction** | `RedactionService` | Descending-offset TXT replacement, PyMuPDF stream/metadata/annotation scrubbing, clean-text PDF rebuild |
| **Verification** | `VerificationService` | Independent disk re-extraction, 4-check TXT / 8-check PDF audit, SHA-256 digest computation |
| **Summarization** | `SummaryService`, `SummaryGuard`, `ModelService` | `SanitizedDocument` enforcement, `<UNTRUSTED_DOCUMENT_CONTENT>` isolation, 6-tier leak & injection shield |
| **Storage** | SQLite (`privydoc.db`) + `data/sessions/{id}/` | Zero-PII relational metadata separated from temporary session files |

```mermaid
flowchart TD
    subgraph PrimaryFlow ["Primary Document & Redaction Pipeline (Ephemeral Session)"]
        In["Uploaded .txt / .pdf"] --> Det["Ingestion + Hybrid Detection + Entity Resolution"]
        Det --> Rev["Human-in-the-Loop Review Workspace"]
        Rev --> Red["RedactionService (TXT & PyMuPDF Stream Scrub)"]
        Red --> Ver{"VerificationService\n(Independent Audit)"}
    end

    Ver -- "FAILED" --> Blocked["Export Blocked (Fail-Closed)\nOptional Clean-Text PDF Rebuild"]
    Ver -- "PASSED (VERIFIED)" --> San

    subgraph SafeBoundary ["Sanitized-Only Summarization Zone (No Raw Source Access)"]
        San["SanitizedDocument Contract\n(Verified Sanitized Text + Placeholders Only)"]
        Sum["SummaryService\n(Local Ollama / Extractive Fallback)"]
        Grd{"SummaryGuard\n(6-Tier Privacy Shield)"}
        Out["Verified Export (.pdf / .txt) & Safe Summary"]
        San --> Sum --> Grd
        Grd -- "PASSED" --> Out
        Grd -- "FAILED" --> Supp["Summary SUPPRESSED (Fail-Closed)"]
    end

    subgraph AuxServices ["Auxiliary Local Persistence & Runtime (127.0.0.1)"]
        DB[("SQLite (privydoc.db)\nZero-PII Metadata & Feedback\n+ AES-256-GCM Opt-In Aliases")]
        SLM[["Local Ollama HTTP API\n(127.0.0.1:11434)"]]
    end

    Rev <--> DB
    Det -. "Optional Proposals" .-> SLM
    Sum -. "Sanitized Prompt" .-> SLM
    Rev -. "Any Review Edit Invalidates & Unlinks" .-> San
```

---

## Privacy and Security

- **Localhost Network Binding:** The FastAPI backend validates that `HOST` is bound to `127.0.0.1` or `localhost` (`validate_local_host`) and restricts CORS to local frontend origins (`127.0.0.1:5173`, `localhost:5173`, `127.0.0.1:3000`, `localhost:3000`). Optional SLM requests target only the configured local Ollama endpoint (`http://127.0.0.1:11434`).
- **Tested Offline Execution Path:** Once dependencies and optional local Ollama model weights are installed, the document processing workflow (ingestion, detection, review, redaction, verification, and summarization) executes locally without outbound network calls (verified by socket-blocked integration tests in `backend/tests/`).
- **Storage Separation & Session Cleanup:** SQLite (`backend/data/privydoc.db`) stores operational metadata (`documents`), decisions (`review_decisions`), and data-minimized feedback (`feedback_records`) with zero raw document text. Uploaded files and extracted text reside in `backend/data/sessions/{document_id}/` and are deleted immediately upon user-initiated purge (`DELETE /api/documents/{id}`) or during application startup cleanup for sessions older than `SESSION_TTL_HOURS` (default: `24` hours).
- **Optional Encrypted Aliases:** Cross-session alias retention is disabled by default. When explicitly enabled (`opt_in_consent=true`), alias ciphertexts are encrypted in `opt_in_encrypted_aliases` using **AES-256-GCM** (`cryptography` `AESGCM`) with a local 256-bit key (`backend/data/.alias_encryption.key`) and purged upon expiration or session deletion.
- **Stale Artifact Invalidation:** Any review mutation (approving, rejecting, manual addition, category change, or entity linking/unlinking) atomically unlinks existing `sanitized.txt`, `sanitized.pdf`, `export_metadata.json`, and `summary.json` files and resets session status to `REVIEWING`.
- **Adversarial Input Hardening (`SEC-01`–`SEC-07`):** Normalizes zero-width/bidirectional control characters and single-codepoint Cyrillic/Greek/fullwidth homoglyphs, enforces upload/extraction bounds (`20 MB`, `500 pages`, `2,000,000 chars`), encloses summarizer input in randomized `<UNTRUSTED_DOCUMENT_CONTENT_{nonce}>` delimiters, and fails closed when verification or `SummaryGuard` checks fail.
- **Host Trust Boundary:** Localhost binding prevents LAN exposure and external cloud transmission in the tested workflow, but does not protect against a compromised host operating system, malicious local processes running under the same user account, or untrusted browser extensions. See [Privacy and Security Specification](Docs/10_Privacy_and_Security_Specification.md) for the complete threat model.

---

## Supported Inputs and Limitations

| Capability / Input Type | Support Status | Operational Behavior & Scope |
| :--- | :---: | :--- |
| **UTF-8 Plain Text (`.txt`)** | **Supported** | Up to 20 MB / 2,000,000 characters; descending-offset Unicode code-point redaction |
| **Text-Based Digital PDF (`.pdf`)** | **Supported** | Up to 20 MB / 500 pages; native PyMuPDF text-stream, annotation & metadata redaction |
| **Scanned / Image-Only PDF** | **Unsupported** | Rejected at ingestion (`IMAGE_ONLY_PDF_NOT_SUPPORTED`); requires prior OCR |
| **Password-Protected / Encrypted PDF** | **Unsupported** | Rejected at ingestion (`ENCRYPTED_FILE_REJECTED`) |
| **Rasterized Text inside PDF Images** | **Unsupported** | Embedded bitmap images (e.g., scanned stamps/signatures) are not OCR-scanned or redacted |
| **Vector Glyph Outlines / Dynamic XFA** | **Unsupported Natively** | Native verification fails closed if residual text remains; explicit clean-text PDF rebuild offered |
| **Supported PII Categories** | **5 Categories** | `PERSON`, `EMAIL`, `PHONE`, `ADDRESS`, `ID_LIKE` |

**Disclosed Operational Limitations:**
- **Lowercase & Diacritic Names:** Heuristic contextual NER relies on title-case capitalization cues and ASCII character ranges; lowercase names in informal notes (e.g., `"rohit verma"`) or names with non-ASCII diacritics (e.g., `"Renée Müller"`) without header labels may require manual selection (`M`).
- **Unconfigured Identifier Prefixes:** Baseline `ID_LIKE` regex patterns target standard formats (`EMP-`, `STU-`, `ACC-`, `CUST-`, `PAN`, `Aadhaar`, `SSN`). Custom organizational prefixes (`BDG-`, `TRK-`) require manual selection or activation via the quorum-gated active-learning loop ($\ge 2$ manual additions).
- **Pseudonymization vs. Mathematical Anonymity:** Entity-indexed placeholders (`[PERSON_1]`) and rule-based quasi-identifier checks improve readability and flag high-risk co-occurrences, but do not guarantee mathematical $k$-anonymity or prevent re-identification from domain background knowledge.
- **Single-User Workstation Scope:** Designed for local single-user execution without multi-tenant authentication or role-based access control. See [Known Limitations](Docs/KNOWN_LIMITATIONS.md) for full details.

---

## Technology Stack

| Layer | Technology | Verified Version | Engineering Rationale |
| :--- | :--- | :--- | :--- |
| **Frontend UI** | React, Vite, Tailwind CSS, React Router, Axios, Lucide | React `18.3.1`, Vite `6.0.3` (`6.4.6`), Tailwind `3.4.16` | Fast local SPA workstation with 3-panel inspection and keyboard-driven review |
| **Backend API** | Python, FastAPI, Pydantic v2, Uvicorn | Python `3.11+` (`3.12.10`), FastAPI `0.162.0`, Pydantic `2.14.2` | Strict schema validation (`SanitizedDocument`, `SLMAnalysisResponse`) at API/service boundaries |
| **Document Engine** | PyMuPDF (`fitz`) | `>=1.24.0` (`1.25.x`) | Word-level PDF bounding-box extraction, page derotation, and stream redaction |
| **Detection & Linking** | Regex, Custom Contextual `NERDetector`, RapidFuzz | `rapidfuzz>=3.9.0` (`3.14.6`), `spacy>=3.7.0` (manifest) | High-precision pattern matching paired with two-pass contextual NER and fuzzy/phonetic coreference |
| **Local SLM Runtime** | Ollama HTTP API (`qwen2.5:1.5b-instruct`) | Local HTTP (`127.0.0.1:11434`, `/api/generate`) | Local contextual candidate proposals and summarization with deterministic offline fallback |
| **Storage & Crypto** | SQLite 3, `cryptography` (`AESGCM`), `hashlib` | SQLite `3`, AES-256-GCM, SHA-256 | Zero-PII metadata persistence, authenticated alias encryption, and post-export byte integrity |
| **Testing & Profiling** | Pytest, HTTPX, Vitest, React Testing Library, `psutil` | Pytest `9.2.0`, Vitest `2.1.8` (`2.1.9`), `psutil` `7.2.2` | 159 backend and 42 frontend automated tests across unit, adversarial, and E2E workflows |

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
PrivyDoc works without Ollama using its deterministic `Regex + NER` detection pipeline and extractive summary fallback. To enable local SLM candidate assistance and generative summarization:
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
2. **Inspect Candidates & Evidence:** In the **Review Workspace**, switch between **Canonical Text** and **PDF View**. Click any highlighted span to inspect detector provenance, heuristic confidence weight, and why the span was flagged.
3. **Approve, Reject, or Link Entities:** Press `A` to approve sensitive items for removal or `R` to reject false positives (preserving them in the output). Switch to the **Entities** tab to approve entire linked name clusters (`"Dr. Marcus Vance"` $\leftrightarrow$ `"M. Vance"`) or manually link/unlink mentions.
4. **Add Manual Redactions:** Highlight any unflagged text with your cursor and press `M` to add a custom redaction span.
5. **Redact & Verify Export:** Open **2. Redact & Verify**, choose a placeholder pattern (`[CATEGORY]`, `[CATEGORY_#]`, `[REDACTED]`, or block mask), and click **Execute Redaction & Verify Output**. Inspect the verification report and SHA-256 digest before downloading the verified `.pdf` or `.txt`.
6. **Generate a Safe Summary:** Open **3. Safe Summary** to generate a structured summary from the `SanitizedDocument` payload, complete with `[§1]` source evidence grounding, `SummaryGuard` check results, and quasi-identifier risk assessment.
7. **Purge Session:** Click the session delete button to remove the temporary session folder and SQLite metadata records.

For detailed operating instructions and a scripted walkthrough, see the [User Guide](Docs/USER_GUIDE.md) and [Demo Guide](Docs/DEMO_GUIDE.md).

---

## Evaluation and Performance

PrivyDoc was evaluated on two frozen synthetic benchmarks totaling **61 documents (122 TXT and PDF files, 305 gold PII spans, and 3 negative 0-PII documents)**: **Suite V1** (`datasets/evaluation`, 25 docs) and **Suite V2** (`datasets/evaluation_stage4`, 36 docs across 17 challenge categories).

| Metric / Dimension | Evaluation Scope | Result | Details |
| :--- | :--- | :---: | :--- |
| **Suite V2 Held-Out Micro F1** | `datasets/evaluation_stage4/test` (12 docs, 56 spans) | **90.74%** | Exact `P = 94.23%`, `R = 87.50%` (`TP = 49, FP = 3, FN = 7`); Overlap F1: **92.59%** |
| **Suite V2 Held-Out Macro F1** | `datasets/evaluation_stage4/test` (5 categories) | **92.62%** | Exact F1: `EMAIL 1.00` · `ID_LIKE 0.96` · `PHONE 0.93` · `ADDRESS 0.86` · `PERSON 0.85` |
| **Suite V1 Held-Out Micro F1** | `datasets/evaluation/test` (8 docs, 45 spans) | **89.89%** | Exact `P = 90.91%`, `R = 88.89%` (`TP = 40, FP = 4, FN = 5`); Overlap F1: **92.13%** |
| **Negative-Doc False Positives** | 3 negative (0-PII) corporate/regulatory docs | **0 FPs** | Zero false alarms on non-PII vendor and ISO compliance documents |
| **Entity Resolution (In-Doc)** | Suite V1 (`5` pos / `775` neg) & V2 (`8` pos / `1,168` neg) | **1.0000 F1** | `0` false merges; `100%` ambiguity safeguard rate on conflicting initials/surnames |
| **Approved-Span Removal** | 34 benchmark scenarios (`38` total tests in `test_redaction.py`) | **100.0%** | `100.0%` rejected span preservation (including identical strings on the same PDF page) |
| **Summary Privacy Safety** | 19 automated `SummaryGuard` scenarios (`test_summary.py`) | **0.0% Leaks** | `100%` fail-closed suppression on injected leaks and prompt-injection payloads |
| **Automated Test Suites** | Backend (`pytest`) + Frontend (`vitest`) | **159 + 42** | `201` total automated tests passing (`0` failures) |
| **End-to-End Latency** | Intel 4-core / 8-thread CPU, 7.85 GB RAM (Windows 11) | **~1.29 s / ~1.39 s** | `1,290.65 ms` (TXT) and `1,387.85 ms` (PDF) upload through verified export & summary |
| **Application Process RSS** | OS Resident Set Size (`psutil.Process().memory_info().rss`) | **~87.33 MB** | Python + PyMuPDF backend process RSS (excludes external Ollama process; heap delta: `1.58 MB`) |

**Evaluation Scope & SLM Notes:**
- All benchmark scores reflect controlled synthetic evaluation datasets and do not establish guaranteed accuracy on arbitrary real-world documents.
- On the held-out benchmark splits (`V1` and `V2`), `89.89%` and `90.74%` exact micro F1 were achieved by the deterministic `Regex + NER` pipeline with Ollama offline. In controlled ablation tests on untitled narrative aliases (`test_stage2_audit_slm_ablation_and_failure_safety`), local SLM proposals increased recall from `0.50` to `1.00` while keeping all novel SLM suggestions in `PENDING` review state.

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
| **System Architecture** | [`Docs/ARCHITECTURE.md`](Docs/ARCHITECTURE.md) | Layered system design, 7-stage pipeline, storage layout, and privacy boundaries |
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
