# PrivyDoc Evaluation Report: TEST Dataset

**Generated At:** `2026-11-23T10:55:41.005799+00:00`  
**Matching Mode:** `exact`  
**Total Documents Evaluated:** `8`  

## 1. Detection Performance (Micro & Macro)

| Metric Set | Precision | Recall | F1 Score | TP | FP | FN |
|---|---|---|---|---|---|---|
| **Overall (Micro)** | **0.5077** | **0.7333** | **0.6000** | 33 | 32 | 12 |
| **Overall (Macro)** | 0.5923 | 0.7125 | 0.6469 | - | - | - |

### Per-Category Breakdown

| PII Category | Precision | Recall | F1 Score | TP | FP | FN |
|---|---|---|---|---|---|---|
| `ADDRESS` | 0.2000 | 0.2500 | 0.2222 | 1 | 4 | 3 |
| `EMAIL` | 1.0000 | 1.0000 | 1.0000 | 8 | 0 | 0 |
| `ID_LIKE` | 0.4615 | 0.7500 | 0.5714 | 6 | 7 | 2 |
| `PERSON` | 0.3000 | 0.5625 | 0.3913 | 9 | 21 | 7 |
| `PHONE` | 1.0000 | 1.0000 | 1.0000 | 9 | 0 | 0 |

## 2. Entity Resolution Clustering Performance

| Metric | Value |
|---|---|
| Pairwise Precision | `0.0435` |
| Pairwise Recall | `1.0000` |
| Pairwise F1 | `0.0834` |
| False Merge Rate | `0.0837` |
| Missed Link Rate | `0.0000` |
| Pairwise TP / FP / FN / TN | `2` / `44` / `0` / `482` |

## 3. Redaction & Summary Verification Metrics

| Verification Phase | Metric | Value | Target |
|---|---|---|---|
| Redaction Export | Approved Removal Rate | `100.0%` | 100.0% |
| Redaction Export | Preserved Rejected Rate | `100.0%` | 100.0% |
| Summarization | Direct Leakage Rate | `0.0%` | 0.0% |
| Summarization | Suppression Correctness | `100.0%` | 100.0% |

## 4. Resource & Efficiency Profiling

| Metric | Measured Value |
|---|---|
| Total Wall Latency | `0.2157 s` |
| Avg Latency Per Document | `0.0270 s` |
| Peak Memory Consumption | `0.15 MB` |
| Total Characters Analyzed | `2309` chars |
| Total Pages Processed | `8` pages |

> [!NOTE]
> All metrics above were obtained exclusively from synthetic corpus evaluation datasets.
> Synthetic test results should not be claimed as guaranteed production accuracy on arbitrary real-world documents.