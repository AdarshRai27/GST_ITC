# Phase 6 — Demo Readiness Report

**Report date:** 2026-10-29 (supersedes the 2026-10-22 draft)
**Phase:** 6 — Verification and demo readiness
**Overall verdict:** **READY WITH DOCUMENTED CONDITIONS** for an authorized
synthetic-data demonstration. Production readiness not claimed.
**Detailed verdict:** see `audit/deployment_readiness.md`.

---

## 1. Executive summary

The Streamlit MVP and deterministic pipeline are complete and re-verified after
defect remediation:

- **215 tests pass** (exit 0), including 21 Streamlit `AppTest` workflow cases.
- `ruff check .` is clean (exit 0).
- `python scripts/verify_pipeline.py` passes **20/20** ground-truth checks.
- A real Streamlit server returns `200 ok` on `/_stcore/health` (root `200`).
- Matching precision = recall = 1.0 against the synthetic ground truth.
- Confirmed matches = exact matches only (2 on the sample); mismatches, fuzzy,
  probable, duplicate, invalid, and unmatched rows are separate KPIs.
- Exact matches are **candidates** (`PROPOSE_ITC_CLAIM`) with mandatory review;
  eligibility remains `UNCERTAIN`.
- Invalid rows cannot be approved; policy is enforced in `decision.py`.
- Uploads are size/type checked, path-traversal safe, and deleted after ingestion.
- No real taxpayer data or secrets are present; `.env` is git-ignored.
- LLM enhancement is opt-in and disabled by default.
- Audit logging and Excel formula-injection protection are verified.

**Not production-ready.** See `audit/deployment_readiness.md` for conditions
(CA validation, GSTR-2B schema assumption, demo-grade audit, single-user
session state).

---

## 2. Phase 6 acceptance criteria (`phases.md`)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Full test suite and Ruff pass | **PASS** | 215 passed, exit 0; `ruff` clean, exit 0 |
| 2 | Fresh local setup instructions tested | **PASS** | Fresh isolated venv: install exit 0; 215 tests, Ruff, verifier, health check all pass |
| 3 | No real taxpayer data or secrets | **PASS** | Secret-pattern scan clean; committed pytest artifacts removed; `.env` ignored |
| 4 | GST-rule limitations and CA-review requirement disclosed | **PASS** | `README.md`, `rules.md`, UI disclaimers, deployment report |
| 5 | Demo repeatable from a clean start | **PASS** | `scripts/verify_pipeline.py` 20/20; AppTest workflow |

---

## 3. Commands and results

| Command | Result | Exit |
|---|---|---:|
| `python -m pytest -q` | 215 passed in ~23 s | 0 |
| `python -m ruff check .` | All checks passed! | 0 |
| `python scripts/verify_pipeline.py` | 20/20 checks passed | 0 |
| `streamlit run src/itc_sentinel/app.py` (headless, port 8518) | `/_stcore/health` → `ok` (200); `/` → 200 | 0 (stopped after check) |

Test breakdown and full verifier output: `audit/test_results.md`.

---

## 4. Verification evidence

### 4.1 Ground truth

| Check | Result |
|---|---|
| Book-row statuses vs `ground_truth.json` | PASS (exact=2, fuzzy=1, amount_mismatch=1, tax_head_mismatch=1, duplicate=1, invalid=1, probable=1, unmatched_books=1, unmatched_gstr2b=1) |
| Confirmed precision / recall | PASS (1.0 / 1.0) |
| Metrics | PASS (10 reconciliation rows, 16 source rows, confirmed=2, review-required=9, exposure ₹8,890.00) |

### 4.2 Workflow (AppTest)

- Sample run produces the expected dashboard and audit events.
- Uploaded CSV + JSON run succeeds; upload directory is empty afterwards.
- Invalid CSV/JSON show actionable errors; a failed run can be followed by a
  successful one.
- Empty dataset produces zero metrics without exceptions.
- Review approval records `books:0` with `previous_state="none"` and an audit
  event; duplicate `books:5` keeps a distinct identity.
- Invalid `books:6` offers only Reject/Pending.
- Export produces a non-empty XLSX and an `export_created` event.
- Re-running rotates `run_id`, clears reviews, and recomputes metrics.

### 4.3 Safety

| Check | Result |
|---|---|
| Formula injection escaped (including leading whitespace) | PASS |
| Upload type/size/traversal/empty checks | PASS |
| Temp uploads deleted on success and failure | PASS |
| Invalid rows cannot be approved | PASS |
| Exact matches are candidates, not claims | PASS |
| No automated filing/payment/message actions | PASS |
| Audit described as demo-grade | PASS |

---

## 5. Remaining conditions

| Condition | Status | Recommendation |
|---|---|---|
| CA validation of tax rules (P3-01) | Open — external | Required before any real-data use |
| GSTR-2B JSON schema | Assumption | Confirm against anonymized real exports |
| Committed pytest artifacts | Removed from working tree; tracked in `HEAD` | `git rm -r --cached pytest-of-rinku` at commit time |
| Production hardening | Out of scope | Auth/RBAC, persistence, tamper-evident audit, CI/CD, monitoring |

---

## 6. Relationship to other audit artifacts

- `audit/core_pipeline_verification.md` — stage-by-stage pipeline evidence.
- `audit/phase_completion_matrix.md` — phase criteria and statuses.
- `audit/test_results.md` — commands, counts, and failure resolutions.
- `audit/implementation_backlog.md` — prioritized open work.
- `audit/deployment_readiness.md` — final verdict and conditions.
- `audit/final_change_summary.md` — files changed and behavior changes.

---

## 7. Confirmation of scope discipline

No new product architecture was introduced. Work was limited to defect fixes,
regression tests, verification, and documentation reconciliation. No Git commits
or deployments were made. No real taxpayer data or credentials were added.

**Next step:** project owner authorizes (a) a commit/recovery point and (b) the
conditions in `audit/deployment_readiness.md` before any external demo.
