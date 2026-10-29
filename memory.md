# ITC Sentinel — Project Working Memory

**Initialized:** 2026-10-16
**Last updated:** 2026-10-29
**Current phase:** Phase 6 — Verification and demo readiness (complete, re-verified
after defect remediation)
**Implementation status:** Phases 0–6 complete for the synthetic-data MVP. One
external task remains open (P3-01: CA validation of tax rules). Deployment not
performed.

## Project goal

Build a local-first MVP for GST Input Tax Credit reconciliation: compare a
purchase register with GSTR-2B, identify and prioritize exceptions, explain
suggested actions, support human review, draft vendor follow-ups, and export
auditable results.

## Decisions made

1. **Streamlit + deterministic Python pipeline.** Minimizes frontend/backend
   integration and supports a fast demo.
2. **No database initially.** Per-run CSV/JSON/JSONL outputs under
   `data/runs/<run_id>/`; persistence revisited only when multi-user needs are
   validated.
3. **Deterministic financial logic.** Matching, amounts, priorities, and actions
   are computed in code, never delegated to an LLM.
4. **LLM is optional.** Wording only; templates work offline; disabled by default.
5. **Synthetic data first.** Seeded fixtures plus independent ground truth.
6. **Human approval required.** No sending, filing, payment holds, or external
   write actions.
7. **Single-user, B2B, bounded-scope demo.** Multi-tenancy, OCR, and production
   integrations are deferred.
8. **GST rules require CA validation.** Unverified assumptions are labelled and
   never presented as legal certainty.
9. **Stable review identity is `record_id`** (`books:<row>` / `gstr2b:<row>`),
   not the GSTIN+invoice label, so duplicate invoices cannot collide.
10. **Uploads are materialised safely.** Bytes go to a run-scoped temp file with
    size/type/traversal checks, then are deleted after ingestion.
11. **Metrics have one definition.** `metrics.py` is the single source of truth;
    confirmed matches = exact matches only.
12. **Run isolation.** Each reconciliation request rotates `run_id`, audit log,
    and review state to prevent cross-run mixing.

## Current status

- Core modules: `schemas.py`, `ingest.py`, `normalize.py`, `matcher.py`,
  `rules.py`, `decision.py`, `metrics.py`, `audit.py`, `messages.py`, `llm.py`,
  `report.py`, `uploads.py`, `app.py`.
- Streamlit UI: sample/upload selection, explicit Run action, Summary,
  Exceptions, Vendor Messages, and Export & Audit tabs, review worklist driven by
  `DecisionResult.review_required`, run-scoped audit log.
- Synthetic fixtures: `data/sample/purchase_register_synthetic.csv`,
  `gstr2b_synthetic.json`, `ground_truth.json`.
- Verification: `pytest` 215 passed; `ruff check .` clean;
  `python scripts/verify_pipeline.py` 20/20 checks pass.
- Streamlit AppTest suite covers sample run, upload success/failure, failed-run
  recovery, empty dataset, review actions, duplicate identity separation,
  invalid-row policy, export, audit events, and run isolation.
- No real taxpayer data or credentials. `.env` is git-ignored.
- No Git commits made in this session.

## Defects fixed during remediation

- **Upload handling:** Streamlit `UploadedFile` objects were treated as paths.
  Added `uploads.py` with size cap (10 MiB), extension checks, filename
  sanitisation/path-traversal guard, empty-file rejection, and guaranteed cleanup.
- **Unstable review identity:** duplicate GSTIN+invoice rows shared a display
  key. Added `MatchResult.record_id` and `record_identity()`.
- **Review worklist coverage:** worklist now uses `review_required`; all nine
  review-required sample rows are selectable.
- **Decision/eligibility policy:** exact matches now emit
  `Action.PROPOSE_ITC_CLAIM` with `review_required=True` (eligibility remains
  `UNCERTAIN`). Invalid rows cannot be approved. Policy lives in `decision.py`
  via `allowed_review_decisions()` / `validate_review_decision()`.
- **Dashboard metrics:** added `metrics.py`; mismatches/fuzzy/probable are never
  counted as confirmed matches; review counts de-duplicate by `record_id` and use
  the latest state.
- **Pipeline robustness:** enforced `fuzzy_threshold`, corrected discrepancy
  reason text, applied `ROUND_HALF_UP` consistently, closed XLSX handles, wrapped
  invalid XLSX as `IngestionError`, hardened formula-injection escaping for
  leading whitespace, and exported stable status codes.
- **Repository hygiene:** removed 23 accidentally committed pytest temp artifacts
  and added ignore patterns for pytest/pip scratch directories.

## Matching metrics (synthetic ground truth)

- Confirmed matches evaluated: 5 (exact=2, fuzzy=1, amount_mismatch=1,
  tax_head_mismatch=1)
- True positives: 5, false positives: 0, false negatives: 0
- Precision: 1.0, recall: 1.0
- Probable: 1 (not confirmed), unmatched books: 1, unmatched GSTR-2B: 1,
  duplicate: 1, invalid: 1.
- Dashboard metrics: 10 reconciliation rows, 16 source rows, confirmed=2,
  review-required=9, provisional exposure=₹8,890.00.

## Known issues / open questions

- **P3-01 — CA validation outstanding.** External dependency. All rules remain
  provisional and eligibility stays `UNCERTAIN`. Blocks real-data/production use,
  not a synthetic-data demo.
- **GSTR-2B JSON schema unconfirmed.** Declared contract in `ingest.py` is an
  assumption pending confirmation against a real, anonymized export.
- **Decision priority thresholds are assumptions** (`high=50000`,
  `medium=10000`), configurable pending validation.
- **Probable matching is loose** (similarity-based, no shared invoice core
  requirement). Such rows are always uncertain and review-required.
- **Duplicate detection is purchase-register only.** GSTR-2B duplicates are
  matched or unmatched normally.
- **Audit trail is demo-grade.** Append-only local JSONL is not tamper-proof or
  legally compliant.
- **LLM is opt-in and disabled by default.** No provider key is read by the
  module.
- **Session state is ephemeral.** Closing the browser resets the current run's
  review state; prior `data/runs/` directories persist unless deleted.
- **Clean-venv install verified (2026-10-29).** Fresh isolated venv installed
  dependencies and reproduced the 215-test suite, Ruff, the 20/20 verifier, and
  the Streamlit health check.
- **No Git commit exists for this remediation.** Requires owner approval.

## Instructions for future sessions

- Read this file and `tasks.md` before making changes.
- Inspect the actual repository before claiming a feature is implemented.
- Work on one phase at a time unless the project owner explicitly changes this
  rule.
- After meaningful changes, update `tasks.md`, `memory.md`, and any affected
  design document.
- Record decisions and their rationale; do not silently drift from the
  architecture.
- Never mark a phase complete without acceptance evidence.
- Do not weaken or delete tests to make a run pass.
- Do not commit unless explicitly authorized.
