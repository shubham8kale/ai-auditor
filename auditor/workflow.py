"""Stage preparation and explicit dependency invalidation. Approval is implemented only in the API."""

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select

from auditor.ai import AIUnavailable, ask_json
from auditor.db import AuditEvent, Document, Engagement, Revision
from auditor.documents import validate_document
from auditor.domain import (
    FSLIS,
    aggregate_accounts,
    amount,
    finding,
    map_by_examples,
    materiality,
    money,
    policy_scope,
    reconcile,
    select_sample,
)
from auditor.requests import request_list
from auditor.vouching import vouch

STAGES = ["onboarding", "mapping", "planning", "sampling", "testing"]


class WorkflowError(ValueError):
    pass


def revisions(db, engagement_id):
    return list(
        db.scalars(
            select(Revision)
            .where(Revision.engagement_id == engagement_id)
            .order_by(Revision.created_at.desc())
        )
    )


def latest(db, engagement_id, stage):
    return db.scalars(
        select(Revision)
        .where(Revision.engagement_id == engagement_id, Revision.stage == stage)
        .order_by(Revision.created_at.desc())
    ).first()


def require_approved(db, engagement_id, stage):
    revision = latest(db, engagement_id, stage)
    if not revision or revision.status != "approved":
        raise WorkflowError(f"Review and approve {stage} before relying on it for the next stage.")
    return revision


def event(db, engagement_id, actor, action, detail):
    db.add(AuditEvent(engagement_id=engagement_id, actor=actor, action=action, detail=detail))


def invalidate(db, engagement, from_stage, reason):
    engagement.version += 1
    affected = STAGES[STAGES.index(from_stage) :]
    for revision in revisions(db, engagement.id):
        if revision.stage in affected and revision.status != "stale":
            revision.status = "stale"
            revision.stale_reason = reason
    return affected


def active_documents(db, engagement_id):
    return list(
        db.scalars(
            select(Document).where(Document.engagement_id == engagement_id).order_by(Document.created_at)
        )
    )


def parsed_documents(documents, kind):
    return [
        doc
        for doc in documents
        if doc.kind == kind and doc.status not in {"uploaded", "processing", "error", "superseded"}
    ]


def document_findings(documents, kind):
    result = []
    for doc in parsed_documents(documents, kind):
        result += [{**f, "document_id": doc.id} for f in doc.findings]
        if doc.status != "accepted":
            result.append(
                finding("document_not_reviewed", f"{doc.filename} has not been accepted by the auditor.")
            )
    return result


