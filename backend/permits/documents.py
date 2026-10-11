"""The papers an application produces: the acknowledgement of receipt, the
letter after a refusal or deferral, and the permit certificate with its QR
code. Laid out plainly; an Assembly's own letterhead and the exact Schedule
forms (42B, 43C) replace this layout when it supplies them."""

import io
from typing import Any
from xml.sax.saxutils import escape

from django.conf import settings
from django.db import connection

from . import registry
from .models import Application

ACT = (
    "Land Use and Spatial Planning Act, 2016 (Act 925) and the Land Use and Spatial"
    " Planning Regulations, 2019 (L.I. 2384)"
)


def verify_url(application: Application) -> str:
    return f"{settings.WEB_APP_URL}/verify/{application.token}"


def site_facts(application: Application) -> dict[str, Any]:
    """Where the site is, in the project's coordinate system, and its area."""
    if application.site_id is None:
        return {}
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ST_X(ST_Centroid(geom_native)), ST_Y(ST_Centroid(geom_native)),"
            " ST_Area(geom_4326::geography), ST_Dimension(geom_4326)"
            " FROM projects_feature WHERE id = %s",
            [application.site_id],
        )
        row = cursor.fetchone()
    if row is None or row[0] is None:
        return {}
    crs = application.project.crs
    return {
        "easting": round(float(row[0]), 2),
        "northing": round(float(row[1]), 2),
        "crs": f"{crs.code} {crs.name}",
        "area_m2": round(float(row[2]), 1) if row[3] == 2 else None,
    }


def _document(title: str) -> tuple[Any, io.BytesIO, Any]:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=title,
    )
    return doc, buffer, getSampleStyleSheet()


