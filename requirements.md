# ITC Sentinel — Requirements

**Version:** 0.1  
**Status:** Initial planning baseline — validate GST rules with a qualified CA before relying on outputs.

## 1. What needs to be built
A local-first MVP that reconciles a purchase register against GSTR-2B data, highlights invoice-level discrepancies and potential ITC exposure, explains why each row was flagged, supports human review, drafts vendor follow-ups, and exports results with an audit trail.

## 2. Project goals
- Turn two messy financial datasets into an explainable reconciliation worklist.
- Surface high-value and time-sensitive exceptions first.
- Keep financial calculations and policy decisions deterministic and testable.
- Make the demo useful without requiring an LLM API or external integrations.
- Demonstrate measurable matching quality using synthetic data with known ground truth.

## 3. Target users
- Chartered accountants and tax practitioners reviewing client ITC.
- Finance/accounting teams at small and medium businesses.
- Project evaluators who need to see an end-to-end, auditable workflow.

## 4. Core features (MVP)
1. **Input ingestion:** CSV/XLSX purchase register and GSTR-2B JSON; clear validation errors.
2. **Normalization:** normalize GSTIN, invoice numbers, dates, and monetary values without silently discarding invalid rows.
3. **Reconciliation:** duplicate detection, exact matching, constrained fuzzy matching, probable matching, and unmatched rows.
4. **Exception classification:** missing in 2B/books, amount mismatch, tax-head mismatch, duplicate, invalid data, and low-confidence match.
5. **Deterministic decision support:** rule-based suggested action, amount at risk, flags, priority, and human-review requirement.
6. **Dashboard:** summary KPIs, exception breakdown, ITC exposure, and prioritized worklist.
7. **Human review:** approve/reject a suggested action with a recorded reason; no external action is executed.
8. **Vendor communication:** editable email/WhatsApp draft with template fallback and copy/download.
9. **Export:** downloadable Excel workbook containing reconciliation, decisions, and summary.
10. **Audit trail:** append-only local record of review decisions and run metadata.
11. **Demo data:** seeded synthetic inputs and ground truth for reproducible demonstrations.
12. **Tests:** unit tests for normalization, matching, rules, decisions, message validation, and end-to-end pipeline.

## 5. Optional features
### Low-complexity candidates
- Downloadable sample input templates and a column-mapping guide.
- Row-level validation report with downloadable rejected/flagged rows.
- Before/after reconciliation comparison between two runs.
- Search, filters, sorting, and CSV export for the exception worklist.
- “Why was this flagged?” explanations generated from deterministic rule metadata.
- Configurable tolerances and deadline warnings, clearly labelled as assumptions.
- Run summary JSON and input file hashes for reproducibility.

### Later, only after user validation
- Multiple clients/GSTINs and financial years.
- Persistent database, login, role-based access, and multi-user review.
- PDF invoice extraction/OCR.
- Additional GST document types, amendments, credit/debit notes, imports, and broader eligibility checks.
- Read-only integrations with approved GST/accounting providers.
- Background jobs, API service, and production monitoring.

## 6. Success criteria
- A user can load sample data, run reconciliation, inspect exceptions, record a review decision, draft a vendor message, and export a workbook end-to-end.
- Same inputs and settings produce the same deterministic reconciliation results.
- Every proposed action has a traceable reason and relevant source values.
- Fuzzy/probable matches are never silently treated as certain.
- Synthetic matching precision/recall are measured against ground truth; report actual results rather than claiming an arbitrary target.
- Invalid files and malformed rows produce actionable errors rather than crashes or silent data loss.
- The app runs locally from documented setup instructions without an LLM key.
- No real taxpayer data is committed to the repository or sent to an LLM by default.

## 7. Constraints and assumptions
- Initial MVP is single-user, local/demo-first, single GSTIN/client and a bounded financial-year dataset.
- Initial supported inputs: purchase register CSV/XLSX and GSTR-2B JSON; input variations must be documented.
- Synthetic data is the default demo dataset.
- No automatic filing, payment hold, vendor message sending, or GST portal actions.
- LLM is optional and limited to language tasks; it cannot set amounts, determine eligibility, or override deterministic rules.
- Tax rules and deadlines are configurable assumptions until reviewed against current official guidance by a CA.
- Treat outputs as decision support, not tax advice.
- Production use with real data requires a separate privacy, security, legal, and domain-validation review.
