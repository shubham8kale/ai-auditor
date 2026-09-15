import asyncio
from types import SimpleNamespace

import pytest

from auditor import vouching


@pytest.mark.parametrize("vague_professional", [False, True])
def test_unreadable_invoice_amount_stays_unresolved_without_aborting_other_assertions(
    monkeypatch, vague_professional
):
    async def semantic(*_args, **_kwargs):
        return {
            "classification": {"status": "pass", "reason": "Cleaning expense"},
            "business_purpose": {"status": "pass", "reason": "Cleaning the client's office"},
        }, {}

    monkeypatch.setattr(vouching, "ask_json", semantic)
    document = SimpleNamespace(
        id="synthetic-doc",
        filename="synthetic.pdf",
        status="needs_attention",
        findings=[{"code": "invalid_amount", "severity": "blocking"}],
        extracted={
            "facts": {
                "entity": "Fictional Client",
                "amount": "unreadable",
                "service_start": "2025-06-01",
                "service_end": "2025-06-30",
            }
        },
    )
    engagement = SimpleNamespace(name="Fictional Client", period_end="2025-12-31", overrides={})
    if vague_professional:
        document.extracted["facts"].update(
            professional_services=True, detailed_matter=False, description="Services rendered"
        )
    result = asyncio.run(vouching.vouch({"amount": "100.00"}, document, engagement, {}))
    assert result["known_error"] is None
    assert result["status"] == "unresolved"
    assert result["checks"]["accuracy"]["status"] == "unresolved"
    assert result["checks"]["period"]["status"] == "pass"
    assert result["checks"]["classification"]["status"] == "pass"
    if vague_professional:
        assert result["checks"]["validity"]["status"] == "unresolved"
