import hashlib
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection, transaction
from django.db.models import Count, Max, QuerySet
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import (
    district_permission,
    has_permission,
    request_user,
    require_district_id,
)
from core.schema import DISTRICT_HEADER
from crs.models import CoordinateSystem
from crs.services import resolve_default, transform_geojson

from . import boundary as boundaries
from . import editing, traverse
from . import geometry as geo
from . import schema as schema_rules
from .models import Feature, Layer, PlanProject
from .serializers import (
    BoundarySerializer,
    BoundaryStatusSerializer,
    FeatureWriteSerializer,
    GeoJSONFeatureSerializer,
    LayerOrderSerializer,
    LayerSerializer,
    MergeSerializer,
    ProjectSerializer,
    RestoreSerializer,
    SplitSerializer,
    TraverseSerializer,
)

SAFE_ACTIONS = {"list", "retrieve", "extent", "features", "boundary", "history"}
MAX_FEATURES_PER_PAGE = 10_000


def permissions_for(view: Any, edit_code: str) -> list[BasePermission]:
    safe = view.action in SAFE_ACTIONS and view.request.method in ("GET", "HEAD", "OPTIONS")
    code = "project.view" if safe else edit_code
    return [IsAuthenticated(), district_permission(code)()]


def _drf(exc: DjangoValidationError) -> serializers.ValidationError:
    return serializers.ValidationError(
        exc.message_dict if hasattr(exc, "error_dict") else exc.messages
    )


def incoming_geometry(geometry: Any, crs_code: str | None, layer: Layer) -> Any:
    """A geometry in the layer's CRS: converted (with the platform's operation)
    only when the caller says it's in another CRS, e.g. EPSG:3857 from the map."""
    if geometry is None or not crs_code or crs_code.strip().upper() == layer.crs.code:
        return geometry
    source = CoordinateSystem.objects.filter(code=crs_code.strip().upper(), is_active=True).first()
    if source is None:
        raise serializers.ValidationError(
            {"geometry_crs": f"Unknown coordinate system {crs_code!r}."}
        )
    try:
        converted, _ = transform_geojson(geometry, source, layer.crs)
    except DjangoValidationError as exc:
        raise _drf(exc) from exc
    return converted


def check_not_locked_boundary(feature: Feature) -> None:
    project = PlanProject.objects.filter(boundary_feature=feature).first()
    if project and project.boundary_status != PlanProject.BoundaryStatus.DRAFT:
        raise serializers.ValidationError(
            "This is an agreed or approved planning-area boundary: reopen it before changing it."
        )


# --- Projects ------------------------------------------------------------------------


@extend_schema(parameters=[DISTRICT_HEADER])
class ProjectViewSet(viewsets.ModelViewSet[PlanProject]):  # boundary actions: ProjectBoundaryMixin
    """Plan projects of the current district. Deleting a project archives it."""

    serializer_class = ProjectSerializer
    queryset = PlanProject.objects.none()  # schema hint; get_queryset() is used
    # PUT only for the planning-area boundary action.
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_permissions(self) -> list[BasePermission]:
        return permissions_for(self, "project.edit")

    def get_queryset(self) -> QuerySet[PlanProject]:
        qs = (
            PlanProject.objects.filter(district_id=require_district_id(self.request))
            .select_related("crs")
            .annotate(layer_count=Count("layers"))
            # GROUP BY queries ignore Meta.ordering, so order explicitly.
            .order_by("-updated_at", "id")
        )
        if self.request.query_params.get("include_archived") != "true":
            qs = qs.exclude(status=PlanProject.Status.ARCHIVED)
        return qs

    def perform_create(self, serializer: serializers.BaseSerializer[PlanProject]) -> None:
        district_id = require_district_id(self.request)
        user = request_user(self.request)
        crs = serializer.validated_data.get("crs") or resolve_default(user, district_id).crs
        if crs.district_id not in (None, district_id):
            raise serializers.ValidationError({"crs": "Not available in this district."})
        serializer.save(district_id=district_id, crs=crs, created_by=user)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        if not kwargs.get("partial"):
            return Response(
                {"detail": "Use PATCH to change a project."},
                status=status.HTTP_405_METHOD_NOT_ALLOWED,
            )
        return super().update(request, *args, **kwargs)

    def perform_destroy(self, instance: PlanProject) -> None:
        instance.status = PlanProject.Status.ARCHIVED
        instance.save(update_fields=["status", "updated_at"])

    @extend_schema(request=LayerOrderSerializer, responses={204: None})
    @action(detail=True, methods=["post"], url_path="layer-order")
    def layer_order(self, request: Request, pk: str | None = None) -> Response:
        """Sets the draw order of all the project's layers (first = top)."""
        project = self.get_object()
        data = LayerOrderSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        ids = data.validated_data["layer_ids"]
        existing = set(project.layers.values_list("id", flat=True))
        if set(ids) != existing or len(ids) != len(existing):
            raise serializers.ValidationError(
                {"layer_ids": "List every layer of the project exactly once."}
            )
        for position, layer_id in enumerate(ids):
            Layer.objects.filter(pk=layer_id).update(order=len(ids) - position)
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Layers --------------------------------------------------------------------------


