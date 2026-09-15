"""Generate an independent synthetic engagement and varied invoice PDFs for manual evaluation.

These are fictional fixtures, never replacement evidence for a real client.
Use --scenario clean for a baseline; --scenario exceptions seeds named failures in the manifest.
"""

import argparse
import csv
import io
import json
from decimal import Decimal
from pathlib import Path

import pypdfium2 as pdfium
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

CLIENT = "Harbor Supply Co."
TRANSACTIONS = [
    ("6100", "Marketing", "2025-02-14", "North Studio", "M-101", "Product catalog design", "18500.00"),
    (
        "6100",
        "Marketing",
        "2025-06-10",
        "City Media",
        "M-102",
        "Wholesale customer advertising campaign",
        "7200.00",
    ),
    (
        "6100",
        "Marketing",
        "2025-12-31",
        "Print Workshop",
        "M-103",
        "Retail product label printing",
        "4300.00",
    ),
    (
        "6200",
        "Legal fees",
        "2025-04-18",
        "Oak Legal",
        "L-201",
        "Review of warehouse lease renewal",
        "12400.00",
    ),
    (
        "6200",
        "Legal fees",
        "2025-10-30",
        "Oak Legal",
        "L-202",
        "Negotiation of supplier distribution contract",
        "7600.00",
    ),
    (
        "6300",
        "Repairs",
        "2025-03-20",
        "Warehouse Works",
        "R-301",
        "Repair of existing warehouse conveyor drive",
        "41800.00",
    ),
    (
        "6300",
        "Repairs",
        "2025-08-12",
        "Lift Service",
        "R-302",
        "Repairs to existing forklift hydraulic system",
        "20700.00",
    ),
    ("6300", "Repairs", "2025-12-29", "Dock Service", "R-303", "Dock door motor repair", "7500.00"),
]


def pdf_letter(path, client=CLIENT):
    pdf = canvas.Canvas(str(path), pagesize=letter)
    pdf.setFillColor(colors.HexColor("#193b55"))
    pdf.setFont("Helvetica-Bold", 23)
    pdf.drawString(48, 737, "Engagement letter")
    pdf.setFillColor(colors.black)
    text = pdf.beginText(48, 692)
    text.setFont("Helvetica", 11)
    text.setLeading(24)
    for line in [
        "SYNTHETIC EVALUATION FIXTURE - NOT A REAL ENGAGEMENT",
        "",
        f"Client: {client}",
        "Fiscal year: January 1, 2025 through December 31, 2025",
        "",
        "Service: annual year-end financial statement audit under AICPA AU-C standards.",
        "Reporting framework: United States generally accepted accounting principles (US GAAP).",
        "The client is privately held and is not a public securities issuer.",
        "This is the second annual audit by our firm; this is a recurring engagement.",
        "The business is in its growth stage and distributes wholesale consumer goods.",
        "Industry profile: wholesale distribution. No related parties are identified in this letter.",
        "The prior-year materiality benchmark was revenue.",
        "",
        "Agreed by: Morgan Ellis, fictional client officer",
        "Date: January 15, 2026",
    ]:
        text.textLine(line)
    pdf.drawText(text)
    pdf.save()


