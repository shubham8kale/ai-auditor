"""Compact evidence context without dropping identities or cutting JSON mid-record."""

import json


def pick(row, keys):
    return {key: row[key] for key in keys if key in row}


def build_context(engagement, revisions, documents, max_chars=10000):
    documents_by_id = {doc.id: doc for doc in documents}
    testing = next((r for r in revisions if r.stage == "testing"), None)
    context = {
        "name": engagement.name,
        "period_end": engagement.period_end,
        "profile": engagement.profile,
        "attention": {
            "complete": True,
            "returned_document_count": sum(doc.status == "returned" for doc in documents),
            "documents_requiring_review": [
                {"filename": doc.filename, "status": doc.status, "findings": doc.findings}
                for doc in documents
                if doc.status != "accepted"
            ],
            "testing_revision_status": testing.status if testing else None,
            "transactions_requiring_follow_up": [
                {
                    "reference": result["transaction"]["ref"],
                    "filename": documents_by_id[result["document_id"]].filename
                    if result.get("document_id") in documents_by_id
                    else None,
                    "document_accepted": result.get("document_accepted", False),
                    "status": result["status"],
                    "checks_needing_attention": {
                        key: check["status"]
                        for key, check in result.get("checks", {}).items()
                        if check.get("status") != "pass"
                    },
                    "known_error": result.get("known_error"),
                    "disposition": result.get("disposition"),
                }
                for result in (testing.payload.get("results", []) if testing else [])
                if result["status"] != "clean" or not result.get("document_accepted")
            ],
        },
        "documents": [
            {
                "id": doc.id,
                "filename": doc.filename,
                "kind": doc.kind,
                "status": doc.status,
                "findings": doc.findings,
            }
            for doc in sorted(documents, key=lambda d: d.status == "accepted")
        ],
        "stages": {},
        "omitted_records": {},
    }
    for revision in revisions:
        payload = revision.payload
        stage = {
            "status": revision.status,
            "stale_reason": revision.stale_reason,
            **pick(
                payload,
                (
                    "findings",
                    "sources",
                    "benchmark",
                    "benchmark_value",
                    "materiality",
                    "pm",
                    "ctt",
                    "rate",
                    "pm_rate",
                    "engagement_risk",
                    "exception_count",
                    "unresolved_count",
                    "known_absolute_error",
                    "population_value",
                    "total_opex",
                ),
            ),
        }
        for key, fields in {
            "accounts": ("number", "name", "fsli", "risk", "balance", "scope_reason", "source"),
            "selections": ("id", "ref", "account_number", "amount", "document_id"),
            "requests": ("id", "title", "status", "why", "source"),
        }.items():
            stage[key] = [pick(row, fields) for row in payload.get(key, [])]
        stage["results"] = [
            {
                **pick(
                    result,
                    (
                        "document_id",
                        "status",
                        "document_accepted",
                        "acceptance_findings",
                        "known_error",
                        "disposition",
                        "disposition_note",
                    ),
                ),
                "transaction": pick(result["transaction"], ("id", "ref", "amount", "account_number")),
                "checks": {
                    key: pick(
                        check,
                        ("status",) if check.get("status") == "pass" else ("status", "reason", "sources"),
                    )
                    for key, check in result.get("checks", {}).items()
                },
            }
            for result in sorted(payload.get("results", []), key=lambda r: r["status"] == "clean")
        ]
        context["stages"][revision.stage] = stage

    # Discard whole records, least relevant collections first. Explicit counts
    # prevent the model from presenting a bounded context as a complete inventory.
    collections = [
        (f"{stage}.{key}", value[key])
        for key in ("accounts", "selections", "requests", "results")
        for stage, value in context["stages"].items()
    ] + [("documents", context["documents"])]
    encoded = json.dumps(context, default=str)
    for name, rows in collections:
        while len(encoded) > max_chars and rows:
            rows.pop()
            context["omitted_records"][name] = context["omitted_records"].get(name, 0) + 1
            encoded = json.dumps(context, default=str)
    if len(encoded) > max_chars:
        raise ValueError("This engagement's chat summary is too large. Use the stage review controls.")
    return encoded
