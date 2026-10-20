"""The exchange API: read-only planning records for national bodies, in
GeoJSON (WGS 84), with a key the district issues. Keys look like
"<district code>.<secret>": the code says which district's records to read,
the secret proves the caller may. No names or contacts ever leave."""

import hashlib
import hmac
import secrets
from datetime import date
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import F, QuerySet
from django.http import Http404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import District
from core.permissions import district_permission, request_user, require_district_id
from core.schema import DISTRICT_HEADER
from core.tenancy import tenant_context
from enforcement import registry as enforcement_registry
from enforcement.models import Notice
from permits import registry as permit_registry
from permits.models import Application
from planmaking.models import PlanProcess
from projects import geometry as geo
from relations import zoning
from relations.models import LayerRole
from reports import returns

from .models import ExchangeKey

SCOPES = {
    "permits": "Permits decided: number, kind, use, storeys, dates and site",
    "plans": "Local plans approved: name, locality, approval date and planning area",
    "zoning": "Zoning: each zone drawn on the map, with its national code",
    "enforcement": "Enforcement notices served: notice, contravention, dates and place",
    "returns": "The district's periodic return (quarter or year)",
}
MAX_FEATURES = 5000


class KeyRefused(APIException):
    """401: the exchange has no sign-in of its own, so DRF would otherwise
    turn an authentication failure into 403."""

    status_code = 401
    default_detail = "Not a valid key."
    default_code = "not_authenticated"


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def key_json(key: ExchangeKey) -> dict[str, Any]:
    return {
        "id": key.pk,
        "name": key.name,
        "prefix": key.prefix,
        "scopes": key.scopes,
        "created_at": key.created_at.isoformat(),
        "created_by": key.created_by.email if key.created_by else None,
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
        "uses": key.uses,
        "revoked_at": key.revoked_at.isoformat() if key.revoked_at else None,
    }


class KeyWriteSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=200)
    scopes = serializers.ListField(
        child=serializers.ChoiceField(choices=list(SCOPES)), min_length=1
    )


@extend_schema(parameters=[DISTRICT_HEADER])
class KeyViewSet(viewsets.GenericViewSet[ExchangeKey]):
    """Keys for national bodies to read the district's records. The key is
    shown once, when made; revoke it to stop its use."""

    queryset = ExchangeKey.objects.none()
    serializer_class = KeyWriteSerializer
    pagination_class = None

    def get_permissions(self) -> list[BasePermission]:
        return [IsAuthenticated(), district_permission("exchange.manage")()]

    def get_queryset(self) -> QuerySet[ExchangeKey]:
        return ExchangeKey.objects.filter(
            district_id=require_district_id(self.request)
        ).select_related("created_by")

    @extend_schema(responses=OpenApiTypes.OBJECT, operation_id="exchange_keys_list")
    def list(self, request: Request) -> Response:
        return Response({"keys": [key_json(k) for k in self.get_queryset()], "scopes": SCOPES})

    @extend_schema(request=KeyWriteSerializer, responses={201: OpenApiTypes.OBJECT})
    def create(self, request: Request) -> Response:
        data = KeyWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        district = District.objects.get(pk=require_district_id(request))
        secret = secrets.token_urlsafe(32)
        key = ExchangeKey.objects.create(
            district=district,
            name=data.validated_data["name"],
            prefix=secret[:12],
            digest=_digest(secret),
            scopes=sorted(set(data.validated_data["scopes"])),
            created_by=request_user(request),
        )
        return Response(
            {**key_json(key), "key": f"{district.code}.{secret}"}, status=status.HTTP_201_CREATED
        )

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def revoke(self, request: Request, pk: str | None = None) -> Response:
        key = self.get_object()
        if key.revoked_at is None:
            key.revoked_at = timezone.now()
            key.save(update_fields=["revoked_at"])
        return Response(key_json(key))


# --- What a key reads ------------------------------------------------------------------------


