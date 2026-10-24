# ITC Sentinel — Architecture

**Version:** 0.1  
**Status:** MVP baseline. Keep this document aligned with implementation and record deviations.

## 1. Overall architecture

A single Python application: Streamlit UI calls a plain-Python reconciliation pipeline. No separate HTTP backend, database, agent framework, or mandatory LLM service in the first MVP.

```text
User
  │ uploads purchase register + GSTR-2B JSON / selects sample data
  ▼
Streamlit UI (app.py)
  ▼
pipeline.py
  ├─ ingest.py       read files and validate structure
  ├─ normalize.py    canonicalize identifiers, dates, and amounts
  ├─ matcher.py      exact → fuzzy → probable matching
  ├─ rules.py        isolated, testable rule calculations
  ├─ decision.py     deterministic action, risk, flags, priority
  ├─ messages.py ─── template draft; optional llm.py language enhancement
  ├─ report.py       Excel export
  └─ audit.py        append-only review events
  ▼
RunResult → Summary / Exceptions / Vendor Drafts / Export & Audit tabs
  ▼
data/runs/<run_id>/ (CSV/JSON/JSONL outputs; ignored by Git)
```

### Agentic framing
- **Perceive:** ingest and normalize input files.
- **Reason:** deterministic reconciliation; optional LLM may explain ambiguous records but cannot alter financial fields.
- **Decide:** deterministic rules generate suggestions and reasons.
- **Act:** propose only; prepare drafts and exports, never send or file.
- **Oversee:** human review and audit history.

## 2. Folder structure

```text
itc-sentinel/
├── requirements.md
├── architecture.md
├── rules.md
├── phases.md
├── tasks.md
├── memory.md
├── README.md
├── requirements.txt
├── pyproject.toml
├── .env.example
├── .gitignore
├── app.py
├── src/itc_sentinel/
│   ├── __init__.py
│   ├── config.py
│   ├── schemas.py
│   ├── ingest.py
│   ├── normalize.py
│   ├── matcher.py
│   ├── rules.py
│   ├── decision.py
│   ├── llm.py
│   ├── messages.py
│   ├── report.py
│   ├── audit.py
│   ├── pipeline.py
│   └── ui/
│       ├── summary.py
│       ├── exceptions.py
│       ├── messages_tab.py
│       └── export_tab.py
├── scripts/
│   ├── generate_synthetic_data.py
│   └── run_pipeline_cli.py
├── data/
│   ├── sample/
│   └── runs/                 # generated; Git-ignored
├── tests/
└── docs/
    ├── demo_script.md
    └── pitch_notes.md
```

## 3. Technology stack

| Area | MVP choice | Reason |
|---|---|---|
| Language | Python 3.11+ | Strong fit for tabular processing and rapid iteration |
| UI | Streamlit | Fast, single-language UI for a local demo |
| Data processing | pandas, numpy | Tabular reconciliation and reporting |
| Fuzzy matching | rapidfuzz | Efficient similarity matching |
| Excel I/O | openpyxl | Read/write XLSX |
| Configuration | dataclasses + python-dotenv | Lightweight settings |
| Optional schemas | Pydantic v2 only if validation complexity warrants it | Avoid unnecessary abstraction |
| Charts | Streamlit native charts; Plotly only if needed | Keep dependencies lean |
| LLM | Provider SDK isolated behind `llm.py` | Optional language enhancement with fallback |
| Testing | pytest | Unit and integration tests |
| Lint/format | Ruff | Consistent code quality |
| Persistence | CSV, JSON, JSONL files | No database setup for the demo |
| Deployment | Local Python environment first | Reliable demo without hosting dependency |

Do not introduce LangChain, LangGraph, CrewAI, FastAPI, React, Postgres, Redis, queues, or Docker Compose in the first MVP unless a documented requirement justifies the additional complexity.

## 4. Frontend architecture
`app.py` is a thin entry point. It collects files/settings, invokes `pipeline.run_pipeline()` on an explicit Run action, stores the current `RunResult` in Streamlit session state, and passes it to four views:

1. **Summary:** total ITC in books, matched/unmatched counts, estimated exposure, priority breakdown, and deadline flags.
2. **Exceptions:** filterable worklist, priority sort, record detail, source-side comparison, rule explanation, and approve/reject.
3. **Vendor messages:** one editable draft per vendor, email and short WhatsApp variants, copy/download.
4. **Export & audit:** Excel download and review-event history.

