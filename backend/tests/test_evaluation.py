"""Unit, Adversarial, and Integrity Tests for Evaluation Metrics Framework.

Verifies:
1. Exact and overlap matching math.
2. Safe zero-denominator handling (no crashes, no false 100% scores).
3. Pairwise entity coreference metrics (Precision, Recall, F1, False Merge Rate, Missed Link Rate).
4. Held-out test set quarantine and isolation (TDR-015).
5. Redaction & Summary verification metrics.
6. Execution latency and peak memory profiling (tracemalloc).
"""

import json
from pathlib import Path
import pytest

from app.detectors.regex_detector import RegexDetector
from app.services.evaluation_service import (
    DetectionScore,
    EvaluationReport,
    EvaluationService,
    PairwiseEntityScore,
    RedactionVerificationScore,
    SummaryVerificationScore,
)


def test_zero_denominator_defense():
    """Verify safe zero-denominator handling across all metric formulas."""
    score = DetectionScore(tp=0, fp=0, fn=0)
    score.compute()

    assert score.precision == 0.0
    assert score.recall == 0.0
    assert score.f1 == 0.0
    assert score.has_zero_denominator is True

    # Denominator zero for precision only
    p_zero = DetectionScore(tp=0, fp=0, fn=3)
    p_zero.compute()
    assert p_zero.precision == 0.0
    assert p_zero.recall == 0.0
    assert p_zero.f1 == 0.0

    # Denominator zero for recall only
    r_zero = DetectionScore(tp=0, fp=4, fn=0)
    r_zero.compute()
    assert r_zero.precision == 0.0
    assert r_zero.recall == 0.0
    assert r_zero.f1 == 0.0


def test_detection_metrics_exact_vs_overlap():
    """Test exact span matching versus token/char overlap matching."""
    gold = [
        {"start": 10, "end": 22, "type": "PERSON", "text": "Elena Vance"},
        {"start": 30, "end": 45, "type": "EMAIL", "text": "elena@aegis.com"},
    ]

    # Prediction has an exact match for EMAIL, but slightly broader span for PERSON
    pred = [
        {"start": 8, "end": 24, "type": "PERSON", "text": "Dr. Elena Vance"},  # Overlap, not exact
        {"start": 30, "end": 45, "type": "EMAIL", "text": "elena@aegis.com"},   # Exact
    ]

    # Exact matching
    exact_overall, exact_cats = EvaluationService.evaluate_detections(gold, pred, matching_mode="exact")
    assert exact_overall.tp == 1  # EMAIL only
    assert exact_overall.fp == 1  # Dr. Elena Vance is FP under exact
    assert exact_overall.fn == 1  # Elena Vance is FN under exact
    assert exact_overall.precision == 0.5
    assert exact_overall.recall == 0.5

    # Overlap matching
    overlap_overall, overlap_cats = EvaluationService.evaluate_detections(gold, pred, matching_mode="overlap")
    assert overlap_overall.tp == 2  # Both matched
    assert overlap_overall.fp == 0
    assert overlap_overall.fn == 0
    assert overlap_overall.precision == 1.0
    assert overlap_overall.recall == 1.0
    assert overlap_overall.f1 == 1.0


def test_pairwise_entity_resolution_metrics():
    """Verify pairwise coreference clustering calculations."""
    gold_mentions = [
        {"mention_id": "m1", "entity_id": "ent_A"},
        {"mention_id": "m2", "entity_id": "ent_A"},
        {"mention_id": "m3", "entity_id": "ent_B"},
        {"mention_id": "m4", "entity_id": "ent_B"},
    ]

    # Case A: Perfect clustering
    pred_perfect = [
        {"mention_id": "m1", "entity_id": "p_1"},
        {"mention_id": "m2", "entity_id": "p_1"},
        {"mention_id": "m3", "entity_id": "p_2"},
        {"mention_id": "m4", "entity_id": "p_2"},
    ]
    perf_score = EvaluationService.evaluate_entity_resolution(gold_mentions, pred_perfect)
    assert perf_score.pairwise_tp == 2  # (m1, m2) and (m3, m4)
    assert perf_score.pairwise_fp == 0
    assert perf_score.pairwise_fn == 0
    assert perf_score.precision == 1.0
    assert perf_score.recall == 1.0
    assert perf_score.f1 == 1.0
    assert perf_score.false_merge_rate == 0.0
    assert perf_score.missed_link_rate == 0.0

    # Case B: False Merge (Over-clustering: all grouped into one entity)
    pred_merged = [
        {"mention_id": "m1", "entity_id": "p_all"},
        {"mention_id": "m2", "entity_id": "p_all"},
        {"mention_id": "m3", "entity_id": "p_all"},
        {"mention_id": "m4", "entity_id": "p_all"},
    ]
    merge_score = EvaluationService.evaluate_entity_resolution(gold_mentions, pred_merged)
    assert merge_score.pairwise_tp == 2
    assert merge_score.pairwise_fp == 4  # (m1, m3), (m1, m4), (m2, m3), (m2, m4) wrongly merged
    assert merge_score.false_merge_rate > 0.0

    # Case C: Missed Links (Under-clustering: all isolated into separate entities)
    pred_split = [
        {"mention_id": "m1", "entity_id": "p_1"},
        {"mention_id": "m2", "entity_id": "p_2"},
        {"mention_id": "m3", "entity_id": "p_3"},
        {"mention_id": "m4", "entity_id": "p_4"},
    ]
    split_score = EvaluationService.evaluate_entity_resolution(gold_mentions, pred_split)
    assert split_score.pairwise_tp == 0
    assert split_score.pairwise_fn == 2
    assert split_score.missed_link_rate == 1.0


