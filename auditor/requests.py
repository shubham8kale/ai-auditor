import hashlib
import re

from auditor.domain import money


def request_list(accounts, profile, policy, documents):
    requests = []

    def add(kind, title, why, source, account=None, required_reference=None):
        key = f"{kind}:{account or ''}:{title}"
        request_id = hashlib.sha256(key.encode()).hexdigest()[:16]
        candidates = []
        for document in documents:
            if document.kind != kind or document.status in {"superseded", "returned", "error"}:
                continue
            facts = document.extracted.get("facts", {})
            # Similar document types do not establish coverage of a particular account or request.
            # Only the unique global TB/GL requests can match automatically.
            if kind not in {"trial_balance", "general_ledger"} and request_id not in document.extracted.get(
                "request_ids", []
            ):
                continue
            if account and kind in {"bank_statement", "bank_reconciliation", "bank_confirmation"}:
                match = next((a for a in accounts if a["number"] == account), None)
                last4 = re.search(r"(\d{4})\s*$", match["name"] if match else "")
                if last4 and facts.get("account_last4") != last4.group(1):
                    continue
            if required_reference and facts.get("reference") != required_reference:
                continue
            candidates.append(document)
        accepted = [doc for doc in candidates if doc.status == "accepted"]
        requests.append(
            {
                "id": request_id,
                "kind": kind,
                "title": title,
                "why": why,
                "source": source,
                "account_number": account,
                "status": "satisfied"
                if accepted
                else ("ready_for_review" if any(d.status == "ready" for d in candidates) else "open"),
                "document_ids": [d.id for d in candidates],
            }
        )

    for kind, title in [
        ("trial_balance", "Year-end trial balance"),
        ("general_ledger", "Full-year general ledger"),
        ("board_minutes", "Signed board minutes through report date"),
        ("contract", "Significant new or amended contracts"),
    ]:
        add(kind, title, "Required for every annual audit", "Prior PBC list standard requests; POL-103")
    for account in accounts:
        number, name, fsli = account["number"], account["name"], account.get("fsli")
        if fsli == "Cash":
            add(
                "bank_statement",
                f"Year-end statement · {name}",
                "Each cash account needs institution-issued support",
                "POL-103 §§3–4",
                number,
            )
            statement_request = requests[-1]["id"]
            eligible_statements = set(requests[-1]["document_ids"])
            bank_balances = []
            for document in documents:
                facts = document.extracted.get("facts", {})
                if (
                    document.kind == "bank_statement"
                    and document.status == "accepted"
                    and document.id in eligible_statements
                    and statement_request in document.extracted.get("request_ids", [])
                ):
                    try:
                        bank_balances.append(money(facts.get("amount")))
                    except ValueError:
                        pass
            add(
                "bank_reconciliation",
                f"Year-end reconciliation · {name}",
                "Reconcile the bank balance to the ledger",
                "POL-103 §§3–4",
                number,
            )
            trigger_balance = max(bank_balances) if bank_balances else money(account["balance"])
            if trigger_balance > money(policy["cash_threshold"]):
                add(
                    "bank_confirmation",
                    f"Direct bank confirmation · {name}",
                    (
                        f"Reviewed period-end statement balance exceeds {policy['cash_threshold']}. "
                        if bank_balances
                        else f"TB balance exceeds {policy['cash_threshold']}; confirm the trigger against the period-end statement balance. "
                    )
                    + "Statement alone cannot close this request.",
                    "POL-103 §5.1; REF-7 Appendix B",
                    number,
                )
        elif fsli in {"Accounts Receivable", "Accounts Payable"}:
            add(
                "ar_aging" if fsli == "Accounts Receivable" else "ap_aging",
                f"Year-end aging · {name}",
                "By customer/vendor, with aging buckets, tied to the account",
                "POL-103 §3",
                number,
            )
        elif fsli == "Inventory":
            add(
                "inventory_listing",
                f"Inventory listing and count support · {name}",
                "Quantities and costs must extend to the recorded balance",
                "POL-103 §3",
                number,
            )
        elif fsli == "Debt":
            add(
                "loan_agreement",
                f"Executed agreement · {name}",
                "Establish terms; newly appearing debt always requires its executed agreement",
                "POL-103 §§4–5",
                number,
            )
            add(
                "lender_statement",
                f"Year-end lender statement · {name}",
                "Support the debt balance",
                "POL-103 §4",
                number,
            )
        elif fsli == "Prepaid Expenses":
            add(
                "other_support",
                f"Prepaid rollforward and underlying policy · {name}",
                "Explain the remaining prepaid balance and retain computations",
                "Prior PBC list; POL-103 §2.5",
                number,
            )
        elif fsli == "Property & Equipment":
            add(
                "fixed_asset_register",
                f"Fixed asset register · {name}",
                "Include additions, disposals and depreciation",
                "Prior PBC list",
                number,
            )
        elif fsli == "Accrued Liabilities":
            add(
                "payroll_register",
                f"Accrual support · {name}",
                "Support the payroll/expense accrual at year-end",
                "Prior PBC list",
                number,
            )
        elif fsli == "Revenue":
            add(
                "other_support",
                f"Full-year sales register · {name}",
                "Support revenue by customer",
                "Prior PBC list",
                number,
            )
    industries = profile.get("industries", [])
    extras = []
    if "food_beverage" in industries:
        extras += [
            ("inventory_listing", "Inventory count sheets with lot / expiration dates", "POL-102 §2.3"),
            ("other_support", "Finished-goods overhead absorption calculation", "POL-102 §2.3"),
            ("other_support", "Top-10 supplier purchase summary", "POL-102 §2.3"),
        ]
    if "wholesale" in industries:
        extras += [
            ("inventory_listing", "Year-end physical inventory count sheets", "POL-102 §2.1"),
            (
                "other_support",
                "Shipping and receiving logs: five business days either side of year-end",
                "POL-102 §2.1",
            ),
            ("contract", "Vendor rebate agreements", "POL-102 §2.1"),
            ("other_support", "Slow-moving inventory report", "POL-102 §2.1"),
        ]
    if "cannabis" in industries:
        extras += [
            ("license", "Current state licenses for every location", "POL-102 §2.2"),
            (
                "state_compliance_report",
                "State seed-to-sale sales and closing inventory reports",
                "POL-102 §2.2",
            ),
            ("other_support", "Monthly cash counts signed by two employees", "POL-102 §2.2"),
            ("other_support", "COGS absorption schedule supporting tax allocation", "POL-102 §2.2"),
        ]
    for kind, title, source in extras:
        add(kind, title, "Mandatory for this client's industry profile", source)
    if profile.get("first_year"):
        for title in [
            "Prior-year closing trial balance",
            "Predecessor auditor contact and access authorization",
            "Support for beginning inventory",
        ]:
            add("other_support", title, "First-year engagement requirement", "POL-102 §4.2; BUL-2023-11 §§3–5")
    else:
        add(
            "other_support",
            "Prior-year closing and current-year opening trial balances",
            "Recurring opening balances must agree to the cent",
            "POL-102 §4.1",
        )
    for party in profile.get("related_parties", []):
        add(
            "contract",
            f"Underlying related-party agreement · {party}",
            "Required regardless of amount",
            "POL-103 §5.3",
        )
    return requests