def invoice(path, row, index, scenario, client=CLIENT):
    _, _, posting_date, vendor, reference, description, recorded = row
    billed_to, service_start, service_end, source_amount = client, posting_date, posting_date, recorded
    expected = []
    if reference == "R-303":
        description = "Repair existing dock door motor: replace worn seals and lubricate. Restores original condition; no new asset or increased capacity."
    if scenario == "exceptions":
        if reference == "L-201":
            source_amount = "12000.00"
            expected.append("accuracy: recorded exceeds source by 400.00")
        if reference == "M-103":
            service_start = service_end = "2026-01-05"
            expected.append("period: service occurred in the following fiscal year")
        if reference == "L-202":
            description = "Services rendered"
            expected.append("acceptance and validity: professional services lack a specific matter")
        if reference == "R-301":
            description = "Purchase and installation of a new warehouse conveyor system"
            expected.append("classification: capital acquisition recorded as repairs")
        if reference == "R-302":
            billed_to = "Harbor Properties LLC"
            expected.append("entity and validity: billed to a different legal entity")
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=letter)
    accent = ["#224767", "#496746", "#825d3d"][index % 3]
    pdf.setFillColor(colors.HexColor(accent))
    pdf.rect(0, 685, 612, 107, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold" if index % 2 else "Times-Bold", 26)
    pdf.drawString(42, 739, vendor)
    pdf.setFont("Helvetica", 13)
    pdf.drawString(42, 707, f"INVOICE {reference}")
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica", 11)
    lines = [
        (640, f"Bill to: {billed_to}"),
        (612, f"Invoice date: {posting_date}"),
        (584, f"Service / delivery dates: {service_start} to {service_end}"),
    ]
    for y, line in lines:
        pdf.drawString(42, y, line)
    pdf.setFillColor(colors.HexColor("#f0f3f6"))
    pdf.rect(42, 480, 528, 58, fill=1, stroke=0)
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(52, 520, "Description of goods / services")
    pdf.setFont("Helvetica", 10)
    if len(description) > 75:
        pdf.drawString(52, 501, description[:75])
        pdf.drawString(52, 487, description[75:])
    else:
        pdf.drawString(52, 495, description)
    pdf.setFont("Helvetica", 12)
    pdf.drawString(42, 440, "Quantity: 1")
    pdf.drawRightString(570, 440, f"Unit price: USD {source_amount}")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawRightString(570, 389, f"Total due: USD {source_amount}")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(42, 335, "Payment terms: net 30 days. No tax or additional charges.")
    pdf.setFillColor(colors.HexColor("#67798a"))
    pdf.setFont("Helvetica", 8)
    pdf.drawString(42, 38, "SYNTHETIC EVALUATION FIXTURE - NOT REAL AUDIT EVIDENCE")
    pdf.save()
    content = stream.getvalue()
    scanned = index % 3 == 2
    if scanned:
        with pdfium.PdfDocument(content) as source:
            page = source[0]
            bitmap = page.render(scale=1.5)
            image = bitmap.to_pil().copy()
            scan = canvas.Canvas(str(path), pagesize=letter)
            scan.drawImage(ImageReader(image), 0, 0, width=612, height=792)
            scan.save()
            image.close()
            bitmap.close()
            page.close()
    else:
        path.write_bytes(content)
    return {
        "reference": reference,
        "recorded_amount": recorded,
        "source_amount": source_amount,
        "known_amount_difference": str(Decimal(recorded) - Decimal(source_amount)),
        "expected_findings": expected,
        "invoice_file": path.name,
        "scanned": scanned,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=["clean", "exceptions"], default="exceptions")
    parser.add_argument("--client-name", default=CLIENT, help="Distinct fictional entity for a separate demo")
    args = parser.parse_args()
    client = args.client_name.strip()
    if not client or len(client) > 60 or any(c in client for c in "\r\n"):
        parser.error("Client name must contain 1–60 characters on one line.")
    root = Path("data/demo") / args.scenario
    root.mkdir(parents=True, exist_ok=True)
    pdf_letter(root / "01-engagement-letter.pdf", client)
    with (root / "02-trial-balance.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerows(
            [
                [client],
                ["Trial balance as of 2025-12-31"],
                ["Synthetic Ledger System export; USD"],
                ["Account number", "Account name", "Balance"],
                ["1000", "Operating checking", "125000"],
                ["1100", "Accounts receivable", "85000"],
                ["1200", "Inventory", "140000"],
                ["2000", "Accounts payable", "-90000"],
                ["3000", "Retained earnings", "-60000"],
                ["4000", "Revenue", "-1000000"],
                ["5000", "Cost of goods sold", "680000"],
                ["6100", "Marketing", "30000"],
                ["6200", "Legal fees", "20000"],
                ["6300", "Repairs", "70000"],
            ]
        )
    with (root / "03-expense-ledger.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerows(
            [
                [client],
                ["Full fiscal year: 2025-01-01 through 2025-12-31"],
                ["Synthetic Ledger System export; all transactions in accounts 6100, 6200 and 6300; USD"],
                ["Account number", "Account name", "Date", "Vendor", "Reference", "Description", "Amount"],
                *TRANSACTIONS,
            ]
        )
    expected = [
        invoice(root / f"invoice-{row[4]}.pdf", row, i, args.scenario, client)
        for i, row in enumerate(TRANSACTIONS)
    ]
    manifest = {
        "synthetic": True,
        "client": client,
        "period_end": "2025-12-31",
        "scenario": args.scenario,
        "expected_materiality": "10000.00",
        "expected_pm": "6500.00",
        "expected_ctt": "500.00",
        "expected_population": "120000.00",
        "expected_selections": 8,
        "invoices": expected,
        "note": "This small fixture intentionally selects all eight expenses. Independent unit tests cover partial sampling. PBC requests beyond these inputs remain open.",
    }
    (root / "expected-results.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Created 11 synthetic source files and expected-results.json in {root}")


if __name__ == "__main__":
    main()
