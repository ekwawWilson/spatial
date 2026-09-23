from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q, QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from pyproj import Transformer
from pyproj.exceptions import ProjError
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import District
from core.permissions import (
    has_permission,
    is_system_admin,
    request_district_id,
    request_user,
    require_district_id,
)

from . import services
from .models import (
    CoordinateSystem,
    DistrictCrsSettings,
    PreferredTransformation,
    SystemCrsSettings,
    UserCrsPreference,
)
from .serializers import (
    CoordinateSystemSerializer,
    CustomSystemSerializer,
    DefinitionPreviewSerializer,
    DefinitionSerializer,
    OperationSerializer,
    PinOperationSerializer,
    SetDefaultSerializer,
    TransformRequestSerializer,
    resolved_data,
)


def api_validation(exc: DjangoValidationError) -> serializers.ValidationError:
    return serializers.ValidationError(exc.messages)


def system_by_code(code: str, field: str) -> CoordinateSystem:
    system = CoordinateSystem.objects.filter(code=code.strip().upper(), is_active=True).first()
    if system is None:
        raise serializers.ValidationError({field: f"Unknown coordinate system {code!r}."})
    return system


def can_edit(request: Request, system: CoordinateSystem) -> bool:
    if is_system_admin(request):
        return True
    return (
        system.district_id is not None
        and system.district_id == request_district_id(request)
        and has_permission(request, "crs.manage")
    )


class CoordinateSystemViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet[CoordinateSystem],
):
    """Coordinate systems available in the current district: built-ins, systems
    added for every district, and the district's own. Row-level security hides
    other districts' custom systems."""

    serializer_class = CoordinateSystemSerializer
    queryset = CoordinateSystem.objects.none()  # schema hint; get_queryset() is used
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self) -> QuerySet[CoordinateSystem]:
        qs = CoordinateSystem.objects.all()
        district_id = request_district_id(self.request)
        # System admins bypass RLS; still show only what's relevant here.
        qs = qs.filter(Q(district__isnull=True) | Q(district_id=district_id))
        if self.request.query_params.get("include_inactive") != "true":
            qs = qs.filter(is_active=True)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(code__icontains=search) | Q(name__icontains=search))
        return qs

    @extend_schema(request=CustomSystemSerializer, responses={201: CoordinateSystemSerializer})
    def create(self, request: Request) -> Response:
        data = CustomSystemSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if data.validated_data["scope"] == "global":
            if not is_system_admin(request):
                raise PermissionDenied(
                    "Only system administrators can add systems for every district."
                )
            district = None
        else:
            district_id = require_district_id(request)
            if not has_permission(request, "crs.manage"):
                raise PermissionDenied("Your role in this district does not allow this.")
            district = District.objects.get(pk=district_id)
        try:
            system = services.register_custom(
                name=data.validated_data["name"],
                definition=data.validated_data["definition"],
                notes=data.validated_data["notes"],
                district=district,
                user=request_user(request),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"definition": exc.messages}) from exc
        return Response(CoordinateSystemSerializer(system).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer: serializers.BaseSerializer[CoordinateSystem]) -> None:
        system = serializer.instance
        assert system is not None
        if not can_edit(self.request, system):
            raise PermissionDenied("You can't change this coordinate system.")
        if (
            serializer.validated_data.get("is_active") is False
            and system.pk == services.system_default().pk
        ):
            raise serializers.ValidationError("The system default can't be deactivated.")
        serializer.save()


class ValidateDefinitionView(APIView):
    """Checks a definition and shows how it would be registered, without saving."""

    @extend_schema(request=DefinitionSerializer, responses=DefinitionPreviewSerializer)
    def post(self, request: Request) -> Response:
        data = DefinitionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            crs = services.parse_definition(data.validated_data["definition"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"definition": exc.messages}) from exc
        info = services.describe(crs)
        return Response(
            {
                "name": info["name"],
                "kind": info["kind"],
                "units": info["units"],
                "area_of_use": info["area_of_use"],
                "bounds": info["bounds"],
                "proj4": info["proj4"],
                "epsg": crs.to_epsg(min_confidence=100),
            }
        )


