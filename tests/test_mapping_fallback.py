import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from auditor import workflow
from auditor.ai import AIUnavailable
from auditor.db import Base, Document, Engagement, Revision


def test_ai_outage_preserves_mapped_rows_and_blocks_unresolved_approval(monkeypatch):
    async def unavailable(*_args, **_kwargs):
        raise AIUnavailable("Free quota unavailable")

    monkeypatch.setattr(workflow, "ask_json", unavailable)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        e = Engagement(
            name="Fictional Client", owner_id="test", period_end="2025-12-31", profile={}, overrides={}
        )
        db.add(e)
        db.flush()
        db.add(
            Revision(engagement_id=e.id, stage="onboarding", input_version=1, payload={}, status="approved")
        )
        rows = [
            {"number": "100", "name": "Checking", "balance": "100.00", "source": "TB!A2"},
            {"number": "200", "name": "Project allocation", "balance": "-100.00", "source": "TB!A3"},
        ]
        db.add(
            Document(
                engagement_id=e.id,
                filename="fictional.csv",
                content_type="text/csv",
                storage_key="test",
                sha256="a" * 64,
                size=100,
                status="accepted",
                kind="trial_balance",
                findings=[],
                extracted={"accounts": rows},
            )
        )
        db.commit()
        result = asyncio.run(workflow.prepare(db, e, "mapping"))
        assert result["accounts"][0]["fsli"] == "Cash"
        assert result["accounts"][0]["source"] == "TB!A2"
        assert result["accounts"][1]["fsli"] is None
        assert result["net_balance"] == "0.00"
        assert any(f["code"] == "unmapped" and f["severity"] == "blocking" for f in result["findings"])
        assert any(f["code"] == "mapping_ai_unavailable" for f in result["findings"])
    engine.dispose()
