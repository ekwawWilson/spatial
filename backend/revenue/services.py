"""The property register built from the map; valuations, rates and bills;
the link to the Assembly's revenue system; the map of what is never billed
and unpaid; and betterment (L.I. 2384 r.40-41)."""

import csv
import io
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Sum

from core.models import User
from permits.models import Counter
from projects import geometry as geo
from projects import styles
from projects.models import Feature, Layer, PlanProject
from relations import procedures
from relations import services as relations
from relations.models import LayerRole

from .models import BettermentCharge, BettermentScheme, Bill, Property, RateBand, Use

CENT = Decimal("0.01")
NEVER_BILLED, UNPAID, PAID = "never_billed", "unpaid", "paid"
STATUS_LABELS = {NEVER_BILLED: "Never billed", UNPAID: "Owing", PAID: "Paid up"}
STATUS_COLOURS = {NEVER_BILLED: "#c0352b", UNPAID: "#d9822b", PAID: "#1f8a5b"}
STATUS_LAYER = "Property rates"
STATUS_SCHEMA: list[dict[str, Any]] = [
    {"name": "property_no", "label": "Property", "type": "text", "required": False},
    {"name": "status", "label": "Rates", "type": "text", "required": False},
    {"name": "billed", "label": "Billed (GHS)", "type": "decimal", "required": False},
    {"name": "paid", "label": "Paid (GHS)", "type": "decimal", "required": False},
]
# r.40(3): the ways the Form 40 notice is published.
PUBLICATION = {
    "newspaper": "In a daily newspaper of national circulation",
    "posted": "Posted in a conspicuous area of the affected land",
    "data_room": "A copy displayed in the Public Data Room",
}
SERVE_WITHIN_DAYS = 90  # r.40(7): Form 41, after the completion of the project
# Words in a map's use or land-use field, and the rate band they mean.
USE_WORDS = (
    ("industr", Use.INDUSTRIAL),
    ("mixed", Use.MIXED),
    ("commerc", Use.COMMERCIAL),
    ("shop", Use.COMMERCIAL),
    ("retail", Use.COMMERCIAL),
    ("office", Use.COMMERCIAL),
    ("school", Use.INSTITUTIONAL),
    ("church", Use.INSTITUTIONAL),
    ("mosque", Use.INSTITUTIONAL),
    ("clinic", Use.INSTITUTIONAL),
    ("hospital", Use.INSTITUTIONAL),
    ("institut", Use.INSTITUTIONAL),
    ("civic", Use.INSTITUTIONAL),
    ("vacant", Use.VACANT),
    ("resid", Use.RESIDENTIAL),
    ("house", Use.RESIDENTIAL),
)


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _decimal(text: Any, what: str) -> Decimal | None:
    if text in (None, ""):
        return None
    try:
        value = Decimal(str(text).replace(",", "").strip())
    except InvalidOperation as exc:
        raise ValidationError(f"{what}: {text!r} is not a number.") from exc
    if value < 0:
        raise ValidationError(f"{what}: {text!r} is negative.")
    return value


def _day(text: Any) -> date | None:
    if text in (None, ""):
        return None
    try:
        return date.fromisoformat(str(text).strip()[:10])
    except ValueError as exc:
        raise ValidationError(f"{text!r} is not a date (YYYY-MM-DD).") from exc


def guess_use(properties: dict[str, Any]) -> str:
    for key in ("use", "land_use", "building", "landuse", "amenity"):
        text = str(properties.get(key) or "").lower()
        for word, use in USE_WORDS:
            if word in text:
                return str(use)
    return str(Use.RESIDENTIAL)


# --- The register ------------------------------------------------------------------------------


def properties_role(project: PlanProject) -> LayerRole:
    roles = relations.roles_of(project)
    role = roles.get("properties") or roles.get("parcels")
    if role is None:
        raise ValidationError(
            "Say which layer holds the properties (buildings or plots) first"
            " (Relationships, Layers)."
        )
    return role


