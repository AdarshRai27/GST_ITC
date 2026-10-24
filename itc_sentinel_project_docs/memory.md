# ITC Sentinel — Project Working Memory

**Initialized:** 2026-10-16  
**Current phase:** Phase 0 — Project setup and scope freeze  
**Current implementation status:** Documentation baseline drafted; actual repository contents have not been inspected in this workspace.

## Project goal
Build a local-first MVP for GST Input Tax Credit reconciliation: compare a purchase register with GSTR-2B, identify and prioritize exceptions, explain suggested actions, support human review, draft vendor follow-ups, and export auditable results.

## Decisions made
1. **Streamlit + Python pipeline for the first MVP.** This minimizes frontend/backend integration and supports a fast demo.
2. **No database initially.** Use per-run CSV/JSON/JSONL outputs; revisit persistence only when multi-user or multi-client needs are validated.
3. **Deterministic financial logic.** Matching, amounts, risk, priorities, and suggested actions are computed in code, not delegated to an LLM.
4. **LLM is optional.** It may improve wording or explanations only; templates must work offline.
5. **Synthetic data first.** Use seeded sample data and ground truth to measure matching quality without exposing client data.
6. **Human approval required for uncertain or high-risk records.** No sending, filing, payment holds, or external write actions.
7. **Single-user, B2B, bounded-scope demo.** Defer multi-tenant access, broad GST document support, OCR, and production integrations.
8. **GST rules require validation.** Do not present legal/tax assumptions as authoritative until checked against current official sources and reviewed by a qualified CA.

## Current status
- Requirements, architecture, rules, phases, tasks, and memory documents have initial drafts.
- No application code has been written as part of this documentation package.
- The user's actual local project directory is not available to inspect or edit directly in this runtime.
- The proposed architecture file supplied in the conversation is the starting design reference, not evidence that any modules exist or work.

## Current file being worked on
`requirements.md`, `architecture.md`, `rules.md`, `phases.md`, `tasks.md`, and `memory.md` — initial planning baseline.

## Known issues / open questions
- Confirm actual repository location and whether this is a fresh project or should be reconciled with an existing implementation.
- Confirm the exact supported GSTR-2B JSON shapes using representative, anonymized samples.
- Verify tax-rule assumptions and effective dates with authoritative sources and CA review.
- Decide how invalid rows are represented in exports and whether a separate validation report is needed.
- Benchmark the matching algorithm on generated ground-truth data before setting a quality target.
- Do not use real taxpayer data in a public hosted demo.

## Instructions for future sessions
- Read this file and `tasks.md` before making changes.
- Inspect the actual repository before claiming a feature is implemented.
- Work on one phase at a time unless the project owner explicitly changes this rule.
- After meaningful changes, update `tasks.md` and `memory.md`, plus any affected design document.
- Record decisions and their rationale; do not silently drift from the architecture.
- Never mark a phase complete without acceptance evidence.
