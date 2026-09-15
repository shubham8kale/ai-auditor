"""Persist job progress; never mistake a process restart or a changed input for a completed run.

The free deployment uses one application worker. Per-engagement locks serialize expensive work;
database version checks reject results prepared against changed inputs.
"""

import asyncio
import logging

from sqlalchemy import select

from auditor.ai import AIUnavailable
from auditor.db import Document, Engagement, Job, Revision, SessionLocal, now
from auditor.documents import read_document, validate_document
from auditor.storage import read_file
from auditor.workflow import WorkflowError, event, invalidate, prepare

logger = logging.getLogger(__name__)
locks: dict[str, asyncio.Lock] = {}
tasks: set[asyncio.Task] = set()


def affected_stage(kind):
    return {
        "trial_balance": "mapping",
        "mapping_library": "mapping",
        "general_ledger": "sampling",
        "invoice": "testing",
    }.get(kind, "onboarding")


def dispatch(job_id):
    task = asyncio.create_task(run_job(job_id))
    tasks.add(task)
    task.add_done_callback(tasks.discard)


async def run_job(job_id):
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job:
            return
        engagement_id = job.engagement_id
    async with locks.setdefault(engagement_id, asyncio.Lock()):
        try:
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                if job.status != "queued":
                    return
                engagement = db.get(Engagement, engagement_id)
                job.status = "running"
                job.message = (
                    "Reading evidence and preparing checks. Free AI requests are paced to respect quota."
                )
                job.detail = {**job.detail, "input_version": engagement.version}
                stage, detail, version = job.stage, dict(job.detail), engagement.version
                db.commit()
            if stage == "document":
                with SessionLocal() as db:
                    document = db.get(Document, detail["document_id"])
                    if document.status == "superseded":
                        raise WorkflowError("This document has been superseded.")
                    document.status = "processing"
                    key, filename, document_id = document.storage_key, document.filename, document.id
                    db.commit()
                extracted = await read_document(await read_file(key), filename, document_id)
                with SessionLocal() as db:
                    engagement = db.scalar(
                        select(Engagement).where(Engagement.id == engagement_id).with_for_update()
                    )
                    if db.get(Job, job_id).status != "running":
                        return  # A restart invalidated this run while the old process was finishing.
                    document = db.get(Document, document_id)
                    if document.status != "processing":
                        raise WorkflowError(
                            "The document changed during processing. Retry using its current state."
                        )
                    document.extracted = extracted
                    document.kind = extracted["kind"]
                    document.findings = validate_document(
                        extracted,
                        engagement.name,
                        engagement.period_end,
                        engagement.overrides.get("aliases", []),
                        engagement.profile,
                    )
                    document.status = (
                        "needs_attention"
                        if any(f["severity"] == "blocking" for f in document.findings)
                        else "ready"
                    )
                    invalidate(
                        db,
                        engagement,
                        affected_stage(document.kind),
                        "Newly processed evidence requires review",
                    )
                    event(
                        db,
                        engagement_id,
                        "AI preparer",
                        "document_processed",
                        {"document_id": document_id, "kind": document.kind, "findings": document.findings},
                    )
                    finish(db, job_id, "completed", "Document ready for review", {"document_id": document_id})
                    db.commit()
            else:
                with SessionLocal() as db:
                    engagement = db.get(Engagement, engagement_id)
                    payload = await prepare(db, engagement, stage)
                    prepared_profile = dict(engagement.profile)
                    db.rollback()  # Preparation is a draft; publish only after checking the current input version.
                with SessionLocal() as db:
                    engagement = db.scalar(
                        select(Engagement).where(Engagement.id == engagement_id).with_for_update()
                    )
                    if db.get(Job, job_id).status != "running":
                        return
                    if engagement.version != version:
                        raise WorkflowError(
                            "Inputs changed while this run was preparing. Its result was discarded; prepare again."
                        )
                    invalidate(db, engagement, stage, "A new revision replaces the earlier preparation")
                    if stage == "onboarding":
                        engagement.profile = prepared_profile
                    revision = Revision(
                        engagement_id=engagement_id,
                        stage=stage,
                        input_version=engagement.version,
                        payload=payload,
                        prepared_by="AI Auditor · deterministic rules + AI proposals",
                    )
                    db.add(revision)
                    db.flush()
                    event(
                        db,
                        engagement_id,
                        "AI preparer",
                        "stage_prepared",
                        {
                            "stage": stage,
                            "revision_id": revision.id,
                            "finding_count": len(payload.get("findings", [])),
                        },
                    )
                    finish(
                        db,
                        job_id,
                        "completed",
                        "Draft saved. Auditor review is required.",
                        {"revision_id": revision.id},
                    )
                    db.commit()
        except asyncio.CancelledError:
            fail_job(
                job_id, "interrupted", "The service stopped before this run completed. Retry the saved job."
            )
            raise
        except (WorkflowError, AIUnavailable, ValueError) as exc:
            # Only domain exceptions are presented verbatim; infrastructure errors can contain credentials.
            message = (
                str(exc)[:1200]
                if isinstance(exc, (WorkflowError, AIUnavailable))
                else "Document or AI response could not be validated. Inspect the source and retry."
            )
            fail_job(job_id, "failed", message)
        except Exception as exc:
            logger.error("Job %s failed (%s)", job_id, type(exc).__name__)
            fail_job(
                job_id,
                "failed",
                "Processing failed. Your original evidence is retained. Retry after checking the service configuration.",
            )


def finish(db, job_id, status, message, detail=None):
    job = db.get(Job, job_id)
    job.status, job.message, job.finished_at = status, message, now()
    job.detail = {**job.detail, **(detail or {})}


def fail_job(job_id, status, message):
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job:
            return
        if job.stage == "document":
            doc = db.get(Document, job.detail.get("document_id"))
            if doc and doc.status == "processing":
                doc.status = "error"
        finish(db, job_id, status, message)
        event(db, job.engagement_id, "System", "job_failed", {"job_id": job_id, "message": message})
        db.commit()