def build_register(project: PlanProject) -> dict[str, int]:
    """A register entry for each property on the map that has none yet,
    numbered by its address where it has one."""
    role = properties_role(project)
    config = role.config
    id_field = str(config.get("id_field", "property_id"))
    number_field = str(config.get("number_field", "house_no"))
    street_field = str(config.get("street_field", "street"))
    have = set(
        Property.objects.filter(project=project, feature__isnull=False).values_list(
            "feature_id", flat=True
        )
    )
    taken = set(Property.objects.filter(project=project).values_list("number", flat=True))
    added = 0
    for feature in Feature.objects.filter(layer=role.layer).order_by("id").iterator():
        if feature.pk in have:
            continue
        props = feature.properties or {}
        house, street = props.get(number_field), props.get(street_field)
        number = str(props.get(id_field) or f"#{feature.pk}")
        if number in taken:
            number = f"{number}-{feature.pk}"
        taken.add(number)
        Property.objects.create(
            district_id=project.district_id,
            project=project,
            feature=feature,
            number=number,
            address=f"{house} {street}".strip() if house and street else "",
            use=guess_use(props),
        )
        added += 1
    return {"added": added, "already": len(have), "total": len(have) + added}


def band_for(district_id: int, year: int, use: str) -> RateBand | None:
    return RateBand.objects.filter(district_id=district_id, year=year, use=use).first()


def assess(prop: Property, year: int) -> tuple[Decimal | None, str]:
    """The rate due for a year, and how it was worked out."""
    band = band_for(prop.district_id, year, prop.use)
    if band is None:
        return None, f"No {year} rate is set for {Use(prop.use).label.lower()} property."
    if prop.rateable_value is None:
        if band.flat is None:
            return None, "Not valued yet, and no flat rate is set for unvalued property."
        return money(band.flat), "flat rate (not valued yet)"
    amount = max(money(prop.rateable_value * band.impost), money(band.minimum))
    return amount, f"{band.impost} × {prop.rateable_value:,.2f}, at least {band.minimum:,.2f}"


def next_bill_reference(district_id: int, code: str, year: int) -> str:
    with transaction.atomic():
        counter, _ = Counter.objects.select_for_update().get_or_create(
            district_id=district_id, kind="rates", year=year
        )
        counter.last += 1
        counter.save(update_fields=["last"])
    return f"{code}/PR/{year}/{counter.last:05d}"


def bill_year(project: PlanProject, year: int, on: date) -> dict[str, Any]:
    """A bill for each property that has none for the year."""
    made, skipped = 0, []
    total = Decimal(0)
    for prop in Property.objects.filter(project=project).exclude(bills__year=year):
        amount, how = assess(prop, year)
        if amount is None:
            skipped.append({"number": prop.number, "reason": how})
            continue
        Bill.objects.create(
            district_id=project.district_id,
            property=prop,
            year=year,
            reference=next_bill_reference(project.district_id, project.district.code, year),
            amount=amount,
            issued_on=on,
        )
        made += 1
        total += amount
    return {
        "billed": made,
        "total": f"{total:.2f}",
        "skipped": skipped[:200],
        "skipped_count": len(skipped),
    }


def status_of(prop: Property) -> str:
    bills = list(prop.bills.all())
    if not bills:
        return NEVER_BILLED
    return UNPAID if any(b.paid < b.amount for b in bills) else PAID


def summary(project: PlanProject) -> dict[str, Any]:
    props = list(Property.objects.filter(project=project).prefetch_related("bills"))
    counts = {NEVER_BILLED: 0, UNPAID: 0, PAID: 0}
    for prop in props:
        counts[status_of(prop)] += 1
    bills = Bill.objects.filter(property__project=project)
    billed = bills.aggregate(t=Sum("amount"))["t"] or Decimal(0)
    paid = bills.aggregate(t=Sum("paid"))["t"] or Decimal(0)
    return {
        "properties": len(props),
        "valued": sum(1 for p in props if p.rateable_value is not None),
        "by_status": counts,
        "billed": f"{billed:.2f}",
        "paid": f"{paid:.2f}",
        "owing": f"{billed - paid:.2f}",
        "collected_pct": round(float(paid / billed * 100), 1) if billed else None,
    }


# --- Imports: the valuation list and the revenue system ---------------------------------------


