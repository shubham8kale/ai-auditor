"""A complete synthetic engagement through the real preparation stages, with AI judgments stubbed.

The fixtures and expected arithmetic are independent of any real client.
"""

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from auditor import vouching
from auditor.corrections import apply_edit
from auditor.db import Base, Document, Engagement, Revision
from auditor.parsing import spreadsheet
from auditor.workflow import prepare


@pytest.mark.parametrize("missing_service_period", [False, True])
def test_full_preparation_keeps_exception_visible_and_correction_stales_dependents(
    monkeypatch, missing_service_period
):
    async def semantic_checks(*_args, **_kwargs):
        return {
            "classification": {
                "status": "pass",
                "reason": "The invoice describes the recorded advertising service.",
            },
            "business_purpose": {"status": "pass", "reason": "The service supports this client's trade."},
        }, {"model": "test-double"}

    monkeypatch.setattr(vouching, "ask_json", semantic_checks)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        engagement = Engagement(
            name="Example Trading Ltd",
            owner_id="synthetic-reviewer",
            period_end="2025-12-31",
            profile={},
            overrides={},
        )
        db.add(engagement)
        db.flush()

        def evidence(identifier, kind, extracted):
            result = Document(
                id=identifier,
                engagement_id=engagement.id,
                filename=identifier + ".csv",
                kind=kind,
                content_type="text/csv",
                storage_key=identifier,
                sha256=identifier.ljust(64, "0"),
                size=100,
                status="accepted",
                extracted={"kind": kind, **extracted},
                findings=[],
                reviewed_by="Synthetic reviewer",
            )
            db.add(result)
            return result

        evidence(
            "letter",
            "engagement_letter",
            {
                "facts": {
                    "entity": engagement.name,
                    "period_end": "2025-12-31",
                    "service": "year_end_audit",
                    "framework": "US GAAP",
                    "issuer": False,
                    "first_year": False,
                    "stage": "growth",
                    "industries": ["wholesale"],
                    "related_parties": [],
                }
            },
        )
        tb = spreadsheet(
            b"account number,account name,balance\n100,Checking,10000\n400,Revenue,-100000\n500,Cost of goods sold,70000\n600,Marketing,20000\n",
            ".csv",
            "tb",
        )
        evidence("tb", "trial_balance", tb)
        gl = spreadsheet(
            b"account number,date,vendor,reference,description,amount\n600,2025-05-01,Sample Agency,INV-01,Advertising,19000\n600,2025-12-31,Sample Agency,INV-02,Advertising,1000\n",
            ".csv",
            "gl",
        )
        evidence("gl", "general_ledger", gl)
        for index, source_amount in [(1, "19000"), (2, "900")]:
            evidence(
                f"invoice-{index}",
                "invoice",
                {
                    "facts": {
                        "entity": engagement.name,
                        "reference": f"INV-0{index}",
                        "vendor": "Sample Agency",
                        "date": "2025-05-01" if index == 1 else "2025-12-31",
                        "amount": source_amount,
                        "description": "Advertising service",
                        "service_start": None if missing_service_period and index == 2 else "2025-01-01",
                        "service_end": None if missing_service_period and index == 2 else "2025-12-31",
                    },
                    "pages": [{"page": 1}],
                },
            )
        db.commit()

        saved = {}
        for stage in ["onboarding", "mapping", "planning", "sampling", "testing"]:
            payload = asyncio.run(prepare(db, engagement, stage))
            revision = Revision(
                engagement_id=engagement.id,
                stage=stage,
                input_version=engagement.version,
                payload=payload,
                status="draft" if stage == "testing" else "approved",
                approved_by=None if stage == "testing" else "Synthetic reviewer",
            )
            db.add(revision)
            db.commit()
            saved[stage] = revision
        assert saved["mapping"].payload["net_balance"] == "0.00"
        assert saved["planning"].payload["materiality"] == "1000.00"
        assert saved["planning"].payload["pm"] == "650.00"
        assert len(saved["sampling"].payload["selections"]) == 2
        results = saved["testing"].payload
        assert results["exception_count"] == 1
        assert results["known_absolute_error"] == "100.00"
        assert results["results"][1]["checks"]["accuracy"]["status"] == "exception"
        assert any(f["code"] == "exception_follow_up" for f in results["findings"])
        assert "1 selections with exceptions" in results["conclusion"]
        if missing_service_period:
            # An amount exception must not hide an unresolved cutoff assertion, even after a disposition.
            engagement.overrides = {
                "dispositions": {
                    results["results"][1]["transaction"]["id"]: {
                        "follow_up": "Amount difference discussed with client"
                    }
                }
            }
            repeated = asyncio.run(prepare(db, engagement, "testing"))
            assert repeated["unresolved_count"] == 1
            assert any(f["code"] == "unresolved_evidence" for f in repeated["findings"])
        apply_edit(
            db,
            engagement,
            {"type": "risk", "risk": "high", "reason": "New control gaps require additional work"},
            "Synthetic reviewer",
        )
        assert saved["mapping"].status == "approved"
        assert all(saved[stage].status == "stale" for stage in ["planning", "sampling", "testing"])
    engine.dispose()
