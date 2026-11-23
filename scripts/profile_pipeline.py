"""Performance Profiler for PrivyDoc End-to-End Pipeline (Phase P8).

Profiles latency and peak memory across all stages:
- Cold and warm startup
- Ingestion (TXT, PDF)
- Hybrid detection (Regex + NER)
- Entity resolution
- Review decision processing
- Redaction and export verification (TXT, native PDF, clean-text PDF)
- Summarization and multi-tiered privacy verification
- Complete end-to-end pipeline
- Peak RAM via tracemalloc
- Host hardware specifications
"""

import json
import os
import platform
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

import psutil
import fitz

from app.core.config import settings
from app.core.security import cleanup_session, get_safe_session_dir
from app.database.session import init_db, delete_document_record, save_document_metadata
from app.processors.txt_processor import TXTProcessor
from app.processors.pdf_processor import PDFProcessor
from app.services.detection_service import DetectionService
from app.detectors.entity_resolver import EntityResolver
from app.services.review_service import ReviewService
from app.services.redaction_service import RedactionService
from app.services.summary_service import SummaryService
from app.services.summary_guard import SummaryGuard
from app.services.model_service import ModelService
from app.schemas.review import ReviewActionRequest, ReviewDecisionAction, ManualCandidateRequest
from app.schemas.redaction import RedactionRequest
from app.schemas.summary import SanitizedDocument, StructuredSummaryContent


SAMPLE_TXT = (
    "INCIDENT INVESTIGATION REPORT - CONFIDENTIAL\n"
    "Date: October 14, 2024\n"
    "Author: Dr. Evelyn Vance (Chief Security Officer)\n"
    "Email: evelyn.vance@novatech-corp.test | Phone: +1 (555) 019-2834\n"
    "Employee ID: EMP-88219\n"
    "Facility: NovaTech Medical Systems, 742 Evergreen Terrace, Springfield, OR 97477\n\n"
    "SUMMARY OF FINDINGS:\n"
    "On October 12, 2024, at approximately 14:30 hours, Dr. Evelyn Vance observed unauthorized access "
    "to the patient record database. The initial breach was reported by system administrator Marcus Brody "
    "(m.brody@novatech-corp.test, +1 (555) 014-9921). E. Vance immediately quarantined workstation WS-402.\n"
    "Patient records belonging to Robert Chen (SSN: 987-65-4321) were accessed. Dr. Vance coordinated with "
    "legal counsel to notify affected individuals.\n"
)


def create_sample_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(50, 72), SAMPLE_TXT, fontsize=11)
    doc.save(str(path))
    doc.close()


