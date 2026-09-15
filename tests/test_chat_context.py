import json
from types import SimpleNamespace

from auditor.chat_context import build_context


def test_large_context_keeps_valid_json_problem_documents_and_reports_omissions():
    engagement = SimpleNamespace(name="Example", period_end="2025-12-31", profile={})
    revision = SimpleNamespace(
        stage="mapping",
        status="stale",
        stale_reason="Account correction",
        payload={
            "accounts": [
                {
                    "number": str(i),
                    "name": "Expense account",
                    "balance": "1000.00",
                    "fsli": "Operating Expenses",
                }
                for i in range(1000)
            ]
        },
    )
    document = SimpleNamespace(
        id="doc-1",
        filename="wrong-entity.pdf",
        kind="invoice",
        status="returned",
        findings=[{"code": "wrong_entity", "message": "Different company", "severity": "blocking"}],
    )
    encoded = build_context(engagement, [revision], [document], max_chars=4000)
    state = json.loads(encoded)
    assert len(encoded) <= 4000
    assert state["documents"][0]["filename"] == "wrong-entity.pdf"
    assert state["stages"]["mapping"]["status"] == "stale"
    remaining = len(state["stages"]["mapping"]["accounts"])
    assert state["omitted_records"]["mapping.accounts"] + remaining == 1000


def test_attention_summary_distinguishes_returned_evidence_from_accepted_exceptions():
    engagement = SimpleNamespace(name="Example", period_end="2025-12-31", profile={})
    cases = [
        ("M-103", "accepted", "exception", "period"),
        ("L-201", "accepted", "exception", "accuracy"),
        ("L-202", "returned", "unresolved", "validity"),
        ("R-301", "accepted", "exception", "classification"),
        ("R-302", "returned", "exception", "validity"),
        ("R-303", "accepted", "clean", None),
    ]
    documents = [
        SimpleNamespace(
            id=ref,
            filename=f"invoice-{ref}.pdf",
            kind="invoice",
            status=review,
            findings=[],
        )
        for ref, review, _, _ in cases
    ]
    revision = SimpleNamespace(
        stage="testing",
        status="draft",
        stale_reason=None,
        payload={
            "results": [
                {
                    "transaction": {"id": ref, "ref": ref},
                    "document_id": ref,
                    "status": status,
                    "document_accepted": review == "accepted",
                    "checks": {check: {"status": status}} if check else {},
                }
                for ref, review, status, check in cases
            ],
        },
    )
    context = json.loads(build_context(engagement, [revision], documents, max_chars=2600))
    attention = context["attention"]
    assert context["omitted_records"]  # Detailed rows were pruned; the summary must survive.
    assert attention["complete"]
    assert attention["returned_document_count"] == 2
    assert {d["filename"] for d in attention["documents_requiring_review"]} == {
        "invoice-L-202.pdf",
        "invoice-R-302.pdf",
    }
    rows = {r["reference"]: r for r in attention["transactions_requiring_follow_up"]}
    assert set(rows) == {"M-103", "L-201", "L-202", "R-301", "R-302"}
    assert rows["R-301"]["document_accepted"] is True
    assert rows["M-103"]["checks_needing_attention"] == {"period": "exception"}
