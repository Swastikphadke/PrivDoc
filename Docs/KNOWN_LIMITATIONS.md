# PrivyDoc — Known Limitations & Scope Boundaries

**Project:** PrivyDoc (Privacy-Aware Document Redaction and Summary Platform)  
**Document Status:** Release Baseline (Phases P0–P9)  
**Last Updated:** 2026-11-23  

This document details the genuine technical constraints, architectural boundaries, and known limitations of the PrivyDoc platform. In accordance with strict academic and engineering standards, these limitations are explicitly documented rather than masked with unreliable heuristics.

---

## 1. Document Format & Ingestion Limitations

### 1.1 Scanned and Image-Only PDFs
- **Limitation:** PrivyDoc operates exclusively on text-based documents containing valid Unicode character streams and PyMuPDF vector text coordinates. It does **not** contain an embedded Optical Character Recognition (OCR) engine or computer-vision raster segmentation.
- **System Behavior:** Scanned, photographed, or purely rasterized image PDFs are automatically detected during ingestion (`PDFProcessor.extract_text_and_coordinates`) and safely rejected with an explicit, actionable error message (`IMAGE_ONLY_PDF_NOT_SUPPORTED`).
- **Mitigation / Safe Usage:** Users must run pre-processing OCR (e.g. Tesseract or Adobe OCR) to generate a searchable text-layer PDF before ingesting into PrivyDoc.

### 1.2 Encrypted and Password-Protected Files
- **Limitation:** Ingestion strictly rejects password-protected PDFs or encrypted TXT containers where decryption keys are not provided at upload time.
- **System Behavior:** Rejects upload with HTTP 400 (`ENCRYPTED_FILE_REJECTED`) without attempting brute-force password cracking.

### 1.3 Interactive XFA Forms & Dynamic PDF Scripts
- **Limitation:** Dynamic XML Forms Architecture (XFA) and proprietary active PDF JavaScript widgets contain non-standard DOM models that cannot be reliably sanitized via standard PDF vector redaction annotations.
- **System Behavior:** Native redaction verification fails closed on complex hidden scripts or XFA structures. The system presents the user with an explicit option to generate a **Clean-Text Reconstructed PDF** derived strictly from verified sanitized plain text, accompanied by a layout-change advisory.

---

## 2. Text Redaction & Formatting Constraints

### 2.1 Tabular Layout & Monospace Alignment
- **Limitation:** In plain-text (`.txt`) documents, replacing variable-length sensitive candidate strings (e.g., replacing a 14-character credit card number with `[ID_LIKE]`) changes the horizontal character count.
- **Impact:** Space-padded ASCII columns or fixed-width financial tables may experience column shifts around redacted cells.
- **Mitigation:** The system supports `BLOCK` placeholder style (`████`) or `CUSTOM` fixed-length placeholders to minimize typographical distortion where strict column alignment is desired.

### 2.2 Right-to-Left (RTL), Case-Sensitivity, and Non-ASCII Script Offsets
- **Limitation:** All canonical offsets are indexed strictly using Unicode code-point positions `[start, end)`. Bidirectional text (e.g. Arabic or Hebrew interspersed with Latin phone numbers or emails) may visually render in reverse order in certain browser textareas despite correct underlying string indices.
- **Lowercase & Diacritic Name Mentions:** Heuristic contextual NER relies on title-case capitalization boundaries (`[A-Z][a-z]+`). Consequently, all-lowercase personal names in informal chat logs (e.g., `"rohit verma"`) or names containing non-ASCII diacritics (e.g., `"Renée Müller"`) without an explicit header label may be missed by automated detection and require human manual selection (`M` shortcut) in the Review Workspace.
- **Unconfigured Identifier Prefixes:** Deterministic `ID_LIKE` detection targets configured prefixes (`EMP`, `STAFF`, `STU`, `ACC`, `ACCT`, `CUST`, `REF`, `PAT`, `MRN`, `PAN`, `Aadhaar`, `SSN`). Arbitrary custom prefixes (`TRK-`, `ASSET-`, `BDG-`) are omitted by default to prevent false positives on version numbers and ISO standards.

---

## 3. Privacy, Anonymity & Quasi-Identifier Boundaries

### 3.1 Non-Anonymity of Direct Redaction
- **Limitation:** Removing direct PII (names, phone numbers, email addresses, employee IDs) does **not** mathematically guarantee complete anonymity.
- **Quasi-Identifier Risk:** If a document contains a combination of rare attributes (e.g., `"The sole Chief Quantum Cryptographer stationed at the Zurich Annex, hired March 2021"`), an adversary with background knowledge can easily re-identify the subject even if the name is replaced by `[PERSON]`.
- **System Defense:** `SummaryGuard` evaluates demographic, departmental, and role-based co-occurrences against a configurable knowledge graph (`config/quasi_identifiers.json`). If unique attribute combinations are detected, the system flags the summary with an explicit, non-bypassable warning:
  > *"Quasi-identifier risk evaluation assesses statistical re-identification risk flags based on demographic or contextual co-occurrences; it does not constitute mathematical or legal proof of complete anonymity."*
- **Explicit Invariant:** PrivyDoc never makes false or mathematically unfounded claims of "guaranteed k-anonymity" or "100% de-identification".

---

## 4. Entity Resolution & Coreference Boundaries

### 4.1 Ambiguous Initials & Shared Surnames
- **Limitation:** When isolated initials appear (e.g., `J. Smith`) in a document where multiple candidate identities exist (e.g., `John Smith` and `James Smith`), deterministic resolution cannot prove identity without speculative guessing.
- **System Behavior:** `EntityResolver` strictly forbids automated merges of ambiguous initials. The system groups them as unconfirmed suggestions and requires the human reviewer to explicitly authorize or reject linking.
- **Shared Surnames:** Surnames alone (e.g., `Mr. Kumar` when `Anil Kumar` and `Sunil Kumar` both exist) are never merged automatically.

---

## 5. Local Hardware & Model Execution Boundaries

### 5.1 Local SLM Inference Constraints
- **Limitation:** Running local Small Language Models (e.g., Qwen 2.5 1.5B or Llama 3.2 1B/3B) requires sufficient CPU/RAM resources. On lower-spec host devices without GPU/NPU acceleration, SLM summarization may take 10–30 seconds.
- **Deterministic Extractive Fallback:** If the local SLM process is offline, times out, or fails schema validation, PrivyDoc automatically activates a deterministic extractive summarizer. The extractive summary operates exclusively on sanitized text and undergoes 100% of the identical multi-tier privacy verification checks.

### 5.2 Network Boundary Invariant
- **Limitation:** The system operates strictly offline on `127.0.0.1`. It does not support distributed multi-node clusters or third-party cloud LLM API integrations (e.g., OpenAI, Anthropic) by design, ensuring zero data egress.