def _authorise(request: Request, scope: str) -> ExchangeKey:
    """The key on the request, if it is live and may read this; inside the
    caller's tenant_context for the key's district."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Key "):
        raise KeyRefused('Send the key as "Authorization: Key <key>".')
    code, _, secret = header[4:].strip().partition(".")
    key = ExchangeKey.objects.filter(prefix=secret[:12]).first() if secret else None
    if key is None or not hmac.compare_digest(key.digest, _digest(secret)):
        raise KeyRefused("Not a valid key.")
    if key.district.code.lower() != code.lower():
        raise KeyRefused("Not a valid key.")
    if key.revoked_at is not None:
        raise KeyRefused("This key has been revoked.")
    if scope not in key.scopes:
        raise PermissionDenied(f"This key may not read {scope}.")
    ExchangeKey.objects.filter(pk=key.pk).update(last_used_at=timezone.now(), uses=F("uses") + 1)
    return key


def _since(request: Request) -> date | None:
    text = request.query_params.get("since")
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise serializers.ValidationError({"since": "YYYY-MM-DD."}) from exc


def _collection(features: list[dict[str, Any]], district: District, dataset: str) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "crs_code": "EPSG:4326",
        "district": {"code": district.code, "name": district.name},
        "dataset": dataset,
        "generated_at": timezone.now().isoformat(),
        "count": len(features),
        "truncated": len(features) >= MAX_FEATURES,
        "features": features,
    }


def _permits(since: date | None) -> list[dict[str, Any]]:
    qs = Application.objects.filter(
        status__in=(
            Application.Status.GRANTED,
            Application.Status.ISSUED,
            Application.Status.REFUSED,
        ),
        decided_on__isnull=False,
    ).select_related("project")
    if since:
        qs = qs.filter(decided_on__gte=since)
    apps = list(qs.order_by("decided_on", "id")[:MAX_FEATURES])
    shapes = geo.read_geometries([a.site_id for a in apps if a.site_id], native=False)
    return [
        {
            "type": "Feature",
            "id": a.number,
            "geometry": shapes.get(a.site_id) if a.site_id else None,
            "properties": {
                "number": a.number,
                "kind": a.get_kind_display(),
                "category": permit_registry.CATEGORY_BY_CODE[a.category].label
                if a.category in permit_registry.CATEGORY_BY_CODE
                else a.category,
                "proposed_use": a.proposed_use,
                "storeys": a.proposed_floors,
                "status": a.get_status_display(),
                "locality": a.project.community or a.project.name,
                "received_on": a.received_on.isoformat(),
                "decided_on": a.decided_on.isoformat() if a.decided_on else None,
                "issued_on": a.issued_on.isoformat() if a.issued_on else None,
                "expires_on": a.expires_on.isoformat() if a.expires_on else None,
            },
        }
        for a in apps
    ]


def _plans(since: date | None) -> list[dict[str, Any]]:
    out = []
    processes = PlanProcess.objects.select_related("project")
    for process in processes:
        approved = process.steps.get("approve")
        if not approved or (since and date.fromisoformat(approved["on"]) < since):
            continue
        project = process.project
        shape = (
            geo.read_geometries([project.boundary_feature_id], native=False).get(
                project.boundary_feature_id
            )
            if project.boundary_feature_id
            else None
        )
        out.append(
            {
                "type": "Feature",
                "id": project.pk,
                "geometry": shape,
                "properties": {
                    "name": project.name,
                    "locality": project.community or project.name,
                    "approved_on": approved["on"],
                    "prepared_by": process.get_origin_display(),
                    "valid_until": process.valid_until.isoformat() if process.valid_until else None,
                },
            }
        )
    return out


def _zoning() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for role in LayerRole.objects.filter(role="zoning").select_related("layer", "project"):
        field = str(role.config.get("zone_field", "zone"))
        features = list(role.layer.features.order_by("id")[: MAX_FEATURES - len(out)])
        shapes = geo.read_geometries([f.pk for f in features], native=False)
        for feature in features:
            value = feature.properties.get(field)
            national = zoning.match(value) if value else None
            out.append(
                {
                    "type": "Feature",
                    "id": feature.pk,
                    "geometry": shapes.get(feature.pk),
                    "properties": {
                        "zone": value,
                        "national_code": national.code if national else None,
                        "national_name": national.name if national else None,
                        "plan": role.project.name,
                        "locality": role.project.community or role.project.name,
                    },
                }
            )
        if len(out) >= MAX_FEATURES:
            break
    return out


def _enforcement(since: date | None) -> list[dict[str, Any]]:
    qs = Notice.objects.filter(served_on__isnull=False).select_related("case", "case__project")
    if since:
        qs = qs.filter(served_on__gte=since)
    notices = list(qs.order_by("served_on", "id")[:MAX_FEATURES])
    ids = [n.case.feature_id for n in notices if n.case.feature_id]
    shapes = geo.read_geometries(ids, native=False)
    return [
        {
            "type": "Feature",
            "id": f"{n.case.number}/{n.pk}",
            "geometry": shapes.get(n.case.feature_id) if n.case.feature_id else None,
            "properties": {
                "case": n.case.number,
                "notice": enforcement_registry.NOTICE_BY_CODE[n.kind].label,
                "form": enforcement_registry.NOTICE_BY_CODE[n.kind].form,
                "contravention": enforcement_registry.CONTRAVENTION_BY_CODE[n.case.contravention][
                    0
                ],
                "locality": n.case.project.community or n.case.project.name,
                "served_on": n.served_on.isoformat() if n.served_on else None,
                "comply_by": n.comply_by.isoformat() if n.comply_by else None,
                "complied_on": n.complied_on.isoformat() if n.complied_on else None,
            },
        }
        for n in notices
    ]


class ExchangeView(APIView):
    """One dataset of a district's records, for a key holder: permits,
    plans, zoning or enforcement as GeoJSON (WGS 84), or the return as JSON.
    ?since=YYYY-MM-DD gives only what was decided, approved or served since."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(
        parameters=[
            OpenApiParameter("since", str, description="YYYY-MM-DD"),
            OpenApiParameter("period", str, description="returns only: 2026 or 2026-Q3"),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request: Request, dataset: str) -> Response:
        if dataset not in SCOPES:
            raise Http404
        header = request.headers.get("Authorization", "")
        code = header[4:].strip().partition(".")[0] if header.startswith("Key ") else ""
        district = District.objects.filter(code__iexact=code, is_active=True).first()
        if district is None:
            raise KeyRefused("Not a valid key.")
        with tenant_context(district.pk):
            _authorise(request, dataset)
            since = _since(request)
            if dataset == "returns":
                try:
                    first, last, label = returns.period(
                        request.query_params.get("period") or str(date.today().year)
                    )
                except DjangoValidationError as exc:
                    raise serializers.ValidationError({"period": exc.messages}) from exc
                body: dict[str, Any] = {
                    "district": {"code": district.code, "name": district.name},
                    **returns.build(district.pk, first, last, label),
                }
            elif dataset == "permits":
                body = _collection(_permits(since), district, dataset)
            elif dataset == "plans":
                body = _collection(_plans(since), district, dataset)
            elif dataset == "zoning":
                body = _collection(_zoning(), district, dataset)
            else:
                body = _collection(_enforcement(since), district, dataset)
        return Response(body)
