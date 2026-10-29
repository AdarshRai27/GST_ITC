# Phase Completion Matrix

**Date:** 2026-10-29
**Basis:** Actual repository contents, `pytest`, `ruff`, `scripts/verify_pipeline.py`,
and `tests/test_app.py` evidence. A phase is marked Complete only where a
checklist item has concrete evidence.

---

## Summary

| Phase | Scope | Status | Notes |
|---|---|---|---|
| 0 | Setup and scope freeze | Complete | Docs, config, environment present |
| 1 | Ingestion and normalization | Complete | CSV/XLSX/JSON, invalid-row preservation |
| 2 | Deterministic reconciliation | Complete | Ground-truth precision/recall = 1.0 |
| 3 | Rules and decision support | Complete with external condition | P3-01 CA validation outstanding |
| 4 | Review, messages, export, audit | Complete | Formula-injection protection verified |
| 5 | Streamlit MVP | Complete | AppTest + live server health check |
| 6 | Verification and demo readiness | Complete with documented conditions | CA review and real-schema confirmation open |

---

## Phase 0 — Setup and scope freeze

| Criterion | Status | Evidence |
|---|---|---|
| Six root Markdown files exist and agree | Complete | Files present at root; stale claims corrected 2026-10-29 |
| Environment setup works | Complete | Fresh isolated venv: dependencies installed (exit 0), 215 tests, Ruff, verifier, and Streamlit health check all pass |
| No secrets or real taxpayer data tracked | Complete | Secret-pattern scan clean; `.env` ignored; pytest artifacts removed |
| Scope and tax assumptions documented | Complete | `README.md`, `requirements.md`, `rules.md` |

---

## Phase 1 — Input ingestion and normalization

| Criterion | Status | Evidence |
|---|---|---|
| Valid CSV/XLSX/JSON fixtures load | Complete | `test_ingest.py` (16), `test_uploads.py` (20) |
| Missing columns / malformed files produce useful errors | Complete | Column-validation and `Malformed JSON` tests; invalid XLSX wrapped as `IngestionError` |
| Invalid rows are not silently discarded | Complete | `normalize_records()` preserves invalid rows; matcher emits `INVALID` |
| Normalization and monetary rounding tests pass | Complete | `test_normalize.py` (26); `ROUND_HALF_UP` policy |

Additional hardening: upload size cap, extension allow-list, filename
sanitisation, path-traversal guard, empty-file rejection, cleanup on success and
failure.

---

## Phase 2 — Deterministic reconciliation

| Criterion | Status | Evidence |
|---|---|---|
| Every matching stage has focused tests | Complete | `test_matcher.py` (29) |
| No invoice used in more than one pair | Complete | One-to-one tests |
| Matching constrained to same normalized GSTIN | Complete | Same-GSTIN tests |
| Precision/recall and error cases measured | Complete | Precision = recall = 1.0 on 5 confirmed rows; probable evaluated separately |

Additional hardening: `fuzzy_threshold` is enforced; discrepancy reasons name the
actual differing fields; stable `record_id` prevents duplicate-identity collapse.

---

## Phase 3 — Rule engine and decision support

| Criterion | Status | Evidence |
|---|---|---|
| Every decision rule has a test and stable reason code | Complete | `test_rules.py` (17), `test_decision.py` (17), `test_review_policy.py` (8) |
| Tax calculations use documented money/rounding policy | Complete | `ROUND_HALF_UP`, `MONEY_PLACES` |
| Unverified legal assumptions visibly labelled | Complete | `ca_verification_required=True`; UI disclaimers |
| No LLM output can change amounts or decisions | Complete | `llm.py` wording-only boundary |
| P3-01: CA validation of tax-sensitive rules | **Pending (external)** | No CA available; eligibility remains `UNCERTAIN` |

**Condition:** Outputs are suitable for a synthetic-data demonstration and
decision-support review only. Real filings require CA validation.

---

## Phase 4 — Review workflow, messages, exports, audit

| Criterion | Status | Evidence |
|---|---|---|
| Review actions recorded with run and invoice identifiers | Complete | `ReviewRecord` now also carries `record_id`, `previous_state`, `new_state` |
| Drafts usable without an LLM key | Complete | Template fallback; `test_messages.py` (10) |
| LLM failures safely fall back | Complete | `test_llm.py` (15) |
| Exports preserve data and block formula injection | Complete | `test_report.py` (17); leading-whitespace formula case added |
| Audit described honestly as local demo logging | Complete | `audit.py` docstring and UI caption |

---

## Phase 5 — Streamlit MVP

| Criterion | Status | Evidence |
|---|---|---|
| New user completes full workflow | Complete | `tests/test_app.py` (21 AppTest cases) |
| Pipeline runs only on explicit request | Complete | Run button; widget changes do not trigger pipeline |
| Review status reflected in UI and audit | Complete | Review table + `REVIEW_ACTION` audit events |
| UI labels uncertainty, not colour alone | Complete | Text labels and definitions in Summary |
| End-to-end smoke test passes | Complete | AppTest + `scripts/verify_pipeline.py`; live health `200 ok` |

Additional hardening: upload handling no longer treats `UploadedFile` as a path;
review worklist is driven by `review_required`; all nine review-required sample
rows are selectable; run ID/audit/review state rotate per run.

---

## Phase 6 — Verification and demo readiness

| Criterion | Status | Evidence |
|---|---|---|
| Full test suite and Ruff pass | Complete | 215 passed; `ruff check .` clean; exit 0 (fresh venv and workspace interpreter) |
| Fresh local setup instructions tested | Complete | Fresh isolated venv: `pip install -r requirements.txt` exit 0; suite/lint/verifier pass |
| No real taxpayer data or secrets | Complete | Scan clean; 23 pytest temp artifacts removed and ignored |
| GST-rule limitations / CA review disclosed | Complete | README, phase notes, deployment report |
| Demo repeatable from a clean start | Complete | `scripts/verify_pipeline.py` 20/20 |
| Live Streamlit startup | Complete | `/_stcore/health` returned `200 ok`; root returned `200` (fresh venv) |

---

## Unsupported / deferred scope (not failures)

- Multi-user authentication, RBAC, tenant isolation, persistent database.
- Additional GST documents, amendments, credit notes, OCR.
- Production integrations, API service, background jobs, monitoring, CI/CD.
- Tamper-proof audit storage.
- Real-taxpayer-data operation.

These remain post-MVP backlog items.
