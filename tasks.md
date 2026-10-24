# ITC Sentinel — Live Task Tracker

**Last updated:** 2026-10-22  
**Overall progress:** 67% — Phases 0–5 complete; Streamlit MVP UI implemented; awaiting owner approval to begin Phase 6.  
**Current phase:** Phase 5 — Streamlit MVP (complete, verified with end-to-end smoke test).

> Do not infer implementation progress from this plan. Mark work complete only after checking the actual repository and recording evidence.

## Current task

None — Phase 4 is complete. Awaiting owner approval to begin Phase 5.

## Phase 0 tasks (completed)

| ID | Task | Phase | Priority | Status | Evidence |
|---|---|---:|---|---|---|
| P0-01 | Establish and reconcile the six root documentation files | 0 | P0 | Complete | Six Markdown files copied from `itc_sentinel_project_docs/` to project root; SHA-256 hash comparison confirmed all six match originals. |
| P0-02 | Inspect actual repository and preserve any existing user work | 0 | P0 | Complete | Repository inspected: empty git tree on `master`, no commits, no existing `.py`/config/test/sample files. Only `itc_sentinel_project_docs/` and `.zip` present (preserved, not deleted). |
| P0-03 | Add `.gitignore`, `.env.example`, `requirements.txt`, `pyproject.toml`, README skeleton | 0 | P0 | Complete | Created: `requirements.txt`, `pyproject.toml`, `.gitignore`, `.env.example`, `README.md`, `src/itc_sentinel/__init__.py`, `tests/`, `data/sample/`, `data/runs/`. `.env.example` contains placeholders only. |
| P0-04 | Verify clean environment setup and scope assumptions | 0 | P1 | Complete | `.venv` created; `pip install -r requirements.txt` exit 0; imports verified; `ruff check .` exit 0; `pytest` exit 5, collected 0 items. Python 3.13.7, pip 26.0. |

## Phase 1 tasks (completed)

| ID | Task | Phase | Priority | Status | Evidence |
|---|---|---:|---|---|---|
| P1-01 | Implement purchase-register and GSTR-2B loaders | 1 | P0 | Complete | `src/itc_sentinel/ingest.py`: `load_purchase_register()` (CSV/XLSX) and `load_gstr2b_json()` (JSON). Declared GSTR-2B JSON contract documented in docstring as an assumption. |
| P1-02 | Implement normalization and row-level validation | 1 | P0 | Complete | `src/itc_sentinel/normalize.py`: GSTIN, invoice-number, date, amount normalization; `normalize_records()` preserves invalid rows with issues. |
| P1-03 | Add ingestion/normalization tests | 1 | P0 | Complete | `tests/test_ingest.py`, `tests/test_normalize.py`, `tests/conftest.py`, `data/sample/purchase_register.csv`, `data/sample/gstr2b.json`. 42 tests collected, 42 passed, exit 0. |

## Phase 2 tasks (completed)

| ID | Task | Phase | Priority | Status | Evidence |
|---|---|---:|---|---|---|
| P2-01 | Generate seeded synthetic datasets with ground truth | 2 | P0 | Complete | `scripts/generate_synthetic_data.py`: deterministic generator for `purchase_register_synthetic.csv`, `gstr2b_synthetic.json`, `ground_truth.json`. All data synthetic; no real taxpayer data. |
| P2-02 | Implement exact/fuzzy/probable matching and exception statuses | 2 | P0 | Complete | `src/itc_sentinel/matcher.py`: `reconcile()` engine with EXACT, AMOUNT_MISMATCH, TAX_HEAD_MISMATCH, FUZZY, PROBABLE, LOW_CONFIDENCE, UNMATCHED_BOOKS, UNMATCHED_GSTR2B, DUPLICATE, INVALID statuses. Same-GSTIN and one-to-one constraints enforced. |
| P2-03 | Measure matching accuracy and add edge-case tests | 2 | P0 | Complete | `tests/test_matcher.py`: 27 tests covering exact, fuzzy, probable, unmatched, duplicate, invalid, amount/tax-head mismatch, competing candidates, one-to-one, determinism, precision/recall. Ground-truth precision=1.0, recall=1.0, true_positives=5, false_positives=0, false_negatives=0. |

