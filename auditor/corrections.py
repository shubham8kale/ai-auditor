"""A small typed edit vocabulary, shared by forms and chat. No approval operation exists here."""

from copy import deepcopy
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from auditor.domain import FSLIS
from auditor.workflow import WorkflowError, active_documents, event, invalidate, latest, revalidate_documents


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=8, max_length=2000)


class MappingEdit(Edit):
    type: Literal["mapping"]
    account_number: str
    fsli: str

    @field_validator("fsli")
    @classmethod
    def valid_fsli(cls, value):
        if value not in FSLIS:
            raise ValueError("Choose an allowed FSLI")
        return value


class RiskEdit(Edit):
    type: Literal["risk"]
    risk: Literal["low", "moderate", "high", "significant"]
    account_number: str | None = None


class BenchmarkEdit(Edit):
    type: Literal["benchmark"]
    benchmark: Literal["Revenue", "Total assets", "Equity", "Pre-tax income"]
    rate: float | None = Field(default=None, gt=0, le=1)


class ProfileEdit(Edit):
    type: Literal["profile"]
    field: Literal[
        "service",
        "framework",
        "issuer",
        "first_year",
        "stage",
        "industries",
        "related_parties",
        "prior_benchmark",
    ]
    value: str | bool | list[str]


class AliasEdit(Edit):
    type: Literal["alias"]
    alias: str = Field(min_length=2, max_length=200)


class InvoiceLink(Edit):
    type: Literal["invoice_link"]
    selection_id: str
    document_id: str


class DispositionEdit(Edit):
    type: Literal["disposition"]
    selection_id: str
    disposition: Literal["client_correction_obtained", "additional_evidence_obtained", "unadjusted_exception"]
    evidence_document_ids: list[str] = Field(default_factory=list)
    follow_up: str = Field(min_length=8, max_length=2000)


Operation = Annotated[
    Union[MappingEdit, RiskEdit, BenchmarkEdit, ProfileEdit, AliasEdit, InvoiceLink, DispositionEdit],
    Field(discriminator="type"),
]
operation_adapter = TypeAdapter(Operation)


def account_exists(db, engagement, number):
    mapping = latest(db, engagement.id, "mapping")
    accounts = (
        mapping.payload.get("accounts", [])
        if mapping
        else [r for d in active_documents(db, engagement.id) for r in d.extracted.get("accounts", [])]
    )
    if number not in {row["number"] for row in accounts}:
        raise WorkflowError("That account number does not exist in this engagement's trial balance.")


def apply_edit(db, engagement, operation, actor):
    edit = operation_adapter.validate_python(operation)
    before = deepcopy(engagement.overrides)
    after = deepcopy(before)
    stage = "planning"
    if isinstance(edit, MappingEdit):
        account_exists(db, engagement, edit.account_number)
        after.setdefault("mappings", {})[edit.account_number] = edit.fsli
        after.setdefault("mapping_reasons", {})[edit.account_number] = edit.reason
        stage = "mapping"
    elif isinstance(edit, RiskEdit):
        if edit.account_number:
            account_exists(db, engagement, edit.account_number)
            after.setdefault("account_risks", {})[edit.account_number] = edit.risk
            after.setdefault("risk_rationales", {})[edit.account_number] = edit.reason
        else:
            after.update(engagement_risk=edit.risk, risk_rationale=edit.reason)
    elif isinstance(edit, BenchmarkEdit):
        after.update(benchmark=edit.benchmark, planning_rationale=edit.reason)
        after.pop("materiality_rate", None)
        if edit.rate is not None:
            after["materiality_rate"] = str(edit.rate)
    elif isinstance(edit, ProfileEdit):
        allowed = {
            "service": {"year_end_audit", "interim_review", "aup", "other"},
            "framework": {"US GAAP", "IFRS", "cash_basis", "tax_basis"},
            "stage": {"growth", "mature"},
            "prior_benchmark": {"Revenue", "Total assets", "Equity", "Pre-tax income"},
        }
        if edit.field in {"issuer", "first_year"} and type(edit.value) is not bool:
            raise WorkflowError("This profile field requires true or false.")
        if edit.field in {"industries", "related_parties"} and not isinstance(edit.value, list):
            raise WorkflowError("This profile field requires a list.")
        if edit.field == "industries" and not set(edit.value) <= {
            "food_beverage",
            "wholesale",
            "cannabis",
            "other",
        }:
            raise WorkflowError("Choose a supported industry profile or 'other'.")
        if edit.field in allowed and (
            not isinstance(edit.value, str) or edit.value not in allowed[edit.field]
        ):
            raise WorkflowError("Invalid value for this profile field.")
        after.setdefault("profile", {})[edit.field] = edit.value
        engagement.profile = {**engagement.profile, edit.field: edit.value}
        stage = "onboarding"
    elif isinstance(edit, AliasEdit):
        after["aliases"] = list(dict.fromkeys(after.get("aliases", []) + [edit.alias]))
        after.setdefault("alias_reasons", {})[edit.alias] = edit.reason
        stage = "onboarding"
    elif isinstance(edit, (InvoiceLink, DispositionEdit)):
        sample = latest(db, engagement.id, "sampling")
        if not sample or edit.selection_id not in {s["id"] for s in sample.payload.get("selections", [])}:
            raise WorkflowError("This selection does not exist in the latest sample.")
        documents = {d.id: d for d in active_documents(db, engagement.id) if d.status != "superseded"}
        if isinstance(edit, InvoiceLink):
            if edit.document_id not in documents or documents[edit.document_id].kind != "invoice":
                raise WorkflowError("Link an invoice from this engagement.")
            after.setdefault("invoice_links", {})[edit.selection_id] = edit.document_id
        else:
            if any(d not in documents for d in edit.evidence_document_ids):
                raise WorkflowError("Disposition evidence must belong to this engagement.")
            if edit.disposition != "unadjusted_exception" and not edit.evidence_document_ids:
                raise WorkflowError(
                    "Attach the correction or follow-up evidence supporting this disposition."
                )
            after.setdefault("dispositions", {})[edit.selection_id] = {**edit.model_dump(), "reviewer": actor}
        stage = "testing"
    engagement.overrides = after
    affected = invalidate(db, engagement, stage, f"{actor}: {edit.reason}")
    if stage == "onboarding":
        revalidate_documents(db, engagement)
    event(
        db,
        engagement.id,
        actor,
        "correction_applied",
        {"operation": edit.model_dump(), "before": before, "after": after, "invalidated_stages": affected},
    )
    return {"stage": stage, "invalidated_stages": affected, "operation": edit.model_dump()}