def rows_of(upload: bytes) -> list[dict[str, str]]:
    text = upload.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValidationError("The file is empty.")
    return [
        {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in reader
    ]


def _find(project: PlanProject, row: dict[str, str]) -> Property | None:
    """The property a row is about: by revenue account, valuation reference, or property number."""
    for key, field in (
        ("revenue_ref", "revenue_ref"),
        ("valuation_ref", "valuation_ref"),
        ("property", "number"),
        ("number", "number"),
    ):
        value = row.get(key)
        if value:
            found = Property.objects.filter(project=project, **{field: value}).first()
            if found is not None:
                return found
    return None


def import_valuations(project: PlanProject, rows: list[dict[str, str]]) -> dict[str, Any]:
    """The Land Valuation Division's list: a rateable value for each property."""
    matched, unmatched = 0, []
    with transaction.atomic():
        for n, row in enumerate(rows, start=2):
            prop = _find(project, row)
            if prop is None:
                unmatched.append(
                    {
                        "row": n,
                        "reference": row.get("valuation_ref")
                        or row.get("property")
                        or row.get("number")
                        or "",
                    }
                )
                continue
            value = _decimal(row.get("rateable_value"), f"Row {n}, rateable_value")
            if value is None:
                unmatched.append(
                    {"row": n, "reference": prop.number, "reason": "no rateable value"}
                )
                continue
            prop.rateable_value = value
            prop.valued_on = _day(row.get("valued_on")) or prop.valued_on
            if row.get("valuation_ref"):
                prop.valuation_ref = row["valuation_ref"]
            if row.get("owner") and not prop.owner_name:
                prop.owner_name = row["owner"]
            prop.save()
            matched += 1
    return {
        "rows": len(rows),
        "matched": matched,
        "unmatched": unmatched[:200],
        "unmatched_count": len(unmatched),
    }


def import_bills(project: PlanProject, rows: list[dict[str, str]]) -> dict[str, Any]:
    """Bills and payments from the revenue system (one row per property and
    year). Reconciliation: each row matches one property, or is reported."""
    matched, unmatched = 0, []
    with transaction.atomic():
        for n, row in enumerate(rows, start=2):
            prop = _find(project, row)
            if prop is None:
                unmatched.append(
                    {
                        "row": n,
                        "reference": row.get("revenue_ref")
                        or row.get("property")
                        or row.get("number")
                        or "",
                    }
                )
                continue
            try:
                year = int(row.get("year") or "")
            except ValueError as exc:
                raise ValidationError(f"Row {n}: year {row.get('year')!r} is not a year.") from exc
            amount = _decimal(row.get("amount"), f"Row {n}, amount")
            paid = _decimal(row.get("paid"), f"Row {n}, paid") or Decimal(0)
            bill = Bill.objects.filter(property=prop, year=year).first()
            if bill is None:
                if amount is None:
                    unmatched.append(
                        {"row": n, "reference": prop.number, "reason": "no bill amount"}
                    )
                    continue
                bill = Bill(
                    district_id=project.district_id,
                    property=prop,
                    year=year,
                    issued_on=_day(row.get("issued_on")) or date(year, 1, 1),
                )
            if amount is not None:
                bill.amount = money(amount)
            bill.paid = money(paid)
            bill.last_paid_on = _day(row.get("paid_on")) or bill.last_paid_on
            bill.reference = row.get("bill") or row.get("reference") or bill.reference
            bill.source = Bill.Source.REVENUE
            bill.save()
            if row.get("revenue_ref") and not prop.revenue_ref:
                prop.revenue_ref = row["revenue_ref"]
                prop.save(update_fields=["revenue_ref", "updated_at"])
            matched += 1
    return {
        "rows": len(rows),
        "matched": matched,
        "unmatched": unmatched[:200],
        "unmatched_count": len(unmatched),
    }


def register_csv(project: PlanProject, personal: bool) -> str:
    """The register, for the revenue system: one row per property, with this year's bill."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "number",
            "address",
            "use",
            "owner",
            "valuation_ref",
            "rateable_value",
            "revenue_ref",
            "year",
            "bill",
            "amount",
            "paid",
            "status",
        ]
    )
    for prop in Property.objects.filter(project=project).prefetch_related("bills"):
        latest = max(prop.bills.all(), key=lambda b: b.year, default=None)
        writer.writerow(
            [
                prop.number,
                prop.address,
                prop.use,
                prop.owner_name if personal else "",
                prop.valuation_ref,
                "" if prop.rateable_value is None else f"{prop.rateable_value:.2f}",
                prop.revenue_ref,
                latest.year if latest else "",
                latest.reference if latest else "",
                f"{latest.amount:.2f}" if latest else "",
                f"{latest.paid:.2f}" if latest else "",
                status_of(prop),
            ]
        )
    return "﻿" + out.getvalue()


# --- The map of what is never billed and unpaid -----------------------------------------------


def status_layer(project: PlanProject, user: User) -> dict[str, Any]:
    """A point at each property, coloured by its rates: never billed, owing, paid up."""
    source = properties_role(project).layer
    layer = project.layers.filter(name=STATUS_LAYER).first()
    if layer is None:
        top = max((x.order for x in project.layers.all()), default=0)
        layer = Layer.objects.create(
            district_id=project.district_id,
            project=project,
            name=STATUS_LAYER,
            domain="H",
            geometry_type="point",
            crs=source.crs,
            schema=STATUS_SCHEMA,
            style={
                "kind": "categorized",
                "field": "status",
                "categories": [
                    {
                        **styles.DEFAULT_SYMBOL,
                        "value": label,
                        "fill": STATUS_COLOURS[code],
                        "stroke": "#ffffff",
                        "point_radius": 6,
                        "fill_opacity": 0.95,
                    }
                    for code, label in STATUS_LABELS.items()
                ],
                "default": dict(styles.DEFAULT_SYMBOL),
                "label_field": None,
            },
            order=top + 1,
            source=Layer.Source.DERIVED,
            created_by=user,
        )
    existing = {str(f.properties.get("property_no")): f for f in layer.features.all()}
    written = 0
    keep: set[str] = set()
    for prop in Property.objects.filter(project=project, feature__isnull=False).prefetch_related(
        "bills"
    ):
        assert prop.feature_id is not None
        centre = geo.centre(prop.feature_id)
        if centre is None:
            continue
        bills = list(prop.bills.all())
        values = {
            "property_no": prop.number,
            "status": STATUS_LABELS[status_of(prop)],
            "billed": float(sum((b.amount for b in bills), Decimal(0))),
            "paid": float(sum((b.paid for b in bills), Decimal(0))),
        }
        keep.add(prop.number)
        feature = existing.get(prop.number)
        if feature is not None and feature.properties == values:
            continue
        if feature is None:
            feature = Feature(
                district_id=project.district_id,
                layer=layer,
                origin=Feature.Origin.IMPORT,
                created_by=user,
            )
        else:
            feature.version += 1
        feature.properties = values
        feature.updated_by = user
        feature.save()
        geo.write_geometry(feature, {"type": "Point", "coordinates": [centre[0], centre[1]]})
        written += 1
    gone = [f.pk for number, f in existing.items() if number not in keep]
    Feature.objects.filter(pk__in=gone).delete()
    return {"layer": layer.pk, "written": written, "removed": len(gone)}


# --- Betterment (L.I. 2384 r.40-41) -----------------------------------------------------------


def find_bettered(scheme: BettermentScheme) -> dict[str, int]:
    """The properties within reach of the works: a charge for each that has none."""
    if scheme.works_feature_id is None:
        raise ValidationError({"works_feature": ["Say which feature on the map is the works."]})
    reach = float(scheme.reach_m)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT p.id, ST_Distance(f.geom_4326::geography, w.geom_4326::geography)"
            " FROM revenue_property p JOIN projects_feature f ON f.id = p.feature_id,"
            " projects_feature w WHERE w.id = %s AND p.project_id = %s"
            " AND f.geom_4326 && ST_Expand(w.geom_4326, %s)"
            " AND ST_DWithin(f.geom_4326::geography, w.geom_4326::geography, %s)",
            [scheme.works_feature_id, scheme.project_id, procedures._degrees(reach), reach],
        )
        rows = cursor.fetchall()
    have = set(scheme.charges.values_list("property_id", flat=True))
    added = 0
    for property_id, distance in rows:
        if property_id in have:
            continue
        charge = BettermentCharge(
            district_id=scheme.district_id,
            scheme=scheme,
            property_id=property_id,
            distance_m=Decimal(str(round(float(distance), 1))),
        )
        charge.amount = charge_amount(scheme, charge)
        charge.save()
        added += 1
    return {"found": len(rows), "added": added}


def charge_amount(scheme: BettermentScheme, charge: BettermentCharge) -> Decimal | None:
    """r.40(2), (4): a fixed sum, or a share of how much the property gained in value."""
    if scheme.basis == BettermentScheme.Basis.SUM:
        return money(scheme.amount)
    if charge.increase is None:
        return None
    return money(charge.increase * scheme.amount)


def scheme_clocks(scheme: BettermentScheme, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    due = scheme.completed_on + timedelta(days=SERVE_WITHIN_DAYS)
    charges = list(scheme.charges.all())
    unserved = [c for c in charges if c.served_on is None]
    late = [c for c in charges if c.served_on and c.served_on > due]
    return {
        "serve_by": due.isoformat(),
        "rule": "r.40(7)",
        "unserved": len(unserved),
        "served_late": len(late),
        "overdue": bool(unserved) and today > due,
        "published": [
            {"code": code, "label": label, "on": scheme.published.get(code)}
            for code, label in PUBLICATION.items()
        ],
    }
