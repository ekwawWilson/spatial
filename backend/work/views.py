from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import district_permission, has_permission, request_user, require_district_id
from core.schema import DISTRICT_HEADER

from . import services
from .people import officer_json


def _perms() -> list[BasePermission]:
    return [IsAuthenticated(), district_permission("district.view")()]


def _drf(exc: DjangoValidationError) -> serializers.ValidationError:
    if hasattr(exc, "message_dict"):
        return serializers.ValidationError(exc.message_dict)
    return serializers.ValidationError({"detail": exc.messages})


@extend_schema(
    parameters=[
        DISTRICT_HEADER,
        OpenApiParameter("mine", OpenApiTypes.BOOL, description="Only the records handed to me."),
    ],
    responses=OpenApiTypes.OBJECT,
)
class WorkView(APIView):
    """What needs doing next across the district: permits, land applications,
    enforcement, requests for information, reviews and appeals, committee
    meetings and zoning scheme duties, the most pressing first. District
    administrators also get the district's setup checklist."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms()

    def get(self, request: Request) -> Response:
        district_id = require_district_id(request)
        user = request_user(request)
        rows = services.items(
            district_id,
            lambda code: has_permission(request, code),
            has_permission(request, "data.sensitive"),
        )
        counts = services.summary(rows, user)
        if request.query_params.get("mine") in ("1", "true"):
            rows = [r for r in rows if r["officer"] and r["officer"]["id"] == user.pk]
        out: dict[str, Any] = {"counts": counts, "items": rows, "setup": None}
        if has_permission(request, "membership.manage"):
            out["setup"] = services.setup(district_id)
        return Response(out)


@extend_schema(parameters=[DISTRICT_HEADER], responses=OpenApiTypes.OBJECT)
class OfficersView(APIView):
    """The district's officers a record can be handed to."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms()

    def get(self, request: Request) -> Response:
        return Response(services.officers(require_district_id(request)))


class AssignSerializer(serializers.Serializer[Any]):
    kind = serializers.ChoiceField(choices=sorted(services.ASSIGN_PERMISSION))
    id = serializers.IntegerField()
    officer = serializers.IntegerField(allow_null=True)


@extend_schema(
    parameters=[DISTRICT_HEADER], request=AssignSerializer, responses=OpenApiTypes.OBJECT
)
class AssignView(APIView):
    """Hands a permit application, land application or enforcement case to an
    officer (or, with officer null, takes it back)."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms()

    def post(self, request: Request) -> Response:
        data = AssignSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        kind = str(data.validated_data["kind"])
        if not has_permission(request, services.ASSIGN_PERMISSION[kind]):
            raise PermissionDenied("Your role can't hand this record to an officer.")
        try:
            record = services.assign(
                require_district_id(request),
                kind,
                int(data.validated_data["id"]),
                data.validated_data["officer"],
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return Response({"kind": kind, "id": record.pk, "officer": officer_json(record.officer)})


@extend_schema(
    parameters=[DISTRICT_HEADER, OpenApiParameter("q", OpenApiTypes.STR, required=True)],
    responses=OpenApiTypes.OBJECT,
)
class SearchView(APIView):
    """Projects, applications, cases, requests, properties and street names
    by number or name. Names of people are searched only for roles that may
    see them."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms()

    def get(self, request: Request) -> Response:
        q = str(request.query_params.get("q", ""))
        results = services.search(
            require_district_id(request),
            q,
            lambda code: has_permission(request, code),
            has_permission(request, "data.sensitive"),
        )
        return Response({"q": q.strip(), "results": results})
