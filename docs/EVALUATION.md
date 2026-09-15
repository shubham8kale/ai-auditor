# Evaluation record

## Automated checks

The isolated backend suite currently has 62 passing tests. It covers monetary
boundaries, policy applicability, sampling, reconciliation, document findings,
ownership, review gates, version conflicts, job interruption, and revision history.
Nine security regression cases added on September 15 cover body-size enforcement,
security headers, private paths, and XML entity rejection; see `SECURITY.md`.
TypeScript checking and production builds have also passed locally and in GitHub
Actions. These checks complement live evaluation; they do not establish model accuracy.

## Live model baseline

An independent fictional engagement contains an engagement letter, trial balance,
expense ledger, and eight invoices. Two invoices are scanned PDFs. The initial
live extraction/assertion run passed 68 of 71 checks. Three discrepancies required
investigation:

| Observation | Cause and action |
| --- | --- |
| A legal invoice naming a warehouse lease renewal was marked insufficiently detailed | The model left the matter-detail flag unknown. Clarified that a specific description can establish the matter without a separate matter number. |
| A vague legal invoice received passing individual assertions | The model relied on the ledger's fuller description. The overall document remained unresolved, but the assertion wording was misleading. The prompt now distinguishes the recorded claim from source support, and a deterministic guard keeps vague professional-services validity unresolved. |
| A purportedly clean repair invoice remained unresolved | Its short description did not distinguish repair from replacement. Expanded the fictional invoice to specify restoration of existing equipment without a new asset or added capacity; did not force the model to pass ambiguous evidence. |

A targeted live regression of these three invoices passed all 22 checks after the
fixes. A temporary free-API rate limit interrupted it; it resumed from cached
extractions. Cached results and exact synthetic source extractions remain in
ignored `tmp/demo-evaluation/`, including the original failed baseline.

## Workflow and deployment

- All five preparation stages passed in an isolated in-memory fixture using
  cached live extraction: materiality 10,000; PM 6,500; eight selections;
  four exceptions, two unresolved selections, and a 400 amount difference. Test-fixture
  approvals are explicitly labeled and do not affect the hosted audit records.
- Hosted page/assets/health checks pass. Anonymous workspace requests are rejected,
  and public configuration contains no server secret key.
- On September 9, the author completed the hosted exception workflow through the
  expense-testing draft: approved the first four stages, reviewed all eight
  invoices, accepted six, and returned two for vague services and wrong entity.
  Two invoice extractions hit free API quota limits and succeeded on manual retry.
  The testing draft identified the expected cutoff, amount, capitalization, and
  entity exceptions. Three selections were clean; one had insufficient service
  detail. Four exceptions and two unresolved selections overlap because the
  wrong-entity invoice is both an exception and unaccepted support. The recorded
  amount difference was 400; other exceptions were not treated as quantified
  amount differences. Final approval correctly remained blocked.
- The author downloaded and opened the hosted testing PDF. A human follow-up
  retained the 400 difference as an unadjusted exception with no client response;
  saving it marked the earlier testing revision stale. The author regenerated the
  draft; the saved note, amount difference, and remaining blockers were verified.
- Hosted use also exposed usability gaps: refresh now retains the engagement and
  stage, sampling shows the selected total, processing/retry notices identify
  documents, and extracted amounts use consistent currency formatting. Each
  frontend change passed TypeScript checking and a production build.
- A hosted assistant question exposed a context-compaction defect: the summary
  retained counts but dropped the identities of unresolved evidence. Chat context
  now includes document filenames/status/findings and compact per-selection
  assertions, links, and dispositions. Oversized contexts omit whole records with
  explicit omission counts instead of slicing JSON. Two regressions cover a large
  workspace, valid bounded JSON, and exclusion of another user's evidence. Live
  verification exposed a second issue: the expanded request exceeded the free
  provider's size limit (HTTP 413). Context now has a 10,000-character budget and
  a 1,000-token response budget; a 413 triggers one smaller, explicitly incomplete
  4,500-character context attempt. A regression verifies the retry retains the
  unresolved document link and remains within budget. The next hosted answer mixed
  returned-document status with accepted-invoice exceptions and omitted the cutoff
  exception. An explicit complete attention summary now separates these categories
  and survives detail pruning. A live check of the smaller context, using the exact
  application prompt and only fictional demo data, correctly named two returned
  documents and all five transactions needing follow-up (3,257 total tokens).
  A regression checks these distinctions even when detailed rows are omitted.
  The author repeated the question after deployment and received the same correct
  distinction: two returned documents and all five transactions needing follow-up.
- Local copies of the latest five hosted fictional workpapers were rendered and
  visually checked across 13 pages. The testing export retains all eight
  references, the 400 difference, and the saved human follow-up. Follow-up metadata
  now appears as a readable table rather than raw JSON.

## Clean-run verification

A separately named fictional clean engagement was exercised through accepted
invoices and approved sampling. Three hosted testing attempts failed with HTTP
503 at different elapsed times. An exact local trace of its testing preparation,
using the saved accepted evidence and a read-only database transaction, produced
eight clean results, zero exceptions, zero unresolved selections, and a zero
amount difference. This diagnostic did not publish or approve a hosted revision.

The adapter retried quota errors but previously aborted immediately on server
availability errors. A reliability fix extends its existing bounded retry loop to
HTTP 502/503/504, with at most four total attempts. Four regression cases cover
recovery, exhaustion, unchanged request content, and immediate failure for invalid
credentials. After deployment, the hosted clean draft contained eight clean
results, zero exceptions, zero unresolved selections, a zero amount difference,
and no blocking findings. The author approved testing on September 9; all five
stages now retain approved status and reviewer records. The author then downloaded
the final testing PDF and confirmed that it displays Approved.

A Docker image built from the tracked source also passed an isolated startup
check: frontend and health responded, and anonymous engagement access returned
401. The disposable container had networking disabled, no host credentials, and
its own local database; it was stopped after verification.

## Practical lessons

A hosted mapping preparation also hit the free AI limit. Mapping requests now
omit redundant source metadata and size their response budget to the unresolved
accounts. If AI remains unavailable, the draft retains deterministic mappings
and blocks approval of unresolved accounts, allowing manual correction. A local
regression verifies this behavior; the exact cause of that provider rejection
was not established by diagnostics.

An engagement letter extraction also exposed confusion between the prior audit
date and the prior materiality benchmark. The extraction schema now restricts
benchmarks to named financial bases, the prompt distinguishes them from dates,
and the review form supports `null` to clear an unsupported fact. A live synthetic
letter regression passed all three checks: unknown benchmark retained, recurring
audit identified, and correct fiscal year-end. An API regression verifies that
clearing a fact preserves the original page and requires renewed evidence review.

1. Strict JSON schemas improve structure but do not guarantee correct evidence interpretation.
2. Judge extraction, assertions, acceptance, and final workflow state separately.
3. Ledger descriptions are claims to test; they cannot substitute for missing invoice detail.
4. A conservative unresolved result can be correct even when a fixture was intended to be clean.
5. Cache live evaluations and rerun affected cases deliberately to conserve free API quota.
6. Keep local calculation checks distinct from hosted end-to-end acceptance and human review.
