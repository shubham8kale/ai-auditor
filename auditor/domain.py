"""Pure audit calculations. Money never passes through binary floating-point arithmetic."""

import math
import re
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

FSLIS = [
    "Cash",
    "Accounts Receivable",
    "Inventory",
    "Prepaid Expenses",
    "Property & Equipment",
    "Accounts Payable",
    "Accrued Liabilities",
    "Debt",
    "Equity",
    "Revenue",
    "Cost of Goods Sold",
    "Operating Expenses",
]
RISKS = ["low", "moderate", "high", "significant"]
PM_RATES = dict(zip(RISKS, map(Decimal, ["0.75", "0.65", "0.60", "0.50"])))
RISK_FACTORS = dict(zip(RISKS, map(Decimal, ["0.5", "1", "2", "3"])))
POLICY_VERSION = "2025-06-30"


def money(value) -> Decimal:
    if value is None or value == "":
        raise ValueError("Missing monetary value")
    text = str(value).strip().replace(",", "").replace("$", "").replace("−", "-")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        result = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"Invalid monetary value: {str(value)[:80]}") from None
    if not result.is_finite():
        raise ValueError("Money must be a finite number")
    try:
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError("Monetary value exceeds supported precision") from None


def amount(value):
    return str(money(value))


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def finding(code, message, severity="blocking", source=""):
    return {"code": code, "message": message, "severity": severity, "source": source}


def policy_scope(profile):
    """Resolve applicability before comparing thresholds. Missing scope is never guessed."""
    service = profile.get("service")
    framework = profile.get("framework")
    issuer = profile.get("issuer")
    issues = []
    if service != "year_end_audit":
        issues.append(
            finding(
                "engagement_scope",
                "This workspace prepares year-end audits. Reviews and agreed-upon procedures require a different workflow.",
                source="POL-100 §3; BUL-2024-03 scope",
            )
        )
    if framework not in {"US GAAP", "IFRS", "cash_basis", "tax_basis"}:
        issues.append(
            finding(
                "framework_missing",
                "The engagement letter must identify the reporting framework.",
                source="POL-115 §3",
            )
        )
    elif framework != "US GAAP":
        issues.append(
            finding(
                "alternative_framework",
                f"{framework} requires framework-specific procedures. Upload the applicable methodology and resolve scope before relying on planning.",
                source="POL-115 §§1–3",
            )
        )
    if issuer is None:
        issues.append(
            finding(
                "issuer_missing",
                "Confirm issuer/nonissuer status from the engagement letter.",
                source="POL-100 §3",
            )
        )
    return {
        "version": POLICY_VERSION,
        "issuer": issuer is True,
        "cash_threshold": "50000.00" if issuer else "250000.00",
        "round_threshold": "5000.00" if issuer else "10000.00",
        "active": ["POL-100", "POL-101", "POL-102", "POL-103", "POL-104", "REF-7 B/C"]
        + (["POL-201"] if issuer else []),
        "excluded": [
            "REF-7 Appendix A (engagement acceptance only)",
            "REF-7 Appendix D (withdrawn)",
            "BUL-2023-11 §2 (superseded)",
            "BUL-2024-03 (review/AUP only)",
        ]
        + ([] if issuer else ["POL-201 (issuer only)"]),
        "findings": issues,
    }


