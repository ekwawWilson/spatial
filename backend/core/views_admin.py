import json
from typing import Any

from django.contrib.gis.gdal import GDALException
from django.contrib.gis.geos import GEOSException, GEOSGeometry, MultiPolygon, Polygon
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from .emails import send_invitation, send_password_reset
from .models import AuditLog, District, Membership, Region, Role, User
from .permissions import (
    IsSystemAdmin,
    district_permission,
    is_system_admin,
    request_district_id,
    request_user,
    require_district_id,
)
from .schema import DISTRICT_HEADER
from .serializers import (
    AuditLogSerializer,
    DistrictSerializer,
    MembershipCreateSerializer,
    MembershipSerializer,
    RegionSerializer,
    UserSerializer,
)

SAFE_ACTIONS = {"list", "retrieve"}


class ReadAnyWriteSystemAdmin(viewsets.ModelViewSet[Any]):
    def get_permissions(self) -> list[BasePermission]:
        if self.action in SAFE_ACTIONS:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsSystemAdmin()]


class RegionViewSet(ReadAnyWriteSystemAdmin):
    queryset = Region.objects.all()
    serializer_class = RegionSerializer
    pagination_class = None


class DistrictBoundarySerializer(serializers.Serializer[None]):
    geometry = serializers.JSONField(help_text="GeoJSON Polygon or MultiPolygon in WGS 84")


def _district_boundary(district: District, request: Request) -> Response:
    if request.method == "PUT":
        if not is_system_admin(request):
            raise PermissionDenied("Only system administrators can load district boundaries.")
        data = DistrictBoundarySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            geom = GEOSGeometry(json.dumps(data.validated_data["geometry"]), srid=4326)
        except (ValueError, GEOSException, GDALException) as exc:
            raise serializers.ValidationError(
                {"geometry": f"Not a valid GeoJSON geometry: {exc}"}
            ) from exc
        if isinstance(geom, Polygon):
            geom = MultiPolygon(geom, srid=4326)
        if not isinstance(geom, MultiPolygon) or not geom.valid:
            raise serializers.ValidationError(
                {"geometry": "Must be a valid polygon or multipolygon."}
            )
        district.boundary = geom
        district.save(update_fields=["boundary"])
    return Response(
        {"geometry": json.loads(district.boundary.geojson) if district.boundary else None}
    )


