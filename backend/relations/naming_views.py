# ruff: noqa: E501 - long calls read better unbroken
from datetime import date
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.permissions import district_permission, request_user, require_district_id
from core.schema import DISTRICT_HEADER
from projects.models import Feature, PlanProject

from . import naming
from .models import StreetName


def _drf(exc: DjangoValidationError) -> serializers.ValidationError:
    if hasattr(exc, "error_dict"):
        return serializers.ValidationError(exc.message_dict)
    return serializers.ValidationError({"detail": exc.messages})


def _day(value: date | None) -> str | None:
    return value.isoformat() if value else None


def street_name_json(item: StreetName) -> dict[str, Any]:
    return {
        "id": item.pk,
        "project": item.project_id,
        "street": item.street_id,
        "name": item.name,
        "basis": item.basis,
        "proposed_by": item.proposed_by,
        "proposed_on": _day(item.proposed_on),
        "consulted_on": _day(item.consulted_on),
        "consultation": item.consultation,
        "decided_on": _day(item.decided_on),
        "decision_note": item.decision_note,
        "published_on": _day(item.published_on),
        "signs_on": _day(item.signs_on),
        "previous_name": item.previous_name,
        "status": item.status,
        "status_label": item.get_status_display(),
    }


class ProposeSerializer(serializers.Serializer[Any]):
    project = serializers.IntegerField()
    street = serializers.IntegerField()
    name = serializers.CharField(max_length=120)
    basis = serializers.CharField(required=False, allow_blank=True)
    proposed_by = serializers.CharField(max_length=200, required=False, allow_blank=True)
    on = serializers.DateField(required=False, help_text="Proposed on. Default: today")


class NamingStepSerializer(serializers.Serializer[Any]):
    on = serializers.DateField(required=False, help_text="Default: today")
    note = serializers.CharField(required=False, allow_blank=True)


class NamingDecisionSerializer(NamingStepSerializer):
    approve = serializers.BooleanField()


class NamingMarkSerializer(serializers.Serializer[Any]):
    step = serializers.ChoiceField(choices=["published", "signs"])
    on = serializers.DateField(required=False, help_text="Default: today")


@extend_schema(parameters=[DISTRICT_HEADER])
class StreetNameViewSet(viewsets.GenericViewSet[StreetName]):
    """Street names from proposal to signs (L.I. 2384 r.28): consulted on,
    approved by the Spatial Planning Committee and then written to the map,
    published, signed."""

    queryset = StreetName.objects.none()
    serializer_class = ProposeSerializer
    PERMISSIONS = {"list": "project.view", "retrieve": "project.view", "decide": "permit.decide"}

    def get_permissions(self) -> list[BasePermission]:
        code = self.PERMISSIONS.get(self.action or "", "relations.edit")
        return [IsAuthenticated(), district_permission(code)()]

    def get_queryset(self) -> QuerySet[StreetName]:
        return StreetName.objects.filter(
            district_id=require_district_id(self.request)
        ).select_related("project", "street")

    @extend_schema(
        parameters=[OpenApiParameter("project", int), OpenApiParameter("status", str)],
        responses=OpenApiTypes.OBJECT,
        operation_id="street_names_list",
    )
    def list(self, request: Request) -> Response:
        qs = self.get_queryset()
        if request.query_params.get("project", "").isdigit():
            qs = qs.filter(project_id=int(request.query_params["project"]))
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return Response({"results": [street_name_json(s) for s in qs[:500]]})

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(street_name_json(self.get_object()))

    @extend_schema(request=ProposeSerializer, responses={201: OpenApiTypes.OBJECT})
    def create(self, request: Request) -> Response:
        data = ProposeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        project = get_object_or_404(
            PlanProject, pk=values["project"], district_id=require_district_id(request)
        )
        street = get_object_or_404(Feature, pk=values["street"], layer__project=project)
        on = values.get("on") or date.today()
        if on > date.today():
            raise serializers.ValidationError({"on": "That date is in the future."})
        try:
            item = naming.propose(
                project,
                street,
                values["name"],
                values.get("basis", ""),
                values.get("proposed_by", ""),
                on,
                request_user(request),
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        body = street_name_json(item)
        body["clashes"] = naming.taken(project, item.name, but=item)
        return Response(body, status=status.HTTP_201_CREATED)

    @extend_schema(request=NamingStepSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def consult(self, request: Request, pk: str | None = None) -> Response:
        """The community has been consulted on the name."""
        item = self.get_object()
        data = NamingStepSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            naming.consult(
                item,
                data.validated_data.get("on") or date.today(),
                data.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return Response(street_name_json(item))

    @extend_schema(request=NamingDecisionSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def decide(self, request: Request, pk: str | None = None) -> Response:
        """The Spatial Planning Committee's decision; an approved name goes onto the map."""
        item = self.get_object()
        data = NamingDecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        try:
            written = naming.decide(
                item,
                values["approve"],
                values.get("on") or date.today(),
                values.get("note", ""),
                request_user(request),
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return Response({**street_name_json(item), **written})

    @extend_schema(request=NamingMarkSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def mark(self, request: Request, pk: str | None = None) -> Response:
        """The approved name published, or its signs put up."""
        item = self.get_object()
        data = NamingMarkSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            naming.mark(
                item, data.validated_data["step"], data.validated_data.get("on") or date.today()
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return Response(street_name_json(item))
