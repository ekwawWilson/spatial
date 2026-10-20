from datetime import date
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q, QuerySet
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import district_permission, has_permission, request_user, require_district_id
from core.schema import DISTRICT_HEADER
from projects.models import Feature, PlanProject

from . import documents, services
from .models import BettermentCharge, BettermentScheme, Bill, Property, RateBand, Use

HIDDEN = "restricted"
MAX_CSV_BYTES = 20 * 1024 * 1024


def _perms(code: str) -> list[BasePermission]:
    return [IsAuthenticated(), district_permission(code)()]


def _drf(exc: DjangoValidationError) -> serializers.ValidationError:
    if hasattr(exc, "error_dict"):
        return serializers.ValidationError(exc.message_dict)
    return serializers.ValidationError({"detail": exc.messages})


def _day(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _money(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


def _project(request: Request, project_id: int) -> PlanProject:
    return get_object_or_404(
        PlanProject.objects.select_related("district"),
        pk=project_id,
        district_id=require_district_id(request),
    )


def bill_json(bill: Bill) -> dict[str, Any]:
    return {
        "id": bill.pk,
        "year": bill.year,
        "reference": bill.reference,
        "amount": _money(bill.amount),
        "paid": _money(bill.paid),
        "owing": _money(bill.amount - bill.paid),
        "issued_on": _day(bill.issued_on),
        "last_paid_on": _day(bill.last_paid_on),
        "source": bill.source,
    }


def property_json(prop: Property, request: Request) -> dict[str, Any]:
    personal = has_permission(request, "data.sensitive")
    return {
        "id": prop.pk,
        "project": prop.project_id,
        "feature": prop.feature_id,
        "number": prop.number,
        "address": prop.address,
        "use": prop.use,
        "use_label": prop.get_use_display(),
        "owner_name": prop.owner_name if personal else (HIDDEN if prop.owner_name else ""),
        "owner_contact": prop.owner_contact if personal else (HIDDEN if prop.owner_contact else ""),
        "valuation_ref": prop.valuation_ref,
        "rateable_value": _money(prop.rateable_value),
        "valued_on": _day(prop.valued_on),
        "revenue_ref": prop.revenue_ref,
        "status": services.status_of(prop),
        "bills": [bill_json(b) for b in prop.bills.all()],
    }


class PropertyWriteSerializer(serializers.Serializer[Any]):
    address = serializers.CharField(max_length=200, required=False, allow_blank=True)
    use = serializers.ChoiceField(choices=Use.choices, required=False)
    owner_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    owner_contact = serializers.CharField(max_length=200, required=False, allow_blank=True)
    valuation_ref = serializers.CharField(max_length=60, required=False, allow_blank=True)
    rateable_value = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal(0), required=False, allow_null=True
    )
    valued_on = serializers.DateField(required=False, allow_null=True)
    revenue_ref = serializers.CharField(max_length=60, required=False, allow_blank=True)


class PaymentSerializer(serializers.Serializer[Any]):
    year = serializers.IntegerField(min_value=2000, max_value=2100)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    on = serializers.DateField(required=False, help_text="Default: today")


@extend_schema(parameters=[DISTRICT_HEADER])
class PropertyViewSet(viewsets.GenericViewSet[Property]):
    """The property register: each rateable property, its valuation and its bills."""

    queryset = Property.objects.none()
    serializer_class = PropertyWriteSerializer

    def get_permissions(self) -> list[BasePermission]:
        return _perms("revenue.view" if self.action in ("list", "retrieve") else "revenue.manage")

    def get_queryset(self) -> QuerySet[Property]:
        return Property.objects.filter(
            district_id=require_district_id(self.request)
        ).prefetch_related("bills")

    @extend_schema(
        parameters=[
            OpenApiParameter("project", int),
            OpenApiParameter("status", str, description="never_billed, unpaid or paid"),
            OpenApiParameter("q", str),
        ],
        responses=OpenApiTypes.OBJECT,
        operation_id="revenue_properties_list",
    )
    def list(self, request: Request) -> Response:
        qs = self.get_queryset()
        params = request.query_params
        if params.get("project", "").isdigit():
            qs = qs.filter(project_id=int(params["project"]))
        if params.get("q"):
            q = params["q"].strip()
            qs = qs.filter(
                Q(number__icontains=q) | Q(address__icontains=q) | Q(revenue_ref__icontains=q)
            )
        rows = [property_json(p, request) for p in qs[:2000]]
        if params.get("status"):
            rows = [r for r in rows if r["status"] == params["status"]]
        return Response({"results": rows[:500], "count": len(rows)})

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(property_json(self.get_object(), request))

    @extend_schema(request=PropertyWriteSerializer, responses=OpenApiTypes.OBJECT)
    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        prop = self.get_object()
        data = PropertyWriteSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        for name, value in data.validated_data.items():
            setattr(prop, name, value)
        prop.save()
        prop.refresh_from_db()
        return Response(property_json(prop, request))

    @extend_schema(request=PaymentSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def payment(self, request: Request, pk: str | None = None) -> Response:
        """A payment against the property's bill for a year."""
        prop = self.get_object()
        data = PaymentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        bill = Bill.objects.filter(property=prop, year=values["year"]).first()
        if bill is None:
            raise serializers.ValidationError({"year": "There is no bill for that year."})
        bill.paid = services.money(bill.paid + values["amount"])
        bill.last_paid_on = values.get("on") or date.today()
        bill.save(update_fields=["paid", "last_paid_on"])
        prop.refresh_from_db()
        return Response(property_json(prop, request))


class RateBandSerializer(serializers.ModelSerializer[RateBand]):
    class Meta:
        model = RateBand
        fields = ["id", "year", "use", "impost", "minimum", "flat"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        impost = attrs.get("impost")
        if impost is not None and not Decimal(0) <= impost < Decimal(1):
            raise serializers.ValidationError(
                {"impost": "A share of the rateable value, e.g. 0.005."}
            )
        return attrs


@extend_schema(parameters=[DISTRICT_HEADER])
class RateBandViewSet(viewsets.ModelViewSet[RateBand]):
    """The district's rates for each use and year (from its fee-fixing resolution)."""

    serializer_class = RateBandSerializer
    queryset = RateBand.objects.none()
    pagination_class = None  # a handful a year

    def get_permissions(self) -> list[BasePermission]:
        return _perms("revenue.view" if self.action in ("list", "retrieve") else "revenue.manage")

    def get_queryset(self) -> QuerySet[RateBand]:
        return RateBand.objects.filter(district_id=require_district_id(self.request))

    def perform_create(self, serializer: serializers.BaseSerializer[RateBand]) -> None:
        district_id = require_district_id(self.request)
        values = serializer.validated_data
        if RateBand.objects.filter(
            district_id=district_id, year=values["year"], use=values["use"]
        ).exists():
            raise serializers.ValidationError(
                {"use": "There is already a rate for this use and year."}
            )
        serializer.save(district_id=district_id)


class BillYearSerializer(serializers.Serializer[Any]):
    year = serializers.IntegerField(min_value=2000, max_value=2100)
    on = serializers.DateField(required=False, help_text="Issued on. Default: today")


class FileSerializer(serializers.Serializer[Any]):
    file = serializers.FileField()


def _csv(request: Request) -> list[dict[str, str]]:
    data = FileSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    upload = data.validated_data["file"]
    if upload.size > MAX_CSV_BYTES:
        raise serializers.ValidationError({"file": "CSV files are limited to 20 MB."})
    try:
        return services.rows_of(upload.read())
    except DjangoValidationError as exc:
        raise _drf(exc) from exc


@extend_schema(parameters=[DISTRICT_HEADER], responses=OpenApiTypes.OBJECT)
class RegisterView(APIView):
    """The project's property register in figures: properties, valued,
    never billed, owing, paid up, and what was billed and collected."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("revenue.view")

    def get(self, request: Request, project_id: int) -> Response:
        return Response(services.summary(_project(request, project_id)))


@extend_schema(parameters=[DISTRICT_HEADER], responses=OpenApiTypes.OBJECT)
class RegisterActionView(APIView):
    """build: a register entry for each property on the map; bills: this
    year's bills; valuations: the valuation list (CSV); revenue: bills and
    payments from the revenue system (CSV); map: the rates map layer."""

    ACTIONS = ("build", "bills", "valuations", "revenue", "map")

    def get_permissions(self) -> list[BasePermission]:
        return _perms("revenue.manage")

    def get_parsers(self) -> list[Any]:
        if self.kwargs.get("what") in ("valuations", "revenue"):
            return [MultiPartParser()]
        return super().get_parsers()

    @extend_schema(request=BillYearSerializer)
    def post(self, request: Request, project_id: int, what: str) -> Response:
        project = _project(request, project_id)
        try:
            if what == "build":
                return Response(services.build_register(project))
            if what == "bills":
                data = BillYearSerializer(data=request.data)
                data.is_valid(raise_exception=True)
                values = data.validated_data
                return Response(
                    services.bill_year(project, values["year"], values.get("on") or date.today())
                )
            if what == "valuations":
                return Response(services.import_valuations(project, _csv(request)))
            if what == "revenue":
                return Response(services.import_bills(project, _csv(request)))
            if what == "map":
                return Response(services.status_layer(project, request_user(request)))
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        raise serializers.ValidationError({"detail": f"One of {', '.join(self.ACTIONS)}."})


@extend_schema(parameters=[DISTRICT_HEADER])
class RegisterCsvView(APIView):
    """The register as a CSV, to load into the revenue system."""

    def get_permissions(self) -> list[BasePermission]:
        return _perms("revenue.view")

    @extend_schema(responses={(200, "text/csv"): OpenApiTypes.STR})
    def get(self, request: Request, project_id: int) -> HttpResponse:
        project = _project(request, project_id)
        text = services.register_csv(project, has_permission(request, "data.sensitive"))
        response = HttpResponse(text.encode("utf-8"), content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="property-register-{project.pk}.csv"'
        )
        return response


# --- Betterment ---------------------------------------------------------------------------------


def charge_json(charge: BettermentCharge, request: Request) -> dict[str, Any]:
    prop = charge.property
    return {
        "id": charge.pk,
        "property": prop.pk,
        "number": prop.number,
        "address": prop.address,
        "owner_name": prop.owner_name
        if has_permission(request, "data.sensitive")
        else (HIDDEN if prop.owner_name else ""),
        "distance_m": f"{charge.distance_m:.1f}",
        "increase": _money(charge.increase),
        "amount": _money(charge.amount),
        "served_on": _day(charge.served_on),
        "paid": _money(charge.paid),
        "paid_on": _day(charge.paid_on),
    }


def scheme_json(scheme: BettermentScheme, request: Request, *, full: bool) -> dict[str, Any]:
    charges = (
        list(scheme.charges.select_related("property")) if full else list(scheme.charges.all())
    )
    total = sum((c.amount or Decimal(0) for c in charges), Decimal(0))
    out: dict[str, Any] = {
        "id": scheme.pk,
        "project": scheme.project_id,
        "name": scheme.name,
        "works": scheme.works,
        "works_feature": scheme.works_feature_id,
        "reach_m": f"{scheme.reach_m:g}",
        "completed_on": _day(scheme.completed_on),
        "basis": scheme.basis,
        "basis_label": scheme.get_basis_display(),
        "amount": f"{scheme.amount:f}".rstrip("0").rstrip("."),
        "charges_count": len(charges),
        "total": f"{total:.2f}",
        "collected": f"{sum((c.paid for c in charges), Decimal(0)):.2f}",
        "clocks": services.scheme_clocks(scheme),
    }
    if full:
        out["charges"] = [charge_json(c, request) for c in charges]
    return out


class SchemeWriteSerializer(serializers.Serializer[Any]):
    project = serializers.IntegerField(required=False)
    name = serializers.CharField(max_length=200, required=False)
    works = serializers.CharField(required=False, allow_blank=True)
    works_feature = serializers.IntegerField(required=False, allow_null=True)
    reach_m = serializers.DecimalField(
        max_digits=8,
        decimal_places=1,
        min_value=Decimal(1),
        max_value=Decimal(5000),
        required=False,
    )
    completed_on = serializers.DateField(required=False)
    basis = serializers.ChoiceField(choices=BettermentScheme.Basis.choices, required=False)
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=4, min_value=Decimal(0), required=False
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        basis, amount = attrs.get("basis"), attrs.get("amount")
        if basis == BettermentScheme.Basis.RATE and amount is not None and amount > 1:
            raise serializers.ValidationError(
                {"amount": "A share of the increase, e.g. 0.25 for a quarter."}
            )
        return attrs


class PublishSerializer(serializers.Serializer[Any]):
    how = serializers.ChoiceField(choices=list(services.PUBLICATION))
    on = serializers.DateField(required=False, help_text="Default: today")


@extend_schema(parameters=[DISTRICT_HEADER])
class SchemeViewSet(viewsets.GenericViewSet[BettermentScheme]):
    """Betterment (L.I. 2384 r.40-41): public works, the properties they
    bettered, the charge on each, and the notices."""

    queryset = BettermentScheme.objects.none()
    serializer_class = SchemeWriteSerializer

    def get_permissions(self) -> list[BasePermission]:
        return _perms(
            "revenue.view" if self.action in ("list", "retrieve", "notice") else "revenue.manage"
        )

    def get_queryset(self) -> QuerySet[BettermentScheme]:
        return BettermentScheme.objects.filter(
            district_id=require_district_id(self.request)
        ).select_related("project", "project__district")

    def _answer(self, scheme: BettermentScheme, code: int = status.HTTP_200_OK) -> Response:
        scheme.refresh_from_db()
        return Response(scheme_json(scheme, self.request, full=True), status=code)

    def _works(self, project_id: int, feature_id: int | None) -> Feature | None:
        if feature_id is None:
            return None
        return get_object_or_404(Feature, pk=feature_id, layer__project_id=project_id)

    @extend_schema(
        parameters=[OpenApiParameter("project", int)],
        responses=OpenApiTypes.OBJECT,
        operation_id="revenue_betterment_list",
    )
    def list(self, request: Request) -> Response:
        qs = self.get_queryset()
        if request.query_params.get("project", "").isdigit():
            qs = qs.filter(project_id=int(request.query_params["project"]))
        return Response({"results": [scheme_json(s, request, full=False) for s in qs[:200]]})

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(scheme_json(self.get_object(), request, full=True))

    @extend_schema(request=SchemeWriteSerializer, responses={201: OpenApiTypes.OBJECT})
    def create(self, request: Request) -> Response:
        data = SchemeWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        missing = [
            k for k in ("project", "name", "completed_on", "amount") if values.get(k) is None
        ]
        if missing:
            raise serializers.ValidationError({k: "Required." for k in missing})
        project = _project(request, values["project"])
        scheme = BettermentScheme.objects.create(
            district_id=project.district_id,
            project=project,
            name=values["name"],
            works=values.get("works", ""),
            works_feature=self._works(project.pk, values.get("works_feature")),
            reach_m=values.get("reach_m", Decimal(100)),
            completed_on=values["completed_on"],
            basis=values.get("basis", BettermentScheme.Basis.SUM),
            amount=values["amount"],
            created_by=request_user(request),
        )
        return self._answer(scheme, status.HTTP_201_CREATED)

    @extend_schema(request=SchemeWriteSerializer, responses=OpenApiTypes.OBJECT)
    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        scheme = self.get_object()
        data = SchemeWriteSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        for name in ("name", "works", "reach_m", "completed_on", "basis", "amount"):
            if name in values:
                setattr(scheme, name, values[name])
        if "works_feature" in values:
            scheme.works_feature = self._works(scheme.project_id, values["works_feature"])
        scheme.save()
        # The charges follow the new sum or rate.
        for charge in scheme.charges.all():
            charge.amount = services.charge_amount(scheme, charge)
            charge.save(update_fields=["amount"])
        return self._answer(scheme)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def find(self, request: Request, pk: str | None = None) -> Response:
        """Finds the bettered properties: those within reach of the works."""
        scheme = self.get_object()
        try:
            found = services.find_bettered(scheme)
        except DjangoValidationError as exc:
            raise _drf(exc) from exc
        body = scheme_json(scheme, request, full=True)
        body["found"] = found
        return Response(body)

    @extend_schema(request=PublishSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def publish(self, request: Request, pk: str | None = None) -> Response:
        """r.40(3): how and when the Form 40 notice was published."""
        scheme = self.get_object()
        data = PublishSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        on = data.validated_data.get("on") or date.today()
        scheme.published = {**scheme.published, data.validated_data["how"]: on.isoformat()}
        scheme.save(update_fields=["published"])
        return self._answer(scheme)

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def notice(self, request: Request, pk: str | None = None) -> HttpResponse:
        """The notice of betterment (Form 40), as a PDF."""
        scheme = self.get_object()
        response = HttpResponse(documents.notice_pdf(scheme), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="betterment-notice-{scheme.pk}.pdf"'
        )
        return response


class ChargeWriteSerializer(serializers.Serializer[Any]):
    increase = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal(0), required=False, allow_null=True
    )
    served_on = serializers.DateField(required=False, allow_null=True)
    paid = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal(0), required=False
    )
    paid_on = serializers.DateField(required=False, allow_null=True)


@extend_schema(parameters=[DISTRICT_HEADER])
class ChargeViewSet(viewsets.GenericViewSet[BettermentCharge]):
    """One property's betterment charge: its assessment, service and payment."""

    queryset = BettermentCharge.objects.none()
    serializer_class = ChargeWriteSerializer

    def get_permissions(self) -> list[BasePermission]:
        return _perms("revenue.view" if self.action == "paper" else "revenue.manage")

    def get_queryset(self) -> QuerySet[BettermentCharge]:
        return BettermentCharge.objects.filter(
            district_id=require_district_id(self.request)
        ).select_related("property", "scheme", "scheme__project", "scheme__project__district")

    @extend_schema(request=ChargeWriteSerializer, responses=OpenApiTypes.OBJECT)
    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        charge = self.get_object()
        data = ChargeWriteSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        for name, value in values.items():
            setattr(charge, name, value)
        if "increase" in values:
            charge.amount = services.charge_amount(charge.scheme, charge)
        if charge.served_on and charge.served_on > date.today():
            raise serializers.ValidationError({"served_on": "That date is in the future."})
        charge.save()
        return Response(charge_json(charge, request))

    @extend_schema(
        parameters=[
            OpenApiParameter("kind", str, description="assessment or certificate"),
            OpenApiParameter("payment", str, description="How to pay (on the assessment notice)"),
        ],
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    @action(detail=True, methods=["get"])
    def paper(self, request: Request, pk: str | None = None) -> HttpResponse:
        """The Form 41 assessment notice, or the r.41 certificate of the sum due or paid."""
        charge = self.get_object()
        kind = request.query_params.get("kind", "assessment")
        if kind not in documents.PAPERS:
            raise serializers.ValidationError({"kind": "assessment or certificate."})
        if charge.amount is None:
            raise serializers.ValidationError({"detail": "The charge has not been assessed yet."})
        if kind == "assessment":
            payment = (
                request.query_params.get("payment")
                or "at the Assembly's revenue office, or as the Assembly directs,"
                " within thirty days of this notice."
            )
            pdf = documents.assessment_pdf(charge, payment)
        else:
            pdf = documents.certificate_pdf(charge)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="betterment-{kind}-{charge.property.number}.pdf"'
        )
        return response
