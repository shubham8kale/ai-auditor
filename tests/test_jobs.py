import asyncio

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auditor import jobs
from auditor.db import Base, Engagement, Job, Revision


@pytest.mark.parametrize("interruption", ["changed_input", "interrupted_run"])
def test_stale_in_flight_preparation_cannot_publish(monkeypatch, interruption):
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(jobs, "SessionLocal", sessions)
    monkeypatch.setattr(jobs, "locks", {})
    with sessions() as db:
        engagement = Engagement(name="Fictional Client", owner_id="reviewer", period_end="2025-12-31")
        db.add(engagement)
        db.flush()
        job = Job(engagement_id=engagement.id, stage="onboarding")
        db.add(job)
        db.commit()
        job_id, engagement_id = job.id, engagement.id

    async def slow_preparation(*_args):
        with sessions() as writer:
            if interruption == "changed_input":
                writer.get(Engagement, engagement_id).version += 1
            else:
                writer.get(Job, job_id).status = "interrupted"
            writer.commit()
        return {"findings": []}

    monkeypatch.setattr(jobs, "prepare", slow_preparation)
    asyncio.run(jobs.run_job(job_id))
    with sessions() as db:
        assert db.scalar(select(Revision)) is None
        assert db.get(Job, job_id).status == ("failed" if interruption == "changed_input" else "interrupted")
    engine.dispose()
