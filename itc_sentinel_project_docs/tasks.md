# ITC Sentinel — Live Task Tracker

**Last updated:** 2026-10-16  
**Overall progress:** 5% — planning baseline only; repository implementation has not been inspected in this workspace.  
**Current phase:** Phase 0 — Project setup and scope freeze.

> Do not infer implementation progress from this plan. Mark work complete only after checking the actual repository and recording evidence.

## Current task
- **[P0-01]** Establish and reconcile the six root documentation files.
  - Priority: P0 / Critical
  - Status: In progress
  - Progress: 80% (drafts prepared; still need to place them in the actual project root and verify consistency)

## Pending tasks

| ID | Task | Phase | Priority | Status |
|---|---|---:|---|---|
| P0-02 | Inspect actual repository and preserve any existing user work | 0 | P0 | Pending |
| P0-03 | Add `.gitignore`, `.env.example`, `requirements.txt`, `pyproject.toml`, README skeleton | 0 | P0 | Pending |
| P0-04 | Verify clean environment setup and scope assumptions | 0 | P1 | Pending |
| P1-01 | Implement purchase-register and GSTR-2B loaders | 1 | P0 | Pending |
| P1-02 | Implement normalization and row-level validation | 1 | P0 | Pending |
| P1-03 | Add ingestion/normalization tests | 1 | P0 | Pending |
| P2-01 | Generate seeded synthetic datasets with ground truth | 2 | P0 | Pending |
| P2-02 | Implement exact/fuzzy/probable matching and exception statuses | 2 | P0 | Pending |
| P2-03 | Measure matching accuracy and add edge-case tests | 2 | P0 | Pending |
| P3-01 | Validate tax-rule assumptions with authoritative sources/CA review | 3 | P0 | Pending |
| P3-02 | Implement deterministic decisions, risk flags, priorities, explanations | 3 | P0 | Pending |
| P3-03 | Add rule and decision tests | 3 | P0 | Pending |
| P4-01 | Implement review audit, safe exports, vendor draft templates | 4 | P1 | Pending |
| P4-02 | Add optional LLM wording enhancement and validation/fallback | 4 | P2 | Pending |
| P5-01 | Build Streamlit dashboard and exception review workflow | 5 | P1 | Pending |
| P5-02 | Add export/audit and vendor-message views | 5 | P1 | Pending |
| P6-01 | Run complete tests, lint, benchmark, and demo checklist | 6 | P0 | Pending |

## Completed tasks
- [x] Initial requirements and MVP scope drafted.
- [x] Initial architecture and stack documented.
- [x] Development rules and AI boundaries documented.
- [x] Sequential phase plan and acceptance checklists drafted.
- [x] Initial task tracker and working-memory baseline drafted.

## Blocked tasks
- **B-01:** Cannot directly modify the user's local Windows repository from this session because the repository itself is not mounted here. The documentation package must be copied/extracted into the actual project root, or the repository must be provided as an upload.
- **B-02:** GST-specific rules remain unverified until checked against current official guidance and reviewed by a qualified CA.

## Progress policy
- Update this tracker after each meaningful code/documentation change.
- Record test commands and outcomes before closing tasks.
- Keep one current task and one active phase.
- Overall progress is based on completed acceptance criteria, not file count or lines of code.
