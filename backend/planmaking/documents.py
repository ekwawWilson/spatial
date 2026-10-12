# ruff: noqa: E501 - the wording of notices reads better unbroken
"""The papers of plan-making: the notices of commencement (Form 27), of the
draft open for comment (Form 28) and of approval (Form 29), and the minutes
of a consultation (Form 56). They say what L.I. 2384 r.23, r.25 and r.65
require; the Schedule's own layouts replace them when the Assembly supplies
its forms."""

from typing import Any
from xml.sax.saxutils import escape

from permits.documents import _document, _facts

from . import registry, services
from .models import Consultation, PlanProcess

PAPERS = {
    "commence": "Notice of commencement of a local plan",
    "notice": "Notice of a draft local plan open for comment",
    "publish_approval": "Notice of approval of a local plan",
}


def paragraphs(process: PlanProcess, paper: str) -> list[str]:
    project = process.project
    district = project.district.name
    area = project.community or project.name
    if paper == "commence":
        return [
            f"Notice is given under section 72(7) of the Land Use and Spatial Planning Act, 2016 (Act 925) that the District Spatial Planning Committee of {district} has commenced the preparation of a local plan for {area}.",
            "Owners and occupiers of land, traditional authorities, residents and other interested persons in the area will be consulted, and are invited to give the Committee any information that should be taken into account.",
            "Records of the consultations held will be displayed in the Public Data Room of the Assembly.",
        ]
    if paper == "notice":
        close = services.comments_close(process)
        until = (
            f"not later than {close.isoformat()}"
            if close
            else f"within {registry.COMMENT_DAYS} days of this notice"
        )
        return [
            f"Notice is given under section 75 of the Land Use and Spatial Planning Act, 2016 (Act 925) that a draft local plan for {area} has been completed by the District Spatial Planning Committee of {district}.",
            f"A copy of the draft local plan is open for inspection by the public in the Public Data Room of the Assembly for {registry.COMMENT_DAYS} days.",
            f"Any person may send the Committee comments on the draft, in the manner of Form 59 of the Schedule to L.I. 2384, {until}.",
            "Comments should, as much as possible, be about the matters a local plan specifies under regulation 24: land use, density, building heights, roads and parking, drainage, sanitation, utilities, social services and the protection of the environment.",
        ]
    approved = services.step_date(process, "approve")
    body = [
        f"Notice is given under section 76(1) of the Land Use and Spatial Planning Act, 2016 (Act 925) that the local plan for {area} was approved on {approved.isoformat() if approved else ''}.",
        "The approved local plan may be inspected in the Public Data Room of the Assembly during business hours.",
        "From the date of this notice, physical development in the area shall conform to the approved local plan.",
    ]
    if process.valid_until:
        body.append(f"The local plan is valid until {process.valid_until.isoformat()}.")
    if process.conditions.strip():
        body.append(
            "The approval is subject to these conditions: "
            + "; ".join(line.strip() for line in process.conditions.splitlines() if line.strip())
            + "."
        )
    return body


def _build(
    title: str,
    district: str,
    heading: str,
    rule: str,
    body_text: list[str],
    facts: list[tuple[str, str]],
    schedule: str,
) -> bytes:
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer

    doc, buffer, styles = _document(title)
    body = styles["BodyText"]
    story: list[Any] = [
        Paragraph(escape(district), styles["Title"]),
        Paragraph(escape(heading), styles["Heading2"]),
        Paragraph(f"({escape(rule)}, L.I. 2384)", styles["Italic"]),
        Spacer(1, 4 * mm),
    ]
    for number, text in enumerate(body_text, start=1):
        story.append(Paragraph(f"{number}. {escape(text)}", body))
    line = "." * 50
    story += [
        Spacer(1, 6 * mm),
        Paragraph("Date: " + line[:24], body),
        Paragraph(f"Signature: {line}", body),
        Paragraph(f"For: {escape(district)}", body),
        Spacer(1, 6 * mm),
        Paragraph(f"<b>{escape(schedule)}</b>", body),
        _facts(facts),
    ]
    doc.build(story)
    return buffer.getvalue()


def paper_pdf(process: PlanProcess, paper: str) -> bytes:
    project = process.project
    step = registry.STEP_BY_CODE[paper]
    facts = [
        ("Local plan", project.name),
        ("Area", project.community or project.name),
        ("Prepared by", process.prepared_by or process.get_origin_display()),
    ]
    return _build(
        f"{PAPERS[paper]}: {project.name}",
        project.district.name,
        PAPERS[paper].upper(),
        f"Form {step.form}, {step.rule}",
        paragraphs(process, paper),
        facts,
        "Schedule: the plan",
    )


def minutes_pdf(consultation: Consultation) -> bytes:
    project = consultation.project
    facts = [
        ("Local plan", project.name),
        ("Stage", registry.STAGE_BY_CODE.get(consultation.stage, consultation.stage)),
        ("Held on", consultation.held_on.isoformat()),
        ("Venue", consultation.venue),
        ("Those consulted", consultation.groups or "—"),
        (
            "Number attending",
            "—" if consultation.attendance is None else str(consultation.attendance),
        ),
    ]
    body = ["Issues raised: " + " ".join(consultation.issues.split())]
    if consultation.outcome.strip():
        body.append("Responses and what was agreed: " + " ".join(consultation.outcome.split()))
    return _build(
        f"Minutes of consultation {consultation.held_on.isoformat()}: {project.name}",
        project.district.name,
        "MINUTES OF PUBLIC AND STAKEHOLDER CONSULTATION",
        "Form 56, r.65(2)",
        body,
        facts,
        "Schedule: the consultation",
    )
