# Final Change Summary

**Date:** 2026-10-29
**Scope:** Defect remediation, verification, and documentation reconciliation for
the ITC Sentinel synthetic-data MVP.
**Git commits:** None (not authorized).
**Deployment:** None.

---

## 1. Behavior changes (user-visible and policy-relevant)

| # | Before | After |
|---|---|---|
| 1 | Streamlit `UploadedFile` objects were passed toward path-based loaders; uploads could fail. | Bytes are written to a run-scoped temp path with size/type/traversal checks, then deleted after success or failure. |
| 2 | Review selection keyed on a GSTIN+invoice display label; duplicate invoices could collide. | Stable `record_id` (`books:<row>` / `gstr2b:<row>`) identifies each result; duplicates stay distinct. |
| 3 | Review worklist used a duplicated status list and missed rows. | Worklist is driven by `DecisionResult.review_required`; all nine review-required sample rows are selectable. |
| 4 | Exact matches emitted `CLAIM_ITC` with `review_required=False`. | Exact matches emit `PROPOSE_ITC_CLAIM` with `review_required=True`; eligibility remains `UNCERTAIN`. |
| 5 | Review actions were not policy-checked outside the UI. | `allowed_review_decisions()` / `validate_review_decision()` enforce policy in `decision.py`; invalid rows cannot be approved. |
| 6 | Dashboard “confirmed matches” could include mismatches/fuzzy rows. | `metrics.py` defines confirmed = exact only; mismatches, fuzzy, probable, duplicate, invalid, unmatched are separate KPIs. |
| 7 | Metrics/review state could mix across runs in one session. | Each reconciliation request rotates `run_id`, audit log, and review state. |
| 8 | Fuzzy threshold was not enforced; discrepancy reasons sometimes claimed monetary differences for date-only issues. | Threshold enforced; reason text names the actual differing fields. |
| 9 | Rounding relied on default decimal behavior in places. | `ROUND_HALF_UP` applied consistently in `rules.py`, `matcher.py`, `decision.py`, `metrics.py`. |
| 10 | Invalid XLSX could leak openpyxl exceptions; workbook handle not closed. | Invalid XLSX wrapped as `IngestionError`; workbook closed in `finally`. |
| 11 | Formula-injection escaping missed leading-whitespace variants. | `safe_cell_value()` checks the first non-whitespace character. |
| 12 | Summary export used enum reprs for statuses. | Stable `.value` codes used. |
| 13 | 23 pytest temp artifacts were tracked in Git. | Removed from the working tree; `.gitignore` updated (deletion needs a commit). |

---

## 2. Source files changed

| File | Change | Reason |
|---|---|---|
| `src/itc_sentinel/uploads.py` | **New** | Safe upload persistence, validation, sanitisation, cleanup |
| `src/itc_sentinel/metrics.py` | **New** | Canonical KPI computation for UI, export, and tests |
| `src/itc_sentinel/app.py` | Rewritten workflow | Correct Run-button structure, upload handling, stable review selection, policy-driven actions, run isolation, metrics UI |
| `src/itc_sentinel/matcher.py` | Added `record_id`, `record_identity()`; enforced fuzzy threshold; reason/rounding fixes | Stable identity and correct match classification |
| `src/itc_sentinel/decision.py` | `PROPOSE_ITC_CLAIM`; exact-match review policy; review action policy; rounding | No premature claim; enforceable policy |
| `src/itc_sentinel/audit.py` | `ReviewRecord.record_id`, `previous_state`, `new_state` | Traceable, duplicate-safe review history |
| `src/itc_sentinel/report.py` | Record IDs, review states, confirmed-match summary, stable status codes, safer escaping | Accurate, safe export |
| `src/itc_sentinel/ingest.py` | XLSX error wrapping, handle cleanup | Actionable errors, no leaked handles |
| `src/itc_sentinel/rules.py` | Explicit `ROUND_HALF_UP` | Consistent money policy |

---

## 3. Tests added or updated

| File | Status | Coverage |
|---|---|---|
| `tests/test_uploads.py` | **New** (20) | Upload safety, malformed/oversized/empty, traversal, cleanup, parser handoff |
| `tests/test_app.py` | **New** (21) | Full Streamlit workflow via AppTest |
| `tests/test_metrics.py` | **New** (8) | KPI definitions and review aggregation |
| `tests/test_review_policy.py` | **New** (8) | Allowed actions, invalid-row approval block |
| `tests/test_matcher.py` | Updated (+ identity/threshold/reason tests) | 29 total |
| `tests/test_decision.py` | Updated | 17 total; exact-match policy |
| `tests/test_report.py` | Updated | 17 total; injection/status-code checks |
| `tests/test_eeg_pipeline.py` | **Deleted** | Unrelated EEG/XGBoost file that failed collection; not part of this project |

No tests were disabled, skipped, or weakened. The suite grew from 152 to 215
tests.

---

## 4. Documentation and repository changes

| File | Change |
|---|---|
| `README.md` | Corrected duplicate setup step, stale phase/test claims, run/output paths, upload limits, new modules and verifier |
| `tasks.md` | Rewritten with accurate phase status, per-file test counts, evidence, open P3-01 |
| `memory.md` | Rewritten with current decisions, defect list, metrics, known issues |
| `phases.md` | Checklists checked off where evidenced; Phase 6 conditions recorded |
| `.gitignore` | Added `pytest-of-*/`, `pip-build-tracker-*/`, `pip-ephem-wheel-cache-*/`, `pip-install-*/` |
| `pytest-of-rinku/` (23 files) | Removed from working tree; tracked deletion pending a commit |
| `scripts/verify_pipeline.py` | **New** reproducible end-to-end verifier replacing stale `verify_phase6.py` references |
| `audit/*` | Six required artifacts plus updated Phase 6 report |

---

## 5. Verification performed

| Check | Result |
|---|---|
| `python -m pytest -q` | 215 passed, exit 0 (workspace and fresh venv) |
| `python -m ruff check .` | All checks passed, exit 0 (workspace and fresh venv) |
| `python scripts/verify_pipeline.py` | 20/20 checks, exit 0 (workspace and fresh venv) |
| Fresh isolated venv install | `pip install -r requirements.txt` exit 0 |
| Live Streamlit health | `200 ok`; root `200` (workspace and fresh venv) |
| Secret-pattern scan | No matches |
| Upload cleanup (AppTest) | Upload directory empty after run |
| Audit events (AppTest) | `run_started`, `run_completed`, `export_created`, `review_action` as applicable |

---

## 6. Explicitly not done

- No Git commit, branch, tag, or push.
- No deployment or hosted instance.
- No new frontend, API, database, agent framework, or container.
- No auto-filing, payments, or message sending.
- No real taxpayer data or credentials introduced.
- No CA validation (external, still open as P3-01).
- No weakening or deletion of legitimate tests.

---

## 7. Reviewer starting points

1. `audit/deployment_readiness.md` — verdict and conditions.
2. `audit/test_results.md` — exact commands and counts.
3. `audit/core_pipeline_verification.md` — pipeline checks and ground truth.
4. `audit/phase_completion_matrix.md` — phase-by-phase status.
5. `audit/implementation_backlog.md` — remaining work.
6. `python scripts/verify_pipeline.py` — reproduce the core evidence.