def profile_cold_startup() -> float:
    cmd = [
        sys.executable,
        "-c",
        (
            "import sys; sys.path.insert(0, 'backend'); "
            "import time; t0 = time.perf_counter(); "
            "import app.main; from app.database.session import init_db; init_db(); "
            "print(time.perf_counter() - t0)"
        )
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(res.stdout.strip())


def profile_warm_startup() -> float:
    from app.database.session import check_db_health
    t0 = time.perf_counter()
    health = check_db_health()
    assert health is True
    return time.perf_counter() - t0


def main():
    print("=" * 70)
    print("PRIVYDOC PIPELINE PERFORMANCE PROFILER (PHASE P8)")
    print("=" * 70)

    # 1. System Specifications
    cpu_info = platform.processor()
    cores_phys = psutil.cpu_count(logical=False)
    cores_log = psutil.cpu_count(logical=True)
    ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 2)
    os_info = f"{platform.system()} {platform.release()} ({platform.version()})"

    print(f"OS:        {os_info}")
    print(f"CPU:       {cpu_info} ({cores_phys} physical / {cores_log} logical cores)")
    print(f"RAM:       {ram_gb} GB total")
    print("-" * 70)

    init_db()

    # 2. Cold and Warm Startup
    print("Profiling Cold Startup...")
    cold_startup_s = profile_cold_startup()
    print(f"  Cold Startup Latency: {cold_startup_s * 1000:.2f} ms ({cold_startup_s:.3f} s)")

    print("Profiling Warm Startup...")
    warm_startup_s = profile_warm_startup()
    print(f"  Warm Startup Latency: {warm_startup_s * 1000:.2f} ms ({warm_startup_s:.4f} s)")

    # Temporary directory for test files
    temp_dir = settings.DATA_DIR / "profiling_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    test_txt_path = temp_dir / "profile_sample.txt"
    test_pdf_path = temp_dir / "profile_sample.pdf"
    test_txt_path.write_text(SAMPLE_TXT, encoding="utf-8")
    create_sample_pdf(test_pdf_path)

    results = {}

    tracemalloc.start()
    t_pipeline_start = time.perf_counter()

    # 3. Ingestion Latencies
    doc_id_txt = "prof_txt_001"
    doc_id_pdf = "prof_pdf_001"

    txt_content = test_txt_path.read_bytes()
    pdf_content = test_pdf_path.read_bytes()

    t0 = time.perf_counter()
    canonical_txt, txt_warns = TXTProcessor.extract(txt_content, "profile_sample.txt")
    s_txt_dir = get_safe_session_dir(doc_id_txt)
    s_txt_dir.mkdir(parents=True, exist_ok=True)
    (s_txt_dir / "original.txt").write_bytes(txt_content)
    (s_txt_dir / "canonical.txt").write_text(canonical_txt, encoding="utf-8")
    save_document_metadata(doc_id_txt, "profile_sample.txt", "txt", "EXTRACTED", 1, len(canonical_txt))
    t_ingest_txt = time.perf_counter() - t0

    t0 = time.perf_counter()
    canonical_pdf, pdf_pages, pdf_coords, pdf_warns = PDFProcessor.extract(pdf_content, "profile_sample.pdf")
    s_pdf_dir = get_safe_session_dir(doc_id_pdf)
    s_pdf_dir.mkdir(parents=True, exist_ok=True)
    (s_pdf_dir / "original.pdf").write_bytes(pdf_content)
    (s_pdf_dir / "canonical.txt").write_text(canonical_pdf, encoding="utf-8")
    coords_json = [c.model_dump() for c in pdf_coords]
    (s_pdf_dir / "coordinates.json").write_text(json.dumps(coords_json), encoding="utf-8")
    save_document_metadata(doc_id_pdf, "profile_sample.pdf", "pdf", "EXTRACTED", pdf_pages, len(canonical_pdf))
    t_ingest_pdf = time.perf_counter() - t0

    print(f"  TXT Ingestion:       {t_ingest_txt * 1000:.2f} ms")
    print(f"  PDF Ingestion:       {t_ingest_pdf * 1000:.2f} ms")

    # 4. Detection Latency (Regex + NER)
    t0 = time.perf_counter()
    det_resp = DetectionService.run_detection(doc_id_txt)
    t_detection = time.perf_counter() - t0
    cands_found = len(det_resp.candidates)
    print(f"  Detection (Hybrid):  {t_detection * 1000:.2f} ms ({cands_found} candidates)")

    # 5. Entity Resolution Latency
    cands = EntityResolver.load_candidates(doc_id_txt)
    canon_text = SAMPLE_TXT
    t0 = time.perf_counter()
    EntityResolver.resolve_entities(doc_id_txt, cands, canon_text, use_slm=False)
    t_resolution = time.perf_counter() - t0
    print(f"  Entity Resolution:   {t_resolution * 1000:.2f} ms")

    # 6. Review API Latency
    cands = EntityResolver.load_candidates(doc_id_txt)
    first_cand = cands[0]
    rev_action = ReviewActionRequest(
        candidate_id=first_cand.candidate_id,
        decision=ReviewDecisionAction.APPROVE,
        apply_to_linked=True,
    )
    t0 = time.perf_counter()
    ReviewService.submit_review(doc_id_txt, rev_action)
    t_review_action = time.perf_counter() - t0

    man_req = ManualCandidateRequest(
        start=SAMPLE_TXT.index("Dr. Vance"),
        end=SAMPLE_TXT.index("Dr. Vance") + len("Dr. Vance"),
        type="PERSON",
    )
    t0 = time.perf_counter()
    ReviewService.add_manual_candidate(doc_id_txt, man_req)
    t_manual_add = time.perf_counter() - t0
    print(f"  Review Action:       {t_review_action * 1000:.2f} ms")
    print(f"  Manual Candidate Add:{t_manual_add * 1000:.2f} ms")

    # Approve all candidates for complete redaction profiling
    cands = EntityResolver.load_candidates(doc_id_txt)
    for c in cands:
        ReviewService.submit_review(
            doc_id_txt,
            ReviewActionRequest(candidate_id=c.candidate_id, decision=ReviewDecisionAction.APPROVE),
        )

    # 7. Redaction & Verification Latency
    # TXT Redaction
    t0 = time.perf_counter()
    red_txt = RedactionService.redact_document(doc_id_txt, RedactionRequest())
    t_redact_txt = time.perf_counter() - t0
    assert red_txt.export_state == "VERIFIED"
    print(f"  TXT Redaction+Verify:{t_redact_txt * 1000:.2f} ms")

    # PDF Detection & Setup
    DetectionService.run_detection(doc_id_pdf)
    pdf_cands = EntityResolver.load_candidates(doc_id_pdf)
    for c in pdf_cands:
        ReviewService.submit_review(
            doc_id_pdf,
            ReviewActionRequest(candidate_id=c.candidate_id, decision=ReviewDecisionAction.APPROVE),
        )

    # Native PDF Redaction
    t0 = time.perf_counter()
    red_pdf_native = RedactionService.redact_document(doc_id_pdf, RedactionRequest())
    t_redact_pdf_native = time.perf_counter() - t0
    assert red_pdf_native.export_state == "VERIFIED"
    print(f"  Native PDF Redaction:{t_redact_pdf_native * 1000:.2f} ms")

    # Fallback Clean-Text PDF Reconstruction
    t0 = time.perf_counter()
    red_pdf_recon = RedactionService.redact_document(
        doc_id_pdf, RedactionRequest(force_text_reconstruction=True)
    )
    t_redact_pdf_recon = time.perf_counter() - t0
    assert red_pdf_recon.export_state == "VERIFIED"
    print(f"  Clean-Text PDF Recon:{t_redact_pdf_recon * 1000:.2f} ms")

    # 8. Summarization and Summary Privacy Guard Latency
    sanitized_txt_content = (s_txt_dir / "sanitized.txt").read_text(encoding="utf-8")
    sanitized_doc = SanitizedDocument(
        document_id=doc_id_txt,
        sanitized_text=sanitized_txt_content,
        export_verification_ref=f"verif_{doc_id_txt}",
        document_format="txt",
        permitted_metadata={},
    )

    t0 = time.perf_counter()
    summary_content = SummaryService.generate_extractive_summary(sanitized_doc.sanitized_text, max_length=250)
    t_summary_gen = time.perf_counter() - t0
    print(f"  Summary Generation:  {t_summary_gen * 1000:.2f} ms (Deterministic Fallback)")

    approved_vals = [c.text for c in cands if c.review_status == "APPROVED"]
    t0 = time.perf_counter()
    guard_report = SummaryGuard.verify_summary(
        summary_content=summary_content,
        sanitized_doc=sanitized_doc,
        guard_references={"approved_values": approved_vals, "entity_variants": []},
    )
    t_summary_guard = time.perf_counter() - t0
    print(f"  Summary Privacy Guard:{t_summary_guard * 1000:.2f} ms (Status: {guard_report.status})")

    # 9. Complete End-to-End TXT and PDF Latencies
    t_e2e_txt = t_ingest_txt + t_detection + t_resolution + t_review_action + t_redact_txt + t_summary_gen + t_summary_guard
    t_e2e_pdf = t_ingest_pdf + t_detection + t_resolution + t_review_action + t_redact_pdf_native + t_summary_gen + t_summary_guard

    print(f"  Complete E2E (TXT):  {t_e2e_txt * 1000:.2f} ms ({t_e2e_txt:.3f} s)")
    print(f"  Complete E2E (PDF):  {t_e2e_pdf * 1000:.2f} ms ({t_e2e_pdf:.3f} s)")

    # 10. Memory Profile (Distinguishing Python Heap Allocation vs OS Process RSS)
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    peak_ram_mb = round(peak_mem / (1024 * 1024), 2)
    proc = psutil.Process()
    process_rss_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
    cpu_pct = psutil.cpu_percent(interval=0.1)
    print(f"  Peak Python Heap (tracemalloc): {peak_ram_mb:.2f} MB")
    print(f"  Actual OS Process Memory (RSS): {process_rss_mb:.2f} MB")
    print(f"  Host CPU Utilization:           {cpu_pct:.1f} %")

    # Cleanup test sessions
    cleanup_session(doc_id_txt)
    delete_document_record(doc_id_txt)
    cleanup_session(doc_id_pdf)
    delete_document_record(doc_id_pdf)
    if test_txt_path.exists():
        test_txt_path.unlink()
    if test_pdf_path.exists():
        test_pdf_path.unlink()

    results = {
        "hardware": {
            "os": os_info,
            "cpu": cpu_info,
            "physical_cores": cores_phys,
            "logical_cores": cores_log,
            "total_ram_gb": ram_gb,
            "python_version": sys.version.split()[0],
            "slm_configured_model": getattr(settings, "SLM_MODEL_NAME", "qwen2.5:1.5b-instruct"),
            "slm_runtime_available": ModelService.check_availability(),
        },
        "latencies_ms": {
            "cold_startup_ms": round(cold_startup_s * 1000, 2),
            "warm_startup_ms": round(warm_startup_s * 1000, 2),
            "txt_ingestion_ms": round(t_ingest_txt * 1000, 2),
            "pdf_ingestion_ms": round(t_ingest_pdf * 1000, 2),
            "hybrid_detection_ms": round(t_detection * 1000, 2),
            "entity_resolution_ms": round(t_resolution * 1000, 2),
            "review_decision_action_ms": round(t_review_action * 1000, 2),
            "manual_candidate_addition_ms": round(t_manual_add * 1000, 2),
            "txt_redaction_and_verification_ms": round(t_redact_txt * 1000, 2),
            "native_pdf_redaction_and_verification_ms": round(t_redact_pdf_native * 1000, 2),
            "clean_text_pdf_reconstruction_ms": round(t_redact_pdf_recon * 1000, 2),
            "summary_generation_fallback_ms": round(t_summary_gen * 1000, 2),
            "summary_privacy_guard_verification_ms": round(t_summary_guard * 1000, 2),
            "complete_e2e_txt_pipeline_ms": round(t_e2e_txt * 1000, 2),
            "complete_e2e_pdf_pipeline_ms": round(t_e2e_pdf * 1000, 2),
        },
        "memory_profile": {
            "python_heap_peak_tracemalloc_mb": peak_ram_mb,
            "os_process_rss_mb": process_rss_mb,
            "host_cpu_percent": cpu_pct,
            "peak_ram_mb": peak_ram_mb,
        },
    }

    out_file = backend_dir / "performance_profile.json"
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("-" * 70)
    print(f"Profiling complete. Output written to {out_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