Keep business logic out of UI modules. Re-running should be explicit, not triggered by every widget change.

## 5. Backend / pipeline architecture
The importable package `itc_sentinel` is the application core. Prefer pure functions: DataFrames/settings in, DataFrames or typed results out. Keep file/network I/O at boundaries.

| Module | Responsibility |
|---|---|
| `ingest.py` | Load CSV/XLSX/JSON; validate columns and size; human-readable errors |
| `normalize.py` | Normalize GSTIN, invoice keys, dates, amounts; preserve flagged rows |
| `matcher.py` | One-to-one matching; exact, fuzzy, probable, unmatched, duplicate |
| `rules.py` | Isolated calculations for configured tax-rule assumptions |
| `decision.py` | Action suggestion, exposure, flags, priority, reason, review requirement |
| `messages.py` | Template drafts, optional LLM enhancement, output validation |
| `llm.py` | Sole LLM boundary; timeout, retry limit, safe fallback |
| `report.py` | Safe Excel export and formula-injection protection |
| `audit.py` | Append-only approval/rejection events |
| `pipeline.py` | Orchestrate stages and return a `RunResult` |
| `schemas.py` | Shared types, enums, stable field names |
| `config.py` | Defaults and environment-based configuration |

## 6. Data design and persistence
No database in the MVP. Each run writes a unique directory:

```text
data/runs/<run_id>/
  recon.csv
  decisions.csv
  vendor_drafts.csv
  meta.json
  audit.jsonl
```

`meta.json` should capture run ID, timestamp, input hashes, `as_of` date, settings, input row counts, output counts, and software version when available. Store no secrets in run metadata.

For financial calculations, use `Decimal` or integer paise where practical; avoid relying on binary floats for authoritative monetary results. Any rounding/tolerance policy must be explicit and tested.

### Post-MVP relational model
If persistence/multi-user support becomes necessary, evaluate PostgreSQL tables for firms/clients, vendors, runs, source invoices, reconciliation rows, decisions, approvals, and messages. Introduce migrations and tenant-scoped access at the same time; do not add a database speculatively.

## 7. API design
**MVP:** no HTTP API. UI calls Python functions directly.

**Possible later API:** FastAPI endpoints for creating runs, fetching run summaries/exceptions, recording approvals, retrieving vendor drafts, and downloading reports. Add authentication, authorization, validation, and tenant isolation before exposing it.

## 8. Authentication flow
**MVP:** no application login; local/demo use with synthetic data only. A public hosted demo must not accept sensitive real taxpayer data.

**Later:** managed identity/OIDC, server-side sessions or short-lived tokens, roles such as firm admin/reviewer/viewer, tenant-scoped authorization on every request, and audit records containing actor identity. Never implement home-grown password storage.

## 9. Security and privacy
- Enforce file type/size limits and validate parsed content.
- Never commit `.env`, API keys, taxpayer data, or generated run data.
- Treat uploaded cells and vendor text as untrusted input.
- Escape spreadsheet formula-leading characters in exported text cells.
- Do not send source documents or taxpayer data to an LLM unless explicitly enabled and the user understands the disclosure.
- LLM output cannot change numeric values or decisions; validate or fall back to templates.
- Do not claim the append-only JSONL file is tamper-proof; it is a demo audit trail, not a production-grade immutable ledger.

## 10. Deployment strategy
1. **Primary:** local virtual environment and `streamlit run app.py`.
2. **Optional demo hosting:** deploy only with synthetic/sample data and secrets stored in host configuration.
3. **Backup:** recorded walkthrough plus exported sample workbook.
4. **Production path:** security review, CA-validated rules, persistent storage, authentication/authorization, tenant isolation, backups, monitoring, dependency scanning, CI, and incident handling.

## 11. Important design decisions
- **D-001:** Streamlit instead of React + API for the first demo; less integration work.
- **D-002:** files instead of a database; supports reproducible local runs.
- **D-003:** deterministic matching/rules own all numeric calculations and actions.
- **D-004:** no agent framework in the MVP; the pipeline is linear and explicit.
- **D-005:** synthetic data with ground truth makes accuracy measurable without exposing client data.
- **D-006:** uncertain/high-risk records require human review.
- **D-007:** every LLM feature has a template fallback.
- **D-008:** support B2B invoices only initially; expand scope after input formats and rules are verified.
- **D-009:** `as_of` date and settings are explicit inputs for reproducibility.
- **D-010:** all recommendations are advisory; nothing is filed, sent, or executed externally.
