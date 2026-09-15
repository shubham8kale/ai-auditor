import pytest
from pydantic import ValidationError

from auditor.documents import Facts, extraction_schema


def test_prior_audit_date_cannot_become_materiality_benchmark():
    with pytest.raises(ValidationError):
        Facts(prior_benchmark="2024-12-31")
    assert Facts(prior_benchmark="Revenue").prior_benchmark == "Revenue"
    assert Facts(prior_benchmark="revenue").prior_benchmark == "Revenue"
    assert Facts().prior_benchmark is None


def test_extraction_schema_closes_every_object_and_requires_known_fields():
    def verify(node):
        if isinstance(node, dict):
            assert "default" not in node
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for value in node.values():
                verify(value)
        elif isinstance(node, list):
            for value in node:
                verify(value)

    schema = extraction_schema()
    verify(schema)
    fields = schema["properties"]["facts"]["properties"]
    assert {choice["type"] for choice in fields["issuer"]["anyOf"]} == {"boolean", "null"}
    assert fields["industries"]["type"] == "array"


def test_unknown_professional_status_and_quote_remain_unknown():
    facts = Facts.model_validate(
        {
            "document_type": "invoice",
            "issuer": None,
            "professional_services": None,
            "source_quotes": {"issuer": None},
        }
    )
    assert facts.issuer is None
    assert facts.professional_services is None
    assert facts.source_quotes["issuer"] is None
    assert facts.industries == []


def test_invoice_sender_is_not_coerced_into_public_issuer_status():
    with pytest.raises(ValidationError):
        Facts.model_validate({"document_type": "invoice", "issuer": "Sample Office Services LLC"})
