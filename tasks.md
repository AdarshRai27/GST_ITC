# ITC Sentinel — Live Task Tracker

**Last updated:** 2026-10-29
**Overall progress:** Phases 0–6 implementation and verification complete for the
synthetic-data MVP. One external validation task (P3-01, CA review) remains open
and is a documented condition, not a code defect.
**Current phase:** Phase 6 — Verification and demo readiness (complete, re-verified
after defect remediation).

> Do not infer implementation progress from this plan. Mark work complete only
> after checking the actual repository and recording evidence.

## Current task

None. Defect remediation and Phase 6 re-verification are complete. Deployment is
not performed; see `audit/deployment_readiness.md` for the verdict and conditions.

## Phase 0 tasks (completed)

| ID | Task | Phase | Priority | Status | Evidence |
|---|---|---:|---|---|---|
| P0-01 | Establish and reconcile the six root documentation files | 0 | P0 | Complete | Six Markdown files at project root; `itc_sentinel_project_docs/` retained. |
| P0-02 | Inspect actual repository and preserve existing user work | 0 | P0 | Complete | Repository inspected; no pre-existing application code overwritten. |
| P0-03 | Add `.gitignore`, `.env.example`, `requirements.txt`, `pyproject.toml`, README | 0 | P0 | Complete | Files exist; `.env.example` contains placeholders only; `.env` git-ignored. |
| P0-04 | Verify clean environment setup and scope assumptions | 0 | P1 | Complete | `.venv` created; dependencies installed; imports and tooling verified. |

## Phase 1 tasks (completed)

| ID | Task | Phase | Priority | Status | Evidence |
|---|---|---:|---|---|---|
| P1-01 | Implement purchase-register and GSTR-2B loaders | 1 | P0 | Complete | `src/itc_sentinel/ingest.py`: `load_purchase_register()` (CSV/XLSX), `load_gstr2b_json()` (JSON). XLSX parse errors are wrapped in `IngestionError`; workbook handles are closed. |
| P1-02 | Implement normalization and row-level validation | 1 | P0 | Complete | `src/itc_sentinel/normalize.py`: GSTIN, invoice, date, amount normalization; invalid rows preserved with issues; `ROUND_HALF_UP` to 2 places. |
| P1-03 | Add ingestion/normalization tests | 1 | P0 | Complete | `tests/test_ingest.py` (16), `tests/test_normalize.py` (26), `tests/test_uploads.py` (20). |

## Phase 2 tasks (completed)

| ID | Task | Phase | Priority | Status | Evidence |
|---|---|---:|---|---|---|
| P2-01 | Generate seeded synthetic datasets with ground truth | 2 | P0 | Complete | `scripts/generate_synthetic_data.py`; `data/sample/*_synthetic.*` + `ground_truth.json`. |
| P2-02 | Implement exact/fuzzy/probable matching and exception statuses | 2 | P0 | Complete | `src/itc_sentinel/matcher.py`; same-GSTIN and one-to-one constraints; `fuzzy_threshold` enforced. |
| P2-03 | Measure matching accuracy and add edge-case tests | 2 | P0 | Complete | `tests/test_matcher.py` (29). Ground truth precision = 1.0, recall = 1.0. Stable `record_id` added so duplicate invoices have distinct identities. |

## Phase 3 tasks (completed except CA review)

| ID | Task | Phase | Priority | Status | Evidence |
|---|---|---:|---|---|---|
| P3-01 | Validate tax-rule assumptions with authoritative sources / CA review | 3 | P0 | **Pending (external)** | No CA validation available in this environment. All rules remain labelled `ca_verification_required=True`; eligibility stays `UNCERTAIN`. |
| P3-02 | Implement deterministic decisions, risk flags, priorities, explanations | 3 | P0 | Complete | `rules.py` + `decision.py`; exact matches emit `PROPOSE_ITC_CLAIM` with `review_required=True`; invalid rows cannot be approved. |
| P3-03 | Add rule and decision tests | 3 | P0 | Complete | `tests/test_rules.py` (17), `tests/test_decision.py` (17), `tests/test_review_policy.py` (8). |

## Phase 4 tasks (completed)

