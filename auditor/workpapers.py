"""Readable PDF snapshots of persisted revisions; source data and approval state stay visible."""

import io
import json
from html import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle


def render_workpaper(engagement, revision):
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    styles["BodyText"].fontSize = 9
    styles["BodyText"].leading = 13
    styles["BodyText"].wordWrap = "CJK"
    styles["Heading2"].keepWithNext = True
    styles["Heading3"].keepWithNext = True
    story = []

    def paragraph(value, style="BodyText"):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), styles[style])

    def heading(value):
        story.extend([Spacer(1, 5 * mm), paragraph(value, "Heading2")])

    def table(headers, rows, widths=None):
        if not rows:
            story.append(paragraph("No rows recorded."))
            return
        cells = [[paragraph(value) for value in headers]] + [
            [paragraph(value if value is not None else "Not established") for value in row] for row in rows
        ]
        result = LongTable(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
        result.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf0f7")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.HexColor("#8899aa")),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#dbe1e8")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(result)

    story.append(paragraph("AI Auditor | " + revision.stage.replace("_", " ").title(), "Title"))
    story.append(paragraph(f"{engagement.name} | Year ended {engagement.period_end}"))
    table(
        ["Review record", "Value"],
        [
            ["Status", revision.status.upper()],
            ["Revision", revision.id],
            ["Prepared by", revision.prepared_by],
            ["Prepared at (UTC)", revision.created_at.isoformat()],
            ["Reviewer", revision.approved_by or "Pending"],
            ["Reviewed at (UTC)", revision.approved_at.isoformat() if revision.approved_at else "Pending"],
            ["Input version", revision.input_version],
        ],
        [45 * mm, 125 * mm],
    )
    if revision.stale_reason:
        story.append(paragraph("STALE: " + revision.stale_reason))
    if revision.status != "approved":
        story.append(paragraph("This revision is not approved for downstream reliance."))
    payload = revision.payload
    heading("Findings and limitations")
    for issue in payload.get("findings", []):
        story.append(
            paragraph(f"{issue['severity'].upper()}: {issue['message']} | {issue.get('source', '')}")
        )
    if not payload.get("findings"):
        story.append(
            paragraph("No blocking preparation findings recorded. This does not constitute an audit opinion.")
        )
    if payload.get("review_scope"):
        story.append(paragraph(payload["review_scope"]))
    if payload.get("profile"):
        heading("Engagement profile")
        table(
            ["Field", "Reviewed value"],
            [
                [k.replace("_", " "), json.dumps(v) if isinstance(v, (list, dict)) else v]
                for k, v in payload["profile"].items()
            ],
            [45 * mm, 125 * mm],
        )
    if payload.get("benchmark"):
        heading("Planning basis")
        table(
            ["Measure", "Value"],
            [
                [key.replace("_", " "), payload.get(key)]
                for key in [
                    "benchmark",
                    "benchmark_value",
                    "rate",
                    "materiality",
                    "pm",
                    "pm_rate",
                    "ctt",
                    "engagement_risk",
                ]
            ],
            [55 * mm, 115 * mm],
        )
        story.append(paragraph(payload.get("rationale", "")))
        story.append(paragraph(payload.get("risk_rationale", "")))
    if payload.get("accounts"):
        heading("Account mapping and scope")
        table(
            ["Account", "Balance", "FSLI / risk", "Basis / source"],
            [
                [
                    f"{r['number']} {r['name']}",
                    r["balance"],
                    f"{r.get('fsli') or 'Unresolved'} / {r.get('risk', 'not assessed')}",
                    f"{r.get('scope_reason') or r.get('reason', '')}\n{r.get('source', '')}",
                ]
                for r in payload["accounts"]
            ],
            [47 * mm, 27 * mm, 43 * mm, 53 * mm],
        )
    if payload.get("requests"):
        heading("Client evidence requests")
        table(
            ["Request", "Status", "Reason / policy"],
            [[r["title"], r["status"], r["why"] + " | " + r["source"]] for r in payload["requests"]],
            [70 * mm, 25 * mm, 75 * mm],
        )
    if payload.get("reconciliation"):
        heading("Population reconciliation")
        table(
            ["Account", "GL", "TB", "Difference"],
            [[r["account_number"], r["gl"], r["tb"], r["difference"]] for r in payload["reconciliation"]],
            [44 * mm, 42 * mm, 42 * mm, 42 * mm],
        )
        story.append(
            paragraph(
                f"Provided population: {payload.get('population_value')}; total OpEx: {payload.get('total_opex')}."
            )
        )
    if payload.get("selections"):
        heading("Selected transactions")
        table(
            ["Transaction", "Amount", "Selection reasons / source"],
            [
                [
                    f"{r['account_number']} | {r['ref']}\n{r['date']} | {r['counterparty']}",
                    r["amount"],
                    "; ".join(r["selection_reasons"]) + "\n" + r["source"],
                ]
                for r in payload["selections"]
            ],
            [65 * mm, 25 * mm, 80 * mm],
        )
    if payload.get("results"):
        heading("Expense testing")
        for result in payload["results"]:
            row = result["transaction"]
            story.append(
                paragraph(
                    f"{row['ref']} | {row['counterparty']} | {row['amount']} | {result['status'].upper()}",
                    "Heading3",
                )
            )
            for assertion, check in result["checks"].items():
                story.append(paragraph(f"{assertion}: {check['status']} — {check['reason']}"))
                for source in check.get("sources", []):
                    story.append(
                        paragraph(
                            f"Source: {source.get('filename', source.get('document_id'))}, page {source.get('page', '?')}"
                        )
                    )
            if result.get("disposition_note"):
                note = result["disposition_note"]
                table(
                    ["Reviewer follow-up", "Record"],
                    [
                        ["Disposition", note.get("disposition", "").replace("_", " ")],
                        ["Reviewer", note.get("reviewer", "Not recorded")],
                        ["Follow-up and conclusion", note.get("follow_up", "")],
                        ["Reason", note.get("reason", "")],
                        ["Evidence document IDs", ", ".join(note.get("evidence_document_ids", []))],
                    ],
                    [45 * mm, 125 * mm],
                )
    if payload.get("conclusion"):
        heading("Proposed conclusion")
        story.append(paragraph(payload["conclusion"]))
    heading("Source references")
    for source in payload.get("sources", []):
        story.append(paragraph(json.dumps(source) if isinstance(source, dict) else source))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#536379"))
        canvas.drawString(
            20 * mm, 12 * mm, "Confidential | " + revision.stage + " | " + revision.status.upper()
        )
        canvas.drawRightString(190 * mm, 12 * mm, str(doc.page))
        canvas.restoreState()

    SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title="Audit workpaper",
        author="AI Auditor",
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