def map_by_examples(name, examples=None):
    key = normalized(name)
    for example in examples or []:
        if normalized(example["account_name"]) == key and example["fsli"] in FSLIS:
            return example["fsli"], "Exact match to the uploaded mapping library", "library"
    # Transparent proposals from the supplied library's categories. Ambiguous names fall through to AI.
    patterns = [
        (r"\b(checking|savings|petty cash|money market)\b", "Cash"),
        (r"\b(receivable|receivables|doubtful accounts)\b", "Accounts Receivable"),
        (r"\binventory\b", "Inventory"),
        (r"\bprepaid\b", "Prepaid Expenses"),
        (
            r"\b(equipment|accumulated depreciation|leasehold improvement|furniture|vehicles)\b",
            "Property & Equipment",
        ),
        (r"\b(accounts payable|trade payables)\b", "Accounts Payable"),
        (r"\b(accrued|payroll liabilities)\b", "Accrued Liabilities"),
        (r"\b(loan|note payable|line of credit)\b", "Debt"),
        (r"\b(stock|retained earnings|paid in capital)\b", "Equity"),
        (r"\b(revenue|revenues|product sales|sales wholesale|sales retail)\b", "Revenue"),
        (r"\b(cogs|cost of goods sold)\b", "Cost of Goods Sold"),
        (
            r"\b(salaries|wages|rent expense|utilities|advertising|marketing|legal|professional fees|repairs|maintenance|insurance expense|office supplies|travel expense)\b",
            "Operating Expenses",
        ),
    ]
    for pattern, fsli in patterns:
        if re.search(pattern, key):
            return (
                fsli,
                f"Account description matches {fsli.lower()} terminology in the prior mapping categories",
                "rule",
            )
    return None, "No unambiguous match. A mapping proposal requires review.", "unresolved"


def aggregate_accounts(accounts):
    totals = defaultdict(Decimal)
    for row in accounts:
        if row.get("fsli"):
            totals[row["fsli"]] += money(row["balance"])
    return {key: amount(value) for key, value in totals.items()}