def _facts(rows: list[tuple[str, str]]) -> Any:
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle

    body = getSampleStyleSheet()["BodyText"]
    table = Table(
        [
            [Paragraph(f"<b>{escape(label)}</b>", body), Paragraph(escape(value), body)]
            for label, value in rows
        ],
        colWidths=[48 * mm, 118 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _about(application: Application) -> list[tuple[str, str]]:
    site = site_facts(application)
    rows = [
        ("Application number", application.number),
        ("Applicant", application.applicant_name),
        ("For", registry.CATEGORY_BY_CODE[application.category].label),
        ("Proposed use", application.proposed_use or "—"),
        ("Locality", application.project.community or application.project.name),
    ]
    if application.proposed_floors is not None:
        rows.append(("Storeys", str(application.proposed_floors)))
    if site:
        rows.append(
            (
                "Site (centre)",
                f"E {site['easting']:,.2f}, N {site['northing']:,.2f} ({site['crs']})",
            )
        )
        if site["area_m2"] is not None:
            rows.append(("Site area", f"{site['area_m2']:,.1f} m²"))
    return rows


def acknowledgement(application: Application) -> bytes:
    """The written acknowledgement of receipt (r.44(6)), with the dates the
    Regulations give the Assembly."""
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer

    from . import services

    doc, buffer, styles = _document(f"Acknowledgement {application.number}")
    district = application.project.district
    kind = application.get_kind_display().lower()
    story: list[Any] = [
        Paragraph(escape(district.name), styles["Title"]),
        Paragraph("Physical Planning Department", styles["Heading3"]),
        Spacer(1, 4 * mm),
        Paragraph(
            f"Acknowledgement of receipt: {escape(kind)} application",
            styles["Heading2"],
        ),
        Paragraph(
            f"Your application was received on {application.received_on.isoformat()}. Quote the"
            " application number below whenever you ask about it. This acknowledgement and the"
            " receipt for the processing fee are not a permit: do not start work until the permit"
            " is issued.",
            styles["BodyText"],
        ),
        Spacer(1, 3 * mm),
        _facts(_about(application)),
        Spacer(1, 5 * mm),
        Paragraph("What happens next", styles["Heading3"]),
    ]
    for clock in services.clocks(application):
        if clock["code"] == "acknowledge":
            continue
        story.append(
            Paragraph(
                f"By {clock['due_on']}: {escape(clock['label'])} ({clock['rule']}).",
                styles["BodyText"],
            )
        )
    story += [
        Spacer(1, 6 * mm),
        Paragraph(f"Issued under the {ACT}.", styles["Italic"]),
    ]
    doc.build(story)
    return buffer.getvalue()


def decision_letter(application: Application) -> bytes:
    """r.44(13): the reasons for a refusal or a deferral, in writing, and how to appeal."""
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer

    doc, buffer, styles = _document(f"Decision {application.number}")
    refused = application.status == Application.Status.REFUSED
    story: list[Any] = [
        Paragraph(escape(application.project.district.name), styles["Title"]),
        Paragraph("District Spatial Planning Committee", styles["Heading3"]),
        Spacer(1, 4 * mm),
        Paragraph(f"Application {'refused' if refused else 'deferred'}", styles["Heading2"]),
        _facts(
            [
                *_about(application),
                (
                    "Decided on",
                    application.decided_on.isoformat() if application.decided_on else "—",
                ),
            ]
        ),
        Spacer(1, 4 * mm),
        Paragraph("Reasons", styles["Heading3"]),
        Paragraph(escape(application.reasons).replace("\n", "<br/>"), styles["BodyText"]),
        Spacer(1, 4 * mm),
    ]
    if refused:
        story.append(
            Paragraph(
                "You may ask for a review of this decision within"
                f" {registry.APPEAL_WITHIN_DAYS} days, first to the District Assembly (Form 53),"
                " then to the Regional Coordinating Council, then to the Land Use and Spatial"
                " Planning Authority. An appeal is decided within"
                f" {registry.APPEAL_DECISION_DAYS} days of being filed.",
                styles["BodyText"],
            )
        )
    else:
        story.append(
            Paragraph(
                "The Physical Planning Department will advise you on what is needed for the"
                " application to be considered again.",
                styles["BodyText"],
            )
        )
    doc.build(story)
    return buffer.getvalue()


def certificate(application: Application) -> bytes:
    """The permit certificate (Form 42B for a planning permit, 43C for a
    development permit), with a QR code that leads to the Assembly's own
    record of it."""
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table

    development = application.kind == Application.Kind.DEVELOPMENT
    title = "Development permit" if development else "Planning permit"
    doc, buffer, styles = _document(f"{title} {application.number}")
    widget = QrCodeWidget(verify_url(application))
    left, bottom, right, top = widget.getBounds()
    size = 34 * mm
    qr = Drawing(size, size, transform=[size / (right - left), 0, 0, size / (top - bottom), 0, 0])
    qr.add(widget)

    rows = [
        *_about(application),
        ("Granted on", application.decided_on.isoformat() if application.decided_on else "—"),
        ("Issued on", application.issued_on.isoformat() if application.issued_on else "—"),
        ("Valid until", application.expires_on.isoformat() if application.expires_on else "—"),
    ]
    story: list[Any] = [
        Paragraph(escape(application.project.district.name), styles["Title"]),
        Paragraph(f"{title} certificate", styles["Heading2"]),
        Paragraph(f"(Form {'43C' if development else '42B'}, L.I. 2384)", styles["Italic"]),
        Spacer(1, 4 * mm),
        _facts(rows),
        Spacer(1, 4 * mm),
        Paragraph("Conditions", styles["Heading3"]),
        Paragraph(
            escape(application.conditions or "None beyond the approved drawings.").replace(
                "\n", "<br/>"
            ),
            styles["BodyText"],
        ),
        Spacer(1, 10 * mm),
    ]
    signatories = ["Physical Planning Officer"] + (["Works Engineer"] if development else [])
    line = "." * 44
    story.append(
        Table(
            [
                [
                    Paragraph(f"{line}<br/>{name}<br/>Date:", styles["BodyText"])
                    for name in signatories
                ]
            ],
            colWidths=[83 * mm] * len(signatories),
        )
    )
    story += [
        Spacer(1, 8 * mm),
        Table(
            [
                [
                    qr,
                    Paragraph(
                        "Scan to check this permit against the Assembly's record, or go to:<br/>"
                        f"{escape(verify_url(application))}<br/><br/>"
                        f"Issued under the {ACT}. If the development is not completed by the"
                        " date above, the permit must be renewed.",
                        styles["BodyText"],
                    ),
                ]
            ],
            colWidths=[40 * mm, 126 * mm],
        ),
    ]
    doc.build(story)
    return buffer.getvalue()
