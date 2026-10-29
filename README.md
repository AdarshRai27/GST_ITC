# ITC Sentinel — GST Input Tax Credit Reconciliation MVP

A local-first MVP that reconciles a purchase register against GSTR-2B data,
highlights invoice-level discrepancies and potential ITC exposure, explains why
each row was flagged, supports human review, drafts vendor follow-ups, and
exports results with an audit trail.

## MVP scope (single-user, demo-first)

- Single GSTIN / client, bounded financial-year dataset.
- Supported inputs: purchase register (CSV/XLSX) and GSTR-2B (JSON).
- Deterministic reconciliation and decision support — no LLM required.
- No automatic filing, payment holds, vendor message sending, or GST portal actions.
- B2B invoices only initially.

## Environment setup

1. Clone / open this repository.
2. Create a project-local virtual environment:

   ```powershell
   python -m venv .venv
   ```

   **Note:** On Windows PowerShell, the default execution policy is "Restricted",
   which blocks `.venv\Scripts\Activate.ps1`. If activation fails, either:
   - Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
   - Or use the venv directly: `.venv\Scripts\python.exe -m <command>`

3. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

4. (Optional) Copy `.env.example` to `.env` and fill in values. `.env` is ignored
   by Git and must never contain committed credentials.

## Run the application

```powershell
streamlit run src/itc_sentinel/app.py
```

The app opens at `http://localhost:8501`. Use the sidebar to:

- Select synthetic sample data or upload your own purchase register (CSV/XLSX)
  and GSTR-2B JSON files.
- Click **Run Reconciliation** to run the deterministic pipeline. The pipeline
  runs only on this explicit action; changing widgets does not re-run it.
- Review results in four tabs: **Summary**, **Exceptions**, **Vendor Messages**,
  **Export & Audit**.
- Generate and download the Excel report. Generated files and audit logs live
  under `data/runs/<run_id>/` (override the root with `ITC_SENTINEL_DATA_DIR`).
  Temporary copies of uploaded files are written under the same run directory
  and deleted after ingestion, whether it succeeds or fails.

Every reconciliation request rotates the run ID, audit log, and review state, so
data from different runs is never mixed in the UI.

## Test, lint, and verification commands

```powershell
# Lint
ruff check .

# Full test suite (215 tests, including Streamlit AppTest workflow tests)
pytest

# Reproducible end-to-end ground-truth verification
python scripts/verify_pipeline.py
```

## Important limitations

- GST rules and deadlines are configurable assumptions. Validate them against
  current official guidance and a qualified chartered accountant before relying
  on outputs.
- Outputs are decision support, not tax advice.
- A match does **not** establish ITC eligibility. All eligibility statuses are
  **UNCERTAIN** pending CA review of tax rules.
- An exact match is only a **candidate** for an ITC claim and still requires
  human review; it is not an approved claim.
- A discrepancy alone does **not** establish wrongdoing.
- Use synthetic data by default. Do not commit real taxpayer data, GSTINs, or
  credentials to this repository.
- Uploads are capped at 10 MiB per file and restricted to `.csv`/`.xlsx`
  (purchase register) and `.json` (GSTR-2B). Filenames are sanitised to prevent
  path traversal.
- The append-only audit log is a local demo trail, not tamper-proof or legally
  compliant storage.
- LLM enhancement is opt-in (`ITC_SENTINEL_LLM_ENABLED=1`) and disabled by default;
  it cannot change reconciliation decisions or numeric results.
- Streamlit session state is ephemeral; closing the browser resets the current
  run's review decisions and audit events. Prior run directories in
  `data/runs/` persist unless deleted.

## Project structure

- `src/itc_sentinel/` — application package:
  - `ingest.py`, `normalize.py`, `schemas.py` — loading and canonicalization.
  - `matcher.py` — deterministic reconciliation and stable `record_id` identity.
  - `rules.py`, `decision.py` — isolated calculations and decision/review policy.
  - `metrics.py` — single source of truth for dashboard/export KPIs.
  - `audit.py`, `messages.py`, `llm.py`, `report.py` — audit trail, vendor drafts,
    optional wording enhancement, Excel export.
  - `uploads.py` — safe temporary storage and cleanup of uploaded files.
  - `app.py` — Streamlit MVP UI.
- `tests/` — pytest suite (215 tests across all phases).
- `scripts/verify_pipeline.py` — end-to-end ground-truth verification.
- `data/sample/` — synthetic demo inputs (ground-truth verified).
- `data/runs/` — generated per-run artifacts (Git-ignored).
- `audit/` — verification and readiness reports.
- Root Markdown documents: `requirements.md`, `architecture.md`, `rules.md`,
  `phases.md`, `tasks.md`, `memory.md`.
