# Deployment Readiness

**Date:** 2026-10-29
**Artifact:** ITC Sentinel synthetic-data MVP
**Verdict:** **READY WITH DOCUMENTED CONDITIONS** — for an authorized,
synthetic-data demonstration only.
**Production readiness:** **NOT CLAIMED**
**Deployment performed:** **No**

---

## 1. Verdict rationale

The application is functionally complete and independently verified end to end:
215 tests pass in both the workspace interpreter and a fresh isolated venv, lint
is clean, the ground-truth pipeline verifier passes 20/20, and a real Streamlit
server returns `200 ok` on its health endpoint. The remaining items are external
validation and documented scope/security conditions, not known code defects.

The verdict is therefore **READY WITH DOCUMENTED CONDITIONS**, not unconditional
demo-ready and not production-ready.

---

## 2. Conditions attached to the verdict

| # | Condition | Why it matters | Required before |
|---|---|---|---|
| C1 | **CA validation of GST/ITC rules is outstanding (P3-01).** | Eligibility is `UNCERTAIN` and rules are unverified. | Any real-taxpayer data, filing support, or eligibility claim |
| C2 | **GSTR-2B JSON schema remains an assumption.** | Real export variants may differ. | Accepting arbitrary real GSTR-2B files |
| C3 | **Single-user, ephemeral session state; demo-grade audit log.** | Reviews reset on browser close; audit is append-only by convention, not tamper-proof. | Multi-user or compliance use |
| C4 | **Accidentally committed pytest artifacts still in Git `HEAD`.** | Working-tree copies removed and `.gitignore` updated; deletion needs a commit. | Repository closeout |
| C5 | **No Git commit made for this remediation.** | Changes are uncommitted by instruction. | Handoff / recovery point |

---

## 3. Evidence supporting readiness

| Area | Evidence | Result |
|---|---|---|
| Fresh isolated install | New venv + `pip install -r requirements.txt` | exit 0 |
| Unit/integration tests | `python -m pytest -q` (workspace and fresh venv) | 215 passed, exit 0 |
| Lint | `python -m ruff check .` (workspace and fresh venv) | All checks passed, exit 0 |
| Ground truth | `python scripts/verify_pipeline.py` (workspace and fresh venv) | 20/20 checks, exit 0 |
| Live server | `/_stcore/health`, `/` on 127.0.0.1:8518 / :8519 | `200 ok`, `200` |
| UI workflow | `tests/test_app.py` (21 AppTest cases) | Sample, upload, errors, review, export, audit, isolation |
| Matching quality | Synthetic ground truth | Precision = recall = 1.0 |
| KPI correctness | `tests/test_metrics.py` | Confirmed = exact only (2), mismatches separate |
| Upload safety | `tests/test_uploads.py` | Type/size/traversal/empty checks, cleanup verified |
| Policy enforcement | `tests/test_review_policy.py` | Invalid rows cannot be approved |
| Export safety | `tests/test_report.py` | Formula injection escaped, stable status codes |

---

## 4. Security and safety review

| Control | Implementation | Assessment |
|---|---|---|
| **Upload type allow-list** | `.csv`/`.xlsx` for purchases; `.json` for GSTR-2B | Pass |
| **Upload size cap** | 10 MiB per file (`MAX_UPLOAD_BYTES`) | Pass for demo; note for large registers |
| **Path traversal** | Basename sanitisation + resolved-parent check | Pass |
| **Temp-file cleanup** | `finally` cleanup after success and failure | Pass (AppTest verified empty upload dir) |
| **Empty / malformed files** | Rejected with actionable `UploadValidationError` / `IngestionError` | Pass |
| **Invalid XLSX** | `BadZipFile` / `InvalidFileException` wrapped as `IngestionError` | Pass |
| **Formula injection** | `safe_cell_value()` prefixes `'` for `= + - @` incl. leading whitespace | Pass |
| **Review policy bypass** | `allowed_review_decisions()` / `validate_review_decision()` in decision layer; UI uses them | Pass |
| **Invalid-row approval** | Approve excluded for `MatchStatus.INVALID` | Pass |
| **Secrets** | No hardcoded keys/passwords found; `.env` ignored; `.env.example` placeholders | Pass |
| **Real taxpayer data** | Synthetic fixtures only; committed pytest artifacts contained synthetic data and were removed | Pass with C4 |
| **LLM data egress** | Disabled by default; wording-only; no provider key read | Pass |
| **Automated external actions** | No filing, payment, email, WhatsApp, or portal calls | Pass |
| **Audit integrity** | Append-only JSONL; explicitly not tamper-proof | Pass as documented demo limitation |
| **Determinism** | No randomness in matching/decisions; stable IDs; explicit rounding | Pass |
| **Dependency surface** | Streamlit, pandas, numpy, rapidfuzz, openpyxl, python-dotenv | Acceptable for demo; no lockfile |

No high-severity code defect was found in the reviewed scope. The material risks
are the documented conditions above, not exploitable vulnerabilities.

---

## 5. Operational readiness

| Item | Status |
|---|---|
| Start command | `streamlit run src/itc_sentinel/app.py` |
| Health endpoint | `/_stcore/health` returns `ok` |
| Output location | `data/runs/<run_id>/` (override with `ITC_SENTINEL_DATA_DIR`) |
| Sample inputs | `data/sample/` (override with `ITC_SENTINEL_SAMPLE_DIR`) |
| Logging | Local append-only JSONL per run |
| Persistence | Files only; no database |
| Multi-user | Not supported |
| Backups / retention | Not implemented (out of scope) |
| Monitoring / alerting | Not implemented (out of scope) |

---

## 6. What would change the verdict

**To unconditional synthetic-data demo readiness:**
- Complete C4 (commit artifact removal) and C5 (commit the remediation).
- Perform a short manual UI pass (backlog B-04).

**To production readiness (separate project phase):**
- Complete C1 (CA validation) and C2 (real schema confirmation).
- Add authentication/RBAC, tenant isolation, and persistent storage.
- Add tamper-evident audit storage, retention policy, and legal/privacy review.
- Add dependency locking/scanning, CI/CD, monitoring, and load testing.

---

## 7. Final statement

ITC Sentinel is **ready to demonstrate on synthetic data** with the conditions
listed above. It is **not** a filing system, does **not** determine ITC
eligibility, and should **not** be used with real taxpayer data until the CA
validation and schema conditions are closed. No deployment was performed.