## Phase 3 tasks (completed)

| ID | Task | Phase | Priority | Status | Evidence |
|---|---|---:|---|---|---|
| P3-02 | Implement deterministic decisions, risk flags, priorities, explanations | 3 | P0 | Complete | `src/itc_sentinel/rules.py` + `src/itc_sentinel/decision.py`: `decide()` engine producing Action, Priority, Flag, ReasonCode, exposure_amount, review_required, eligibility_status per match result. |
| P3-03 | Add rule and decision tests | 3 | P0 | Complete | `tests/test_rules.py` (10 tests) + `tests/test_decision.py` (22 tests), all passing. |

## Phase 4 tasks (completed)

| ID | Task | Phase | Priority | Status | Evidence |
|---|---|---:|---|---|---|
| P4-01 | Implement review audit, safe exports, vendor draft templates | 4 | P1 | Complete | `src/itc_sentinel/audit.py` (AuditLog, AuditEvent, ReviewRecord, append-only JSONL), `src/itc_sentinel/report.py` (Excel export with formula-injection protection), `src/itc_sentinel/messages.py` (deterministic vendor drafts). |
| P4-02 | Add optional LLM wording enhancement and validation/fallback | 4 | P2 | Complete | `src/itc_sentinel/llm.py` (opt-in LLM boundary, template fallback, no provider by default). |

## Pending tasks

| ID | Task | Phase | Priority | Status |
|---|---|---:|---|---|
| P3-01 | Validate tax-rule assumptions with authoritative sources/CA review | 3 | P0 | Pending |
| P5-01 | Build Streamlit dashboard and exception review workflow | 5 | P1 | Complete |
| P5-02 | Add export/audit and vendor-message views | 5 | P1 | Complete |
| P5-03 | Launch Streamlit locally and perform end-to-end smoke test | 5 | P0 | Complete |
| P6-01 | Run complete tests, lint, benchmark, and demo checklist | 6 | P0 | Pending |

## Completed tasks

- [x] Initial requirements and MVP scope drafted.
- [x] Initial architecture and stack documented.
- [x] Development rules and AI boundaries documented.
- [x] Sequential phase plan and acceptance checklists drafted.
- [x] Initial task tracker and working-memory baseline drafted.
- [x] P0-01: Six root Markdown files placed at project root and verified identical to originals.
- [x] P0-02: Repository inspected; existing user work preserved (none present).
- [x] P0-03: Configuration and skeleton files created.
- [x] P0-04: Environment verified — venv, dependency install, imports, ruff, pytest.
- [x] P1-01: Purchase-register (CSV/XLSX) and GSTR-2B (JSON) loaders implemented with validation.
- [x] P1-02: Normalization (GSTIN, invoice, date, amount) implemented; invalid rows preserved.
- [x] P1-03: Ingestion/normalization tests implemented (42 tests, all passing).
- [x] P2-01: Seeded synthetic datasets with ground truth generated.
- [x] P2-02: Deterministic matching engine implemented with all exception statuses.
- [x] P2-03: Matching accuracy measured and edge-case tests added (27 matcher tests, all passing).
- [x] P3-02: Deterministic decision engine implemented (rules.py + decision.py).
- [x] P3-03: Rule and decision tests implemented (34 tests across test_rules.py + test_decision.py, all passing).
- [x] P4-01: Review audit, safe exports, and vendor draft templates implemented (audit.py, report.py, messages.py).
- [x] P4-02: Optional LLM wording enhancement with validation/fallback implemented (llm.py).

## Blocked tasks

- **B-01:** RESOLVED. Repository is mounted at `C:\Users\rinku\ML Project\GST_ITC`; six documentation files placed at project root and verified consistent. Original `itc_sentinel_project_docs/` and `.zip` retained.
- **B-02:** GST-specific rules remain unverified until checked against current official guidance and reviewed by a qualified CA. Not a blocker for Phase 0–4 implementation — all unverified rules are explicitly provisional (ca_verification_required=True in rules.py rule sources) and eligibility_status is UNCERTAIN for all match statuses.

## Phase 4 verification evidence (recorded 2026-10-17)

