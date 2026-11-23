"""CLI Evaluation Harness for PrivyDoc.

Reproduces all reported metrics deterministically from committed synthetic datasets.
Produces unadjusted, honest evaluation reports formatted in Markdown and JSON.

Usage:
    python scripts/evaluate.py --split test --matching exact --output-md Docs/EVALUATION_REPORT.md
"""

import argparse
import json
import sys
from pathlib import Path

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "backend"))

from app.services.evaluation_service import EvaluationReport, EvaluationService


def run_evaluation(
    split: str = "test",
    matching: str = "exact",
    output_md: str | None = None,
    output_json: str | None = None,
) -> int:
    """Run evaluation benchmark across specified split and render report."""
    dataset_dir = BASE_DIR / "datasets" / "evaluation"
    if not dataset_dir.exists():
        print(f"Error: Dataset directory '{dataset_dir}' does not exist.")
        print("Please run 'python scripts/generate_synthetic_corpus.py' first.")
        return 1

    print(f"============================================================")
    print(f"PrivyDoc Evaluation Harness")
    print(f"Split: {split.upper()} | Matching: {matching.upper()}")
    print(f"============================================================")

    splits_to_run = ["dev", "val", "test"] if split == "all" else [split]

    all_reports = []
    for sp in splits_to_run:
        print(f"Running benchmark on '{sp}' split...")
        rep = EvaluationService.run_benchmark_on_dataset(
            dataset_dir=dataset_dir,
            split=sp,
            matching_mode=matching,
        )
        all_reports.append(rep)
        print(
            f"[{sp.upper()}] Evaluated {rep.document_count} docs | "
            f"Micro P: {rep.micro_detection.precision:.4f} | "
            f"R: {rep.micro_detection.recall:.4f} | "
            f"F1: {rep.micro_detection.f1:.4f} | "
            f"Entity F1: {rep.entity_metrics.f1:.4f} | "
            f"Latency: {rep.performance.total_latency_seconds:.3f}s"
        )

    # Use primary report for markdown output
    primary_report = all_reports[-1]
    md_content = EvaluationService.format_markdown_report(primary_report)

    if output_md:
        out_path = Path(output_md)
        if not out_path.is_absolute():
            out_path = BASE_DIR / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md_content, encoding="utf-8")
        print(f"Markdown report written to: {out_path}")

    if output_json:
        json_path = Path(output_json)
        if not json_path.is_absolute():
            json_path = BASE_DIR / json_path
        json_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Serialize report dataclasses
        from dataclasses import asdict
        payload = [asdict(r) for r in all_reports]
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"JSON report written to: {json_path}")

    return 0


def main():
    parser = argparse.ArgumentParser(description="PrivyDoc Evaluation CLI Harness")
    parser.add_argument(
        "--split",
        choices=["dev", "val", "test", "all"],
        default="test",
        help="Dataset split to evaluate (default: test - held out)",
    )
    parser.add_argument(
        "--matching",
        choices=["exact", "overlap"],
        default="exact",
        help="Span matching mode (default: exact)",
    )
    parser.add_argument(
        "--output-md",
        default="Docs/EVALUATION_REPORT.md",
        help="Path for generated Markdown evaluation report",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional path for JSON output report",
    )

    args = parser.parse_args()
    ret = run_evaluation(
        split=args.split,
        matching=args.matching,
        output_md=args.output_md,
        output_json=args.output_json,
    )
    sys.exit(ret)


if __name__ == "__main__":
    main()
