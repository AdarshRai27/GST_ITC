# Test Results

**Date:** 2026-10-29
**Environment:** Windows, Python 3.13.7, streamlit 1.66.1, pandas 2.3.3,
openpyxl 3.1.5, rapidfuzz 3.14.6
**Working directory:** `C:\Users\rinku\ML Project\GST_ITC`

---

## 1. Commands and outcomes

| Command | Result | Exit code |
|---|---|---:|
| `python -m pytest -q` | **215 passed** in ~23 s | 0 |
| `python -m ruff check .` | **All checks passed!** | 0 |
| `python scripts/verify_pipeline.py` | **20/20 checks passed** | 0 |
| `streamlit run ... --server.address=127.0.0.1 --server.port=8518` | `/_stcore/health` → `200 ok`; `/` → `200` | 0 (stopped after check) |
| **Fresh isolated venv:** `pip install -r requirements.txt` | Succeeded | 0 |
| **Fresh isolated venv:** `python -m pytest -q` | **215 passed** in ~24 s | 0 |
| **Fresh isolated venv:** `python -m ruff check .` | **All checks passed!** | 0 |
| **Fresh isolated venv:** `python scripts/verify_pipeline.py` | **20/20 checks passed** | 0 |
| **Fresh isolated venv:** Streamlit health | `200 ok` | 0 (stopped after check) |

No tests were skipped, xfailed, weakened, or deleted to obtain these results. The
only deleted test file is the previously unrelated `tests/test_eeg_pipeline.py`
(EEG/XGBoost code that did not belong to this project and failed collection).

---

## 2. Pytest breakdown (215 collected)

| File | Tests | Focus |
|---|---:|---|
| `tests/test_app.py` | 21 | Streamlit AppTest: sample/upload runs, errors, review, export, audit, isolation |
| `tests/test_audit.py` | 11 | Append-only audit, review records |
| `tests/test_decision.py` | 17 | Actions, priorities, eligibility, exposure |
| `tests/test_ingest.py` | 16 | CSV/XLSX/JSON loading and errors |
| `tests/test_llm.py` | 15 | Opt-in boundary and fallback |
| `tests/test_matcher.py` | 29 | Exact/fuzzy/probable, duplicates, thresholds, `record_id` |
| `tests/test_messages.py` | 10 | Deterministic vendor drafts |
| `tests/test_metrics.py` | 8 | KPI definitions and review aggregation |
| `tests/test_normalize.py` | 26 | GSTIN/invoice/date/amount normalization |
| `tests/test_report.py` | 17 | Export sheets, injection protection, status codes |
| `tests/test_review_policy.py` | 8 | Allowed actions / invalid-row approval block |
| `tests/test_rules.py` | 17 | Isolated calculations and rule sources |
| `tests/test_uploads.py` | 20 | Upload safety, size/type/traversal, cleanup, parser handoff |
| **Total** | **215** | |

---

## 3. New regression tests added during remediation

| File | New coverage |
|---|---|
| `tests/test_uploads.py` | CSV/XLSX/JSON uploads, malformed/empty/oversized/unsupported files, traversal filenames, repeated uploads, cleanup, invalid XLSX handoff |
| `tests/test_app.py` | Sample run, upload run with temp-file deletion, invalid CSV/JSON errors, failed-run recovery, empty dataset, exact review, duplicate identity separation, invalid no-approve, export, audit event types, run isolation, all review rows selectable |
| `tests/test_metrics.py` | Exact-only confirmed KPI, mismatch separation, review latest-state de-duplication, cross-run review exclusion, empty run, exposure |
| `tests/test_review_policy.py` | Policy allow-list, invalid rows cannot be approved, non-reviewable rows reject actions, normalization, unknown/non-string actions |
| `tests/test_matcher.py` | Unique/duplicate-aware `record_id`, fallback identity, `fuzzy_threshold` boundary, discrepancy reason text |
| `tests/test_report.py` | Leading-whitespace formula injection, stable status codes, confirmed-match definition |

---

## 4. End-to-end verifier checks (20/20)

```text
[PASS] purchase-register ingestion — 9 rows
[PASS] GSTR-2B ingestion — 7 rows
[PASS] normalization preserves rows
[PASS] book-row statuses match ground truth
[PASS] unmatched GSTR-2B indices match ground truth — [5]
[PASS] status counts match ground truth
[PASS] confirmed-match precision = 1.0
[PASS] confirmed-match recall = 1.0
[PASS] one decision per reconciliation row
[PASS] exact matches are candidates, not approved claims
[PASS] invalid rows cannot be approved
[PASS] confirmed KPI excludes mismatches — 2
[PASS] review-required count — 9
[PASS] no records reviewed initially
[PASS] source-row count — 16
[PASS] Excel export creates expected sheets — Summary, Reconciliation, Decisions
[PASS] Excel file is non-empty
[PASS] formula injection is escaped
[PASS] audit log round-trips
[PASS] provisional exposure is quantified — 8890.00
```

---

## 5. Streamlit workflow evidence (AppTest)

Verified programmatically:

- Sample run produces 10 decisions and the expected metrics.
- Uploaded CSV + JSON run produces 10 decisions; temp upload directory is empty
  afterwards.
- Invalid CSV error includes `column validation` and `invoice_date`.
- Invalid JSON error includes `Malformed JSON`.
- Failed upload can be followed by a successful run.
- Empty dataset produces zero metrics with no exception.
- Reviewing `books:0` records an approval with `previous_state="none"` and emits
  a `review_action` audit event.
- Duplicate rows `books:5` and `books:0` remain distinct review identities.
- Invalid row `books:6` exposes only Reject/Pending.
- Export produces a non-empty XLSX (`PK` header) and a `export_created` event.
- Re-running rotates `run_id`, clears reviews, and keeps confirmed matches at 2.
- All nine review-required sample rows are present in the selector.

---

## 6. Failures encountered during remediation and resolution

| Failure | Cause | Resolution |
|---|---|---|
| `test_unsupported_object_rejected` did not raise | A bare `object()` has no `name`, so extension validation failed first | Test now uses an object with a `.name` but no read/getbuffer |
| `test_purchase_and_gstr2b_uploads_do_not_collide` raised unsupported type | Second fixture used `.csv` with a JSON-only extension list | Fixture changed to `.json` |
| `NameError: MatchResult` in `test_matcher.py` | New test used `MatchResult` without importing it | Added import |
| Ruff import-order failures | New imports not sorted | `ruff check --fix` |

These were test/import issues; no production behavior was weakened.

---

## 7. Reproducibility notes

- The verifier uses only repository fixtures under `data/sample/` and a temp
  directory for the export/audit round-trip.
- Tests that touch run directories use `tmp_path` or `ITC_SENTINEL_DATA_DIR`, so
  they do not mix with local demo runs.
- A fresh isolated venv (`%TEMP%\itc_venv_check`) reproduced the install, the
  215-test suite, Ruff, the 20/20 verifier, and the Streamlit health check. The
  workspace interpreter produced identical results.
