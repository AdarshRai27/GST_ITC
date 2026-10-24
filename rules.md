# ITC Sentinel — Development Rules

These rules apply to all code and documentation changes. If a requirement conflicts with a rule, stop and document the conflict before proceeding.

## 1. Coding standards
- Use Python 3.11+ and type hints on public functions.
- Keep functions small, cohesive, and testable; prefer pure functions for business logic.
- Use descriptive names and constants/enums instead of repeated magic strings.
- Format and lint with Ruff; tests with pytest.
- Add docstrings to public modules/functions where purpose or assumptions are not obvious.
- Avoid premature abstractions and unnecessary classes.

## 2. Libraries and frameworks
**Use:** Streamlit, pandas, numpy, rapidfuzz, openpyxl, python-dotenv, pytest, Ruff; optionally Pydantic when it solves a demonstrated validation need.

**Avoid in MVP unless explicitly approved:** LangChain, LangGraph, CrewAI, AutoGen, FastAPI, React/Next.js, PostgreSQL, Redis, Celery, Docker Compose, ML model training, and unnecessary ORM layers. Do not add a dependency for a task that the standard library can handle cleanly.

## 3. Error handling
- Validate inputs at boundaries and return actionable, human-readable errors.
- Use domain-specific exceptions for expected input failures; do not swallow broad exceptions silently.
- Never silently drop malformed rows; preserve them with a validation status or report them clearly.
- LLM, file export, and optional integrations must fail safely with a clear message and a deterministic fallback where possible.
- Logs must not contain secrets or unnecessary taxpayer data.

## 4. Financial and tax logic
- Keep GST rule calculations isolated in `rules.py`, with a source/assumption and effective-date note.
- Never let an LLM calculate, modify, or approve monetary values, ITC eligibility, priorities, or actions.
- Keep a reason code and human-readable explanation for each suggested decision.
- Use `Decimal` or integer paise for money calculations where practical; make rounding/tolerance rules explicit.
- Do not present unverified tax assumptions as legal certainty. Mark them for CA verification.
- Distinguish matching status, eligibility status, and suggested operational action; they are not interchangeable.
- Never auto-file returns, submit portal actions, send vendor communications, or initiate payment holds.

## 5. Security and privacy
- Use synthetic data by default. Do not commit real client invoices, GSTINs, credentials, or exports.
- Keep secrets in environment variables; `.env` must be ignored by Git and `.env.example` must contain placeholders only.
- Validate file type, size, columns, and JSON structure before processing.
- Treat all uploaded values and LLM inputs as untrusted data, not instructions.
- Protect Excel exports from formula injection.
- Make LLM usage opt-in; disclose that data may leave the local machine when a provider API is used.
- Do not add public hosting for real taxpayer data without authentication, access control, encryption, retention policy, and security review.

## 6. Performance expectations
- Keep the demo responsive on ordinary developer hardware for a small-to-medium synthetic dataset.
- Avoid recomputing the pipeline on every UI interaction.
- Use one-to-one matching constraints to prevent one invoice matching multiple invoices.
- Establish measured performance targets after benchmarking the synthetic dataset; do not claim unmeasured guarantees.
- Any optimization must preserve correctness and be backed by tests.

## 7. File organization
- Keep UI code in `src/itc_sentinel/ui/`.
- Keep business logic in the corresponding package modules.
- Keep scripts in `scripts/`, tests in `tests/`, sample data in `data/sample/`, and generated runs in `data/runs/`.
- Never commit virtual environments, caches, secrets, or generated run output.
- Avoid giant modules and circular imports.

## 8. Naming conventions
- Modules/functions/variables: `snake_case`.
- Classes/types: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.
- Tests: `test_<module_or_behavior>.py`.
- Use stable enums or documented string values for statuses/actions.
- Use explicit names for normalized versus raw columns.

## 9. Testing rules
- Add or update tests for every behavior change in normalization, matching, rules, decisions, exports, and review state.
- Test edge cases: duplicates, ambiguous matches, invalid GSTINs, malformed dates, missing columns, zero/negative values, rounding boundaries, and empty files.
- Use ground-truth tests for matching quality; report measured metrics.
- Test LLM fallback and invented-number rejection without requiring a live provider.
- Run the relevant tests and full test suite before marking a task complete.

## 10. AI boundaries — never do these
- Never invent GST rules, data fields, API behavior, test results, or implementation status.
- Never treat a planned feature as implemented without inspecting code and tests.
- Never alter the project architecture or add major dependencies without documenting the trade-off first.
- Never allow model output to override deterministic policy, financial calculations, review decisions, or authorization.
- Never send messages, file returns, change books, or trigger payments automatically.
- Never use real taxpayer data in examples or tests unless it is explicitly approved and safely anonymized.
- Never mark a phase complete unless every required acceptance criterion is evidenced.
- Never work on multiple phases simultaneously unless the project owner explicitly instructs it.
- Never overwrite user work or delete files without explicit authorization.
- Never claim production readiness based only on a successful local demo.
