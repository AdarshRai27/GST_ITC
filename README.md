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
   .venv\Scripts\Activate.ps1
   ```

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
- Click **Run Reconciliation** to deterministic reconciliation pipeline.
- Review results in four tabs: **Summary**, **Exceptions**, **Vendor Messages**, **Export & Audit**.
- Use **Download Excel Workbook** to save the report to `data/runs/<run_id>/reconciliation.xlsx`.

Note: `app.py` and the pipeline modules are implemented through Phase 5. Phases 0–4
establish the skeleton and configuration.

## Test and lint commands

```powershell
# Lint
ruff check .

# Tests
pytest
```

## Important limitations

- GST rules and deadlines are configurable assumptions. Validate them against
  current official guidance and a qualified chartered accountant before relying
  on outputs.
- Outputs are decision support, not tax advice.
- Use synthetic data by default. Do not commit real taxpayer data, GSTINs, or
  credentials to this repository.
- The append-only audit log is a local demo trail, not tamper-proof storage.
- LLM enhancement is opt-in (`ITC_SENTINEL_LLM_ENABLED=1`) and disabled by default;
  it cannot change reconciliation decisions or numeric results.
- A match does **not** establish ITC eligibility. All eligibility statuses are
  **UNCERTAIN** pending CA review of tax rules.
- A discrepancy alone does **not** establish wrongdoing.
- Streamlit session state is ephemeral; closing the browser resets the current
  run's review decisions and audit events. Prior run directories in
  `data/runs/` persist unless deleted.

## Project structure

- `src/itc_sentinel/` — application package (business logic, added incrementally
  through Phases 0–5).
- `tests/` — pytest suite (152 tests across all phases).
- `data/sample/` — synthetic demo inputs (ground-truth verified).
- `data/runs/` — generated per-run artifacts (Git-ignored; one directory per
  Streamlit session run).
- `app.py` — Streamlit MVP UI (Phase 5).
- Root Markdown documents: `requirements.md`, `architecture.md`, `rules.md`,
  `phases.md`, `tasks.md`, `memory.md`.