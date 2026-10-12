# ruff: noqa: E501 - the wording of notices reads better unbroken
"""The papers of a land application: the public notice inviting comments,
the notice to the owners of abutting land (Form 35), the decision, and the
notice of an approval to the Lands Commission. They follow what L.I. 2384
r.33 and r.54 require each to say; the Schedule's own layouts replace them
when the Assembly supplies its forms."""

from typing import Any
from xml.sax.saxutils import escape

from permits.documents import _document, _facts

from . import registry, services
from .models import Application

PAPERS = {
    "notice": "Public notice of the application",
    "abutting": "Notice to the owners of abutting land",
    "decision": "Decision",
    "lands": "Notice to the Lands Commission",
}


def what(application: Application) -> str:
    """The application in a sentence."""
    spec = registry.KIND_BY_CODE[application.kind]
    land = ", ".join(p["label"] for p in services.parcels(application)) or "the land described"
    if application.kind == "rezoning":
        return (
            f"the re-zoning of {land} from {application.current_zone or 'its present zone'}"
            f" to {application.proposed_zone}"
        )
    if application.kind == "change_of_use":
        return (
            f"a change of use of {land} from {application.current_use or 'its present use'}"
            f" to {application.proposed_use}"
        )
    if application.kind == "subdivision":
        into = f" into {application.lots} plots" if application.lots else ""
        return f"the subdivision of {land}{into}"
    return f"the {spec.label.lower()} ({land})"


def _about(application: Application) -> list[tuple[str, str]]:
    spec = registry.KIND_BY_CODE[application.kind]
    on_map = services.parcels(application)
    rows = [
        ("Application number", application.number),
        ("For", spec.label),
        ("Applicant", application.applicant_name),
        ("Locality", application.project.community or application.project.name),
        ("Received on", application.received_on.isoformat()),
    ]
    if on_map:
        rows.append(("Land", ", ".join(p["label"] for p in on_map)))
        rows.append(("Area", f"{sum(p['area_m2'] for p in on_map):,.1f} m²"))
    if application.description:
        rows.append(("Proposal", application.description))
    return rows


def paragraphs(application: Application, paper: str) -> tuple[str, str, list[str]]:
    """(title, the rule it is given under, the paragraphs)."""
    spec = registry.KIND_BY_CODE[application.kind]
    district = application.project.district.name
    subject = what(application)
    close = services.comments_close(application)
    until = (
        f"not later than {close.isoformat()}"
        if close
        else f"within {spec.comment_days} days of this notice"
    )
    if paper == "notice":
        rule = "r.33(11)-(13)" if application.kind == "rezoning" else "r.54(2)"
        return (
            f"NOTICE OF AN APPLICATION FOR {spec.label.upper()}",
            rule,
            [
                f"Notice is given that {application.applicant_name} has applied to {district} for {subject}.",
                "A copy of the application may be inspected in the Public Data Room of the Assembly during business hours.",
                f"Any person may send the Assembly a comment, representation or objection on the application, in the manner of Form 59 of the Schedule to L.I. 2384, {until}.",
                "Comments and objections received will be referred to the applicant for a response before the application is decided.",
            ],
        )
    if paper == "abutting":
        return (
            "NOTICE TO OWNERS OF ABUTTING LAND",
            "Form 35, r.33(8)-(10)",
            [
                f"Take notice that {application.applicant_name} has applied to {district} for {subject}.",
                "You are given this notice as the owner of land abutting the land to which the application relates.",
                f"You may send the Assembly a comment or objection on the application {until}.",
                "The application may be inspected in the Public Data Room of the Assembly.",
            ],
        )
    if paper == "decision":
        approved = application.status == Application.Status.APPROVED
        on = application.decided_on.isoformat() if application.decided_on else ""
        body = [
            f"Your application for {subject} was considered by the District Spatial Planning Committee and was {'APPROVED' if approved else 'REFUSED'} on {on}."
        ]
        if approved and application.conditions.strip():
            body.append("The approval is subject to these conditions:")
            body += [
                f"({chr(97 + i)}) {line.strip()}"
                for i, line in enumerate(application.conditions.splitlines()[:26])
                if line.strip()
            ]
        if approved and application.kind == "rezoning":
            body.append(
                "This approval constitutes a permit by the Assembly (r.33(18)). It will be recorded, published in the Gazette and lodged in the Public Data Room."
            )
        if not approved:
            body.append("The reasons for the refusal are:")
            body += [
                f"({chr(97 + i)}) {line.strip()}"
                for i, line in enumerate(application.reasons.splitlines()[:26])
                if line.strip()
            ]
            body.append(
                "If you are dissatisfied with this decision you may apply for a review of it under section 168 of the Land Use and Spatial Planning Act, 2016 (Act 925)."
            )
        return ("DECISION ON AN APPLICATION", spec.decide_rule, body)
    return (
        f"NOTICE OF APPROVAL OF A {spec.label.upper()}",
        "r.54(12)",
        [
            f"Notice is given to the Lands Commission that {district} on {application.decided_on.isoformat() if application.decided_on else ''} approved {subject}, on the application of {application.applicant_name}.",
            "The Commission is asked to endorse or amend the records at the Land Registry in respect of the land to reflect the approval, within three months of receiving this notice (r.54(13)).",
            *(
                [
                    "The approval is subject to these conditions: "
                    + "; ".join(
                        line.strip() for line in application.conditions.splitlines() if line.strip()
                    )
                    + "."
                ]
                if application.conditions.strip()
                else []
            ),
        ],
    )


def recipient(application: Application, paper: str) -> str:
    if paper == "notice":
        return "The public"
    if paper == "abutting":
        return "The owners of land abutting the land described in the Schedule"
    if paper == "lands":
        return "The Lands Commission"
    return ", ".join(v for v in (application.applicant_name, application.applicant_address) if v)


def paper_pdf(application: Application, paper: str) -> bytes:
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer

    district = application.project.district.name
    title, rule, body_text = paragraphs(application, paper)
    doc, buffer, styles = _document(f"{PAPERS[paper]} {application.number}")
    body = styles["BodyText"]
    indent = body.clone("indent", leftIndent=10 * mm)
    story: list[Any] = [
        Paragraph(escape(district), styles["Title"]),
        Paragraph(escape(title), styles["Heading2"]),
        Paragraph(f"({escape(rule)}, L.I. 2384)", styles["Italic"]),
        Spacer(1, 3 * mm),
        Paragraph(f"<b>To:</b> {escape(recipient(application, paper))}", body),
        Spacer(1, 3 * mm),
    ]
    number = 0
    for text in body_text:
        if text.startswith("(") and text[2:3] == ")":
            story.append(Paragraph(escape(text), indent))
        else:
            number += 1
            story.append(Paragraph(f"{number}. {escape(text)}", body))
    line = "." * 50
    story += [
        Spacer(1, 6 * mm),
        Paragraph("Date: " + line[:24], body),
        Paragraph(f"Signature: {line}", body),
        Paragraph(f"For: {escape(district)}", body),
        Spacer(1, 6 * mm),
        Paragraph("<b>Schedule: the application</b>", body),
        _facts(_about(application)),
    ]
    if paper == "abutting":
        rows = [
            (p["label"], p["owner"] or "Owner not on record")
            for p in services.abutting(application)
        ]
        if rows:
            story += [Spacer(1, 4 * mm), Paragraph("<b>Abutting land</b>", body), _facts(rows)]
    doc.build(story)
    return buffer.getvalue()
