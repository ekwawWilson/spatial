import csv
import io
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models import QuerySet
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Membership
from core.permissions import district_permission, has_permission, request_user, require_district_id
from core.schema import DISTRICT_HEADER
from projects import boundary as boundaries
from projects.models import PlanProject

from . import services
from .models import Attachment, Item, Template, TemplateItem

MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024


def _perms(code: str) -> list[BasePermission]:
    return [IsAuthenticated(), district_permission(code)()]


def _project(request: Request, project_id: int) -> PlanProject:
    return get_object_or_404(PlanProject, pk=project_id, district_id=require_district_id(request))


def item_row(item: Item) -> dict[str, Any]:
    project = item.project
    report = boundaries.report(project)
    boundary_feature_id = project.boundary_feature_id if report.get("exists") else None
    evaluation = services.evaluate(item, report, boundary_feature_id)
    return services.item_json(item, evaluation, timezone.localdate())


class ItemUpdateSerializer(serializers.ModelSerializer[Item]):
    class Meta:
        model = Item
        fields = ["status", "owner", "due_date", "notes", "linked_layer"]


class AttachmentUploadSerializer(serializers.Serializer[Any]):
    file = serializers.FileField()


class TemplateItemSerializer(serializers.ModelSerializer[TemplateItem]):
    class Meta:
        model = TemplateItem
        fields = [
            "id",
            "group",
            "key",
            "title",
            "description",
            "kind",
            "domain",
            "geometry_type",
            "rules",
            "order",
        ]

    def validate_rules(self, rules: Any) -> Any:
        allowed = {
            "min_features",
            "min_coverage",
            "min_attributes",
            "max_age_days",
            "min_verified",
            "boundary_status",
            "no_overlaps",
        }
        if not isinstance(rules, dict):
            raise serializers.ValidationError("Rules must be an object.")
        unknown = set(rules) - allowed
        if unknown:
            raise serializers.ValidationError(f"Unknown rule(s): {', '.join(sorted(unknown))}.")
        for key in ("min_coverage", "min_attributes", "min_verified"):
            if key in rules and not (
                isinstance(rules[key], (int, float)) and 0 <= rules[key] <= 100
            ):
                raise serializers.ValidationError(f"{key} must be a percentage from 0 to 100.")
        for key in ("min_features", "max_age_days"):
            if key in rules and not (isinstance(rules[key], int) and rules[key] >= 0):
                raise serializers.ValidationError(f"{key} must be a whole number.")
        if "boundary_status" in rules and rules["boundary_status"] not in (
            "draft",
            "agreed",
            "approved",
        ):
            raise serializers.ValidationError("boundary_status must be draft, agreed or approved.")
        return rules

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        if kind == "layer":
            if attrs.get("geometry_type", getattr(self.instance, "geometry_type", "")) not in (
                "point",
                "line",
                "polygon",
            ):
                raise serializers.ValidationError(
                    {"geometry_type": "A layer item needs a geometry type: point, line or polygon."}
                )
        return attrs


# --- Project checklist --------------------------------------------------------------------


