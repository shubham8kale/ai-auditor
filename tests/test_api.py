import json
from datetime import timedelta

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auditor import main
from auditor.auth import User, current_user
from auditor.db import Document, Job, Portal, Revision, get_db, now


@pytest.fixture
def api(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", sessions)
    dispatched = []
    monkeypatch.setattr(main, "dispatch", dispatched.append)

    async def reviewer(request: Request):
        identity = request.headers.get("X-Test-User")
        if not identity:
            raise HTTPException(401, "Sign in")
        return User(identity, "Reviewer " + identity)

    def database():
        with sessions() as session:
            yield session

    async def store(*_args):
        pass

    main.app.dependency_overrides[current_user] = reviewer
    main.app.dependency_overrides[get_db] = database
    monkeypatch.setattr(main, "save_file", store)
    with TestClient(main.app) as client:
        yield client, sessions, dispatched
    main.app.dependency_overrides.clear()


def create(client, owner="a"):
    response = client.post(
        "/api/engagements",
        headers={"X-Test-User": owner},
        json={"name": "Example Trading Ltd", "period_end": "2025-12-31"},
    )
    assert response.status_code == 201
    return response.json()


def test_health_and_public_config_never_expose_server_credentials(api):
    client, _, _ = api
    assert client.get("/health").json() == {"status": "ok"}
    config = client.get("/api/config")
    assert set(config.json()) == {
        "supabase_url",
        "publishable_key",
        "local_auth",
        "ai_configured",
        "max_upload_mb",
    }
    assert config.headers["cache-control"] == "no-store"
    assert client.get("/api/engagements").status_code == 401


def test_security_headers_and_private_paths(api):
    client, _, _ = api
    response = client.get("/api/config")
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    for path in ("/.env", "/.git/config", "/docs", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_ownership_filters_lists_and_rejects_cross_engagement_documents(api):
    client, sessions, _ = api
    one, two = create(client, "a"), create(client, "b")
    assert [e["id"] for e in client.get("/api/engagements", headers={"X-Test-User": "b"}).json()] == [
        two["id"]
    ]
    assert client.get(f"/api/engagements/{one['id']}", headers={"X-Test-User": "b"}).status_code == 404
    with sessions() as db:
        doc = Document(
            engagement_id=one["id"],
            filename="private.csv",
            content_type="text/csv",
            storage_key="private",
            sha256="a" * 64,
            size=5,
        )
        db.add(doc)
        db.commit()
        document_id = doc.id
    assert (
        client.get(
            f"/api/engagements/{two['id']}/documents/{document_id}", headers={"X-Test-User": "b"}
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/engagements/{one['id']}/documents/{document_id}/source", headers={"X-Test-User": "b"}
        ).status_code
        == 404
    )


def test_upload_preserves_original_and_records_job_without_accepting_it(api):
    client, sessions, dispatched = api
    engagement = create(client)
    url = f"/api/engagements/{engagement['id']}/documents"
    payload = b"account number,account name,balance\n100,Checking,100\n300,Equity,-100\n"
    response = client.post(
        url, headers={"X-Test-User": "a"}, files={"file": ("../../evidence.csv", payload, "text/csv")}
    )
    assert response.status_code == 202
    assert dispatched == [response.json()["job_id"]]
    with sessions() as db:
        doc = db.get(Document, response.json()["document_id"])
        assert doc.filename == "evidence.csv"
        assert doc.status == "uploaded"
        assert doc.reviewed_by is None
        assert ".." not in doc.storage_key
    assert (
        client.post(
            url, headers={"X-Test-User": "a"}, files={"file": ("again.csv", payload, "text/csv")}
        ).status_code
        == 409
    )


def test_latest_draft_approval_requires_resolved_findings_and_prerequisites(api):
    client, sessions, _ = api
    engagement = create(client)
    base = f"/api/engagements/{engagement['id']}"
    with sessions() as db:
        blocked = Revision(
            engagement_id=engagement["id"],
            stage="onboarding",
            input_version=1,
            payload={"findings": [{"severity": "blocking", "message": "Missing framework"}]},
        )
        planning = Revision(
            engagement_id=engagement["id"], stage="planning", input_version=1, payload={"findings": []}
        )
        db.add_all([blocked, planning])
        db.commit()
        blocked_id, planning_id = blocked.id, planning.id
    assert (
        client.post(
            base + f"/revisions/{blocked_id}/approve", headers={"X-Test-User": "a"}, json={"version": 1}
        ).status_code
        == 409
    )
    assert (
        client.post(
            base + f"/revisions/{planning_id}/approve", headers={"X-Test-User": "a"}, json={"version": 1}
        ).status_code
        == 409
    )


def test_approval_records_identity_and_rejects_old_screen_version(api):
    client, sessions, _ = api
    engagement = create(client)
    base = f"/api/engagements/{engagement['id']}"
    with sessions() as db:
        draft = Revision(
            engagement_id=engagement["id"], stage="onboarding", input_version=1, payload={"findings": []}
        )
        db.add(draft)
        db.commit()
        identifier = draft.id
    approved = client.post(
        base + f"/revisions/{identifier}/approve", headers={"X-Test-User": "a"}, json={"version": 1}
    )
    assert approved.status_code == 200
    assert approved.json()["approved_by"] == "Reviewer a"
    assert approved.json()["approved_at"]
    stale = client.post(
        base + "/corrections",
        headers={"X-Test-User": "a"},
        json={
            "version": 1,
            "operation": {"type": "risk", "risk": "high", "reason": "New control deficiencies identified"},
        },
    )
    assert stale.status_code == 409


def test_pending_processing_prevents_approval(api):
    client, sessions, _ = api
    engagement = create(client)
    with sessions() as db:
        draft = Revision(
            engagement_id=engagement["id"], stage="onboarding", input_version=1, payload={"findings": []}
        )
        db.add_all([draft, Job(engagement_id=engagement["id"], stage="document")])
        db.commit()
        identifier = draft.id
    response = client.post(
        f"/api/engagements/{engagement['id']}/revisions/{identifier}/approve",
        headers={"X-Test-User": "a"},
        json={"version": 1},
    )
    assert response.status_code == 409


def test_portal_exposes_requests_only_and_expiry_is_enforced(api):
    client, sessions, _ = api
    engagement = create(client)
    result = client.post(
        f"/api/engagements/{engagement['id']}/portal", headers={"X-Test-User": "a"}, json={"version": 1}
    )
    token = result.json()["token"]
    portal = client.get("/api/portal", headers={"X-Portal-Token": token})
    assert portal.status_code == 200
    assert set(portal.json()) == {"name", "period_end", "requests", "max_upload_mb"}
    assert (
        client.get(f"/api/engagements/{engagement['id']}", headers={"X-Portal-Token": token}).status_code
        == 401
    )
    with sessions() as db:
        record = db.scalar(select(Portal))
        assert record.token_hash != token
        record.expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/portal", headers={"X-Portal-Token": token}).status_code == 404


def test_unsupported_extraction_can_be_cleared_without_changing_original_page(api):
    client, sessions, _ = api
    engagement = create(client)
    original = {"page": 1, "text": "We audited the year ended December 31, 2024."}
    with sessions() as db:
        doc = Document(
            engagement_id=engagement["id"],
            filename="letter.pdf",
            content_type="application/pdf",
            storage_key="original-unchanged",
            sha256="b" * 64,
            size=100,
            kind="engagement_letter",
            status="ready",
            findings=[],
            extracted={
                "kind": "engagement_letter",
                "pages": [original],
                "facts": {
                    "document_type": "engagement_letter",
                    "entity": "Example Trading Ltd",
                    "period_end": "2025-12-31",
                    "framework": "US GAAP",
                    "prior_benchmark": "2024-12-31",
                },
            },
        )
        db.add(doc)
        db.commit()
        identifier = doc.id
    response = client.post(
        f"/api/engagements/{engagement['id']}/documents/{identifier}/facts",
        headers={"X-Test-User": "a"},
        json={
            "version": 1,
            "changes": {"prior_benchmark": None},
            "reason": "The date establishes audit history, not a materiality benchmark",
            "source_reference": "Page 1: prior audit date only",
        },
    )
    assert response.status_code == 200
    assert response.json()["extracted"]["facts"]["prior_benchmark"] is None
    assert response.json()["extracted"]["pages"] == [original]
    assert response.json()["reviewed_by"] is None


def test_pdf_export_marks_unapproved_revision_and_contains_sources(api):
    import io

    from pypdf import PdfReader

    client, sessions, _ = api
    engagement = create(client)
    with sessions() as db:
        revision = Revision(
            engagement_id=engagement["id"],
            stage="planning",
            input_version=1,
            payload={"findings": [], "sources": ["POL-101 section 1"]},
        )
        db.add(revision)
        db.commit()
        identifier = revision.id
    result = client.get(
        f"/api/engagements/{engagement['id']}/revisions/{identifier}/pdf", headers={"X-Test-User": "a"}
    )
    assert result.status_code == 200
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(result.content)).pages)
    assert "DRAFT" in text
    assert "not approved for downstream reliance" in text
    assert "POL-101 section 1" in text