class DistrictViewSet(ReadAnyWriteSystemAdmin):
    """System admins see every district; everyone else sees the districts they
    belong to. Districts are deactivated, never deleted."""

    serializer_class = DistrictSerializer
    queryset = District.objects.none()  # schema hint; get_queryset() is used
    # PUT only for the boundary action; districts themselves use PATCH.
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    pagination_class = None

    @extend_schema(
        methods=["PUT"], request=DistrictBoundarySerializer, responses=OpenApiTypes.OBJECT
    )
    @extend_schema(methods=["GET"], responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get", "put"])
    def boundary(self, request: Request, pk: str | None = None) -> Response:
        """The district's official boundary (WGS 84), used to check planning areas."""
        return _district_boundary(self.get_object(), request)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        if not kwargs.get("partial"):
            return Response(
                {"detail": "Use PATCH to change a district."},
                status=status.HTTP_405_METHOD_NOT_ALLOWED,
            )
        return super().update(request, *args, **kwargs)

    def get_queryset(self) -> QuerySet[District]:
        qs = District.objects.select_related("region")
        if is_system_admin(self.request):
            return qs
        return qs.filter(
            memberships__user=request_user(self.request),
            memberships__is_active=True,
            is_active=True,
        )


class UserViewSet(viewsets.ModelViewSet[User]):
    """System administration of accounts. Users are deactivated, not deleted,
    so their audit history stays attributable."""

    serializer_class = UserSerializer
    queryset = User.objects.none()  # schema hint; get_queryset() is used
    permission_classes = [IsAuthenticated, IsSystemAdmin]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self) -> QuerySet[User]:
        qs = User.objects.all()
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(email__icontains=search.strip())
        return qs

    def perform_create(self, serializer: serializers.BaseSerializer[User]) -> None:
        user = User.objects.create_user(
            email=serializer.validated_data["email"],
            first_name=serializer.validated_data.get("first_name", ""),
            last_name=serializer.validated_data.get("last_name", ""),
            is_system_admin=serializer.validated_data.get("is_system_admin", False),
        )
        serializer.instance = user
        send_password_reset(user)

    def perform_update(self, serializer: serializers.BaseSerializer[User]) -> None:
        if serializer.instance == self.request.user:
            data = serializer.validated_data
            if data.get("is_active") is False or data.get("is_system_admin") is False:
                raise serializers.ValidationError(
                    "You can't deactivate yourself or remove your own system admin rights."
                )
        serializer.save()

    @extend_schema(request=None, responses=UserSerializer)
    @action(detail=True, methods=["post"])
    def unlock(self, request: Request, pk: str | None = None) -> Response:
        user = self.get_object()
        user.failed_login_count = 0
        user.locked_until = None
        user.save(update_fields=["failed_login_count", "locked_until"])
        return Response(UserSerializer(user).data)

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["post"], url_path="send-password-reset")
    def send_password_reset(self, request: Request, pk: str | None = None) -> Response:
        send_password_reset(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(parameters=[DISTRICT_HEADER])
class MembershipViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet[Membership],
):
    """People with access to the current district (X-District-ID).

    Deleting a membership deactivates it. A district always keeps at least one
    active district administrator.
    """

    serializer_class = MembershipSerializer
    queryset = Membership.objects.none()  # schema hint; get_queryset() is used
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self) -> list[BasePermission]:
        code = "membership.view" if self.action in SAFE_ACTIONS else "membership.manage"
        return [IsAuthenticated(), district_permission(code)()]

    def get_queryset(self) -> QuerySet[Membership]:
        district_id = require_district_id(self.request)
        return Membership.objects.filter(district_id=district_id).select_related("user")

    @extend_schema(request=MembershipCreateSerializer, responses={201: MembershipSerializer})
    def create(self, request: Request) -> Response:
        data = MembershipCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        district = get_object_or_404(District, pk=require_district_id(request))
        email = data.validated_data["email"].strip().lower()

        user = User.objects.filter(email=email).first()
        invite = user is None
        if user is None:
            user = User.objects.create_user(
                email=email,
                first_name=data.validated_data.get("first_name", ""),
                last_name=data.validated_data.get("last_name", ""),
            )
        membership, created = Membership.objects.get_or_create(
            user=user, district=district, defaults={"role": data.validated_data["role"]}
        )
        if not created:
            if membership.is_active:
                raise serializers.ValidationError({"email": "This person is already a member."})
            membership.role = data.validated_data["role"]
            membership.is_active = True
            membership.save(update_fields=["role", "is_active"])
        if invite:
            send_invitation(user, district.name, request_user(request))
        return Response(MembershipSerializer(membership).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer: serializers.BaseSerializer[Membership]) -> None:
        membership = serializer.instance
        assert membership is not None
        data = serializer.validated_data
        losing_admin = membership.role == Role.DISTRICT_ADMIN and (
            data.get("role", membership.role) != Role.DISTRICT_ADMIN
            or data.get("is_active", membership.is_active) is False
        )
        if losing_admin:
            self._ensure_another_admin(membership)
        serializer.save()

    def perform_destroy(self, instance: Membership) -> None:
        if instance.role == Role.DISTRICT_ADMIN and instance.is_active:
            self._ensure_another_admin(instance)
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    @staticmethod
    def _ensure_another_admin(membership: Membership) -> None:
        others = Membership.objects.filter(
            district_id=membership.district_id, role=Role.DISTRICT_ADMIN, is_active=True
        ).exclude(pk=membership.pk)
        if not others.exists():
            raise serializers.ValidationError(
                "A district must keep at least one active district administrator."
            )


class CanViewAudit(BasePermission):
    """System admins: always. Others: audit.view in the current district."""

    message = ""

    def has_permission(self, request: Request, view: Any) -> bool:
        if is_system_admin(request):
            return True
        inner = district_permission("audit.view")()
        allowed = inner.has_permission(request, view)
        self.message = inner.message
        return allowed


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet[AuditLog]):
    """Change history. District admins see their district; system admins see
    everything, or one district when X-District-ID is sent."""

    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.none()  # schema hint; get_queryset() is used
    permission_classes = [IsAuthenticated, CanViewAudit]

    @extend_schema(
        parameters=[
            OpenApiParameter("table", str),
            OpenApiParameter("action", str, enum=["INSERT", "UPDATE", "DELETE"]),
            OpenApiParameter("user_id", int),
            OpenApiParameter("row_id", str),
            OpenApiParameter("since", str, description="ISO 8601 date-time"),
            OpenApiParameter("until", str, description="ISO 8601 date-time"),
        ]
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        entries = page if page is not None else queryset
        # One query for the actors' emails instead of one per row.
        user_ids = {entry.user_id for entry in entries if entry.user_id}
        emails = dict(User.objects.filter(id__in=user_ids).values_list("id", "email"))
        context = {**self.get_serializer_context(), "user_emails": emails}
        data = self.get_serializer(entries, many=True, context=context).data
        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    def get_queryset(self) -> QuerySet[AuditLog]:
        qs = AuditLog.objects.all()
        district_id = request_district_id(self.request)
        if district_id is not None:
            qs = qs.filter(district_id=district_id)
        params = self.request.query_params
        for param, field in (("table", "table_name"), ("action", "action"), ("row_id", "row_id")):
            if params.get(param):
                qs = qs.filter(**{field: params[param]})
        if params.get("user_id"):
            try:
                qs = qs.filter(user_id=int(params["user_id"]))
            except ValueError:
                raise serializers.ValidationError({"user_id": "Must be a number."}) from None
        for param, lookup in (("since", "occurred_at__gte"), ("until", "occurred_at__lte")):
            if params.get(param):
                moment = parse_datetime(params[param])
                if moment is None:
                    raise serializers.ValidationError({param: "Use ISO 8601 date-time."})
                qs = qs.filter(**{lookup: moment})
        return qs
