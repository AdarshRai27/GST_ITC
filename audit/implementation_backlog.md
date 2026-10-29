# Implementation Backlog

**Date:** 2026-10-29
**Scope:** Open items after the synthetic-data MVP remediation. Nothing here is
required to complete the demo; each item is either an external validation step, a
documented assumption, or post-MVP production work.

---

## P0 — Before any real-taxpayer-data use

### B-01. CA validation of GST/ITC rules (task P3-01)
- **Status:** Open — external dependency.
- **Why:** Rules and eligibility assumptions are not CA-validated. Every
  `eligibility_status` is currently `UNCERTAIN`.
- **Action:** Have a qualified Chartered Accountant review `rules.py` rule
  sources, rounding/tolerance policy, tax-head treatment, and exposure
  calculations; record sign-off and effective dates.
- **Impact:** Blocks real-data reliance, filing support, and any claim that the
  app determines ITC eligibility.
- **Owner:** Project owner / CA.

### B-02. Confirm the GSTR-2B JSON contract against a real anonymized export
- **Status:** Open — assumption documented in `ingest.py`.
- **Why:** The declared shape `{gstin, period, invoices:[...]}` may not cover
  every export variant (e.g., amendments, credit notes, multi-sheet exports).
- **Action:** Obtain one anonymized export per supported variant; add fixtures and
  parser tests; update the contract documentation.
- **Impact:** Real uploads may fail or silently omit fields for unsupported
  variants.

### B-03. Remove accidentally committed pytest artifacts from Git history
- **Status:** Working-tree copies removed; still tracked in `HEAD`.
- **Why:** 23 pytest temp files were committed in `46c8b0a`. They contain only
  synthetic data, but they are generated artifacts and do not belong in version
  control.
- **Action (requires commit authorization):**
  `git rm -r --cached pytest-of-rinku` and commit the deletion; the new
  `.gitignore` patterns prevent recurrence.
- **Impact:** Repository hygiene and reproducibility only; no runtime effect.

---

## P1 — Before presenting the demo outside the team

### B-04. Verify a fully isolated clean-venv install
- **Status:** **Resolved (2026-10-29).**
- **Evidence:** Fresh `python -m venv` in `%TEMP%`; `pip install -r
  requirements.txt` exit 0; 215 tests passed; Ruff clean; verifier 20/20;
  Streamlit health `200 ok` — all inside the isolated venv.
- **Remaining:** Re-run on the actual target demo machine before an external
  presentation (environment-specific differences are still possible).

### B-05. Manual usability pass of the Streamlit UI
- **Status:** Open — AppTest covers behavior, not visual polish.
- **Why:** AppTest verifies widgets and state, not layout, readability, or
  keyboard navigation.
- **Action:** Run the app, complete the workflow with synthetic files, check the
  four tabs, disclaimers, review form, and download on a fresh browser session.
- **Impact:** Demo quality only.

### B-06. Add a small end-to-end test for XLSX upload through the UI
- **Status:** Open — parser-level XLSX upload is tested; UI-level XLSX is not.
- **Why:** The AppTest upload path currently uses CSV + JSON; XLSX is covered in
  `test_uploads.py` but not through Streamlit.
- **Action:** Add an AppTest case uploading a generated XLSX purchase register.
- **Impact:** Closes a small coverage gap; no known defect.

---

## P2 — Post-MVP / production hardening (explicitly out of scope)

- Persistent database and multi-client support.
- Authentication, RBAC, and tenant isolation.
- Tamper-evident or externally anchored audit storage.
- Amendments, credit notes, debit notes, and OCR ingestion.
- Approved GST portal integrations and filing workflows.
- API service, background jobs, monitoring, CI/CD.
- Dependency scanning, pinned lockfile, and reproducible builds.
- Data-retention and privacy policy, DPIA, and legal review.
- Accessibility and responsive-design review.
- Performance testing on large registers (current cap: 10 MiB/upload; the
  matcher is O(n·m) per GSTIN group).

---

## Technical debt / known limitations

| Item | Impact | Note |
|---|---|---|
| Probable matching is similarity-only | Medium-confidence rows may be unrelated invoices | Always `review_required`; never confirmed |
| Duplicate detection is books-side only | GSTR-2B duplicates are not separately flagged | Documented scope boundary |
| Audit log is append-only by convention | Not tamper-proof | Stated in code/UI/docs |
| Session state is ephemeral | Closing browser resets current run | Per-run files persist under `data/runs/` |
| Priority thresholds are assumptions | Priority ordering may not match a firm's policy | Configurable in `DecisionSettings` |
| No lockfile | Dependency drift possible | `requirements.txt` uses bounded ranges |

---

## Deliberately not done

- No new frontend, API, database, agent framework, or container.
- No auto-filing, payments, or message sending.
- No weakening/removal of tests to improve results.
- No Git commits (not authorized).
- No real taxpayer data introduced.
