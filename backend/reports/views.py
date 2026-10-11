import io
from typing import Any
from xml.sax.saxutils import escape

from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import District
from core.permissions import district_permission, require_district_id
from core.schema import DISTRICT_HEADER

from . import services


def _perms() -> list[BasePermission]:
    return [IsAuthenticated(), district_permission("reports.view")()]


@extend_schema(parameters=[DISTRICT_HEADER], responses=OpenApiTypes.OBJECT)
class ComplianceView(APIView):
    """The district's statutory deadlines: permits (L.I. 2384 r.44), requests
    for information (r.64), enforcement steps (r.57) and zoning scheme duties
    (r.29): what is open, what is overdue, and how often the limits are met."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms()

    def get(self, request: Request) -> Response:
        return Response(services.compliance(require_district_id(request)))


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:g}%"


def report_pdf(district: District, data: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Statutory deadlines: {district.name}",
    )

    def table(rows: list[list[str]], widths: list[float]) -> Table:
        made = Table(
            [[Paragraph(escape(str(c)), body) for c in row] for row in rows], colWidths=widths
        )
        made.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return made

    permits, requests = data["permits"], data["requests"]
    decided_in_time = _pct(permits["decided_within_limit_pct"])
    answered_in_time = _pct(requests["answered_within_limit_pct"])
    story: list[Any] = [
        Paragraph(escape(district.name), styles["Title"]),
        Paragraph(
            "Statutory deadlines under the Land Use and Spatial Planning Regulations, 2019"
            " (L.I. 2384)",
            styles["Heading3"],
        ),
        Paragraph(f"As of {data['as_of']}. Counted from the platform's records.", body),
        Spacer(1, 4 * mm),
        table(
            [
                ["Duty", "Open", "Past its date", "Met in time this year"],
                [
                    f"Permit applications: decision within {permits['limit_days']} days (r.44)",
                    str(permits["open"]),
                    str(permits["overdue"]),
                    f"{decided_in_time} of {permits['decided_this_year']} decided",
                ],
                [
                    f"Requests for information: answer within {requests['limit_days']} days (r.64)",
                    str(requests["open"]),
                    str(requests["overdue"]),
                    f"{answered_in_time} of {requests['answered_this_year']} answered",
                ],
                [
                    "Enforcement cases: the steps of r.57",
                    str(data["enforcement"]["open"]),
                    str(data["enforcement"]["overdue"]),
                    "—",
                ],
                [
                    "Zoning schemes: the duties of r.29",
                    str(data["zoning"]["schemes"]),
                    str(data["zoning"]["overdue"]),
                    "—",
                ],
            ],
            [86 * mm, 18 * mm, 26 * mm, 40 * mm],
        ),
        Spacer(1, 3 * mm),
        Paragraph(
            "Average time from receipt to decision this year: "
            + (
                "—"
                if permits["average_days_to_decision"] is None
                else f"{permits['average_days_to_decision']:g} days"
            )
            + f". Applications received this year: {permits['received_this_year']}.",
            body,
        ),
        Paragraph(
            "Public Data Room: "
            + ("open online" if data["dataroom"]["is_open"] else "not open online")
            + f"; {data['dataroom']['published_projects']} project(s) published;"
            f" {data['dataroom']['documents_on_display']} document(s) on display.",
            body,
        ),
    ]
    if permits["late"]:
        story += [
            Spacer(1, 4 * mm),
            Paragraph("Permit applications past a deadline", styles["Heading3"]),
            table(
                [["Application", "Step", "Rule", "Due", "Days late"]]
                + [
                    [r["number"], r["step"], r["rule"], r["due_on"], str(r["days_late"])]
                    for r in permits["late"]
                ],
                [38 * mm, 70 * mm, 20 * mm, 24 * mm, 18 * mm],
            ),
        ]
    late_other = [
        [r["number"], r["step"], r["due_on"] or "—"] for r in data["enforcement"]["late"]
    ] + [
        [r["scheme"], f"{r['duty']} ({r['rule'].split(':')[0]})", r["due_on"]]
        for r in data["zoning"]["late"]
    ]
    if late_other:
        story += [
            Spacer(1, 4 * mm),
            Paragraph("Enforcement steps and zoning duties past their date", styles["Heading3"]),
            table([["Case or scheme", "Step", "Due"], *late_other], [50 * mm, 96 * mm, 24 * mm]),
        ]
    doc.build(story)
    return buffer.getvalue()


@extend_schema(
    parameters=[DISTRICT_HEADER], responses={(200, "application/pdf"): OpenApiTypes.BINARY}
)
class CompliancePdfView(APIView):
    """The same, as a page to print or file: for management meetings and
    for the district's performance assessment."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms()

    def get(self, request: Request) -> HttpResponse:
        district_id = require_district_id(request)
        district = District.objects.get(pk=district_id)
        data = services.compliance(district_id)
        response = HttpResponse(report_pdf(district, data), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="statutory-deadlines-{district.code}-{data["as_of"]}.pdf"'
        )
        return response
