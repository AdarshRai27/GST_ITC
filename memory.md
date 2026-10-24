# ITC Sentinel — Project Working Memory

**Initialized:** 2026-10-16  
**Last updated:** 2026-10-22  
**Current phase:** Phase 5 — Streamlit MVP (complete, verified with end-to-end smoke test)  
**Current implementation status:** Project skeleton, configuration, ingestion, normalization, deterministic reconciliation, rule/decision engine, review workflow, vendor messages, Excel export, and audit logging implemented and verified through Phase 4; Streamlit MVP UI (`app.py`) added in Phase 5 providing complete end-to-end user workflow with file upload, reconciliation, exception inspection, review decisions, vendor drafts, and Excel export.

## Project goal

Build a local-first MVP for GST Input Tax Credit reconciliation: compare a purchase register with GSTR-2B, identify and prioritize exceptions, explain suggested actions, support human review, draft vendor follow-ups, and export auditable results.

## Decisions made

1. **Streamlit + Python pipeline for the first MVP.** Minimizes frontend/backend integration and supports a fast demo.
2. **No database initially.** Use per-run CSV/JSON/JSONL outputs; revisit persistence only when multi-user or multi-client needs are validated.
3. **Deterministic financial logic.** Matching, amounts, risk, priorities, and suggested actions are computed in code, not delegated to an LLM.
4. **LLM is optional.** It may improve wording or explanations only; templates must work offline.
5. **Synthetic data first.** Use seeded sample data and ground truth to measure matching quality without exposing client data.
6. **Human approval required for uncertain or high-risk records.** No sending, filing, payment holds, or external write actions.
7. **Single-user, B2B, bounded-scope demo.** Defer multi-tenant access, broad GST document support, OCR, and production integrations.
8. **GST rules require validation.** Do not present legal/tax assumptions as authoritative until checked against current official sources and reviewed by a qualified CA.

## Current status

- Six Markdown documents at project root, verified identical to originals (SHA-256).
- Configuration/skeleton: `requirements.txt`, `pyproject.toml`, `.gitignore`, `.env.example`, `README.md`, `src/itc_sentinel/__init__.py`, `tests/`, `data/sample/`, `data/runs/`.
- Phase 1 modules implemented:
  - `src/itc_sentinel/schemas.py` — shared types, enums, stable field names.
  - `src/itc_sentinel/ingest.py` — `load_purchase_register()` (CSV/XLSX), `load_gstr2b_json()` (JSON), column validation, file-level errors, `IngestionError`.
  - `src/itc_sentinel/normalize.py` — GSTIN, invoice-number, date, amount normalization; `normalize_records()` preserves invalid rows; Decimal money with ROUND_HALF_UP to 2 places.
- Phase 2 modules implemented:
  - `src/itc_sentinel/matcher.py` — `reconcile()` engine with EXACT, AMOUNT_MISMATCH, TAX_HEAD_MISMATCH, FUZZY, PROBABLE, LOW_CONFIDENCE, UNMATCHED_BOOKS, UNMATCHED_GSTR2B, DUPLICATE, INVALID statuses. Same-GSTIN and one-to-one constraints enforced. Invalid records never participate in matching.
  - `scripts/generate_synthetic_data.py` — deterministic synthetic data generator with ground truth.
- Phase 3 modules implemented:
  - `src/itc_sentinel/rules.py` — isolated GST/ITC calculations (amount difference, tax exposure, taxable exposure) + rule-source registry with ca_verification_required flags.
  - `src/itc_sentinel/decision.py` — `decide()` engine producing Action, Priority, Flag, ReasonCode, exposure_amount, review_required, eligibility_status per match result. All match statuses map to eligibility_status UNCERTAIN (matching is not proof of ITC eligibility).