def materiality(accounts, profile, overrides):
    scope = policy_scope(profile)
    findings = list(scope["findings"])
    totals = aggregate_accounts(accounts)
    risk = overrides.get("engagement_risk", "moderate")
    if risk not in RISKS:
        raise ValueError("Risk must be low, moderate, high, or significant")
    stage = profile.get("stage", "growth")
    benchmark = overrides.get("benchmark", "Pre-tax income" if stage == "mature" else "Revenue")
    rates = {
        "Revenue": ("0.005", "0.0025", "0.01") if scope["issuer"] else ("0.01", "0.005", "0.02"),
        "Total assets": ("0.005", "0.0025", "0.01") if scope["issuer"] else ("0.01", "0.005", "0.02"),
        "Equity": ("0.02", "0.01", "0.05"),
        "Pre-tax income": ("0.03", "0.02", "0.05") if scope["issuer"] else ("0.05", "0.03", "0.10"),
    }
    if benchmark not in rates:
        raise ValueError("Unknown materiality benchmark")
    if scope["issuer"] and benchmark == "Equity":
        findings.append(
            finding(
                "issuer_equity",
                "The supplied issuer supplement does not provide an equity benchmark. Obtain applicable methodology.",
                source="POL-201 §2",
            )
        )
    revenue = -money(totals.get("Revenue", "0"))
    assets = sum((money(totals.get(k, "0")) for k in FSLIS[:5]), Decimal(0))
    pretax = (
        revenue - money(totals.get("Cost of Goods Sold", "0")) - money(totals.get("Operating Expenses", "0"))
    )
    values = {
        "Revenue": revenue,
        "Total assets": assets,
        "Equity": -money(totals.get("Equity", "0")),
        "Pre-tax income": pretax,
    }
    base = values[benchmark]
    guideline, lower, upper = map(Decimal, rates[benchmark])
    rate = Decimal(str(overrides.get("materiality_rate", guideline)))
    rationale = overrides.get("planning_rationale", "")
    if not rate.is_finite() or rate <= 0 or rate > 1:
        raise ValueError("Materiality rate must be a positive fraction no greater than 1")
    if rate != guideline and not rationale:
        findings.append(
            finding(
                "rate_rationale",
                "A non-guideline percentage needs a documented reason.",
                source="POL-101 §1.1",
            )
        )
    if not lower <= rate <= upper:
        findings.append(
            finding(
                "partner_concurrence",
                "This percentage is outside the supplied range. A partner concurrence record is required; ordinary stage approval cannot replace it.",
                source="POL-101 §1.1",
            )
        )
    default_benchmark = "Pre-tax income" if stage == "mature" else "Revenue"
    if benchmark != default_benchmark and not rationale:
        findings.append(
            finding(
                "benchmark_rationale",
                "Explain the departure from the client-stage benchmark.",
                source="POL-102 §3",
            )
        )
    if base <= 0:
        findings.append(
            finding(
                "nonpositive_benchmark",
                "The selected benchmark is zero or negative. Select and justify an appropriate alternative.",
                source="POL-101 §1.1",
            )
        )
    if any(not row.get("fsli") for row in accounts):
        findings.append(finding("unmapped_accounts", "Resolve unmapped accounts before finalizing planning."))
    material = max(money(base * rate), Decimal(0))
    pm_rate = PM_RATES[risk]
    if profile.get("first_year"):
        pm_rate = min(pm_rate, Decimal("0.60"))
    if scope["issuer"]:
        pm_rate = min(pm_rate, Decimal("0.55"))
    pm = money(material * pm_rate)
    ctt = money(material * Decimal("0.03" if scope["issuer"] else "0.05"))
    industries = profile.get("industries", [])
    elevated = {"Inventory", "Cost of Goods Sold"} if "food_beverage" in industries else set()
    if "wholesale" in industries:
        elevated |= {"Inventory", "Revenue"}
    if "cannabis" in industries:
        elevated |= {"Inventory", "Cost of Goods Sold", "Cash", "Accrued Liabilities"}
    account_risks = overrides.get("account_risks", {})
    scoped = []
    for row in accounts:
        fsli = row.get("fsli")
        floor = "high" if fsli in elevated else risk
        row_risk = account_risks.get(row["number"], floor)
        qualitative = fsli in elevated
        included = bool(fsli and (abs(money(totals.get(fsli, "0"))) >= pm or qualitative))
        if row_risk not in RISKS:
            raise ValueError("Invalid account risk")
        if (
            qualitative
            and RISKS.index(row_risk) < RISKS.index("high")
            and not overrides.get("risk_rationales", {}).get(row["number"])
        ):
            findings.append(
                finding(
                    "risk_floor",
                    f"Account {row['number']} needs a reason for a risk below high.",
                    source="POL-101 §3; POL-102 §2",
                )
            )
        scoped.append(
            {
                **row,
                "risk": row_risk,
                "in_scope": included,
                "qualitative": qualitative,
                "scope_reason": "Mapping unresolved; scope cannot be determined"
                if not fsli
                else "Industry risk flag"
                if qualitative
                else (
                    "FSLI at or above PM"
                    if included
                    else "FSLI below PM; no identified qualitative flag in the supplied profile"
                ),
            }
        )
    prior = profile.get("prior_benchmark")
    if prior and normalized(prior) != normalized(benchmark) and not rationale:
        findings.append(
            finding(
                "prior_benchmark_change",
                "Explain why the benchmark differs from the prior year.",
                source="POL-101 §1.1",
            )
        )
    risk_reason = overrides.get(
        "risk_rationale",
        "Moderate is a provisional preparation assumption. Reassess growth, control capacity, prior errors and industry risks before sign-off.",
    )
    return {
        "benchmark": benchmark,
        "benchmark_value": amount(base),
        "rate": str(rate),
        "guideline": str(guideline),
        "materiality": amount(material),
        "pm": amount(pm),
        "pm_rate": str(pm_rate),
        "ctt": amount(ctt),
        "engagement_risk": risk,
        "risk_rationale": risk_reason,
        "accounts": scoped,
        "totals": totals,
        "policy": scope,
        "findings": findings,
        "rationale": rationale
        or f"{benchmark} follows the {stage}-stage profile. The guideline rate is {rate * 100}%. Performance materiality uses {risk} engagement risk and applicable caps.",
        "sources": ["POL-101 p.1 §§1–3", "POL-102 p.2 §§3–4"]
        + (["POL-201 p.1 §2"] if scope["issuer"] else []),
    }