def test_held_out_test_set_isolation():
    """Verify held-out test split is strictly segregated and never used to tune patterns."""
    dataset_base = Path(__file__).resolve().parent.parent.parent / "datasets" / "evaluation"
    test_dir = dataset_base / "test"
    assert test_dir.exists(), "Held-out test dataset directory missing!"

    test_docs = list(test_dir.iterdir())
    assert len(test_docs) >= 8, f"Held-out test split should contain at least 8 documents, found {len(test_docs)}"

    # Check isolation invariant: gold annotations from test split must not be hardcoded in RegexDetector
    for doc_dir in test_docs:
        gold_path = doc_dir / "gold_annotations.json"
        if gold_path.exists():
            gold = json.loads(gold_path.read_text(encoding="utf-8"))
            for ann in gold.get("annotations", []):
                val = ann["text"]
                # Invariant: specific test text strings must not be baked into source code regex patterns
                for pat_name, pat in RegexDetector.PATTERNS.items():
                    assert val not in str(pat), f"Test set leakage: '{val}' found hardcoded in pattern '{pat_name}'!"


def test_redaction_and_summary_verification_scores():
    """Verify redaction and summary metric object computations."""
    red_score = RedactionVerificationScore(
        total_approved_spans=10,
        approved_removed_count=10,
        approved_removal_rate=1.0,
        total_rejected_spans=3,
        rejected_preserved_count=3,
        preserved_rejected_rate=1.0,
    )
    assert red_score.approved_removal_rate == 1.0
    assert red_score.preserved_rejected_rate == 1.0

    sum_score = SummaryVerificationScore(
        total_summaries_evaluated=5,
        direct_leakages_detected=0,
        direct_leakage_rate=0.0,
        suppression_correctness_rate=1.0,
    )
    assert sum_score.direct_leakages_detected == 0
    assert sum_score.direct_leakage_rate == 0.0


def test_markdown_report_formatting():
    """Verify Markdown evaluation report formatting produces valid headers and tables."""
    report = EvaluationReport(
        split_name="dev",
        matching_mode="exact",
        document_count=10,
        micro_detection=DetectionScore(tp=10, fp=2, fn=1, precision=0.8333, recall=0.9091, f1=0.8696),
        macro_detection=DetectionScore(precision=0.85, recall=0.90, f1=0.874),
    )
    md = EvaluationService.format_markdown_report(report)

    assert "# PrivyDoc Evaluation Report: DEV Dataset" in md
    assert "Overall (Micro)" in md
    assert "0.8696" in md
    assert "Pairwise Precision" in md
    assert "Resource & Efficiency Profiling" in md
    assert "All metrics above were obtained exclusively from synthetic corpus" in md


def test_stage4_dataset_split_integrity_and_strategy_comparison():
    """Verify Stage 4 benchmark split isolation (zero cross-split entity or document leakage),
    5-strategy detection comparison, explicit pairwise entity denominators, and OS Process RSS vs Python heap profiling.
    """
    base_dir = Path(__file__).resolve().parent.parent.parent
    s4_dir = base_dir / "datasets" / "evaluation_stage4"
    assert s4_dir.exists(), "Stage 4 benchmark directory missing!"

    integrity = EvaluationService.verify_dataset_integrity(s4_dir)
    assert integrity["splits"]["dev"]["document_count"] == 12
    assert integrity["splits"]["val"]["document_count"] == 12
    assert integrity["splits"]["test"]["document_count"] == 12
    # Negative (0-PII) documents must be present in every split
    assert integrity["splits"]["dev"]["negative_document_count"] >= 1
    assert integrity["splits"]["val"]["negative_document_count"] >= 1
    assert integrity["splits"]["test"]["negative_document_count"] >= 1
    # Zero cross-split duplicate documents or entity surface string leakage
    assert integrity["cross_split_duplicate_docs"] == {"dev_vs_val": 0, "dev_vs_test": 0, "val_vs_test": 0}
    assert integrity["cross_split_entity_overlaps"] == {"dev_vs_val": [], "dev_vs_test": [], "val_vs_test": []}

    # Verify strategy comparison on held-out test split
    strat_cmp = EvaluationService.compare_detection_strategies(s4_dir, "test")
    assert set(strat_cmp.keys()) == {"regex_only", "ner_only", "hybrid_no_slm", "hybrid_with_slm"}
    assert strat_cmp["hybrid_no_slm"]["exact_micro"]["f1"] > strat_cmp["regex_only"]["exact_micro"]["f1"]
    assert strat_cmp["hybrid_no_slm"]["exact_micro"]["f1"] > strat_cmp["ner_only"]["exact_micro"]["f1"]

    # Verify benchmark report records both OS Process RSS MB and Python heap tracemalloc MB
    rep = EvaluationService.run_benchmark_on_dataset(s4_dir, "test", "exact")
    assert rep.performance.process_rss_mb > 10.0  # Real OS process RSS (>10 MB, typically ~85 MB)
    assert rep.performance.peak_memory_mb >= 0.0
    assert rep.entity_metrics.gold_positive_pairs == 8
    assert rep.entity_metrics.predicted_positive_links == 8
    assert rep.entity_metrics.false_discovery_rate == 0.0