async def prepare(db, engagement: Engagement, stage: str):
    if stage not in STAGES:
        raise WorkflowError("Unknown stage")
    documents = active_documents(db, engagement.id)
    profile = dict(engagement.profile)
    overrides = engagement.overrides
    if stage == "onboarding":
        letters = parsed_documents(documents, "engagement_letter")
        if not letters:
            raise WorkflowError("Upload and process the engagement letter first.")
        if len(letters) > 1:
            raise WorkflowError(
                "More than one active engagement letter exists. Mark superseded copies before preparing onboarding."
            )
        facts = letters[0].extracted.get("facts", {})
        profile = {
            key: facts.get(key)
            for key in [
                "service",
                "framework",
                "issuer",
                "first_year",
                "stage",
                "industries",
                "related_parties",
                "prior_benchmark",
            ]
        }
        profile["stage"] = profile.get("stage") or "growth"
        profile["industries"] = profile.get("industries") or []
        profile["related_parties"] = profile.get("related_parties") or []
        profile.update(overrides.get("profile", {}))
        engagement.profile = profile
        policy = policy_scope(profile)
        accounts = [
            r for d in parsed_documents(documents, "trial_balance") for r in d.extracted.get("accounts", [])
        ]
        for row in accounts:
            row["fsli"] = map_by_examples(row["name"])[0]
        findings = list(policy["findings"]) + document_findings(documents, "engagement_letter")
        if profile.get("first_year") is None:
            findings.append(
                finding(
                    "history_missing", "The letter does not establish first-year versus recurring status."
                )
            )
        if not profile["industries"] or "other" in profile["industries"]:
            findings.append(
                finding(
                    "industry_policy_missing",
                    "The supplied policy pack does not establish this industry's requirements. Obtain the applicable profile.",
                )
            )
        return {
            "profile": profile,
            "policy": policy,
            "requests": request_list(accounts, profile, policy, documents),
            "findings": findings,
            "sources": [{"document_id": letters[0].id, "page": 1}],
            "review_scope": "Approve the client profile and request plan. Open PBC requests remain open; this does not accept missing evidence.",
        }
    require_approved(db, engagement.id, STAGES[STAGES.index(stage) - 1])
    if stage == "mapping":
        tbs = parsed_documents(documents, "trial_balance")
        if len(tbs) != 1:
            raise WorkflowError(
                "Exactly one active current-year trial balance is needed. Supersede old copies rather than combining them."
            )
        tb = tbs[0]
        examples = [
            r for d in parsed_documents(documents, "mapping_library") for r in d.extracted.get("mappings", [])
        ]
        accounts = []
        for original in tb.extracted.get("accounts", []):
            row = dict(original)
            fsli, reason, method = map_by_examples(row["name"], examples)
            if row["number"] in overrides.get("mappings", {}):
                fsli = overrides["mappings"][row["number"]]
                reason, method = (
                    overrides.get("mapping_reasons", {}).get(row["number"], "Auditor correction"),
                    "reviewer",
                )
            accounts.append({**row, "fsli": fsli, "reason": reason, "method": method})
        unknown = [row for row in accounts if not row["fsli"]]
        ai_runs = []
        ai_unavailable = False
        if unknown:
            import json

            try:
                proposals, run = await ask_json(
                    "Suggest mappings to these allowed FSLIs: "
                    + json.dumps(FSLIS)
                    + '. Return {"mappings":[{"number":"...","fsli":null,"reason":"..."}]}. '
                    "Use null if the business nature is genuinely ambiguous. Do not invent account numbers. "
                    + json.dumps(
                        {
                            "accounts": [{"number": r["number"], "name": r["name"]} for r in unknown],
                            "examples": [
                                {"account_name": r["account_name"], "fsli": r["fsli"]} for r in examples[:65]
                            ],
                            "profile": {k: profile.get(k) for k in ("industries", "framework", "service")},
                        }
                    ),
                    max_tokens=min(1600, max(600, len(unknown) * 160)),
                )
                ai_runs.append(run)
            except AIUnavailable:
                # Save available deterministic preparation; human mapping remains possible without AI.
                proposals = {}
                ai_unavailable = True
            by_number = {p.get("number"): p for p in proposals.get("mappings", []) if isinstance(p, dict)}
            for row in unknown:
                proposal = by_number.get(row["number"], {})
                if proposal.get("fsli") in FSLIS:
                    row.update(
                        fsli=proposal["fsli"],
                        reason=str(proposal.get("reason", "AI mapping proposal")),
                        method="AI proposal",
                    )
        findings = document_findings(documents, "trial_balance")
        if ai_unavailable:
            findings.append(
                finding(
                    "mapping_ai_unavailable",
                    "AI mapping was unavailable. Completed library/rule mappings are retained; resolve the remaining accounts manually or prepare again when AI is available.",
                    "warning",
                )
            )
        if any(not row["fsli"] for row in accounts):
            findings.append(
                finding(
                    "unmapped",
                    "Resolve the remaining mapping judgments before approving the mapped trial balance.",
                )
            )
        if not accounts:
            findings.append(finding("empty_tb", "No account rows were extracted."))
        return {
            "accounts": accounts,
            "totals": aggregate_accounts(accounts),
            "findings": findings,
            "ai_runs": ai_runs,
            "net_balance": amount(sum((money(r["balance"]) for r in accounts), Decimal(0))),
            "requests": request_list(accounts, profile, policy_scope(profile), documents),
            "source_document_id": tb.id,
            "sources": ["POL-103 §3; prior mapping library"],
        }
    mapping = require_approved(db, engagement.id, "mapping")
    if stage == "planning":
        return materiality(mapping.payload["accounts"], profile, overrides)
    planning = require_approved(db, engagement.id, "planning")
    if stage == "sampling":
        ledgers = parsed_documents(documents, "general_ledger")
        if not ledgers:
            raise WorkflowError("Upload and process the expense general ledger first.")
        transactions = [r for d in ledgers for r in d.extracted.get("transactions", [])]
        accounts = planning.payload["accounts"]
        expense_accounts = {
            a["number"]: a for a in accounts if a["fsli"] == "Operating Expenses" and a["in_scope"]
        }
        population = [r for r in transactions if r["account_number"] in expense_accounts]
        findings = document_findings(documents, "general_ledger")
        rec = reconcile(population, accounts)
        if any(not row["ties"] for row in rec):
            findings.append(
                finding(
                    "gl_reconciliation",
                    "One or more GL account totals do not agree to the reviewed TB.",
                    source="POL-104 §2",
                )
            )
        if not population:
            findings.append(
                finding("empty_population", "No transactions match in-scope operating expense accounts.")
            )
        fingerprints = [
            (r["account_number"], r["date"], r["ref"], r["amount"], r["counterparty"]) for r in population
        ]
        if len(fingerprints) != len(set(fingerprints)):
            findings.append(
                finding(
                    "duplicate_transactions",
                    "Possible repeated transactions across uploaded ledgers. Resolve duplicate source records before selection.",
                )
            )
        from datetime import date, timedelta

        end = date.fromisoformat(engagement.period_end)
        try:
            previous_end = end.replace(year=end.year - 1)
        except ValueError:
            previous_end = end.replace(year=end.year - 1, day=28)
        start = (previous_end + timedelta(days=1)).isoformat()
        if any(not start <= row["date"] <= engagement.period_end for row in population):
            findings.append(
                finding("population_period", "The population includes dates outside the fiscal year.")
            )
        groups = defaultdict(list)
        for row in population:
            if start <= row["date"] <= engagement.period_end:
                groups[expense_accounts[row["account_number"]]["risk"]].append(row)
        samples = [
            select_sample(
                rows,
                planning.payload["pm"],
                risk,
                planning.payload["policy"]["round_threshold"],
                engagement.period_end,
                profile.get("related_parties"),
            )
            for risk, rows in groups.items()
        ]
        supplied_numbers = {r["account_number"] for r in population}
        missing = [a for k, a in expense_accounts.items() if k not in supplied_numbers]
        if missing:
            findings.append(
                finding(
                    "partial_opex_coverage",
                    "This test covers only the reconciled provided accounts. Additional in-scope accounts still need ledger detail.",
                    "warning",
                    "POL-101 §2; POL-104 §2",
                )
            )
        return {
            "groups": samples,
            "selections": [s for group in samples for s in group["selections"]],
            "reconciliation": rec,
            "missing_accounts": missing,
            "findings": findings,
            "population_value": amount(sum((money(r["amount"]) for r in population), Decimal(0))),
            "total_opex": planning.payload["totals"].get("Operating Expenses", "0.00"),
            "sources": ["POL-101 p.2 §4", "REF-7 p.1 Appendix C", "POL-104 §2"],
            "review_scope": "Approve only the listed, reconciled accounts and their sample. Missing account detail remains outstanding.",
        }
    sample = require_approved(db, engagement.id, "sampling")
    invoices = parsed_documents(documents, "invoice")
    results = []
    for selection in sample.payload["selections"]:
        # Match by explicit reference; a model is not allowed to silently pick a vaguely similar invoice.
        explicit = overrides.get("invoice_links", {}).get(selection["id"])
        candidates = (
            [d for d in invoices if d.id == explicit]
            if explicit
            else [
                d
                for d in invoices
                if d.extracted.get("facts", {}).get("reference") == selection["ref"] and selection["ref"]
            ]
        )
        if len(candidates) > 1:
            result = await vouch(selection, None, engagement, profile)
            result["match_issue"] = (
                "Multiple invoices share this reference. Link the correct source explicitly."
            )
        else:
            result = await vouch(selection, candidates[0] if candidates else None, engagement, profile)
        result["disposition_note"] = overrides.get("dispositions", {}).get(selection["id"])
        results.append(result)
    exceptions = [r for r in results if r["status"] == "exception"]
    unresolved = [
        r
        for r in results
        if r["status"] in {"unresolved", "missing_evidence"}
        or any(check["status"] == "unresolved" for check in r["checks"].values())
        or (r.get("document_id") and not r.get("document_accepted"))
    ]
    known = sum((money(r["known_error"]) for r in results if r["known_error"] is not None), Decimal(0))
    findings = []
    if unresolved:
        findings.append(
            finding(
                "unresolved_evidence",
                f"{len(unresolved)} selections still have unresolved evidence or assertions.",
            )
        )
    for result in exceptions:
        if not result.get("disposition_note"):
            findings.append(
                finding(
                    "exception_follow_up",
                    f"Selection {result['transaction']['ref']} requires a documented human disposition and client follow-up.",
                )
            )
    conclusion = (
        f"{len(exceptions)} selections with exceptions; {len(unresolved)} unresolved selections. "
        f"Known net amount difference: {amount(known)}. Materiality {planning.payload['materiality']}; PM {planning.payload['pm']}. "
        "Judgmental selections do not establish statistical projection. Conclusion is limited to the listed tested accounts. "
    )
    conclusion += (
        "Client follow-up is pending."
        if findings
        else "Prepared for auditor review; the auditor determines the final conclusion."
    )
    return {
        "results": results,
        "exception_count": len(exceptions),
        "unresolved_count": len(unresolved),
        "known_net_error": amount(known),
        "known_absolute_error": amount(
            sum((abs(money(r["known_error"])) for r in results if r["known_error"] is not None), Decimal(0))
        ),
        "materiality": planning.payload["materiality"],
        "pm": planning.payload["pm"],
        "ctt": planning.payload["ctt"],
        "conclusion": conclusion,
        "findings": findings,
        "sources": ["POL-101 §4.4", "POL-104 §§1–5"],
        "scope": sample.payload["reconciliation"],
    }


def revalidate_documents(db, engagement):
    for document in active_documents(db, engagement.id):
        if document.extracted:
            document.findings = validate_document(
                document.extracted,
                engagement.name,
                engagement.period_end,
                engagement.overrides.get("aliases", []),
                engagement.profile,
            )
            if document.status == "accepted" and any(f["severity"] == "blocking" for f in document.findings):
                document.status = "needs_attention"
                document.reviewed_at = None
                document.reviewed_by = None
