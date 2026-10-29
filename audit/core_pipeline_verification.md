# Core Pipeline Verification

**Date:** 2026-10-29
**Scope:** Deterministic synthetic-data pipeline, end to end
**Command:** `python scripts/verify_pipeline.py`
**Result:** 20/20 checks passed, exit code 0

---

## 1. Pipeline stages verified

| Stage | Module | Input | Output | Verified by |
|---|---|---|---|---|
| Ingestion | `ingest.py` | `data/sample/purchase_register_synthetic.csv` | 9 raw rows | `purchase-register ingestion` |
| Ingestion | `ingest.py` | `data/sample/gstr2b_synthetic.json` | 7 raw invoices | `GSTR-2B ingestion` |
| Normalization | `normalize.py` | Raw rows | Canonical `NormalizedRecord` rows (9 + 7) | `normalization preserves rows` |
| Reconciliation | `matcher.py` | Normalized records | 10 reconciliation results | `book-row statuses match ground truth`, `status counts match ground truth` |
| Decision support | `decision.py` | Match results | 10 `DecisionResult` objects | `one decision per reconciliation row` |
| Metrics | `metrics.py` | Result + decisions | Documented KPI set | `confirmed KPI excludes mismatches`, `review-required count`, `source-row count` |
| Export | `report.py` | Decisions (+ drafts/reviews/audit) | XLSX workbook | `Excel export creates expected sheets`, `Excel file is non-empty` |
| Audit | `audit.py` | Events | Append-only JSONL round-trip | `audit log round-trips` |

---

## 2. Ground-truth reconciliation results

Expected and observed book-row statuses:

| Books row | Expected status | Observed |
|---:|---|---|
| 0 | exact | exact |
| 1 | exact | exact |
| 2 | fuzzy | fuzzy |
| 3 | amount_mismatch | amount_mismatch |
| 4 | tax_head_mismatch | tax_head_mismatch |
| 5 | duplicate | duplicate |
| 6 | invalid | invalid |
| 7 | unmatched_books | unmatched_books |
| 8 | probable | probable |

GSTR-2B-only row: index 5 → `unmatched_gstr2b`.

Status counts (observed = expected):

```text
exact=2, fuzzy=1, amount_mismatch=1, tax_head_mismatch=1,
duplicate=1, invalid=1, probable=1, unmatched_books=1, unmatched_gstr2b=1
```

Matching quality on the five confirmed-status rows:

- True positives: 5
- False positives: 0
- False negatives: 0
- Precision: 1.0
- Recall: 1.0
- Probable matches are evaluated separately and never counted as confirmed.

---

## 3. Decision and policy checks

| Check | Result |
|---|---|
| One decision per reconciliation row | PASS |
| Exact matches are `PROPOSE_ITC_CLAIM`, not approved claims | PASS |
| Exact matches set `review_required=True` (eligibility remains `UNCERTAIN`) | PASS |
| Invalid rows cannot be approved (`allowed_review_decisions` excludes approve) | PASS |
| Invalid-row `validate_review_decision(..., "approve")` raises `ValueError` | PASS |
| Non-review-required rows reject review actions | PASS |

Policy lives in `decision.py`; the UI does not define its own allow-list.

---

## 4. Metrics checks

| Metric | Expected | Observed |
|---|---:|---:|
| Reconciliation rows | 10 | 10 |
| Source rows | 16 | 16 |
| Confirmed matches (exact only) | 2 | 2 |
| Review required | 9 | 9 |
| Reviewed initially | 0 | 0 |
| Provisional exposure | ₹8,890.00 | ₹8,890.00 |

Confirmed matches exclude amount mismatches, tax-head mismatches, fuzzy,
probable, duplicate, invalid, and unmatched rows.

---

## 5. Export and audit checks

| Check | Result |
|---|---|
| Workbook contains Summary, Reconciliation, Decisions (plus Drafts/Review/Audit when supplied) | PASS |
| Workbook file non-empty | PASS |
| Formula-injection escaping for `=`, and for leading-whitespace `  =` | PASS |
| Audit event round-trips through append-only JSONL | PASS |
| Summary sheet uses stable status codes, not `MatchStatus.*` reprs | PASS (unit test) |

---

## 6. Failure-path verification (AppTest)

`tests/test_app.py` verifies:

- Malformed purchase CSV produces an actionable column-validation error and no
  dashboard.
- Malformed GSTR-2B JSON produces an actionable "Malformed JSON" error.
- A failed run can be followed by a successful run without stale UI state.
- Uploaded temp files are removed after both successful and failed ingestion.
- Empty datasets produce zero metrics without exceptions.
- Re-running rotates `run_id`, clears review records, and recomputes metrics.

---

## 7. Determinism

- Matching and decisions use no randomness.
- Re-running the same fixtures produces identical statuses, counts, and
  exposure.
- Duplicate rows receive distinct stable IDs (`books:0` vs `books:5`).
- Rounding is explicit (`ROUND_HALF_UP`, 2 decimal places) across matching,
  rules, decisions, and metrics.

---

## 8. Residual verification gaps

1. **CA rule validation (P3-01):** not performed; eligibility remains
   `UNCERTAIN` by design.
2. **Real GSTR-2B export variants:** the declared JSON contract is an assumption.
3. **Fully isolated clean-venv install:** verified 2026-10-29 (install, 215
   tests, Ruff, 20/20 verifier, and Streamlit health check).
4. **Audit immutability:** append-only by convention, not tamper-proof.

These are documented conditions, not silent failures.
