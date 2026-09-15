# AI Auditor

A personal project for evidence-led audit preparation and review. The UI and API are deployed
together on Render with named Supabase authentication.

[Open the demo app](https://ai-auditor-o2ym.onrender.com/). An account is required
and there is no self-service sign-up. The free service may take time to wake after
inactivity. Extraction is paced at a minimum of 32 seconds between model calls to
fit the free API quota; uploaded documents queue and process one at a time. Queued
and failed documents are identified by name, with a retry control for quota failures.

The owner's private workspace holds two fictional engagements that are meant to be read as a
pair. **Cedar Supply Co.** shows the clean path, approved through all five stages.
**Harbor Supply Co.** shows the opposite: its expense testing stops at a draft with
four exceptions, two unresolved selections, and a $400 amount difference, and final
approval stays blocked on purpose.

## What it does

The workspace prepares engagement requests, account mapping, materiality and scope,
expense samples, and invoice testing. Every stage saves a draft with source
references. Human approval is required before downstream work. Corrections retain
history and invalidate affected approvals. Workpapers export as PDFs.

AI extracts document facts and proposes judgments. Decimal arithmetic, policy
thresholds, selection rules, ownership checks, and approval controls run in Python.
Chat can propose typed corrections with reasons; it cannot approve work.

## Walkthrough in plain language

| Step | What the reviewer does | What the application produces |
| --- | --- | --- |
| 1. Engagement and requests | Upload the engagement letter, check its facts, and approve the profile | A client profile and a list of evidence to request |
| 2. Account mapping | Upload and review the trial balance and optional prior mapping library | Proposed financial statement categories for each account |
| 3. Materiality and scope | Review the benchmark, thresholds, and risk assumptions | The size of an error that matters for planning and the accounts requiring work |
| 4. Expense sample | Review the expense ledger and its reconciliation to the trial balance | Selected transactions, amounts, and the reason each was selected |
| 5. Expense testing | Upload invoices, review extraction, inspect checks, and record follow-up | Evidence-linked exceptions, unresolved items, and a draft conclusion |

The **trial balance** is the account-level summary. The **general ledger** contains
the individual transactions behind it. **Materiality** is a planning threshold;
**performance materiality (PM)** is a lower working threshold; the **clearly trivial
threshold (CTT)** is smaller still. These thresholds do not make evidence gaps or
qualitative exceptions disappear.

“Ready” means extraction succeeded. “Accept evidence” confirms the reviewed
document can support testing; it does not mean the ledger entry is correct.
“Approve stage” signs off a particular preparation revision. An **exception** is
a detected mismatch; **unresolved** means the support is insufficient. A selection
can have both. A correction makes affected work **stale** until prepared again.

For example, the fictional ledger records $12,400 while its invoice shows $12,000.
The reviewer can accept the accurately extracted invoice, and testing still flags
the $400 difference. A follow-up note retains that difference and does not claim
that the client corrected it. PDF exports preserve the saved revision's status.

## Technical deep-dive: architecture

AI reads documents and proposes judgments; deterministic Python owns monetary
calculations, policy thresholds, selection rules, and approval controls. The
[review guide](docs/REVIEW_GUIDE.md) continues this deep-dive with file-by-file
responsibilities, the data flow, review questions, and implementation limitations.

| Component | Technology | Purpose |
| --- | --- | --- |
| Review UI | React, TypeScript, Vite | Evidence, workpapers, corrections, approval history |
| API and jobs | FastAPI, Python 3.12 | Validation, calculations, persistent job states |
| Data and identity | Supabase | PostgreSQL, named-user auth, private original files |
| Model | Groq `qwen/qwen3.8-27b` | Structured vision extraction and judgment proposals |
| Deployment | One Docker service on Render | Serves both frontend and backend |

The policy baseline the application enforces (document standards, materiality and
sampling rules, client-context profiles, evidence documentation) is an illustrative
methodology implemented in code with section references such as `POL-103 §2.1`.
It is not a published professional standard.

Inference Zero Data Retention must be enabled before confidential model requests.
Production requires PostgreSQL, named authentication, and private storage. App
tables have RLS enabled and direct access revoked from public Supabase roles.

## Development

Use the dedicated `.venv` for all project Python commands. On a fresh Windows
checkout with Python 3.12, create it with `py -3.12 -m venv .venv`. Install with:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -e ".[dev]"
```

Copy `.env.example` to `.env` for a new setup. The defaults permit local
SQLite/file storage. The development auth bypass must never be enabled on an
internet-accessible service.

For frontend development, use Node 24, run `npm ci` in `frontend/`, then `npm run dev`.
In another terminal start the API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn auditor.main:app --host 127.0.0.1 --port 8000
```

The Vite development server proxies API calls to port 8000. Alternatively, build
the frontend with `npm run build` and use the API server to serve it.

The Dockerfile builds both components. With a privately prepared production env
file, `docker build -t ai-auditor:local .` builds the image and
`docker run --env-file .env.render -p 127.0.0.1:8000:10000 ai-auditor:local` runs it.
Only one application instance should use a database at a time. The health check
is `/health`; it checks the process and a database query, not model availability.

The variable names `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY` also accept
Supabase's current publishable and secret keys respectively. Only the publishable
key is returned to the browser. Never place the server secret in frontend settings.

## Validation

- 62 tests pass: `.\.venv\Scripts\python.exe -m pytest -q`. Security checks
  are recorded in [Security](SECURITY.md).
- Lint passes: `.\.venv\Scripts\python.exe -m ruff check auditor tests scripts`.
- TypeScript checking and the Vite production build pass.
- A Linux Docker build and local named-account sign-in succeed. Anonymous
  engagement access returns HTTP 401; all seven app tables have RLS enabled.
- The hosted page, JavaScript, CSS, and `/health` respond successfully. Signed-out
  requests to `/api/engagements` and `/api/me` return HTTP 401; the upload portal
  rejects a missing token. Public configuration exposes only intended settings
  and a publishable key.
  The hosted exception workflow was completed through a testing draft:
  eight selections, four expected exceptions, two unresolved selections, and a
  $400 recorded amount difference. Final approval remains blocked by evidence
  gaps and pending follow-up, as intended. The testing PDF was downloaded and
  opened; a saved human follow-up correctly invalidated the earlier draft and
  appeared in the regenerated results.
- GitHub Actions passes the backend checks and frontend build on Linux.
- A hosted assistant check correctly distinguishes the two returned invoices from
  all five transactions needing follow-up; evidence acceptance does not conceal
  transaction exceptions.
- The clean fictional engagement completed all five hosted stages through
  human approval: eight clean results, zero exceptions, zero unresolved selections,
  and a $0.00 amount difference. Its testing PDF displays Approved. A later fix
  added bounded retries for transient provider errors; its regression coverage is
  included in the current test suite.
- A synthetic five-stage integration test checks arithmetic, visible exceptions,
  unresolved cutoff evidence, and invalidation after a risk correction.
- API tests cover cross-user access, upload handling, stale-version rejection,
  review gates, portal expiry, and draft PDF export. Job tests reject old results
  after input changes and interruptions.
- A live synthetic image test passed eight extraction checks, including retaining
  an unknown service period. Repeat deliberately with
  `.\.venv\Scripts\python.exe scripts/check_groq.py`; it consumes free API quota.
  The first attempt exposed ambiguous issuer wording and invalid empty-field
  types, leading to explicit field meanings and a closed JSON schema.
- Independent clean/exception demo files can be generated with
  `.\.venv\Scripts\python.exe scripts/create_demo.py --scenario clean`
  (or `--scenario exceptions`). They are fictional, not real client evidence.
- The resumable live evaluator is
  `.\.venv\Scripts\python.exe scripts/evaluate_demo.py --scenario exceptions`.
  It sends only the generated fictional files to Groq and tests invoice assertions.
  Results stay under ignored `tmp/demo-evaluation/`; unchanged successful calls are
  cached to conserve quota. `--fresh` deliberately repeats calls. This evaluation
  does not create production engagements or perform human approval.

These checks do not establish complete model accuracy or audit readiness.
See [the review guide](docs/REVIEW_GUIDE.md) for code navigation and limitations.
See [the evaluation record](docs/EVALUATION.md) for observed model failures and fixes.

## Tools, AI assistance, and review

Codex with the Astra model assisted with source analysis, design alternatives,
implementation, tests, debugging, and documentation. Claude performed a separate
repository review. Python/Pytest/Ruff, TypeScript/Vite, Docker, Git, and GitHub
provided development and validation tooling. PDF inspection used pypdf, PDFium,
and rendered images; spreadsheets used openpyxl. The Groq-hosted model is a
runtime product dependency for extraction and judgment proposals, distinct from
the AI tools used to develop the application.

The author approved the decision baseline before implementation and maintained
working agreements in `AGENTS.md`. Unresolved product and audit-method choices
were presented with alternatives for the author to decide. The author handled
account setup and hosted testing, checked source facts, accepted or returned
evidence, and explicitly approved stages; these actions were not delegated to chat.

Live testing caught three interpretation failures: the model left a legal
matter-detail flag unknown despite a specific description, relied on a ledger
description when the invoice itself was vague, and could not distinguish repair
from replacement in an ambiguous fictional invoice. Responses included clearer
field definitions, a deterministic validity guard, and better fictional source
evidence, followed by targeted live regressions. See the
[evaluation record](docs/EVALUATION.md) for the original outcomes and limitations.

The architecture assumes model judgments can be wrong. Python calculates money,
applies policy thresholds and sample selection, and enforces approval gates.
Missing required evidence and blocking findings prevent approval; model output
cannot approve a stage or bypass those gates. Individual semantic judgments still
require human review.

### Hindsight

- Treat an incomplete ledger as an explicit blocked scenario alongside a separate
  complete fictional scenario. This makes the distinction between a software
  failure and an evidence gap clear early.
- Run a small live extraction/assertion check before broad implementation. A
  valid JSON response can still contain an incorrect interpretation.
- Budget free API calls before batch uploads, and identify each queued or failed
  document clearly. Cache repeatable evaluation results.
- Test assistant questions against a fully populated workspace. A compact context
  must retain the identities behind its summary counts.
- Track phase time from the start and reserve a separate review period. Commit
  timestamps are useful evidence but cannot reconstruct hands-on time accurately.

## Data handling

Real client documents, client-derived results, private analysis, generated local
fixtures, credentials, and temporary files are excluded from Git. Do not commit them.

The hosted instance requires an owner-provisioned account; no shared login is
published. Its current stored examples are fictional. See [Security](SECURITY.md)
for the access model, audit scope, and remaining limitations.
