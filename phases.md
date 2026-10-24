# ITC Sentinel — Development Phases

**Rule:** Work on one phase at a time. A phase is complete only when its checklist passes and evidence is recorded in `tasks.md` and `memory.md`.

## Phase 0 — Project setup and scope freeze
**Objective:** Establish a reproducible project skeleton and confirm MVP assumptions.

**Features/work**
- Create project structure and six root documentation files.
- Add dependency file, Ruff/pytest configuration, `.gitignore`, `.env.example`, README skeleton.
- Define supported input contracts and synthetic-data strategy.

**Deliverables:** runnable skeleton, docs, setup instructions.

**Dependencies:** none.

**Completion checklist**
- [ ] Six root Markdown files exist and agree with each other.
- [ ] Environment setup works on a clean machine.
- [ ] No secrets or real taxpayer data are tracked.
- [ ] Scope and tax assumptions are explicitly documented.

## Phase 1 — Input ingestion and normalization
**Objective:** Load supported files safely and produce canonical rows.

**Features/work**
- CSV/XLSX purchase register loader.
- GSTR-2B JSON loader for the documented supported structure.
- Column/type/date/amount validation and row-level issues.
- Normalize GSTIN, invoice numbers, dates, and monetary values.

**Deliverables:** `ingest.py`, `normalize.py`, schemas, sample files, tests.

**Dependencies:** Phase 0.

**Completion checklist**
- [ ] Valid CSV/XLSX/JSON fixtures load.
- [ ] Missing columns and malformed files produce useful errors.
- [ ] Invalid rows are not silently discarded.
- [ ] Normalization and monetary rounding tests pass.

## Phase 2 — Deterministic reconciliation
**Objective:** Match purchase-register and GSTR-2B invoices transparently.

**Features/work**
- Detect duplicate purchase-register rows.
- Exact matching, then constrained fuzzy matching, then probable matching.
- Enforce same-GSTIN and one-to-one match constraints.
- Classify unmatched, amount mismatch, tax-head mismatch, and duplicate rows.
- Generate synthetic data plus ground truth.

**Deliverables:** `matcher.py`, synthetic-data generator, accuracy tests.

**Dependencies:** Phase 1.

**Completion checklist**
- [ ] Every matching stage has focused unit tests.
- [ ] No invoice is used in more than one pair.
- [ ] Matching is constrained to the same normalized GSTIN.
- [ ] Precision/recall and error cases are measured and reported.

## Phase 3 — Rule engine and decision support
**Objective:** Calculate risk flags and explainable suggested actions.

**Features/work**
- Isolated, configurable rules for approved scope.
- Suggested action, ITC exposure, priority, and reason per row.
- Explicit human-review conditions.
- CA verification of tax-sensitive rules before presenting them as reliable.

**Deliverables:** `rules.py`, `decision.py`, configuration, decision tests, rule-source notes.

**Dependencies:** Phase 2.

**Completion checklist**
- [ ] Every decision rule has a test and stable reason code.
- [ ] Tax calculations use a documented money/rounding policy.
- [ ] Unverified legal assumptions are visibly labelled.
- [ ] No LLM output can change amounts or decisions.

## Phase 4 — Review workflow, messages, exports, and audit
**Objective:** Let a reviewer act on the worklist and preserve evidence.

**Features/work**
- Human approve/reject with optional reason.
- Template-based vendor drafts; optional LLM wording enhancement with validation.
- Excel export with formula-injection protection.
- Append-only local audit events and per-run metadata.

**Deliverables:** `audit.py`, `messages.py`, `llm.py` (optional), `report.py`, tests.

**Dependencies:** Phase 3.

**Completion checklist**
- [ ] Review actions are recorded with run and invoice identifiers.
- [ ] Drafts can be used without an LLM key.
- [ ] LLM failures safely fall back to templates.
- [ ] Exports preserve data and protect text cells from formula injection.
- [ ] Audit is described honestly as local demo logging, not tamper-proof storage.

## Phase 5 — Streamlit MVP
**Objective:** Provide the complete end-to-end user workflow.

**Features/work**
- Sample data and file upload.
- Summary dashboard, exception filters/detail, review controls.
- Vendor drafts and export/audit views.
- Input guidance, disclaimers, clear loading/error states.

**Deliverables:** `app.py`, UI modules, demo script, README.

**Dependencies:** Phases 1–4.

**Completion checklist**
- [ ] A new user can complete the full workflow without developer intervention.
- [ ] Pipeline runs only when explicitly requested.
- [ ] Review status is reflected in the UI and audit history.
- [ ] UI labels uncertainty and does not rely on color alone.
- [ ] End-to-end smoke test passes.

## Phase 6 — Verification and demo readiness
**Objective:** Validate quality, reproducibility, and safe presentation.

**Features/work**
- Run all tests and linting.
- Verify sample outputs and matching metrics.
- Benchmark on documented synthetic dataset.
- Finalize setup/demo documentation and limitations.

**Deliverables:** test report, demo script, known-limitations section, readiness checklist.

**Dependencies:** Phase 5.

**Completion checklist**
- [ ] Full test suite and Ruff pass.
- [ ] Fresh local setup instructions have been tested.
- [ ] No real taxpayer data or secrets are in the repository.
- [ ] GST-rule limitations and CA-review requirement are disclosed.
- [ ] Demo can be repeated from a clean start.

## Post-MVP backlog (not part of initial phases)
- Persistent database and multi-client support.
- Authentication/RBAC and tenant isolation.
- Additional GST documents, amendments, credit notes, and OCR.
- Approved external integrations.
- API service, background jobs, monitoring, and production hardening.
