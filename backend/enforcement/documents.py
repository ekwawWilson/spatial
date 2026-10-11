# ruff: noqa: E501 - the wording of the Schedule's forms reads better unbroken
"""The notices as papers to serve, worded after the Schedule of L.I. 2384
(Forms 47, 48A, 48B, 49 and 50). The Assembly's letterhead replaces the plain
heading when it supplies one."""

from typing import Any
from xml.sax.saxutils import escape

from permits.documents import _document, _facts
from projects import geometry as geo

from . import registry
from .models import Notice

CLOSING = (
    "If you fail to comply with this notice, the District Assembly may take further"
    " enforcement action without further recourse to you.",
    "You may contact the District Assembly if you require further information.",
)


def _lettered(text: str) -> list[str]:
    """Each line of what was typed becomes (a), (b), (c)..."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return [f"({chr(97 + i)}) {line}" for i, line in enumerate(lines[:26])]


def _property(notice: Notice) -> list[tuple[str, str]]:
    case = notice.case
    rows = [
        ("Case", case.number),
        ("Locality", case.project.community or case.project.name),
    ]
    if case.owner_address:
        rows.append(("Address", case.owner_address))
    centre = geo.centre(case.feature_id) if case.feature_id is not None else None
    if centre is not None:
        crs = case.project.crs
        rows.append(("Position", f"E {centre[0]:,.2f}, N {centre[1]:,.2f} ({crs.code} {crs.name})"))
    return rows


def paragraphs(notice: Notice) -> tuple[list[str], list[str]]:
    """(the "whereas" paragraphs, the "take notice that" paragraphs)."""
    case = notice.case
    district = case.project.district.name
    _label, section = registry.CONTRAVENTION_BY_CODE[case.contravention]
    grounds = _lettered(notice.grounds)
    required = _lettered(notice.required)
    by = notice.comply_by.isoformat() if notice.comply_by else "the date the Assembly states"
    contrary = f"The above acts are in contravention of {section}."

    if notice.kind == "enforcement":
        return (
            [
                "The following has come to the attention of the District Assembly in respect of"
                ' the property described in the Schedule ("the Property"):',
                *grounds,
                contrary,
            ],
            [
                f"You are required by the District Assembly to take the remedial actions stated below by {by}:",
                *required,
                "If you fail to comply with this Enforcement Notice within the time stated, the"
                " District Assembly may take further enforcement action without further recourse to you.",
                f"This notice takes effect on {notice.issued_on.isoformat()}.",
                CLOSING[1],
            ],
        )
    if notice.kind == "stop":
        return (
            [
                "The District Assembly's attention has been drawn to the following:",
                *grounds,
                "This Stop Notice / Order for Discontinuance is issued by the District Assembly, in"
                " exercise of its powers under section 160 of the Land Use and Spatial Planning Act,"
                " 2016 (Act 925).",
                contrary,
            ],
            [
                "YOU ARE HEREBY ORDERED to immediately STOP / DISCONTINUE the prohibited activity"
                " mentioned above.",
                *required,
                *CLOSING,
            ],
        )
    if notice.kind == "rectification":
        return (
            [
                f"The District Assembly on {case.opened_on.isoformat()} conducted an inspection of the"
                " property described in the Schedule.",
                f"The District Assembly determined that {case.description or 'the property'} is in"
                " contravention of the District Spatial Development Framework, structure plan, local"
                f" plan or the zoning scheme for {district}.",
                "The reasons for this determination are:",
                *grounds,
            ],
            [
                "You are required to take the following remedial action to bring your Property into"
                " conformity with the District Spatial Development Framework, structure plan, local"
                f" plan or the zoning scheme for {district} by {by}:",
                *required,
                *CLOSING,
            ],
        )
    if notice.kind == "revocation":
        permit = case.permit
        number = permit.number if permit else "—"
        granted = permit.decided_on.isoformat() if permit and permit.decided_on else "—"
        kind = permit.get_kind_display().lower() if permit else "permit"
        return (
            [
                f"{district} on {granted} granted you a {kind} with Permit No. {number}, subject to"
                " the conditions stated in it.",
                "It has come to the attention of the District Assembly that you are in breach of the"
                " following conditions of your permit:",
                *grounds,
                contrary,
                "This Revocation Notice is issued by the District Assembly, in exercise of its powers"
                " in paragraph (d) of section 160 of Act 925 and subregulation (1) of regulation 55 of"
                " L.I. 2384.",
            ],
            [
                "You are required to respond in writing to the District Assembly within"
                f" {registry.SHOW_CAUSE_DAYS} days after receipt of this notice, to show cause why your"
                " permit should not be revoked.",
                *required,
                "If you fail to respond within that time, the District Assembly may take further"
                " enforcement action without recourse to you.",
                CLOSING[1],
            ],
        )
    if notice.kind == "entry":
        return (
            [
                "The District Assembly is taking enforcement action in respect of the property"
                " described in the Schedule, for the following reasons:",
                *grounds,
            ],
            [
                "An authorised officer of the District Assembly will enter the property"
                + (f" on or after {by}" if notice.comply_by else "")
                + ", in exercise of the power of entry under section 164 of the Land Use and Spatial"
                " Planning Act, 2016 (Act 925).",
                f"This notice is given at least {registry.ENTRY_NOTICE_DAYS} days before entry, as"
                " regulation 58 of L.I. 2384 requires.",
                *required,
                CLOSING[1],
            ],
        )
    return (
        [
            "The following has come to the attention of the District Assembly in respect of the"
            " property described in the Schedule:",
            *grounds,
            contrary,
        ],
        [f"You are required to take the following action by {by}:", *required, *CLOSING],
    )


def notice_pdf(notice: Notice) -> bytes:
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer

    spec = registry.NOTICE_BY_CODE[notice.kind]
    case = notice.case
    district = case.project.district.name
    doc, buffer, styles = _document(f"{spec.label} {case.number}")
    body = styles["BodyText"]
    indent = body.clone("indent", leftIndent=10 * mm)
    form = f"Form {spec.form}, " if spec.form else ""
    story: list[Any] = [
        Paragraph(escape(district), styles["Title"]),
        Paragraph(escape(spec.label.upper()), styles["Heading2"]),
        Paragraph(f"({form}{escape(spec.rule)}, L.I. 2384)", styles["Italic"]),
        Spacer(1, 3 * mm),
        Paragraph(f"<b>Issued by:</b> {escape(district)}", body),
        Paragraph(
            "<b>To:</b> "
            + escape(
                ", ".join(v for v in (case.owner_name, case.owner_address) if v)
                or "The owner or occupier"
            ),
            body,
        ),
        Spacer(1, 3 * mm),
    ]
    whereas, take_notice = paragraphs(notice)
    number = 0
    for heading, block in (("WHEREAS", whereas), ("NOW THEREFORE TAKE NOTICE THAT", take_notice)):
        story.append(Paragraph(f"<b>{heading}</b>", body))
        for text in block:
            if text.startswith("(") and text[2:3] == ")":
                story.append(Paragraph(escape(text), indent))
            else:
                number += 1
                story.append(Paragraph(f"{number}. {escape(text)}", body))
        story.append(Spacer(1, 2 * mm))
    line = "." * 50
    story += [
        Spacer(1, 6 * mm),
        Paragraph(f"Date: {notice.issued_on.isoformat()}", body),
        Paragraph(f"Signature: {line}", body),
        Paragraph(f"Name: {line}", body),
        Paragraph(f"CHIEF EXECUTIVE, {escape(district)}", body),
        Spacer(1, 6 * mm),
        Paragraph("<b>Schedule: the Property</b>", body),
        _facts(_property(notice)),
    ]
    doc.build(story)
    return buffer.getvalue()