- Python 3.13.7, pip 26.2.1 (in `.venv`).
- `pip install -r requirements.txt` exit 0; `pip install -e .` exit 0.
- `ruff check .` exit 0, "All checks passed!".
- `pytest` exit 0, collected 152 items, 152 passed, 0 failed (test_audit.py: 11, test_decision.py: 22, test_ingest.py: 16, test_llm.py: 17, test_matcher.py: 27, test_messages.py: 10, test_normalize.py: 26, test_report.py: 10, test_rules.py: 13).
- No secrets or real taxpayer data introduced. `.env` is git-ignored; `.env.example` has placeholders only.
- No commits made; git working tree untracked on `master`.

## Phase 4 module responsibilities

- `src/itc_sentinel/audit.py`: `AuditEvent`, `AuditEventType`, `AuditLog` (append-only JSONL), `ReviewRecord`, `ReviewDecision`. Append-only audit trail with stable identifiers, ISO 8601 timestamps, no secrets logged. Honest about not being tamper-proof.
- `src/itc_sentinel/messages.py`: `VendorDraft`, `DraftCategory`, `draft_vendor_message()`. Deterministic templates for amount_mismatch, tax_head_mismatch, missing_in_2b, duplicate, invalid_data, low_confidence_match. Drafts only — never sent. Neutral wording, no legal claims.
- `src/itc_sentinel/llm.py`: `enhance_wording()`, `is_llm_enabled()`. Opt-in LLM boundary (env var `ITC_SENTINEL_LLM_ENABLED=1`). Template fallback when disabled or provider unavailable. LLM cannot change numeric values or decisions.
- `src/itc_sentinel/report.py`: `export_workbook()`, `safe_cell_value()`. Excel export with Summary, Reconciliation, Decisions, Vendor Drafts, Review, and Audit sheets. Formula-injection protection (apostrophe-escaped formula-leading chars). Monetary precision via MONEY_PLACES. Provisional exposure labeling.

## Phase 5 module responsibilities

- `src/itc_sentinel/app.py`: Streamlit MVP entry point. Collects file uploads, invokes pipeline modules (`ingest`, `normalize`, `matcher`, `decision`, `messages`, `report`, `audit`) in sequence, stores `ReconciliationResult` and `DecisionResult` in session state, provides four tabbed views (Summary, Exceptions, Vendor Messages, Export & Audit). Handles loading indicators, error states, and disclaimer display. Does not reimplement matching or tax calculations.
- `src/itc_sentinel/audit.py`: Same as Phase 4 — append-only audit logging, review record persistence, audit event tracking. Updated to support Streamlit rerun safety (run_id-based audit log paths, duplicate prevention on rerun).
- `src/itc_sentinel/messages.py`: Same as Phase 4 — deterministic vendor message drafts for 6 discrepancy categories. UI tab displays drafts with template text; user can edit before use; LLM enhancement disabled by default.
- `src/itc_sentinel/report.py`: Same as Phase 4 — Excel workbook export with formula-injection protection. Updated to accept `review_records` and `audit_events` for inclusion in the Export & Audit tab.
- `src/itc_sentinel/llm.py`: Same as Phase 4 — opt-in LLM boundary with template fallback. UI preserves disabled-by-default behavior.

## Phase 4 acceptance criteria

| # | Criterion (`phases.md:94-99`) | Status | Evidence |
|---|---|---|---|
| 1 | Review actions are recorded with run and invoice identifiers | **Pass** | `ReviewRecord` has `review_id`, `run_id`, `invoice_key`; `AuditEvent` has `run_id`, `invoice_key` |
| 2 | Drafts can be used without an LLM key | **Pass** | `draft_vendor_message()` uses templates by default; `enhance_wording(enabled=False)` returns template unchanged |
| 3 | LLM failures safely fall back to templates | **Pass** | `enhance_wording()` catches provider exceptions and returns original text |
| 4 | Exports preserve data and protect text cells from formula injection | **Pass** | `safe_cell_value()` escapes `=`, `+`, `-`, `@`, tab prefixes; tests verify |
| 5 | Audit is described honestly as local demo logging, not tamper-proof storage | **Pass** | Module docstring and code comments state this explicitly |

