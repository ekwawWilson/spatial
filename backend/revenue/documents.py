# ruff: noqa: E501 - the wording of notices reads better unbroken
"""Betterment papers: the notice of betterment (Form 40, r.40(3)), the
betterment assessment notice to each owner (Form 41, r.40(7)), and the
certificate of the sum due or paid (r.41(2)-(4)). They say what the
Regulations require; the Schedule's layouts replace them when the Assembly
supplies its forms."""

from datetime import date
from typing import Any
from xml.sax.saxutils import escape

from permits.documents import _document, _facts

from .models import BettermentCharge, BettermentScheme

PAPERS = {
    "assessment": "Betterment assessment notice",
    "certificate": "Certificate of betterment",
}


def _build(
    title: str,
    district: str,
    heading: str,
    rule: str,
    to: str,
    body: list[str],
    facts: list[tuple[str, str]],
) -> bytes:
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer

    doc, buffer, styles = _document(title)
    text = styles["BodyText"]
    story: list[Any] = [
        Paragraph(escape(district), styles["Title"]),
        Paragraph(escape(heading), styles["Heading2"]),
        Paragraph(f"({escape(rule)}, L.I. 2384)", styles["Italic"]),
        Spacer(1, 3 * mm),
        Paragraph(f"<b>To:</b> {escape(to)}", text),
        Spacer(1, 3 * mm),
    ]
    for number, paragraph in enumerate(body, start=1):
        story.append(Paragraph(f"{number}. {escape(paragraph)}", text))
    line = "." * 50
    story += [
        Spacer(1, 6 * mm),
        Paragraph(f"Date: {date.today().isoformat()}", text),
        Paragraph(f"Signature: {line}", text),
        Paragraph(f"For: {escape(district)}", text),
        Spacer(1, 6 * mm),
        Paragraph("<b>Schedule</b>", text),
        _facts(facts),
    ]
    doc.build(story)
    return buffer.getvalue()


def _basis(scheme: BettermentScheme) -> str:
    if scheme.basis == BettermentScheme.Basis.SUM:
        return f"a sum of GHS {scheme.amount:,.2f} on each bettered property"
    return f"{scheme.amount * 100:g}% of the increase in the value of each bettered property"


def notice_pdf(scheme: BettermentScheme) -> bytes:
    district = scheme.project.district.name
    area = scheme.project.community or scheme.project.name
    body = [
        f"Notice is given that {district} has completed {scheme.name}{f' ({scheme.works})' if scheme.works else ''} at {area}, on {scheme.completed_on.isoformat()}.",
        f"The public works have increased the value of land within {scheme.reach_m:g} metres of them. Under regulation 40 of the Land Use and Spatial Planning Regulations, 2019 (L.I. 2384) the Assembly has fixed a betterment charge of {_basis(scheme)}.",
        "Each owner of an affected property will be served with a betterment assessment notice stating the charge on the property and the mode of payment.",
        "A copy of this notice and of the list of affected properties may be inspected in the Public Data Room of the Assembly.",
    ]
    facts = [
        ("Works", scheme.name),
        ("Locality", area),
        ("Completed on", scheme.completed_on.isoformat()),
        ("Properties affected", str(scheme.charges.count())),
    ]
    return _build(
        f"Notice of betterment: {scheme.name}",
        district,
        "NOTICE OF BETTERMENT",
        "Form 40, r.40(3)",
        "The public, and the owners of land in the area",
        body,
        facts,
    )


def _owner(charge: BettermentCharge) -> str:
    prop = charge.property
    return ", ".join(
        v for v in (prop.owner_name or "The owner", prop.address or f"property {prop.number}") if v
    )


def _property_facts(charge: BettermentCharge) -> list[tuple[str, str]]:
    prop = charge.property
    rows = [
        ("Property", prop.number),
        ("Address", prop.address or "—"),
        ("Works", charge.scheme.name),
        ("Distance from the works", f"{charge.distance_m:,.1f} m"),
    ]
    if charge.increase is not None:
        rows.append(("Increase in value", f"GHS {charge.increase:,.2f}"))
    rows.append(
        (
            "Betterment charge",
            f"GHS {charge.amount:,.2f}" if charge.amount is not None else "to be assessed",
        )
    )
    return rows


def assessment_pdf(charge: BettermentCharge, payment: str) -> bytes:
    scheme = charge.scheme
    district = scheme.project.district.name
    body = [
        f"{district} completed {scheme.name} on {scheme.completed_on.isoformat()}. The works have increased the value of the property described in the Schedule.",
        f"Under regulation 40 of L.I. 2384 the betterment charge on the property is GHS {charge.amount or 0:,.2f}, being {_basis(scheme)}.",
        f"The charge is payable {payment}",
        "A sum certified by the Assembly to be due and payable is recoverable as a civil debt (regulation 41(2)), and may be set off against a claim for compensation (regulation 41(5)).",
    ]
    return _build(
        f"Betterment assessment {charge.property.number}",
        district,
        "BETTERMENT ASSESSMENT NOTICE",
        "Form 41, r.40(7)",
        _owner(charge),
        body,
        _property_facts(charge),
    )


def certificate_pdf(charge: BettermentCharge) -> bytes:
    scheme = charge.scheme
    district = scheme.project.district.name
    owing = (charge.amount or 0) - charge.paid
    if owing <= 0:
        heading, body = (
            "CERTIFICATE OF PAYMENT OF BETTERMENT",
            [
                f"{district} certifies that the betterment charge of GHS {charge.amount or 0:,.2f} on the property described in the Schedule, arising from {scheme.name}, has been paid{f' (last payment on {charge.paid_on.isoformat()})' if charge.paid_on else ''}.",
                "This certificate is conclusive evidence of the facts stated in it (regulation 41(4) of L.I. 2384).",
            ],
        )
    else:
        heading, body = (
            "CERTIFICATE OF BETTERMENT DUE",
            [
                f"{district} certifies that a betterment charge of GHS {charge.amount or 0:,.2f} was assessed on the property described in the Schedule, arising from {scheme.name}; GHS {charge.paid:,.2f} has been paid, and GHS {owing:,.2f} is due and payable.",
                "The sum due is recoverable as a civil debt (regulation 41(2)), and this certificate is conclusive evidence of the facts certified (regulation 41(3) of L.I. 2384).",
            ],
        )
    return _build(
        f"Betterment certificate {charge.property.number}",
        district,
        heading,
        "r.41",
        _owner(charge),
        body,
        _property_facts(charge),
    )