@extend_schema(parameters=[DISTRICT_HEADER], responses=OpenApiTypes.OBJECT)
class ChecklistView(APIView):
    """A project's readiness checklist: items with their metrics and rule
    checks, the score, progress per group, and blockers."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.view" if self.request.method == "GET" else "checklist.edit")

    def get(self, request: Request, project_id: int) -> Response:
        return Response(services.checklist(_project(request, project_id)))

    @extend_schema(request=None)
    def post(self, request: Request, project_id: int) -> Response:
        """Adds items that were added to the template after the project started."""
        project = _project(request, project_id)
        added = services.add_missing_items(project)
        return Response({"added": added, **services.checklist(project)})


@extend_schema(
    parameters=[DISTRICT_HEADER, OpenApiParameter("format", str, enum=["csv", "pdf"])],
    responses={200: OpenApiTypes.BINARY},
)
class ChecklistExportView(APIView):
    """The checklist as CSV or PDF."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.view")

    def get(self, request: Request, project_id: int) -> HttpResponse:
        data = services.checklist(_project(request, project_id))
        fmt = request.query_params.get("format", "csv")
        stem = f"checklist-{project_id}-{timezone.localdate().isoformat()}"
        if fmt == "csv":
            response = HttpResponse(csv_bytes(data), content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="{stem}.csv"'
            return response
        if fmt == "pdf":
            response = HttpResponse(pdf_bytes(data), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{stem}.pdf"'
            return response
        raise serializers.ValidationError({"format": "Use csv or pdf."})


STATUS_LABELS = dict(Item.Status.choices)
GROUP_LABELS = dict(Item._meta.get_field("group").choices or [])


def _fmt(value: Any) -> str:
    return "" if value is None else f"{value:.0f}" if isinstance(value, float) else str(value)


def csv_bytes(data: dict[str, Any]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "Group",
            "Item",
            "Status",
            "Complete",
            "Owner",
            "Due",
            "Layer",
            "Features",
            "Coverage %",
            "Attributes %",
            "Verified %",
            "Newest data",
            "Problems",
            "Notes",
        ]
    )
    for item in data["items"]:
        m = item["metrics"] or {}
        writer.writerow(
            [
                GROUP_LABELS.get(item["group"], item["group"]),
                item["title"],
                STATUS_LABELS.get(item["status"], item["status"]),
                "yes" if item["complete"] else "no",
                item["owner_name"] or "",
                item["due_date"] or "",
                m.get("layer_name", ""),
                _fmt(m.get("feature_count")),
                _fmt(m.get("coverage")),
                _fmt(m.get("attributes")),
                _fmt(m.get("verified")),
                (m.get("newest") or "")[:10],
                " ".join(c["problem"] for c in item["checks"] if not c["ok"]),
                item["notes"],
            ]
        )
    writer.writerow([])
    writer.writerow(
        ["Score", f"{data['score']}%", f"{data['complete']} of {data['total']} items complete"]
    )
    # A byte-order mark so Excel opens the UTF-8 file correctly.
    return ("﻿" + out.getvalue()).encode("utf-8")


def pdf_bytes(data: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    small = styles["BodyText"].clone("small", fontSize=8, leading=10)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Readiness checklist: {data['project_name']}",
    )
    story: list[Any] = [
        Paragraph(f"Readiness checklist: {escape(data['project_name'])}", styles["Title"]),
        Paragraph(
            f"Score {data['score']}% ({data['complete']} of {data['total']} items complete)."
            f" Printed {timezone.localdate().isoformat()}.",
            styles["BodyText"],
        ),
        Spacer(1, 4 * mm),
    ]
    if data["blockers"]:
        story.append(Paragraph("Blockers", styles["Heading2"]))
        for blocker in data["blockers"]:
            story.append(
                Paragraph(f"<b>{escape(blocker['title'])}</b>: {escape(blocker['problem'])}", small)
            )
        story.append(Spacer(1, 4 * mm))
    rows: list[list[Any]] = [["Item", "Status", "Owner / due", "Measures", "Problems"]]
    group = None
    group_rows = []
    for item in data["items"]:
        if item["group"] != group:
            group = item["group"]
            group_rows.append(len(rows))
            rows.append(
                [
                    Paragraph(f"<b>{escape(GROUP_LABELS.get(group, group))}</b>", small),
                    "",
                    "",
                    "",
                    "",
                ]
            )
        m = item["metrics"] or {}
        measures = []
        if "feature_count" in m:
            measures.append(f"{m['feature_count']} features")
            for key, label in (
                ("coverage", "coverage"),
                ("attributes", "attributes"),
                ("verified", "verified"),
            ):
                if m.get(key) is not None:
                    measures.append(f"{m[key]:.0f}% {label}")
        elif "exists" in m:
            measures.append(
                f"{m['status']}, {m['area_ha']:.2f} ha" if m["exists"] else "no boundary"
            )
        rows.append(
            [
                Paragraph(("✓ " if item["complete"] else "") + escape(item["title"]), small),
                Paragraph(STATUS_LABELS.get(item["status"], item["status"]), small),
                Paragraph(
                    escape(" / ".join(x for x in (item["owner_name"], item["due_date"]) if x)),
                    small,
                ),
                Paragraph(escape(", ".join(measures)), small),
                Paragraph(
                    escape(" ".join(c["problem"] for c in item["checks"] if not c["ok"])), small
                ),
            ]
        )
    table = Table(rows, colWidths=[70 * mm, 25 * mm, 45 * mm, 60 * mm, 72 * mm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for index in group_rows:
        style += [
            ("SPAN", (0, index), (-1, index)),
            ("BACKGROUND", (0, index), (-1, index), colors.HexColor("#dce6f1")),
        ]
    table.setStyle(TableStyle(style))
    story.append(table)
    doc.build(story)
    return buffer.getvalue()


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --- Items and attachments ------------------------------------------------------------------


@extend_schema(parameters=[DISTRICT_HEADER])
class ItemViewSet(
    mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet[Item]
):
    """Checklist items: status, owner, due date, notes, linked layer,
    attachments; and a layer created for the item (the Draw action)."""

    serializer_class = ItemUpdateSerializer
    queryset = Item.objects.none()
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_permissions(self) -> list[BasePermission]:
        if self.action == "retrieve":
            return _perms("project.view")
        if self.action == "create_layer":
            return [*_perms("checklist.edit"), district_permission("layer.edit")()]
        return _perms("checklist.edit")

    def get_queryset(self) -> QuerySet[Item]:
        return Item.objects.filter(district_id=require_district_id(self.request)).select_related(
            "project", "owner", "linked_layer"
        )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(item_row(self.get_object()))

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        item = self.get_object()
        data = ItemUpdateSerializer(item, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        owner = values.get("owner")
        if (
            owner is not None
            and not Membership.objects.filter(
                user=owner, district_id=item.district_id, is_active=True
            ).exists()
        ):
            raise serializers.ValidationError(
                {"owner": "The owner must be a member of this district."}
            )
        layer = values.get("linked_layer")
        if layer is not None and layer.project_id != item.project_id:
            raise serializers.ValidationError({"linked_layer": "Pick a layer of this project."})
        if "status" in values and values["status"] != item.status:
            if "linked_layer" in values:
                item.linked_layer = layer
            problems = services.status_problems(
                item, values["status"], has_permission(request, "checklist.verify")
            )
            if problems:
                raise serializers.ValidationError({"status": problems})
        data.save()
        return Response(item_row(item))

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        if not kwargs.get("partial"):
            return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
        return super().update(request, *args, **kwargs)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="create-layer")
    def create_layer(self, request: Request, pk: str | None = None) -> Response:
        """Creates a layer for a layer item (named after it, in its domain) and links it."""
        item = self.get_object()
        if item.kind != "layer":
            raise serializers.ValidationError("Only map-layer items have a layer.")
        if item.linked_layer_id:
            raise serializers.ValidationError("This item already has a layer.")
        layer = services.create_layer_for(item, request_user(request))
        return Response({"layer": layer.pk, **item_row(item)}, status=status.HTTP_201_CREATED)

    @extend_schema(
        request={"multipart/form-data": AttachmentUploadSerializer}, responses=OpenApiTypes.OBJECT
    )
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def attachments(self, request: Request, pk: str | None = None) -> Response:
        """Attaches a document (e.g. the Assembly resolution) to the item."""
        item = self.get_object()
        data = AttachmentUploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        upload = data.validated_data["file"]
        if upload.size > MAX_ATTACHMENT_BYTES:
            raise serializers.ValidationError({"file": "Attachments are limited to 50 MB."})
        name = Path(upload.name).name or "document"
        attachment = Attachment.objects.create(
            district_id=item.district_id,
            item=item,
            name=name,
            path="",
            size=upload.size,
            uploaded_by=request_user(request),
        )
        relative = Path("readiness") / str(item.district_id) / f"{attachment.pk}-{name}"
        target = Path(settings.MEDIA_ROOT) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as fh:
            for chunk in upload.chunks():
                fh.write(chunk)
        attachment.path = str(relative)
        attachment.save(update_fields=["path"])
        return Response(item_row(item), status=status.HTTP_201_CREATED)


@extend_schema(parameters=[DISTRICT_HEADER])
class AttachmentViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet[Attachment]):
    queryset = Attachment.objects.none()

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.view" if self.action == "download" else "checklist.edit")

    def get_queryset(self) -> QuerySet[Attachment]:
        return Attachment.objects.filter(district_id=require_district_id(self.request))

    @extend_schema(responses={200: OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def download(self, request: Request, pk: str | None = None) -> FileResponse:
        attachment = self.get_object()
        path = Path(settings.MEDIA_ROOT) / attachment.path
        if not attachment.path or not path.is_file():
            raise Http404("The file is missing.")
        return FileResponse(open(path, "rb"), as_attachment=True, filename=attachment.name)

    def perform_destroy(self, instance: Attachment) -> None:
        path = Path(settings.MEDIA_ROOT) / instance.path
        instance.delete()
        if instance.path and path.is_file():
            path.unlink()


# --- District dashboard and template ------------------------------------------------------


@extend_schema(parameters=[DISTRICT_HEADER], responses=OpenApiTypes.OBJECT)
class DashboardView(APIView):
    """Readiness of every active project in the district."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.view")

    def get(self, request: Request) -> Response:
        projects = (
            PlanProject.objects.filter(district_id=require_district_id(request))
            .exclude(status="archived")
            .order_by("name")
        )
        rows = []
        for project in projects:
            data = services.checklist(project)
            rows.append(
                {
                    "project": project.pk,
                    "name": project.name,
                    "status": project.status,
                    "score": data["score"],
                    "complete": data["complete"],
                    "total": data["total"],
                    "groups": data["groups"],
                    "blockers": data["blockers"],
                }
            )
        return Response(
            {
                "score": round(sum(r["score"] for r in rows) / len(rows)) if rows else 0,
                "projects": rows,
            }
        )


@extend_schema(parameters=[DISTRICT_HEADER], responses=OpenApiTypes.OBJECT)
class TemplateView(APIView):
    """The checklist template used for the district's new projects: its own
    (after customising) or the platform default. DELETE reverts to the default."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("project.view" if self.request.method == "GET" else "checklist.template")

    def get(self, request: Request) -> Response:
        template = services.template_for(require_district_id(request))
        return Response(template_json(template))

    @extend_schema(request=None)
    def post(self, request: Request) -> Response:
        """Makes the district's own copy of the default template to edit."""
        template = services.customise_template(require_district_id(request))
        return Response(template_json(template), status=status.HTTP_201_CREATED)

    def delete(self, request: Request) -> Response:
        Template.objects.filter(district_id=require_district_id(request)).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def template_json(template: Template | None) -> dict[str, Any]:
    if template is None:
        return {"id": None, "name": None, "own": False, "items": []}
    return {
        "id": template.pk,
        "name": template.name,
        "own": template.district_id is not None,
        "items": TemplateItemSerializer(
            template.items.order_by("group", "order", "id"), many=True
        ).data,
    }


@extend_schema(parameters=[DISTRICT_HEADER])
class TemplateItemViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet[TemplateItem],
):
    """Items of the district's own template. The first change makes the
    district's copy of the default. Projects keep their own copies, so
    changes here apply to new projects (and to "add missing items")."""

    serializer_class = TemplateItemSerializer
    queryset = TemplateItem.objects.none()
    http_method_names = ["post", "patch", "delete", "head", "options"]

    def get_permissions(self) -> list[BasePermission]:
        return _perms("checklist.template")

    def get_queryset(self) -> QuerySet[TemplateItem]:
        return TemplateItem.objects.filter(template__district_id=require_district_id(self.request))

    def perform_create(self, serializer: TemplateItemSerializer) -> None:  # type: ignore[override]
        template = services.customise_template(require_district_id(self.request))
        if template.items.filter(key=serializer.validated_data["key"]).exists():
            raise serializers.ValidationError(
                {"key": "The template already has an item with this key."}
            )
        serializer.save(template=template)

    def get_object(self) -> TemplateItem:
        # Editing an item of the default (before customising) edits the copy.
        pk = self.kwargs["pk"]
        district_id = require_district_id(self.request)
        source = get_object_or_404(TemplateItem, pk=pk)
        if source.template.district_id is None:
            template = services.customise_template(district_id)
            return get_object_or_404(TemplateItem, template=template, key=source.key)
        if source.template.district_id != district_id:
            raise Http404
        return source
