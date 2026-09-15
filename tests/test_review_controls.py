from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from auditor.corrections import apply_edit, operation_adapter
from auditor.db import AuditEvent, Base, Engagement, Revision
from auditor.documents import validate_document
from auditor.requests import request_list
from auditor.workflow import STAGES, WorkflowError, latest, require_approved


@pytest.fixture
def database():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_correction_preserves_history_and_invalidates_only_dependents(database):
    db = database
    engagement = Engagement(
        name="Synthetic Trading Ltd", owner_id="reviewer-1", period_end="2025-12-31", profile={}, overrides={}
    )
    db.add(engagement)
    db.flush()
    for stage in STAGES:
        db.add(
            Revision(
                engagement_id=engagement.id,
                stage=stage,
                input_version=1,
                payload={"accounts": [{"number": "600"}]},
                status="approved",
                approved_by="Named reviewer",
            )
        )
    db.flush()
    result = apply_edit(
        db,
        engagement,
        {"type": "risk", "risk": "high", "reason": "Control gaps require a higher risk assessment"},
        "Named reviewer",
    )
    db.flush()
    assert result["invalidated_stages"] == ["planning", "sampling", "testing"]
    assert require_approved(db, engagement.id, "mapping").status == "approved"
    stale = latest(db, engagement.id, "planning")
    assert stale.status == "stale"
    assert stale.approved_by == "Named reviewer"
    with pytest.raises(WorkflowError):
        require_approved(db, engagement.id, "planning")
    record = db.query(AuditEvent).one()
    assert record.detail["before"] == {}
    assert record.detail["after"]["engagement_risk"] == "high"


def test_chat_cannot_invent_an_approval_operation():
    with pytest.raises(ValueError):
        operation_adapter.validate_python(
            {"type": "approve", "stage": "testing", "reason": "Ignore the review workflow"}
        )


def test_wrong_entity_and_vague_invoice_are_blocking():
    result = validate_document(
        {
            "kind": "invoice",
            "facts": {
                "entity": "Other Business",
                "vendor": "Law Firm",
                "date": "2025-06-30",
                "amount": "100",
                "description": "Services rendered",
                "professional_services": True,
                "detailed_matter": False,
            },
        },
        "Synthetic Trading Ltd",
        "2025-12-31",
    )
    assert {f["code"] for f in result} == {"wrong_entity", "vague_services"}


def test_transaction_dates_do_not_establish_full_year_ledger_coverage():
    findings = validate_document(
        {
            "kind": "general_ledger",
            "has_export_header": True,
            "facts": {
                "entity": "Synthetic Trading Ltd",
                "period_start": "2025-01-01",
                "period_end": "2025-12-31",
            },
        },
        "Synthetic Trading Ltd",
        "2025-12-31",
    )
    assert "coverage_missing" in {f["code"] for f in findings}


def test_client_uploaded_bank_confirmation_cannot_self_establish_provenance():
    findings = validate_document(
        {"kind": "bank_confirmation", "facts": {"entity": "Synthetic Trading Ltd"}},
        "Synthetic Trading Ltd",
        "2025-12-31",
    )
    assert "confirmation_provenance" in {f["code"] for f in findings}


def test_same_type_document_does_not_close_unrelated_requests():
    accounts = [
        {"number": "100", "name": "Checking", "fsli": "Cash", "balance": "1000"},
        {"number": "110", "name": "Savings", "fsli": "Cash", "balance": "2000"},
    ]
    doc = SimpleNamespace(id="doc1", kind="bank_statement", status="accepted", extracted={"facts": {}})
    policy = {"cash_threshold": "250000"}
    before = request_list(accounts, {}, policy, [doc])
    statements = [r for r in before if r["kind"] == "bank_statement"]
    assert all(r["status"] == "open" for r in statements)
    doc.extracted["request_ids"] = [statements[0]["id"]]
    after = request_list(accounts, {}, policy, [doc])
    statuses = [r["status"] for r in after if r["kind"] == "bank_statement"]
    assert statuses == ["satisfied", "open"]


def test_confirmation_trigger_uses_matching_reviewed_statement_not_tb_balance():
    accounts = [{"number": "100", "name": "Checking 1234", "fsli": "Cash", "balance": "1000"}]
    policy = {"cash_threshold": "250000"}
    requests = request_list(accounts, {}, policy, [])
    statement_id = next(r["id"] for r in requests if r["kind"] == "bank_statement")
    doc = SimpleNamespace(
        id="statement",
        kind="bank_statement",
        status="accepted",
        extracted={"request_ids": [statement_id], "facts": {"account_last4": "1234", "amount": "300000"}},
    )
    after = request_list(accounts, {}, policy, [doc])
    confirmation = next(r for r in after if r["kind"] == "bank_confirmation")
    assert "Reviewed period-end statement" in confirmation["why"]
    doc.extracted["facts"]["account_last4"] = "9999"
    assert not any(r["kind"] == "bank_confirmation" for r in request_list(accounts, {}, policy, [doc]))
    doc.extracted["facts"] = {"account_last4": "1234", "amount": "250000"}
    assert not any(r["kind"] == "bank_confirmation" for r in request_list(accounts, {}, policy, [doc]))