| ID | Task | Phase | Priority | Status | Evidence |
|---|---|---:|---|---|---|
| P4-01 | Implement review audit, safe exports, vendor draft templates | 4 | P1 | Complete | `audit.py`, `report.py`, `messages.py`; review records carry `record_id`, `previous_state`, `new_state`; export escapes formula-injection prefixes including leading whitespace. |
| P4-02 | Add optional LLM wording enhancement and validation/fallback | 4 | P2 | Complete | `llm.py`; opt-in, disabled by default, template fallback. |

## Phase 5 tasks (completed)

| ID | Task | Phase | Priority | Status | Evidence |
|---|---|---:|---|---|---|
| P5-01 | Build Streamlit dashboard and exception review workflow | 5 | P1 | Complete | `app.py`; four tabs; review worklist driven by `review_required`; all 9 review-required sample rows selectable. |
| P5-02 | Add export/audit and vendor-message views | 5 | P1 | Complete | Excel download, audit event table, recorded-review table. |
| P5-03 | Launch Streamlit locally and perform end-to-end smoke test | 5 | P0 | Complete | `tests/test_app.py` (21 AppTest cases) plus `scripts/verify_pipeline.py`. |

## Phase 6 tasks (completed)

| ID | Task | Phase | Priority | Status | Evidence |
|---|---|---:|---|---|---|
| P6-01 | Run complete tests, lint, benchmark, and demo checklist | 6 | P0 | Complete | `pytest`: 215 passed; `ruff check .`: clean; `scripts/verify_pipeline.py`: 20/20 checks pass; reproduced in a fresh isolated venv. |
| P6-02 | Fix upload, review-identity, worklist, policy, and metric defects | 6 | P0 | Complete | `uploads.py`, `record_id`, `metrics.py`, review policy functions, tests listed in `audit/final_change_summary.md`. |
| P6-03 | Reconcile documentation and issue deployment verdict | 6 | P0 | Complete | `README.md`, `tasks.md`, `memory.md`, `phases.md`, and `audit/` reports updated to match code. |

## Test totals (verified 2026-10-29)

| File | Tests |
|---|---:|
| `tests/test_app.py` | 21 |
| `tests/test_audit.py` | 11 |
| `tests/test_decision.py` | 17 |
| `tests/test_ingest.py` | 16 |
| `tests/test_llm.py` | 15 |
| `tests/test_matcher.py` | 29 |
| `tests/test_messages.py` | 10 |
| `tests/test_metrics.py` | 8 |
| `tests/test_normalize.py` | 26 |
| `tests/test_report.py` | 17 |
| `tests/test_review_policy.py` | 8 |
| `tests/test_rules.py` | 17 |
| `tests/test_uploads.py` | 20 |
| **Total** | **215** |

## Verification evidence (recorded 2026-10-29)

- `python -m pytest -q` — 215 passed, exit 0 (workspace and fresh isolated venv).
- `python -m ruff check .` — "All checks passed!", exit 0 (workspace and fresh venv).
- `python scripts/verify_pipeline.py` — 20/20 checks pass, exit 0 (workspace and fresh venv).
- Fresh isolated venv: `pip install -r requirements.txt` exit 0; Streamlit health `200 ok`.
- Synthetic ground truth: exact=2, fuzzy=1, amount_mismatch=1,
  tax_head_mismatch=1, duplicate=1, invalid=1, probable=1, unmatched_books=1,
  unmatched_gstr2b=1. Precision = recall = 1.0.
- Metrics: 10 reconciliation rows, 16 source rows, 2 confirmed (exact only),
  9 review-required, provisional exposure ₹8,890.00.
- Uploaded temp files are deleted after success and failure (AppTest verified).
- No secrets or real taxpayer data found; `.env` is git-ignored.
- No Git commits made during this session.

## Blocked / open items

- **P3-01 (CA validation):** External dependency; not available. Not a code
  blocker for a synthetic-data demo, but blocks any real-data or production use.
- **B-01:** RESOLVED. Repository available locally; six documentation files present.
- **B-02:** GST-specific rules remain unverified until reviewed by a qualified CA.
  All unverified rules are explicitly provisional and eligibility stays `UNCERTAIN`.

## Progress policy

- Update this tracker after each meaningful code/documentation change.
- Record test commands and outcomes before closing tasks.
- Keep one current task and one active phase.
- Overall progress is based on completed acceptance criteria, not file count or
  lines of code.