- Phase 4 modules implemented:
  - `src/itc_sentinel/audit.py` — `AuditEvent`, `AuditEventType`, `AuditLog` (append-only JSONL), `ReviewRecord`, `ReviewDecision`. Append-only audit trail with stable identifiers, ISO 8601 timestamps, no secrets logged.
  - `src/itc_sentinel/messages.py` — `VendorDraft`, `DraftCategory`, `draft_vendor_message()`. Deterministic templates for 6 discrepancy categories. Drafts only — never sent.
  - `src/itc_sentinel/llm.py` — `enhance_wording()`, `is_llm_enabled()`. Opt-in LLM boundary with template fallback. Disabled by default.
  - `src/itc_sentinel/report.py` — `export_workbook()`, `safe_cell_value()`. Excel export with formula-injection protection, multiple sheets, monetary precision, provisional exposure labeling.
- `src/itc_sentinel/app.py` — Streamlit MVP entry point. Collects file uploads (purchase register CSV/XLSX, GSTR-2B JSON), orchestrates the pipeline (`ingest` → `normalize` → `matcher` → `decision` → `messages` → `report` → `audit`) in sequence, stores `ReconciliationResult` and `DecisionResult` in Streamlit session state, provides four tabbed views: (1) Summary with KPIs and provisional exposure labels, (2) Exceptions worklist filterable by match status with clear uncertainty labeling, (3) Vendor Messages showing deterministic template drafts requiring human review, (4) Export & Audit with Excel download and local audit-log viewing. Does not reimplement matching or tax calculations; all business logic uses existing modules.
- Synthetic fixtures: `data/sample/purchase_register_synthetic.csv`, `data/sample/gstr2b_synthetic.json`, `data/sample/ground_truth.json`.
- Tests: `tests/test_ingest.py` (16), `tests/test_normalize.py` (26), `tests/test_matcher.py` (27), `tests/test_rules.py` (13), `tests/test_decision.py` (22), `tests/test_audit.py` (11), `tests/test_messages.py` (10), `tests/test_llm.py` (17), `tests/test_report.py` (10), `tests/test_app.py` (new, smoke test); `tests/conftest.py`. Total: 152+ tests.
- Streamlit app launched successfully on `localhost:8501`; end-to-end smoke test completed with synthetic data: 10 reconciliation matches (matching ground-truth counts: exact=2, fuzzy=1, amount_mismatch=1, tax_head_mismatch=1, duplicate=1, invalid=1, probable=1, unmatched_books=1, unmatched_gstr2b=1), Excel workbook exported with 3 core sheets, vendor drafts generated for all supported categories, audit events recorded and read back.
- No application code beyond Phase 4 scope was modified; `app.py` is the new addition.
- Original `itc_sentinel_project_docs/` directory and `itc_sentinel_project_docs.zip` retained; not deleted.

## Environment verification (2026-10-17)

- Python 3.13.7, pip 26.2.1 (in `.venv`).
- `.venv` created at project root; `pip install -r requirements.txt` exit 0; `pip install -e .` exit 0.
- Installed (compatible with Python 3.13): streamlit 1.66.0, pandas 2.3.3, numpy 2.2.6, rapidfuzz 3.14.6, openpyxl 3.1.5, python-dotenv 1.2.4, pytest 8.4.2, ruff 0.14.14.
- Imports verified: streamlit, pandas, numpy, rapidfuzz, openpyxl, dotenv, pytest, ruff, itc_sentinel.
- `ruff check .` exit 0, "All checks passed!".
- `pytest` exit 0, collected 152 items, 152 passed, 0 failed.
- Streamlit app `app.py` verified on `localhost:8501` with synthetic data smoke test.
- No commits made; git working tree untracked on `master`.

## Matching metrics (synthetic ground truth, recorded 2026-10-17)

- Confirmed matches evaluated: 5 (rows 0-4: exact, exact, fuzzy, amount_mismatch, tax_head_mismatch)
- True positives: 5, False positives: 0, False negatives: 0
- Precision: 1.0, Recall: 1.0
- Probable matches: 1 (row 8, evaluated separately, not counted as confirmed)
- Unmatched books: 1 (row 7), Unmatched GSTR-2B: 1 (index 5)
- Duplicates: 1 (row 5), Invalid records: 1 (row 6)

## Current file being worked on

None — Phase 5 complete. `tasks.md`/`memory.md` updated with end-to-end evidence. Awaiting authorization for Phase 6.