def feature_json(feature: Feature, geometry: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "type": "Feature",
        "id": feature.pk,
        "geometry": geometry,
        "properties": feature.properties,
        "meta": {
            "uuid": str(feature.uuid),
            "version": feature.version,
            "origin": feature.origin,
            "verified": feature.verified,
            "updated_at": feature.updated_at.isoformat(),
        },
    }


FEATURE_LIST_PARAMS = [
    DISTRICT_HEADER,
    OpenApiParameter(
        "geometry",
        str,
        enum=["wgs84", "native"],
        description="wgs84 (default, for maps) or native (exact coordinates of record)",
    ),
    OpenApiParameter("bbox", str, description="minLon,minLat,maxLon,maxLat (WGS 84)"),
    OpenApiParameter("limit", int, description=f"Default 5000, max {MAX_FEATURES_PER_PAGE}"),
    OpenApiParameter("offset", int),
]


@extend_schema(parameters=[DISTRICT_HEADER])
class LayerViewSet(viewsets.ModelViewSet[Layer]):
    """Layers of the current district's projects (filter with ?project=)."""

    serializer_class = LayerSerializer
    queryset = Layer.objects.none()  # schema hint; get_queryset() is used
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    pagination_class = None

    def get_permissions(self) -> list[BasePermission]:
        if self.action == "features" and self.request.method == "POST":
            return [IsAuthenticated(), district_permission("feature.edit")()]
        return permissions_for(self, "layer.edit")

    def get_queryset(self) -> QuerySet[Layer]:
        qs = (
            Layer.objects.filter(district_id=require_district_id(self.request))
            .select_related("crs")
            .annotate(feature_count=Count("features"))
            # GROUP BY queries ignore Meta.ordering: draw order, top first.
            .order_by("-order", "id")
        )
        project = self.request.query_params.get("project")
        if project:
            if not project.isdigit():
                raise serializers.ValidationError({"project": "Must be a project id."})
            qs = qs.filter(project_id=int(project))
        return qs

    def perform_create(self, serializer: serializers.BaseSerializer[Layer]) -> None:
        project: PlanProject = serializer.validated_data["project"]
        # System admins can see every district's projects; keep new layers in
        # the district the request acts in.
        if project.district_id != require_district_id(self.request):
            raise serializers.ValidationError({"project": "Not a project of this district."})
        crs = serializer.validated_data.get("crs") or project.crs
        if crs.district_id not in (None, project.district_id):
            raise serializers.ValidationError({"crs": "Not available in this district."})
        top = project.layers.aggregate(m=Max("order"))["m"] or 0
        serializer.save(
            district_id=project.district_id,
            crs=crs,
            order=top + 1,
            created_by=request_user(self.request),
            source=Layer.Source.DRAWN,
        )

    def perform_update(self, serializer: serializers.BaseSerializer[Layer]) -> None:
        layer = serializer.instance
        assert layer is not None
        data = serializer.validated_data
        if "crs" in data and data["crs"] != layer.crs and layer.features.exists():
            raise serializers.ValidationError(
                {"crs": "A layer's coordinate system can't change once it has features."}
            )
        if "schema" in data:
            self._check_schema_change(layer, data["schema"])
        serializer.save()

    def _check_schema_change(self, layer: Layer, new_schema: list[dict[str, Any]]) -> None:
        """Refuses changes that would lose or invalidate stored values, listing
        which features block them. Removing a field needs ?confirm_drop=name."""
        old = {f["name"]: f for f in layer.schema}
        new = {f["name"]: f for f in new_schema}
        confirmed = set(filter(None, self.request.query_params.get("confirm_drop", "").split(",")))
        features = Feature.objects.filter(layer=layer)
        errors: list[str] = []
        for name in old.keys() - new.keys():
            holding = features.filter(**{f"properties__{name}__isnull": False}).count()
            if holding and name not in confirmed:
                errors.append(
                    f"Removing '{name}' would delete its value from {holding} feature(s). "
                    f"Confirm with ?confirm_drop={name}."
                )
        for name, field in new.items():
            before = old.get(name)
            if before is None or (
                before["type"] == field["type"] and before.get("choices") == field.get("choices")
            ):
                continue
            values = features.filter(**{f"properties__{name}__isnull": False}).values_list(
                "id", f"properties__{name}"
            )
            bad = schema_rules.incompatible_values(field, values)
            if bad:
                sample = ", ".join(map(str, bad[:20]))
                errors.append(
                    f"'{name}': {len(bad)} existing value(s) don't fit the new definition "
                    f"(features {sample})."
                )
        if errors:
            raise serializers.ValidationError({"schema": errors})
        for name in (old.keys() - new.keys()) & confirmed:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE projects_feature"
                    " SET properties = properties - %s, version = version + 1"
                    " WHERE layer_id = %s AND properties ? %s",
                    [name, layer.pk, name],
                )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def extent(self, request: Request, pk: str | None = None) -> Response:
        """Bounding box of the layer's features, native and WGS 84."""
        return Response(geo.extent(self.get_object()))

    @extend_schema(methods=["GET"], parameters=FEATURE_LIST_PARAMS, responses=OpenApiTypes.OBJECT)
    @extend_schema(
        methods=["POST"], request=FeatureWriteSerializer, responses={201: GeoJSONFeatureSerializer}
    )
    @action(detail=True, methods=["get", "post"])
    def features(self, request: Request, pk: str | None = None) -> Response:
        layer = self.get_object()
        if request.method == "POST":
            return self._create_feature(request, layer)
        return self._list_features(request, layer)

    def _list_features(self, request: Request, layer: Layer) -> Response:
        params = request.query_params
        native = params.get("geometry", "wgs84") == "native"
        try:
            limit = min(int(params.get("limit", 5000)), MAX_FEATURES_PER_PAGE)
            offset = max(int(params.get("offset", 0)), 0)
        except ValueError:
            raise serializers.ValidationError("limit and offset must be numbers.") from None
        qs = Feature.objects.filter(layer=layer)
        bbox = params.get("bbox")
        if bbox:
            try:
                min_x, min_y, max_x, max_y = (float(v) for v in bbox.split(","))
            except ValueError:
                raise serializers.ValidationError(
                    {"bbox": "Use minLon,minLat,maxLon,maxLat."}
                ) from None
            from django.contrib.gis.geos import Polygon

            qs = qs.filter(geom_4326__bboverlaps=Polygon.from_bbox((min_x, min_y, max_x, max_y)))
        total = qs.count()
        page = list(qs.order_by("id")[offset : offset + limit])
        geometries = geo.read_geometries((f.pk for f in page), native=native)
        return Response(
            {
                "type": "FeatureCollection",
                "crs_code": layer.crs.code if native else "EPSG:4326",
                "numberMatched": total,
                "numberReturned": len(page),
                "next_offset": offset + limit if offset + limit < total else None,
                "features": [feature_json(f, geometries.get(f.pk)) for f in page],
            }
        )

    def _create_feature(self, request: Request, layer: Layer) -> Response:
        data = FeatureWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            properties = schema_rules.validate_properties(
                layer.schema, data.validated_data.get("properties", {})
            )
            geometry = incoming_geometry(
                data.validated_data.get("geometry"), data.validated_data.get("geometry_crs"), layer
            )
            if geometry is not None:
                geo.check_geometry(geometry, layer)
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        user = request_user(request)
        feature = Feature.objects.create(
            district_id=layer.district_id,
            layer=layer,
            properties=properties,
            created_by=user,
            updated_by=user,
        )
        geo.write_geometry(feature, geometry)
        native = geo.read_geometries([feature.pk], native=True)[feature.pk]
        return Response(feature_json(feature, native), status=status.HTTP_201_CREATED)