## Phase 5 acceptance criteria

| # | Criterion (`phases.md:114-119`) | Status | Evidence |
|---|---|---|---|
| 1 | A new user can complete the full workflow without developer intervention | **Pass** | End-to-end: file upload → reconciliation → exception review → vendor draft → export, all through UI |
| 2 | Pipeline runs only when explicitly requested | **Pass** | Reconciliation triggered by "Run Reconciliation" button; not on every widget change |
| 3 | Review status is reflected in the UI and audit history | **Pass** | Review decisions recorded via UI; displayed in Export tab audit trail |
| 4 | UI labels uncertainty and does not rely on color alone | **Pass** | Summary tab uses text labels + color as supplementary; disclaimer aboutUNCERTAIN eligibility |
| 5 | End-to-end smoke test passes | **Pass** | Synthetic data run: 10 matches, export with 3 sheets, vendor drafts generated, audit events recorded |
| 6 | Clear distinction between observed data, provisional estimates, and human-reviewed decisions | **Pass** | Summary tab explicitly labels provisional exposure, UNCERTAIN eligibility, and review-required items |

## Supported input contracts

| # | Criterion (`phases.md:94-99`) | Status | Evidence |
|---|---|---|---|
| 1 | Review actions are recorded with run and invoice identifiers | **Pass** | `ReviewRecord` has `review_id`, `run_id`, `invoice_key`; `AuditEvent` has `run_id`, `invoice_key` |
| 2 | Drafts can be used without an LLM key | **Pass** | `draft_vendor_message()` uses templates by default; `enhance_wording(enabled=False)` returns template unchanged |
| 3 | LLM failures safely fall back to templates | **Pass** | `enhance_wording()` catches provider exceptions and returns original text |
| 4 | Exports preserve data and protect text cells from formula injection | **Pass** | `safe_cell_value()` escapes `=`, `+`, `-`, `@`, tab prefixes; tests verify |
| 5 | Audit is described honestly as local demo logging, not tamper-proof storage | **Pass** | Module docstring and code comments state this explicitly |

## Phase 5 acceptance criteria

| # | Criterion (`phases.md:114-119`) | Status | Evidence |
|---|---|---|---|
| 1 | A new user can complete the full workflow without developer intervention | **Pass** | End-to-end: file upload → reconciliation → exception review → vendor draft → export, all through UI |
| 2 | Pipeline runs only when explicitly requested | **Pass** | Reconciliation triggered by "Run Reconciliation" button; not on every widget change |
| 3 | Review status is reflected in the UI and audit history | **Pass** | Review decisions recorded via UI; displayed in Export tab audit trail |
| 4 | UI labels uncertainty and does not rely on color alone | **Pass** | Summary tab uses text labels + color as supplementary; disclaimer aboutUNCERTAIN eligibility |
| 5 | End-to-end smoke test passes | **Pass** | Synthetic data run: 10 matches, export with 3 sheets, vendor drafts generated, audit events recorded |
| 6 | Clear distinction between observed data, provisional estimates, and human-reviewed decisions | **Pass** | Summary tab explicitly labels provisional exposure, UNCERTAIN eligibility, and review-required items |

## Supported input contracts

**Purchase register (CSV/XLSX):** columns `gstin`, `invoice_number`, `invoice_date`, `taxable_value`, `cgst`, `sgst`, `igst`, `cess`, `vendor_name`. Required: `gstin`, `invoice_number`, `invoice_date`, `taxable_value`.

**GSTR-2B JSON (declared contract — assumption pending confirmation):**
```json
{ "gstin": "...", "period": "MMYYYY", "invoices": [ { "supplier_gstin", "invoice_number", "invoice_date", "taxable_value", "cgst", "sgst", "igst", "cess", "invoice_type" }, ... ] }
```
Only `GSTR2B_INVOICE_FIELDS` are read; extra fields ignored. Contract is documented in `ingest.py` docstring and is NOT claimed to cover every GSTR-2B export variant.

## Progress policy

- Update this tracker after each meaningful code/documentation change.
- Record test commands and outcomes before closing tasks.
- Keep one current task and one active phase.
- Overall progress is based on completed acceptance criteria, not file count or lines of code.
