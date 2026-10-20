# ruff: noqa: E501 - the wording of notices reads better unbroken
"""The notice of a meeting (Form 5, r.6) and its minutes."""

from typing import Any
from xml.sax.saxutils import escape

from permits.documents import _document, _facts

from . import registry, services
from .models import Meeting


def _paper(title: str, heading: str, rule: str, district: str, body: list[Any]) -> bytes:
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer

    doc, buffer, styles = _document(title)
    story: list[Any] = [
        Paragraph(escape(district), styles["Title"]),
        Paragraph(escape(heading), styles["Heading2"]),
        Paragraph(f"({escape(rule)}, L.I. 2384)", styles["Italic"]),
        Spacer(1, 4 * mm),
        *body,
    ]
    doc.build(story)
    return buffer.getvalue()


def notice_pdf(meeting: Meeting) -> bytes:
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer

    text = getSampleStyleSheet()["BodyText"]
    name = registry.COMMITTEES[meeting.committee.kind]
    district = meeting.committee.district.name
    body: list[Any] = [
        Paragraph(
            escape(
                f"Notice is given that a meeting of the {name} of {district} will be held on {meeting.held_on.isoformat()}{f' at {meeting.venue}' if meeting.venue else ''}."
            ),
            text,
        ),
        Spacer(1, 3 * mm),
        Paragraph("<b>Agenda</b>", text),
    ]
    for n, item in enumerate(meeting.agenda, start=1):
        body.append(Paragraph(escape(f"{n}. {item['title']}"), text))
    if not meeting.agenda:
        body.append(Paragraph("1. Any other business", text))
    body += [
        Spacer(1, 6 * mm),
        Paragraph("Signature: " + "." * 50, text),
        Paragraph(escape(f"Secretary, {name}"), text),
        Spacer(1, 4 * mm),
        Paragraph("<b>To the members</b>", text),
        _facts(
            [
                (m["name"], registry.OFFICE_LABELS.get(m["office"], ""))
                for m in meeting.committee.members
            ]
            or [("—", "No members recorded")]
        ),
    ]
    return _paper(
        f"Notice of meeting {meeting.held_on}", "NOTICE OF MEETING", "Form 5, r.6", district, body
    )


def minutes_pdf(meeting: Meeting) -> bytes:
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer

    text = getSampleStyleSheet()["BodyText"]
    name = registry.COMMITTEES[meeting.committee.kind]
    district = meeting.committee.district.name
    q = services.quorum(meeting)
    present = [m for m in meeting.committee.members if m["name"] in meeting.attendance]
    body: list[Any] = [
        _facts(
            [
                ("Committee", name),
                ("Held on", meeting.held_on.isoformat()),
                ("Venue", meeting.venue or "—"),
                (
                    "Quorum",
                    f"{'Formed' if q['met'] else 'NOT formed'}: {q['present']} present, {q['needed']} needed ({q['rule']})"
                    + (
                        f"; absent: {'; '.join(q['missing_offices'])}"
                        if q["missing_offices"]
                        else ""
                    ),
                ),
            ]
        ),
        Spacer(1, 3 * mm),
        Paragraph("<b>Present</b>", text),
        _facts(
            [(m["name"], registry.OFFICE_LABELS.get(m["office"], "")) for m in present]
            or [("—", "No attendance recorded")]
        ),
        Spacer(1, 3 * mm),
        Paragraph("<b>Proceedings</b>", text),
    ]
    for n, item in enumerate(meeting.agenda, start=1):
        outcome = registry.OUTCOMES.get(item.get("outcome", ""), "")
        body.append(Paragraph(f"<b>{n}. {escape(item['title'])}</b>", text))
        body.append(Paragraph(escape(f"{outcome}. {item.get('minute') or ''}".strip()), text))
    if meeting.notes:
        body += [
            Spacer(1, 3 * mm),
            Paragraph("<b>Other matters</b>", text),
            Paragraph(escape(meeting.notes), text),
        ]
    body += [
        Spacer(1, 6 * mm),
        Paragraph("Chairperson: " + "." * 40, text),
        Paragraph("Secretary: " + "." * 40, text),
    ]
    return _paper(
        f"Minutes {meeting.held_on}",
        f"MINUTES OF THE MEETING OF THE {name.upper()}",
        "r.6-7",
        district,
        body,
    )