# --- Features ------------------------------------------------------------------------


@extend_schema(parameters=[DISTRICT_HEADER])
class FeatureViewSet(
    mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet[Feature]
):  # Editing actions (history, restore, split, merge) are added below via FeatureEditingMixin.
    """One feature. Geometry is exchanged in the layer's native CRS. Updates
    must send the version they edited; a stale version gets 409 Conflict."""

    queryset = Feature.objects.none()  # schema hint; get_queryset() is used
    # Documents the response shape only; features are serialised by feature_json().
    serializer_class = GeoJSONFeatureSerializer  # type: ignore[assignment]

    def get_permissions(self) -> list[BasePermission]:
        code = (
            "project.view" if self.request.method in ("GET", "HEAD", "OPTIONS") else "feature.edit"
        )
        return [IsAuthenticated(), district_permission(code)()]

    def get_queryset(self) -> QuerySet[Feature]:
        return Feature.objects.filter(district_id=require_district_id(self.request)).select_related(
            "layer", "layer__crs"
        )

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        feature = self.get_object()
        return Response(
            feature_json(feature, geo.read_geometries([feature.pk], native=True)[feature.pk])
        )

    @extend_schema(
        request=FeatureWriteSerializer,
        responses={200: GeoJSONFeatureSerializer, 409: OpenApiTypes.OBJECT},
    )
    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        data = FeatureWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if "version" not in data.validated_data:
            raise serializers.ValidationError({"version": "Send the version you edited."})
        with transaction.atomic():
            feature = get_object_or_404(
                self.get_queryset().select_for_update(of=("self",)), pk=kwargs["pk"]
            )
            if feature.version != data.validated_data["version"]:
                current = geo.read_geometries([feature.pk], native=True)[feature.pk]
                return Response(
                    {
                        "detail": "Someone else changed this feature since you loaded it.",
                        "current": feature_json(feature, current),
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            layer = feature.layer
            check_not_locked_boundary(feature)
            if "geometry" in data.validated_data:
                data.validated_data["geometry"] = incoming_geometry(
                    data.validated_data["geometry"], data.validated_data.get("geometry_crs"), layer
                )
            try:
                if "properties" in data.validated_data:
                    changes = schema_rules.validate_properties(
                        layer.schema, data.validated_data["properties"], partial=True
                    )
                    feature.properties = {**feature.properties, **changes}
                if (
                    "geometry" in data.validated_data
                    and data.validated_data["geometry"] is not None
                ):
                    geo.check_geometry(data.validated_data["geometry"], layer)
            except DjangoValidationError as exc:
                raise _drf(exc) from exc
            feature.version += 1
            feature.updated_by = request_user(request)
            feature.save(update_fields=["properties", "version", "updated_by", "updated_at"])
            if "geometry" in data.validated_data:
                geo.write_geometry(feature, data.validated_data["geometry"])
        native = geo.read_geometries([feature.pk], native=True)[feature.pk]
        return Response(feature_json(feature, native))


# --- Vector tiles ----------------------------------------------------------------------

TILE_SQL = """
WITH bounds AS (SELECT ST_TileEnvelope(%(z)s, %(x)s, %(y)s) AS geom),
tile AS (
    SELECT f.id,
           f.properties,
           ST_AsMVTGeom(ST_Transform(f.geom_4326, 3857), bounds.geom, 4096, 64, true) AS geom
    FROM projects_feature f, bounds
    WHERE f.layer_id = %(layer)s
      AND f.geom_4326 && ST_Transform(bounds.geom, 4326)
)
SELECT ST_AsMVT(tile.*, 'features', 4096, 'geom', 'id') FROM tile WHERE geom IS NOT NULL
"""


class LayerTileView(APIView):
    """Mapbox Vector Tile of one layer (layer name 'features'; feature id = MVT id;
    properties as attributes). Served inside the request's tenant context, so
    row-level security applies to tiles like everything else."""

    def get_permissions(self) -> list[BasePermission]:
        return [IsAuthenticated(), district_permission("project.view")()]

    @extend_schema(
        parameters=[DISTRICT_HEADER],
        responses={(200, "application/vnd.mapbox-vector-tile"): OpenApiTypes.BINARY, 204: None},
    )
    def get(self, request: Request, layer_id: int, z: int, x: int, y: int) -> HttpResponse:
        if not (0 <= z <= 22 and 0 <= x < 2**z and 0 <= y < 2**z):
            raise serializers.ValidationError("Tile coordinates out of range.")
        layer = Layer.objects.filter(pk=layer_id, district_id=require_district_id(request)).first()
        if layer is None:
            raise PermissionDenied("No such layer in this district.")
        stamp = Feature.objects.filter(layer=layer).aggregate(n=Count("id"), t=Max("updated_at"))
        etag = (
            '"'
            + hashlib.sha256(
                f"{layer.pk}/{z}/{x}/{y}/{stamp['n']}/{stamp['t']}".encode()
            ).hexdigest()[:32]
            + '"'
        )
        if request.headers.get("If-None-Match") == etag:
            return HttpResponse(status=304, headers={"ETag": etag})
        with connection.cursor() as cursor:
            cursor.execute(TILE_SQL, {"z": z, "x": x, "y": y, "layer": layer.pk})
            data = bytes(cursor.fetchone()[0] or b"")
        headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
        if not data:
            return HttpResponse(status=204, headers=headers)
        return HttpResponse(
            data, content_type="application/vnd.mapbox-vector-tile", headers=headers
        )


# --- Phase 6: editing, boundaries, traverses -------------------------------------------


class FeatureEditingMixin:
    """History, restore, split and merge for FeatureViewSet."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def history(self, request: Request, pk: str | None = None) -> Response:
        """Every version of the feature, newest first."""
        feature = self.get_object()  # type: ignore[attr-defined]
        return Response(editing.history(feature))

    @extend_schema(request=RestoreSerializer, responses=GeoJSONFeatureSerializer)
    @action(detail=True, methods=["post"])
    def restore(self, request: Request, pk: str | None = None) -> Response:
        """Makes an earlier version current again (as a new version)."""
        data = RestoreSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            feature = self.get_queryset().select_for_update(of=("self",)).get(pk=pk)  # type: ignore[attr-defined]
            check_not_locked_boundary(feature)
            if feature.version != data.validated_data["version"]:
                return Response(
                    {"detail": "Someone else changed this feature since you loaded it."}, status=409
                )
            try:
                feature = editing.restore(
                    feature, data.validated_data["audit_id"], request_user(request)
                )
            except DjangoValidationError as exc:
                raise _drf(exc) from exc
        return Response(
            feature_json(feature, geo.read_geometries([feature.pk], native=True)[feature.pk])
        )

    @extend_schema(request=SplitSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def split(self, request: Request, pk: str | None = None) -> Response:
        """Cuts the feature with a line; returns all the pieces."""
        data = SplitSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            feature = self.get_queryset().select_for_update(of=("self",)).get(pk=pk)  # type: ignore[attr-defined]
            check_not_locked_boundary(feature)
            if feature.version != data.validated_data["version"]:
                return Response(
                    {"detail": "Someone else changed this feature since you loaded it."}, status=409
                )
            blade = incoming_geometry(
                data.validated_data["blade"], data.validated_data.get("blade_crs"), feature.layer
            )
            try:
                pieces = editing.split(feature, blade, request_user(request))
            except DjangoValidationError as exc:
                raise _drf(exc) from exc
        geometries = geo.read_geometries([p.pk for p in pieces], native=True)
        return Response({"features": [feature_json(p, geometries[p.pk]) for p in pieces]})

    @extend_schema(request=MergeSerializer, responses=GeoJSONFeatureSerializer)
    @action(detail=False, methods=["post"])
    def merge(self, request: Request) -> Response:
        """Unites touching features of one layer into one."""
        data = MergeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        ids = data.validated_data["feature_ids"]
        if data.validated_data["keep"] not in ids:
            raise serializers.ValidationError({"keep": "Must be one of the merged features."})
        with transaction.atomic():
            features = list(self.get_queryset().select_for_update(of=("self",)).filter(pk__in=ids))  # type: ignore[attr-defined]
            if len(features) != len(set(ids)):
                raise serializers.ValidationError(
                    {"feature_ids": "Some features don't exist here."}
                )
            for feature in features:
                check_not_locked_boundary(feature)
            keep = next(f for f in features if f.pk == data.validated_data["keep"])
            try:
                merged = editing.merge(features, keep, request_user(request))
            except DjangoValidationError as exc:
                raise _drf(exc) from exc
        return Response(
            feature_json(merged, geo.read_geometries([merged.pk], native=True)[merged.pk])
        )


class ProjectBoundaryMixin:
    """The planning area of a project (ProjectViewSet)."""

    @extend_schema(methods=["GET"], responses=OpenApiTypes.OBJECT)
    @extend_schema(methods=["PUT"], request=BoundarySerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get", "put"])
    def boundary(self, request: Request, pk: str | None = None) -> Response:
        """GET: the validation report. PUT: create or replace the boundary."""
        project = self.get_object()  # type: ignore[attr-defined]
        if request.method == "PUT":
            if not has_permission(request, "project.edit"):
                raise PermissionDenied("Your role in this district does not allow this.")
            data = BoundarySerializer(data=request.data)
            data.is_valid(raise_exception=True)
            layer = boundaries.boundary_layer(project, request_user(request))
            geometry = incoming_geometry(
                data.validated_data["geometry"], data.validated_data.get("geometry_crs"), layer
            )
            try:
                boundaries.set_boundary(
                    project, geometry, data.validated_data["method"], request_user(request)
                )
            except DjangoValidationError as exc:
                raise _drf(exc) from exc
            project.refresh_from_db()
        return Response(boundaries.report(project))

    @extend_schema(request=BoundaryStatusSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="boundary-status")
    def boundary_status(self, request: Request, pk: str | None = None) -> Response:
        """Moves the boundary through draft -> agreed -> approved (or reopens it)."""
        project = self.get_object()  # type: ignore[attr-defined]
        data = BoundaryStatusSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        target = data.validated_data["status"]
        if project.boundary_feature is None:
            raise serializers.ValidationError("Create the boundary first.")
        try:
            code = boundaries.required_permission(project.boundary_status, target)
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        if not has_permission(request, code):
            raise PermissionDenied(
                "Only district administrators can approve a boundary or reopen an approved one."
                if code == "boundary.approve"
                else "Your role in this district does not allow this."
            )
        if target != "draft":
            report = boundaries.report(project)
            if not report["valid"]:
                raise serializers.ValidationError(
                    f"The boundary is invalid: {report['invalid_reason']}"
                )
        project.boundary_status = target
        project.save(update_fields=["boundary_status", "updated_at"])
        return Response(boundaries.report(project))


class TraverseView(APIView):
    """Computes a bearing-and-distance traverse: stations, misclosure, accuracy
    ratio and (optionally) the Bowditch-adjusted polygon. Nothing is saved."""

    @extend_schema(request=TraverseSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request: Request) -> Response:
        data = TraverseSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        legs = [(leg["bearing"], leg["distance"]) for leg in data.validated_data["legs"]]
        try:
            result = traverse.compute(
                tuple(data.validated_data["start"]),
                legs,
                adjust=data.validated_data["adjust"],
                scale_factor=data.validated_data["scale_factor"],
            )
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        return Response({**result.as_dict(), "polygon": traverse.to_polygon(result)})


# Attach the Phase 6 actions to the viewsets (kept in mixins above for readability).
class ProjectWithBoundaryViewSet(ProjectBoundaryMixin, ProjectViewSet):
    pass


class FeatureWithEditingViewSet(FeatureEditingMixin, FeatureViewSet):
    def perform_destroy(self, instance: Feature) -> None:
        check_not_locked_boundary(instance)
        instance.delete()