def reconcile(transactions, accounts):
    values = defaultdict(Decimal)
    for row in transactions:
        values[row["account_number"]] += money(row["amount"])
    account_map = {row["number"]: row for row in accounts}
    rows = []
    for key, total in sorted(values.items()):
        tb = account_map.get(key)
        tb_value = money(tb["balance"]) if tb else None
        rows.append(
            {
                "account_number": key,
                "account_name": tb["name"] if tb else "Unrecognized account",
                "gl": amount(total),
                "tb": amount(tb_value) if tb_value is not None else None,
                "difference": amount(total - tb_value) if tb_value is not None else None,
                "ties": tb_value is not None and total == tb_value,
            }
        )
    return rows


def select_sample(transactions, pm_value, risk, round_threshold, period_end, related_parties=None):
    pm = money(pm_value)
    if pm <= 0:
        raise ValueError("Positive performance materiality is required before sampling")
    if risk not in RISKS:
        raise ValueError("Unknown sampling risk")
    reasons = defaultdict(list)
    related = {normalized(x) for x in related_parties or []}
    eligible = [row for row in transactions if row["date"] <= period_end]
    positive = [row for row in eligible if money(row["amount"]) > 0]
    certain = [row for row in positive if money(row["amount"]) > pm]
    certain_ids = {row["id"] for row in certain}
    remainder = [row for row in positive if row["id"] not in certain_ids]
    remaining_value = sum((money(row["amount"]) for row in remainder), Decimal(0))
    formula_count = math.ceil(remaining_value / pm * RISK_FACTORS[risk])
    actual_count = min(len(remainder), formula_count)
    for row in certain:
        reasons[row["id"]].append("Individually significant (> PM)")
    for row in sorted(remainder, key=lambda r: (-money(r["amount"]), r["date"], r["id"]))[:actual_count]:
        reasons[row["id"]].append("High-value remainder selection")
    for row in eligible:
        value = money(row["amount"])
        if normalized(row.get("counterparty", "")) in related or row.get("related_party"):
            reasons[row["id"]].append("Related party: mandatory selection")
        if value >= money(round_threshold) and value % Decimal("1000") == 0:
            reasons[row["id"]].append("Round-dollar mandatory selection")
        if value <= 0:
            reasons[row["id"]].append(
                "Credit/zero entry: separate judgmental review, excluded from positive sampling value"
            )
    accounts = {row["account_number"] for row in eligible}
    for account in accounts:
        latest_date = max(row["date"] for row in eligible if row["account_number"] == account)
        # With date-only source data, include tied last-date rows rather than invent intraday ordering.
        for row in eligible:
            if row["account_number"] == account and row["date"] == latest_date:
                reasons[row["id"]].append("Last recorded date in account before period end")
    selected = [{**row, "selection_reasons": reasons[row["id"]]} for row in eligible if row["id"] in reasons]
    return {
        "selections": selected,
        "population_count": len(eligible),
        "population_value": amount(sum((money(r["amount"]) for r in eligible), Decimal(0))),
        "positive_population_value": amount(sum((money(r["amount"]) for r in positive), Decimal(0))),
        "remaining_value": amount(remaining_value),
        "certain_count": len(certain),
        "formula_count": formula_count,
        "remainder_count": actual_count,
        "risk": risk,
        "factor": str(RISK_FACTORS[risk]),
        "pm": amount(pm),
        "round_threshold": amount(round_threshold),
        "selected_count": len(selected),
        "selected_value": amount(sum((money(r["amount"]) for r in selected), Decimal(0))),
        "sources": ["POL-101 p.2 §§4.1–4.3", "REF-7 p.1 Appendix C"],
        "projection": "High-value and mandatory selections are judgmental. Statistical projection is not established by this selection method.",
    }
