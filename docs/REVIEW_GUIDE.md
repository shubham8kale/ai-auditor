# Review guide

This is a preparation and review application, not an autonomous audit opinion.
Original files, extracted facts, proposed judgments, human corrections, and
approvals are separate records.

## Read the implementation in this order

| File | Responsibility | Important boundary |
| --- | --- | --- |
| `auditor/domain.py` | Policy selection, materiality, scope, sampling, reconciliation | Decimal arithmetic; no model decides a calculation |
| `auditor/parsing.py` | Spreadsheet rows, totals, and cell references | A footer is checked, not counted as another transaction |
| `auditor/documents.py` | PDF/image extraction and evidence checks | Extracted facts remain proposals until reviewed |
| `auditor/workflow.py` | Five preparation stages and revision history | Earlier stages require approval; corrections stale dependent work |
| `auditor/vouching.py` | Invoice assertions and evidence references | Missing evidence stays unresolved; exceptions remain visible |
| `auditor/corrections.py` | Typed edits with reasons | Chat has no approval operation |
| `auditor/chat_context.py` | Compact workspace context for assistant answers | Evidence identities remain linked; omitted records are explicitly counted |
| `auditor/jobs.py` | Persistent job states and result publication | Changed inputs or interrupted runs cannot publish an old result |
| `auditor/main.py` | Authenticated API and explicit approval routes | Every engagement/document lookup checks ownership |
| `frontend/src/main.tsx` | Review workspace, evidence dialogs, client upload portal | User approval is a separate button, not a chat answer |
| `auditor/workpapers.py` | PDF snapshots of saved revisions | Draft/stale state and reviewer identity remain visible |

## Data flow

1. An authenticated auditor creates an engagement and uploads evidence.
2. The API keeps the original in private storage and records its hash.
3. A persisted job parses rows or asks the vision model for structured facts.
4. Local validation checks entity, period, completeness, and document-specific requirements.
5. The auditor reviews the original and extracted facts, then accepts or returns the document.
6. Preparation produces a draft revision. The auditor resolves blockers and explicitly approves it.
7. Corrections retain an audit event and invalidate affected approvals. Prior revisions remain readable.

An upload link grants only a time-limited ability to read the request list and
submit files. It does not grant access to evidence downloads or audit results.

## What to challenge during review

| Question | Where to inspect or exercise |
| --- | --- |
| Can another user read this engagement? | API ownership tests; try a second named account |
| Can an incomplete GL be treated as the entire expense population? | Document findings and sampling reconciliation |
| Can a model approve its own work? | Typed correction schema and revision approval endpoint |
| Does a correction erase an earlier approval? | Review history: old actor/time retained, revision becomes stale |
| Can a disposition conceal missing cutoff evidence? | Workflow integration regression with missing service dates |
| Does the bank confirmation trigger use the correct account statement? | Request matching and threshold regression |
| Can a restart leave an apparent successful result? | Job interruption tests and saved job status |
| Are invoice dates substituted for service dates? | Extraction smoke test and cutoff assertion |
| Are policy judgments hard-coded to one client? | Independent generated demo, generic domain functions |

## Synthetic evaluation data

`scripts/create_demo.py --scenario clean` and `--scenario exceptions` create
separate fictional datasets under ignored `data/demo/`. They contain an engagement
letter, balanced trial balance, expense ledger, eight invoices, and an expected
results manifest. Invoice designs vary; two are scanned PDFs.

The exception dataset contains a wrong entity, a service after year-end, a $400
amount discrepancy, vague legal services, and a possible capital expenditure.
The clean dataset is a baseline. These documents must never be attached as
support for a real client.

The automated five-stage integration test substitutes predictable semantic model
responses. It tests workflow and arithmetic, not real-model accuracy. Live model
evaluation and the hosted fictional path through testing have also been exercised;
see `docs/EVALUATION.md` for outcomes.

## Review handoff

Read this guide, the README, and the evaluation record before changing code.
Use the project `.venv`. Local tests substitute model responses and do not send
documents to any provider. Do not start another production-config application
process against a live job database. Use an isolated local database for review
experiments.

Focus independent review on approval bypasses, incorrect evidence acceptance,
arithmetic/policy boundaries, chat edits, stale work, and ownership isolation.
For each issue, record a reproducible trigger, expected versus actual behavior,
severity, and the relevant file/line. Review suggested fixes before applying them.
Incomplete evidence must remain a documented blocker; changing source files or
inventing metadata is not a software fix. Never place a password in the README
or repository.

## Current limitations to discuss honestly

- One application process handles jobs. Horizontal scaling requires a shared queue
  and distributed coordination; do not run two deployments against the same job tables.
- Free model quotas pace extraction and may require retries. A stopped service
  marks unfinished jobs interrupted; a reviewer must retry them.
- The policy baseline is implemented in code with source references to an
  illustrative methodology (`POL-`, `REF-`, and `BUL-` identifiers). Uploading a
  new policy does not automatically replace the approved rules.
- PBC requests cover more evidence types than the expense-testing demonstration.
  Specialist support and direct bank-confirmation provenance can require work
  outside the application. Uploading a file is not sufficient proof.
- The application prepares expense testing and related planning; it does not
  perform every substantive audit procedure or issue a final audit opinion.
- Schema creation is transactional, but schema migrations, formal retention and
  deletion tools, recovery drills, and a broader model evaluation remain future work.
- Regression and hosted checks do not guarantee complete model accuracy.
