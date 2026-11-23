# PrivyDoc — User Manual & Operating Guide

**Product:** PrivyDoc (Privacy-Aware Document Redaction and Summarization Tool)  
**Version:** 1.0.0 (Release-Ready Baseline, Phases P0–P9)  
**Target Audience:** Document Reviewers, Compliance Officers, Legal Teams, Academic Evaluators  
**Last Updated:** 2026-11-23  

---

## 1. Introduction

PrivyDoc is an offline, privacy-first desktop web application designed to safely redact Personally Identifiable Information (PII) from sensitive documents (TXT and PDF) and generate privacy-preserving structured summaries.

Unlike cloud-based tools, **PrivyDoc operates 100% locally on your machine**. Your confidential documents, extracted text, and personal data never leave your computer.

---

## 2. System Requirements & Quickstart

### Prerequisites
- **Operating System:** Windows 10/11, macOS, or Linux.
- **Python:** Version 3.12 or later.
- **Node.js:** Version 18.0 or later (with npm).
- **Optional Local SLM:** [Ollama](https://ollama.com) running `qwen2.5:1.5b-instruct` on `http://127.0.0.1:11434` for advanced AI-driven name linking and generative summaries. (If Ollama is not running, PrivyDoc operates seamlessly in deterministic rule-based and extractive mode).

### Starting PrivyDoc

Open two terminal windows:

#### Terminal 1 — Backend (FastAPI)
```powershell
cd C:\Users\Admin\Desktop\PrivDoc
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
*Backend runs on `http://127.0.0.1:8000` with interactive OpenAPI documentation at `/docs`.*

#### Terminal 2 — Frontend (React 19)
```powershell
cd C:\Users\Admin\Desktop\PrivDoc\frontend
npm run dev
```
*Frontend runs on `http://127.0.0.1:5173`.*

Open your web browser and navigate to: **`http://127.0.0.1:5173`**.

---

## 3. Step-by-Step User Workflow

The PrivyDoc interface guides you through a 5-stage document privacy lifecycle:

```
[ Ingest Document ] ──> [ Review Candidates ] ──> [ Execute Redaction ] ──> [ Verify Export ] ──> [ Privacy Summary ]
```

---

### Step 1: Uploading a Document

1. From the **Dashboard**, locate the **Upload Document** card.
2. Drag and drop your file or click **Select File**.
3. Supported formats:
   - **Plain Text (`.txt`):** Ingested with UTF-8 normalization.
   - **Digital PDF (`.pdf`):** Text-based PDFs with native coordinate preservation.
   - *Maximum file size:* 20 MB.
4. Click **Upload & Process Document**. PrivyDoc automatically creates an isolated ephemeral session, canonicalizes the text, and runs the hybrid detection engine.

---

### Step 2: The Document Review Workspace

Upon upload, you are automatically directed to the **Review Workspace**:

```
+-----------------------------------------------------------------------------------+
|  [Back to Dashboard]   Document: incident_report.pdf (PDF, 2 Pages)   [Proceed ->] |
+------------------------------------------+----------------------------------------+
|                                          |  Review Candidates (14 Total)          |
|  DOCUMENT VIEWER                         |  [Approved: 0] [Rejected: 0] [Pend: 14]|
|                                          |                                        |
|  Page 1 of 2  [Prev] [Next]  [Zoom]      |  Filter: [ All | High | Med | Low ]    |
|  +------------------------------------+  +----------------------------------------+
|  | INCIDENT REPORT                    |  | [PERSON] Dr. Evelyn Vance       [0.95] |
|  | Investigator: Dr. Evelyn Vance     |  | Entity: Dr. Evelyn Vance (Cluster 1)   |
|  | Contact: evelyn.vance@novatech...  |  | Occurrences: 3 in document             |
|  | Employee ID: EMP-88219              |  | [Approve (A)] [Reject (R)] [Redact All]|
|  |                                    |  +----------------------------------------+
|  | (Candidates highlighted in color)  |  | [EMAIL] evelyn.vance@novatech... [0.99] |
|  +------------------------------------+  +----------------------------------------+
```

#### Color-Coded PII Categories
PrivyDoc assigns distinct visual themes to detected categories:
- **PERSON (Purple):** Full names, initials, surnames, titles.
- **EMAIL (Blue):** Corporate and personal email addresses.
- **PHONE (Cyan):** International and domestic telephone numbers.
- **ADDRESS (Amber):** Street addresses, postal codes, suites.
- **ID_LIKE (Emerald):** Employee IDs, account numbers, SSNs.
- **FINANCIAL (Rose):** Credit cards, IBANs, bank accounts.
- **ORGANIZATION (Indigo):** Corporate entities and institutions.
- **MANUAL / CUSTOM (Slate):** User-highlighted custom spans.

#### Candidate Review Actions
- **Approve (Key `A`):** Marks the candidate for physical redaction.
- **Reject (Key `R`):** Declares the candidate a false positive (e.g., project code or standard name). The text will remain unredacted in the final document.
- **Undo / Pending:** Resets the decision to unreviewed.
- **Redact All Similar:** Approves all occurrences sharing the exact normalized text across the entire document in a single click.
- **Redact Entire Entity Cluster:** Approves all related name variants (e.g., "Dr. Vance", "E. Vance", and "Evelyn Vance") simultaneously.

#### Adding Manual Redactions
If an unflagged sensitive item exists in the document:
1. Highlight the text span with your mouse cursor in the Document Viewer.
2. Click **Mark as Redaction Candidate** (or press Key `M`).
3. Select the PII category. PrivyDoc registers the candidate with exact canonical offsets and renders a visual highlight.

#### Keyboard Shortcuts
| Shortcut | Action |
|---|---|
| `A` | Approve currently selected candidate |
| `R` | Reject currently selected candidate |
| `M` | Create manual candidate from text selection |
| `ArrowDown` | Move to next candidate in list |
| `ArrowUp` | Move to previous candidate in list |

---

### Step 3: Redaction & Export

When candidate review is satisfactory, navigate to the **Export View**:

1. **Review Gatekeeper:** The export panel displays the current review status:
   - Green indicator if all candidates have been reviewed.
   - Amber warning if unreviewed candidates remain (you can still proceed; unreviewed items remain unredacted).
2. **Choose Placeholder Style:**
   - `CATEGORY` (Recommended): Replaces text with semantic labels (e.g., `[PERSON]`, `[EMAIL]`).
   - `GENERIC`: Replaces text with uniform markers (e.g., `[REDACTED]`).
   - `MASK`: Overwrites characters with mask symbols (e.g., `***`).
3. Click **Execute Redaction & Verify Export**.

#### Physical Stream Redaction (Not Black Boxes)
PrivyDoc does not overlay opaque black boxes on top of text. For PDF files, PyMuPDF permanently scrubs character glyphs and vector paths from the underlying PDF binary. For TXT files, text is replaced using descending-offset string reconstruction.

---

### Step 4: Export Verification Audit

Before any file can be downloaded, PrivyDoc's independent `VerificationService` re-opens the generated file and conducts a 4-point automated audit:
1. **Re-Extraction:** Extracts all text from the output file.
2. **Approved String Audit:** Confirms that 0 approved sensitive strings appear.
3. **Variant Audit:** Confirms that 0 name variants or aliases appear.
4. **Hidden Structure Audit:** Inspects PDF metadata, form fields, and annotations.

#### Verification Badges
- **VERIFIED (Green Badge):** Passed 100% of verification checks. Download is unlocked.
- **RECONSTRUCTED (Blue Badge):** Native PDF contained non-sanitizable structures; a clean-text PDF was reconstructed from verified sanitized text.
- **FAILED (Red Badge):** Verification detected residual strings. Download is strictly blocked to prevent data leakage.

#### The Invalidation Safeguard
If you return to the Review Workspace and modify any candidate decision after an export has been generated, **PrivyDoc immediately invalidates and deletes the old export artifacts**. This prevents downloading stale or desynchronized files.

---

### Step 5: Privacy-Preserving Summarization

From the verified export screen, click **Generate Privacy Summary**:

1. **Guaranteed Input Isolation:** The summarizer receives *only* the verified sanitized text (with placeholders). It has zero access to original unredacted text or candidate objects.
2. **Generation Modes:**
   - **Local SLM:** Uses local Ollama model (`qwen2.5:1.5b-instruct`) with strict `<UNTRUSTED_DOCUMENT_CONTENT>` prompt containment.
   - **Extractive Fallback:** Deterministic offline sentence extraction used automatically if Ollama is offline or when requested.
3. **SummaryGuard Multi-Tiered Audit:** Every generated summary must pass:
   - *Direct Leakage Check:* Zero approved sensitive names.
   - *PII Re-Detection Check:* Zero regex or NER detections in summary text.
   - *Quasi-Identifier Risk Evaluation:* Flags co-occurring demographic attributes.
   - *Source Consistency Check:* Ensures dates and numbers match the sanitized text.
   - *Prompt Injection Check:* Rejects reflected override instructions.
4. **Structured Presentation:** Verified summaries display clear key points, important findings, and grounded citations.
5. **Suppression Safety:** If any privacy check fails, the summary is marked `SUPPRESSED` and concealed from view.

---

### Step 6: Session Deletion & Privacy Hygiene

When your work is complete:
1. Click the red **Purge Session & Delete All Data** button.
2. PrivyDoc immediately and permanently purges:
   - The ephemeral session folder (`data/sessions/{id}/`).
   - All uploaded files, canonical text, coordinates, and candidates.
   - All SQLite database metadata records.

---

## 4. Frequently Asked Questions & Troubleshooting

### Q: Why does the summary badge say "EXTRACTIVE_FALLBACK"?
**A:** If Ollama is not installed or running on `127.0.0.1:11434`, PrivyDoc gracefully activates its deterministic extractive summarizer. To enable local AI summarization, start Ollama and run `ollama pull qwen2.5:1.5b-instruct`.

### Q: Can PrivyDoc redact scanned images or scanned PDFs?
**A:** PrivyDoc is engineered for digital text and text-based PDFs. Scanned PDFs without an embedded OCR text layer will trigger a warning. For scanned files, perform OCR prior to uploading to PrivyDoc.

### Q: What should I do if a PDF verification status says "FAILED"?
**A:** If native vector redaction fails verification due to complex font encodings or overlapping vector graphics, PrivyDoc will offer the **Reconstruct Clean-Text PDF** alternative. This builds a brand-new, clean PDF exclusively from verified sanitized text.