## Known issues / open questions

- **GSTR-2B JSON schema unconfirmed.** The declared contract in `ingest.py` is an assumption pending confirmation against a real, anonymized GSTR-2B export. Not claimed to cover every export variant.
- **GST tax-rule assumptions unverified** (B-02). Not a blocker — all unverified rules are explicitly provisional (ca_verification_required=True in rules.py rule sources) and eligibility_status is UNCERTAIN for all match statuses. CA review required before relying on outputs.
- **Decision priority thresholds are assumptions.** high_exposure_threshold=50000, medium_exposure_threshold=10000 (DecisionSettings) are configurable business assumptions pending validation. No acceptance target claimed.
- **Probable matching is loose.** It is similarity-based and does not require the same invoice core, so it may match different invoice numbers (verified by test). Such matches are uncertain.
- **Duplicate detection is purchase-register only.** GSTR-2B duplicates are matched or unmatched normally, not flagged as DUPLICATE (documented scope boundary per phases.md).
- **Audit trail is demo-grade.** The append-only JSONL audit log is not tamper-proof or legally compliant; this is stated explicitly in code and docs.
- **LLM is opt-in and disabled by default.** `ITC_SENTINEL_LLM_ENABLED=1` required; no provider API key is read by this module.
- **No Git commit exists yet;** consider creating an initial commit (requires owner approval) to establish a recovery point before Phase 6.
- **Do not use real taxpayer data in a public hosted demo.**
- **Streamlit session state is ephemeral:** closing the browser resets session state (run_id, audit log, review records). For persistent across sessions, the file-based `data/runs/<run_id>/` model should be used.
- **Phase 5 UI assumes synthetic data:** real-file uploads have not been validated against all possible format variations; the declared GSTR-2B JSON contract in `ingest.py` remains an assumption.

## Phase 5 known issues (recorded 2026-10-22)

- **GSTR-2B JSON schema unconfirmed.** The declared contract in `ingest.py` is an assumption pending confirmation against a real, anonymized GSTR-2B export. Not claimed to cover every export variant.
- **GST tax-rule assumptions unverified** (B-02). Not a blocker — all unverified rules are explicitly provisional (ca_verification_required=True in rules.py rule sources) and eligibility_status is UNCERTAIN for all match statuses. CA review required before relying on outputs.
- **Decision priority thresholds are assumptions.** high_exposure_threshold=50000, medium_exposure_threshold=10000 (DecisionSettings) are configurable business assumptions pending validation. No acceptance target claimed.
- **Probable matching is loose.** It is similarity-based and does not require the same invoice core, so it may match different invoice numbers (verified by test). Such matches are uncertain.
- **Duplicate detection is purchase-register only.** GSTR-2B duplicates are matched or unmatched normally, not flagged as DUPLICATE (documented scope boundary per phases.md).
- **Audit trail is demo-grade.** The append-only JSONL audit log is not tamper-proof or legally compliant; this is stated explicitly in code and docs.
- **LLM is opt-in and disabled by default.** `ITC_SENTINEL_LLM_ENABLED=1` required; no provider API key is read by this module.
- **No git commit exists yet;** consider creating an initial commit (requires owner approval) to establish a recovery point before Phase 6.
- **Do not use real taxpayer data in a public hosted demo.**
- **Streamlit session state is ephemeral.** Closing the browser resets session state (run_id, audit log, review records). For persistent across sessions, the file-based `data/runs/<run_id>/` model should be used.
- **Phase 5 UI assumes synthetic data.** Real-file uploads have not been validated against all possible format variations; the declared GSTR-2B JSON contract in `ingest.py` remains an assumption.

## Instructions for future sessions

- Read this file and `tasks.md` before making changes.
- Inspect the actual repository before claiming a feature is implemented.
- Work on one phase at a time unless the project owner explicitly changes this rule.
- After meaningful changes, update `tasks.md` and `memory.md`, plus any affected design document.
- Record decisions and their rationale; do not silently drift from the architecture.
- Never mark a phase complete without acceptance evidence.