class DefaultsView(APIView):
    """The three configurable defaults and the one in effect for new projects.
    Changing a default never changes existing projects."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        user = request_user(request)
        district_id = request_district_id(request)
        district_setting = (
            DistrictCrsSettings.objects.filter(district_id=district_id)
            .select_related("default_crs")
            .first()
            if district_id
            else None
        )
        user_pref = (
            UserCrsPreference.objects.filter(user=user).select_related("preferred_crs").first()
        )
        return Response(
            {
                "system": CoordinateSystemSerializer(services.system_default()).data,
                "district": CoordinateSystemSerializer(district_setting.default_crs).data
                if district_setting
                else None,
                "user": CoordinateSystemSerializer(user_pref.preferred_crs).data
                if user_pref
                else None,
                "effective": resolved_data(services.resolve_default(user, district_id)),
            }
        )


class SetSystemDefaultView(APIView):
    @extend_schema(request=SetDefaultSerializer, responses={204: None})
    def put(self, request: Request) -> Response:
        if not is_system_admin(request):
            raise PermissionDenied("Only system administrators can change the system default.")
        data = SetDefaultSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        system = data.validated_data["crs"]
        if system is None or system.district_id is not None:
            raise serializers.ValidationError(
                {"crs": "Choose a system available to every district."}
            )
        SystemCrsSettings.objects.update_or_create(pk=1, defaults={"default_crs": system})
        return Response(status=status.HTTP_204_NO_CONTENT)


class SetDistrictDefaultView(APIView):
    @extend_schema(request=SetDefaultSerializer, responses={204: None})
    def put(self, request: Request) -> Response:
        district_id = require_district_id(request)
        if not has_permission(request, "crs.manage"):
            raise PermissionDenied("Your role in this district does not allow this.")
        data = SetDefaultSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        system = data.validated_data["crs"]
        if system is None:
            DistrictCrsSettings.objects.filter(district_id=district_id).delete()
        else:
            if system.district_id not in (None, district_id):
                raise serializers.ValidationError({"crs": "Not available in this district."})
            DistrictCrsSettings.objects.update_or_create(
                district_id=district_id, defaults={"default_crs": system}
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class SetMyDefaultView(APIView):
    @extend_schema(request=SetDefaultSerializer, responses={204: None})
    def put(self, request: Request) -> Response:
        user = request_user(request)
        data = SetDefaultSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        system = data.validated_data["crs"]
        if system is None:
            UserCrsPreference.objects.filter(user=user).delete()
        else:
            if system.district_id is not None:
                raise serializers.ValidationError(
                    {"crs": "Personal defaults must be available in every district."}
                )
            UserCrsPreference.objects.update_or_create(
                user=user, defaults={"preferred_crs": system}
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class TransformView(APIView):
    """Converts points or a GeoJSON geometry between two systems. The response
    names the operation used and its stated accuracy."""

    @extend_schema(request=TransformRequestSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        data = TransformRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        source = system_by_code(data.validated_data["from_crs"], "from_crs")
        target = system_by_code(data.validated_data["to_crs"], "to_crs")
        try:
            if "points" in data.validated_data:
                points, op = services.transform_points(
                    data.validated_data["points"], source, target
                )
                result: dict[str, Any] = {"points": [list(p) for p in points]}
            else:
                geometry, op = services.transform_geojson(
                    data.validated_data["geometry"], source, target
                )
                result = {"geometry": geometry}
        except DjangoValidationError as exc:
            raise api_validation(exc) from exc
        result["operation"] = OperationSerializer(op).data
        return Response(result)


PAIR_PARAMS = [
    OpenApiParameter("from_crs", str, required=True),
    OpenApiParameter("to_crs", str, required=True),
]


class OperationsView(APIView):
    """Candidate operations between two systems, the one currently used, and
    (system admins) pinning a specific one."""

    @extend_schema(parameters=PAIR_PARAMS, responses=OpenApiTypes.OBJECT)
    def get(self, request: Request) -> Response:
        source = system_by_code(request.query_params.get("from_crs", ""), "from_crs")
        target = system_by_code(request.query_params.get("to_crs", ""), "to_crs")
        return Response(
            {
                "current": OperationSerializer(services.describe_operation(source, target)).data,
                "candidates": [
                    OperationSerializer(op).data
                    for op in services.candidate_operations(source, target)
                ],
            }
        )

    @extend_schema(request=PinOperationSerializer, responses={204: None})
    def put(self, request: Request) -> Response:
        if not is_system_admin(request):
            raise PermissionDenied("Only system administrators can pin transformations.")
        data = PinOperationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        source = system_by_code(data.validated_data["from_crs"], "from_crs")
        target = system_by_code(data.validated_data["to_crs"], "to_crs")
        pipeline = data.validated_data["pipeline"]
        try:
            Transformer.from_pipeline(pipeline)
        except ProjError as exc:
            raise serializers.ValidationError(
                {"pipeline": f"Not a valid PROJ pipeline: {exc}"}
            ) from exc
        known = {op.pipeline: op for op in services.candidate_operations(source, target)}
        match = known.get(pipeline)
        # One pin per pair: drop a pin stored for the reverse direction.
        PreferredTransformation.objects.filter(source=target, target=source).delete()
        PreferredTransformation.objects.update_or_create(
            source=source,
            target=target,
            defaults={
                "pipeline": pipeline,
                "name": data.validated_data["name"] or (match.name if match else "Custom pipeline"),
                "accuracy_m": data.validated_data["accuracy_m"]
                if data.validated_data["accuracy_m"] is not None
                else (match.accuracy_m if match else None),
            },
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(parameters=PAIR_PARAMS, responses={204: None})
    def delete(self, request: Request) -> Response:
        if not is_system_admin(request):
            raise PermissionDenied("Only system administrators can pin transformations.")
        source = system_by_code(request.query_params.get("from_crs", ""), "from_crs")
        target = system_by_code(request.query_params.get("to_crs", ""), "to_crs")
        PreferredTransformation.objects.filter(
            Q(source=source, target=target) | Q(source=target, target=source)
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