@pytest.mark.parametrize("oversize", [False, True])
def test_chat_retains_problem_document_identity_in_large_workspace(api, monkeypatch, oversize):
    client, sessions, _ = api
    engagement = create(client)
    other = create(client, owner="b")
    with sessions() as db:
        for eid, filename in [(engagement["id"], "vague-invoice.pdf"), (other["id"], "private-other.pdf")]:
            db.add(
                Document(
                    id=eid + "-doc",
                    engagement_id=eid,
                    filename=filename,
                    content_type="application/pdf",
                    storage_key="private",
                    sha256="a" * 64,
                    size=10,
                    kind="invoice",
                    status="returned",
                    findings=[
                        {"code": "vague_services", "severity": "blocking", "message": "Missing detail"}
                    ],
                )
            )
        db.add(
            Revision(
                engagement_id=engagement["id"],
                stage="testing",
                input_version=1,
                payload={
                    "unused_large_transcription": "Original source text " * 1500,
                    "results": [
                        {
                            "transaction": {"id": "selection-1", "ref": "L-202", "amount": "7600.00"},
                            "document_id": engagement["id"] + "-doc",
                            "status": "unresolved",
                            "document_accepted": False,
                            "checks": {
                                "validity": {"status": "unresolved", "reason": "Missing service detail"}
                            },
                        }
                    ],
                },
            )
        )
        db.commit()

    calls = []

    async def answer(prompt, **kwargs):
        calls.append(prompt)
        if oversize and len(calls) == 1:
            raise main.AIRequestTooLarge("Request too large")
        snapshot = prompt.split("\nSTATE:\n", 1)[1].split("\nUSER MESSAGE:\n", 1)[0]
        state = json.loads(snapshot)
        assert len(snapshot) <= (4500 if oversize else 10000)
        assert "private-other.pdf" not in snapshot
        assert "Original source text" not in snapshot
        document = state["documents"][0]
        result = state["stages"]["testing"]["results"][0]
        assert document["filename"] == "vague-invoice.pdf"
        assert document["status"] == "returned"
        assert state["attention"]["returned_document_count"] == 1
        assert state["attention"]["transactions_requiring_follow_up"][0]["reference"] == "L-202"
        assert result["document_id"] == document["id"]
        assert result["transaction"]["ref"] == "L-202"
        assert result["checks"]["validity"]["status"] == "unresolved"
        return {"answer": "L-202: vague-invoice.pdf requires service detail.", "operation": None}, {}

    monkeypatch.setattr(main, "ask_json", answer)
    response = client.post(
        f"/api/engagements/{engagement['id']}/chat",
        headers={"X-Test-User": "a"},
        json={"version": 1, "message": "Which documents need attention?"},
    )
    assert response.status_code == 200
    assert len(calls) == (2 if oversize else 1)
