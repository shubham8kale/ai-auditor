"""Opt-in live check: send one generated synthetic invoice through the actual extraction pipeline.

Run with the project's venv after configuring Groq and confirming inference ZDR.
Uses the free API quota. Never reads real client documents or prints credentials.
"""

import asyncio
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from auditor.ai import AIUnavailable
from auditor.documents import read_document


async def main():
    with Image.new("RGB", (1200, 760), "white") as image:
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=36)
        lines = [
            "SYNTHETIC TEST INVOICE",
            "Vendor: Sample Office Services LLC",
            "Bill to: Example Trading Ltd",
            "Invoice number: TEST-1042",
            "Invoice date: 2025-11-18",
            "Description: Office cleaning services",
            "Total due: USD 1,234.56",
            "Service period: not stated",
        ]
        for index, line in enumerate(lines):
            draw.text((50, 40 + index * 78), line, fill="black", font=font)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
    try:
        result = await read_document(buffer.getvalue(), "synthetic-test.png", "synthetic-groq-smoke")
        facts = result["facts"]
        checks = {
            "invoice_type": result["kind"] == "invoice",
            "entity": facts.get("entity") == "Example Trading Ltd",
            "vendor": facts.get("vendor") == "Sample Office Services LLC",
            "amount": facts.get("amount") == "1234.56",
            "reference": facts.get("reference") == "TEST-1042",
            "date": facts.get("date") == "2025-11-18",
            "unknown_issuer": facts.get("issuer") is None,
            "missing_service_period_not_invented": facts.get("service_start") is None
            and facts.get("service_end") is None,
        }
        report = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
            "passed": all(checks.values()),
            "ai_runs": result["ai_runs"],
        }
        Path("tmp").mkdir(exist_ok=True)
        Path("tmp/groq-smoke-result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report))
        return 0 if report["passed"] else 1
    except AIUnavailable as exc:
        print("AI check failed: " + str(exc))
    except Exception as exc:
        print("AI check failed: " + type(exc).__name__ + "; details suppressed")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
