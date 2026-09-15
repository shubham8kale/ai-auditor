"""Opt-in live evaluation of fictional demo files; never writes to the application database.

Generate both demos with create_demo.py first. Results and extracted synthetic facts are
cached under ignored tmp/ so an interrupted evaluation can resume without repeating calls.
This evaluates extraction and invoice assertions, not human approval or browser behavior.
"""

import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from auditor.config import settings
from auditor.documents import read_document, validate_document
from auditor.domain import money, normalized
from auditor.parsing import spreadsheet
from auditor.vouching import vouch

ROOT = Path(__file__).resolve().parents[1]


async def evaluate(scenario, fresh, references=None):
    folder = ROOT / "data" / "demo" / scenario
    manifest = json.loads((folder / "expected-results.json").read_text(encoding="utf-8"))
    assert manifest["synthetic"] is True
    invoices = [i for i in manifest["invoices"] if not references or i["reference"] in references]
    if references and {i["reference"] for i in invoices} != set(references):
        raise SystemExit("Unknown invoice reference; check the generated manifest.")
    out = ROOT / "tmp" / "demo-evaluation" / scenario
    if references:
        out /= "targeted-" + "-".join(sorted(set(references)))
    out.mkdir(parents=True, exist_ok=True)
    checks, extracted = [], {}
    code_hash = hashlib.sha256(
        b"".join((ROOT / "auditor" / p).read_bytes() for p in ["ai.py", "documents.py", "vouching.py"])
        + settings().groq_model.encode()
    ).hexdigest()

    def check(name, passed):
        checks.append({"name": name, "passed": bool(passed)})

    def save_report(completed=False):
        report = {
            "synthetic": True,
            "scenario": scenario,
            "invoice_references": [i["reference"] for i in invoices],
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "code_hash": code_hash,
            "checks": checks,
            "completed": completed,
            "passed": completed and all(c["passed"] for c in checks),
            "completed_extractions": list(extracted),
            "scope": "Live extraction and invoice assertions; no real audit approvals or production writes.",
        }
        (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    profile = {"industries": ["wholesale"]}
    files = ["01-engagement-letter.pdf", "02-trial-balance.csv", "03-expense-ledger.csv"]
    if references:
        files = []
    files += [invoice["invoice_file"] for invoice in invoices]
    for filename in files:
        data = (folder / filename).read_bytes()
        fingerprint = hashlib.sha256(data + code_hash.encode()).hexdigest()
        cache = out / (filename + ".json")
        saved = json.loads(cache.read_text()) if cache.exists() and not fresh else {}
        if saved.get("fingerprint") == fingerprint:
            result = saved["extracted"]
            print("Cached extraction:", filename, flush=True)
        else:
            print("Extracting:", filename, flush=True)
            result = await read_document(data, filename, "demo-" + filename)
            cache.write_text(
                json.dumps({"fingerprint": fingerprint, "extracted": result}, indent=2), encoding="utf-8"
            )
        extracted[filename] = result
        facts = result["facts"]
        expected_entity = (
            "Harbor Properties LLC"
            if scenario == "exceptions" and filename == "invoice-R-302.pdf"
            else manifest["client"]
        )
        check(filename + ": entity", normalized(facts.get("entity")) == normalized(expected_entity))
        findings = validate_document(result, manifest["client"], manifest["period_end"], profile=profile)
        codes = {f["code"] for f in findings if f["severity"] == "blocking"}
        expected_codes = set()
        if scenario == "exceptions" and filename == "invoice-R-302.pdf":
            expected_codes.add("wrong_entity")
        if scenario == "exceptions" and filename == "invoice-L-202.pdf":
            expected_codes.add("vague_services")
        check(filename + ": acceptance findings", codes == expected_codes)
        if filename.startswith("invoice-"):
            invoice = next(i for i in manifest["invoices"] if i["invoice_file"] == filename)
            check(filename + ": invoice type", result["kind"] == "invoice")
            check(filename + ": reference", facts.get("reference") == invoice["reference"])
            check(
                filename + ": amount",
                facts.get("amount") is not None and money(facts["amount"]) == money(invoice["source_amount"]),
            )
            if invoice["scanned"]:
                check(filename + ": vision used", result["pages"][0]["method"] == "vision")
        elif filename.startswith("01-"):
            for field, expected in {
                "service": "year_end_audit",
                "framework": "US GAAP",
                "issuer": False,
                "first_year": False,
                "period_end": "2025-12-31",
                "stage": "growth",
            }.items():
                check("letter: " + field, facts.get(field) == expected)
        save_report()
        print("Checks so far:", sum(c["passed"] for c in checks), "/", len(checks), flush=True)

    ledger = (
        extracted["03-expense-ledger.csv"]["transactions"]
        if "03-expense-ledger.csv" in extracted
        else spreadsheet(
            (folder / "03-expense-ledger.csv").read_bytes(), ".csv", "demo-03-expense-ledger.csv"
        )["transactions"]
    )
    check(
        "population total", sum(money(t["amount"]) for t in ledger) == money(manifest["expected_population"])
    )
    engagement = SimpleNamespace(name=manifest["client"], period_end=manifest["period_end"], overrides={})
    for invoice in invoices:
        filename, reference = invoice["invoice_file"], invoice["reference"]
        source = extracted[filename]
        findings = validate_document(source, engagement.name, engagement.period_end, profile=profile)
        # Acceptance here is only a test-fixture state in memory, never a real reviewer approval.
        document = SimpleNamespace(
            id="demo-" + filename,
            filename=filename,
            extracted=source,
            status="needs_attention" if any(f["severity"] == "blocking" for f in findings) else "accepted",
            findings=findings,
        )
        transaction = next(t for t in ledger if t["ref"] == reference)
        fingerprint = hashlib.sha256(
            json.dumps([source, transaction, code_hash], sort_keys=True).encode()
        ).hexdigest()
        cache = out / (reference + "-assertions.json")
        saved = json.loads(cache.read_text()) if cache.exists() and not fresh else {}
        if saved.get("fingerprint") == fingerprint:
            result = saved["result"]
            print("Cached assertions:", reference, flush=True)
        else:
            print("Testing invoice assertions:", reference, flush=True)
            result = await vouch(transaction, document, engagement, profile)
            cache.write_text(
                json.dumps({"fingerprint": fingerprint, "result": result}, indent=2), encoding="utf-8"
            )
        check(
            reference + ": known amount difference",
            money(result["known_error"]) == money(invoice["known_amount_difference"]),
        )
        if scenario == "clean" or not invoice["expected_findings"]:
            check(reference + ": clean baseline", result["status"] == "clean")
        else:
            assertion = {
                "M-103": "period",
                "L-201": "accuracy",
                "L-202": "validity",
                "R-301": "classification",
                "R-302": "validity",
            }[reference]
            status = result["checks"][assertion]["status"]
            check(
                reference + ": seeded issue stays visible",
                status in ({"exception", "unresolved"} if reference == "L-202" else {"exception"}),
            )
        save_report()
        print("Checks so far:", sum(c["passed"] for c in checks), "/", len(checks), flush=True)
    failed = [c["name"] for c in checks if not c["passed"]]
    save_report(completed=True)
    print(
        json.dumps({"checks": len(checks), "failed": failed, "report": str(out / "report.json")}), flush=True
    )
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=["clean", "exceptions"], default="exceptions")
    parser.add_argument(
        "--references", nargs="+", help="Run a targeted invoice regression using manifest references"
    )
    parser.add_argument(
        "--fresh", action="store_true", help="Repeat live calls instead of reusing unchanged cached results"
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(evaluate(args.scenario, args.fresh, args.references)))
