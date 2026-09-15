from decimal import Decimal

import pytest

from auditor.domain import materiality, money, policy_scope, reconcile, select_sample
from auditor.parsing import spreadsheet


def profile(**changes):
    return {
        "service": "year_end_audit",
        "framework": "US GAAP",
        "issuer": False,
        "first_year": False,
        "stage": "growth",
        "industries": ["wholesale"],
        **changes,
    }


def accounts():
    # Synthetic balanced miniature ledger; no supplied data.
    return [
        {"number": "100", "name": "Checking", "fsli": "Cash", "balance": "120000.00"},
        {"number": "300", "name": "Retained earnings", "fsli": "Equity", "balance": "-20000.00"},
        {"number": "400", "name": "Revenue", "fsli": "Revenue", "balance": "-1000000.00"},
        {"number": "500", "name": "Cost of goods sold", "fsli": "Cost of Goods Sold", "balance": "700000.00"},
        {"number": "600", "name": "Marketing", "fsli": "Operating Expenses", "balance": "200000.00"},
    ]


def transaction(identifier, amount, date="2025-06-30", account="600", **extra):
    return {
        "id": identifier,
        "account_number": account,
        "date": date,
        "amount": amount,
        "counterparty": "Example vendor",
        "ref": identifier,
        **extra,
    }


def test_money_uses_decimal_rounding_and_accepts_accounting_negatives():
    assert money("($1,234.565)") == Decimal("-1234.57")
    assert money("0.105") + money("0.105") == Decimal("0.22")


@pytest.mark.parametrize("value", [None, "", "NaN", "Infinity", "not an amount", "1e100"])
def test_missing_and_nonfinite_money_is_rejected(value):
    with pytest.raises(ValueError):
        money(value)


def test_materiality_and_caps_are_independent_of_historical_workpapers():
    recurring = materiality(accounts(), profile(), {})
    first = materiality(accounts(), profile(first_year=True), {})
    issuer = materiality(accounts(), profile(issuer=True), {})
    assert (recurring["materiality"], recurring["pm"], recurring["ctt"]) == ("10000.00", "6500.00", "500.00")
    assert first["pm"] == "6000.00"
    assert (issuer["materiality"], issuer["pm"], issuer["ctt"]) == ("5000.00", "2750.00", "150.00")


def test_scope_is_resolved_before_applying_thresholds():
    result = policy_scope(profile(service="interim_review", framework="IFRS", issuer=None))
    assert {f["code"] for f in result["findings"]} == {
        "engagement_scope",
        "alternative_framework",
        "issuer_missing",
    }
    assert "POL-201" not in policy_scope(profile())["active"]
    assert "POL-201" in policy_scope(profile(issuer=True))["active"]


def test_unmapped_account_does_not_appear_to_be_validly_excluded_from_scope():
    rows = accounts()
    rows[-1]["fsli"] = None
    result = materiality(rows, profile(), {})
    assert "unmapped_accounts" in {f["code"] for f in result["findings"]}
    assert result["accounts"][-1]["scope_reason"] == "Mapping unresolved; scope cannot be determined"


def test_prior_benchmark_case_does_not_invent_a_change_but_different_basis_requires_reason():
    same = materiality(accounts(), profile(prior_benchmark="revenue"), {})
    changed = materiality(accounts(), profile(prior_benchmark="Equity"), {})
    assert "prior_benchmark_change" not in {f["code"] for f in same["findings"]}
    assert "prior_benchmark_change" in {f["code"] for f in changed["findings"]}


def test_outside_range_cannot_be_cleared_with_ordinary_rationale():
    result = materiality(
        accounts(), profile(), {"materiality_rate": "0.03", "planning_rationale": "A reviewer explanation"}
    )
    assert "partner_concurrence" in {f["code"] for f in result["findings"]}


def test_low_risk_on_elevated_industry_account_requires_reason():
    result = materiality(accounts(), profile(), {"account_risks": {"400": "low"}})
    assert "risk_floor" in {f["code"] for f in result["findings"]}


def test_selection_ceiling_mandatory_dedup_and_date_ties():
    rows = [
        transaction("large", "12000"),
        transaction("high", "7000"),
        transaction("round", "10000", date="2025-12-20"),
        transaction("last1", "200", date="2025-12-31"),
        transaction("last2", "300", date="2025-12-31"),
        transaction("related", "100", account="610", counterparty="Owner Services"),
        transaction("credit", "-50", account="610"),
    ]
    result = select_sample(rows, "10000", "low", "10000", "2025-12-31", ["Owner Services"])
    assert result["certain_count"] == 1  # Exactly PM is not individually significant.
    assert result["remaining_value"] == "17600.00"
    assert result["formula_count"] == 1  # ceil(17,600 / 10,000 * 0.5)
    selected = {r["id"]: r for r in result["selections"]}
    assert set(selected) == {"large", "round", "last1", "last2", "related", "credit"}
    assert len(selected["round"]["selection_reasons"]) == 2
    assert result["positive_population_value"] == "29600.00"
    assert result["population_value"] == "29550.00"


def test_selection_rejects_zero_pm():
    with pytest.raises(ValueError):
        select_sample([], "0", "moderate", "10000", "2025-12-31")


def test_reconciliation_retains_unknown_account_and_cent_difference():
    result = reconcile([transaction("a", "199999.99"), transaction("b", "10", account="999")], accounts())
    assert result[0]["difference"] == "-0.01"
    assert result[1]["tb"] is None
    assert not any(r["ties"] for r in result)


def test_parser_recomputes_totals_and_does_not_trust_footer():
    data = b"account number,account name,debit,credit\n100,Checking,100,\n300,Equity,,99\nTotal,,100,100\n"
    result = spreadsheet(data, ".csv", "synthetic")
    assert result["net_balance"] == "1.00"
    assert len(result["accounts"]) == 2
    assert "tb_unbalanced" in {f["code"] for f in result["findings"]}


def test_empty_amount_is_not_silently_zero():
    result = spreadsheet(b"account number,account name,debit,credit\n100,Checking,,\n", ".csv", "synthetic")
    assert not result["accounts"]
    assert result["findings"][0]["code"] == "invalid_row"
