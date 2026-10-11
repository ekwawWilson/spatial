"""The national zones and their standards, from LUSPA's Revised Zoning
Guidelines and Planning Standards (2025). L.I. 2384 r.29(2) and r.47 require
zoning schemes and physical development to conform to them.

Transcribed from the published document (a scanned PDF), so every value here
is also shown to the district's administrators, who adopt the standards for
their district and can correct or tighten them (relations.DevelopmentStandard).
Nothing here is applied to a district until it is adopted.

Source pages: list of zones (p. xiii-xiv), colour codes (Table 2, p. 3-5),
permissible and prohibited uses (Tables 3-7, p. 8-16), site development
standards (section 2.6, p. 17).
"""

import re
from dataclasses import dataclass, field
from typing import Any

SOURCE = "LUSPA Revised Zoning Guidelines and Planning Standards (2025)"
SOURCE_CODE = "luspa-2025"
FOOT_M = 0.3048


@dataclass(frozen=True)
class SiteStandard:
    """Section 2.6: plot dimensions, site coverage, height limits and building lines."""

    min_plot_m2: float
    max_coverage_pct: float
    front_setback_m: float
    side_setback_m: float
    rear_setback_m: float
    min_width_m: float | None = None
    min_floors: int | None = None
    max_floors: int | None = None
    height: str = ""  # as printed


@dataclass(frozen=True)
class Zone:
    code: str
    name: str
    group: str
    colour: str  # the fill, from Table 2 (hex column)
    pattern: str = ""  # Table 2's description where the zone is drawn with a pattern
    site: SiteStandard | None = None
    permitted: tuple[str, ...] = ()
    prohibited: tuple[str, ...] = ()
    # Words that, found in a property's recorded use, suggest a prohibited use.
    # A suggestion for a person to check, never a finding.
    prohibited_keywords: tuple[str, ...] = ()
    aliases: tuple[str, ...] = field(default_factory=tuple)


def _ft(feet: float) -> float:
    return round(feet * FOOT_M, 1)


_NOXIOUS = ("filling station", "fuel station", "gas station", "petrol", "cemetery", "crematori")
_INDUSTRY = ("industr", "factory", "warehouse")

ZONES: tuple[Zone, ...] = (
    Zone(
        "Re A",
        "Residential Zone A: low density",
        "Residential",
        "#CC7722",
        site=SiteStandard(
            min_plot_m2=930,
            max_coverage_pct=40,
            front_setback_m=6,
            side_setback_m=3,
            rear_setback_m=5,
            min_width_m=_ft(70),
            max_floors=2,
            height="up to 2 storeys",
        ),
        permitted=(
            "Detached, duplex and courtyard houses",
            "Public open spaces, e.g. a playground",
            "Neighbourhood shops, clinics and pharmacies (250 m² floor area)",
            "Pre-school and basic school",
            "House-based small family businesses (at most 2 employees)",
            "Place of worship (at least 0.5 acre / 2,023 m²)",
            "Cylinder exchange points",
            "Electric vehicle charging stations and solar-integrated facilities",
        ),
        prohibited=(
            "Transportation for haulage",
            "Block of flats",
            "Industrial development",
            "Large commercial complex",
            "Crematorium or cemetery",
            "Animal husbandry",
            "Mixed-use buildings with a significant business component",
            "Gas filling stations",
        ),
        prohibited_keywords=(
            *_INDUSTRY,
            *_NOXIOUS,
            "haulage",
            "flats",
            "apartment",
            "husbandry",
            "livestock",
        ),
        aliases=("residential a", "residential zone a", "low density residential"),
    ),
    Zone(
        "Re B",
        "Residential Zone B: medium density",
        "Residential",
        "#E5AA70",
        site=SiteStandard(
            min_plot_m2=647,
            max_coverage_pct=50,
            front_setback_m=6,
            side_setback_m=3,
            rear_setback_m=3,
            min_width_m=_ft(50),
            max_floors=3,
            height="up to 3 storeys",
        ),
        permitted=(
            "Detached, duplex, row and compound houses",
            "Open space",
            "Local shop",
            "Basic education and child or daycare centre",
            "Community facilities, e.g. clinic, post office",
            "Places of worship",
            "Government business",
            "Limited road network to provide access",
            "Markets with repair workshops",
            "Home businesses with up to 3 employees",
            "Public transport stops or a minor terminal",
            "Segregated waste collection",
            "Cylinder exchange points",
            "Electric vehicle charging stations and solar-integrated facilities",
        ),
        prohibited=(
            "High-density residential blocks, e.g. multi-storey apartment blocks",
            "Major industrial development, e.g. factories and warehouses",
            "Major commercial development",
            "Transportation hubs, e.g. bus terminals or truck depots",
            "Warehousing",
            "Major sports facilities",
            "Cemeteries",
            "Animal husbandry",
            "Stockyard",
            "Noxious or hazardous uses",
            "Gas filling stations",
        ),
        prohibited_keywords=(
            *_INDUSTRY,
            *_NOXIOUS,
            "terminal",
            "depot",
            "stadium",
            "husbandry",
            "livestock",
            "stockyard",
        ),
        aliases=("residential b", "residential zone b", "medium density residential"),
    ),
    Zone(
        "Re C",
        "Residential Zone C: high-rise apartments",
        "Residential",
        "#BB8855",
        site=SiteStandard(
            min_plot_m2=4047,
            max_coverage_pct=75,
            front_setback_m=6,
            side_setback_m=3,
            rear_setback_m=3,
            min_floors=3,
            height="minimum 3 storeys",
        ),
        permitted=(
            "Multi-storey flats and apartment buildings",
            "Hostels",
            "Institutional accommodation, e.g. staff housing, barracks",
            "Public open spaces",
            "Places of worship",
            "Pharmacies and clinics",
            "Home business, childcare centre",
            "Pre-school, primary and junior high school",
            "Public transport facilities",
            "Hotels, guest houses, motels, lodges",
            "Recreation facilities serving the community",
            "Informal economic activities; shops at ground floor level only",
            "Cylinder exchange points",
            "Electric vehicle charging stations and solar-integrated facilities",
        ),
        prohibited=(
            "All industrial development, e.g. factories, workshops and warehouses",
            "Animal husbandry",
            "Cemetery and crematorium",
            "Transport use warehousing, e.g. bus depots, lorry park or logistics",
            "Major sports and recreation facilities",
            "Gas filling stations",
        ),
        prohibited_keywords=(
            *_INDUSTRY,
            *_NOXIOUS,
            "workshop",
            "depot",
            "lorry park",
            "stadium",
            "husbandry",
            "livestock",
        ),
        aliases=("residential c", "residential zone c", "high rise apartments"),
    ),
    Zone(
        "Re D",
        "Residential Zone D: high density (low-rise)",
        "Residential",
        "#98623C",
        site=SiteStandard(
            min_plot_m2=182,
            max_coverage_pct=60,
            front_setback_m=3,
            side_setback_m=1.5,
            rear_setback_m=1.5,
            min_width_m=_ft(40),
            min_floors=1,
            max_floors=3,
            height="1 to 3 storeys",
        ),
        permitted=(
            "Detached, semi-detached, row and compound housing",
            "Home business, e.g. small shops, tailoring, food vending",
            "Parks and playground",
            "Places of worship",
            "Childcare centre",
            "Local markets",
            "Clinic",
            "Pharmacy",
            "Outdoor and indoor recreational facilities",
            "Day care, primary and junior high schools",
            "Public transport facilities, e.g. taxi rank and lorry parks",
            "Light industrial development, e.g. small workshops",
            "Informal economic activities",
            "Cylinder exchange points",
            "Electric vehicle charging stations and solar-integrated facilities",
        ),
        prohibited=(
            "Heavy industrial development",
            "Large service industries",
            "Major commercial premises",
            "Animal husbandry",
            "Cemetery or crematorium",
            "Transportation depots",
            "Major infrastructure installations: power plants, waste dumps",
            "Gas filling stations",
        ),
        prohibited_keywords=(
            "heavy industr",
            "factory",
            *_NOXIOUS,
            "depot",
            "power plant",
            "waste dump",
            "husbandry",
            "livestock",
        ),
        aliases=("residential d", "residential zone d", "high density residential"),
    ),
    Zone(
        "Re Z",
        "Redevelopment / renewal / upgrading zone",
        "Residential",
        "#000000",
        pattern="Area delineated by a broken black line",
        site=SiteStandard(
            min_plot_m2=1011,
            max_coverage_pct=75,
            front_setback_m=2.5,
            side_setback_m=2.5,
            rear_setback_m=3,
            min_width_m=_ft(70),
            min_floors=3,
            height="minimum 3 storeys",
        ),
        permitted=(
            "High-rise and high-density residential developments",
            "Local markets",
            "Mixed uses",
            "Convenience shops",
            "Urban health centre",
            "Places of worship",
            "Basic school",
            "Public open spaces",
            "Business and commercial activities",
            "Home-based economic activities",
            "Cylinder exchange points",
            "Electric vehicle charging stations and solar-integrated facilities",
        ),
        prohibited=(
            "Massive infrastructural development that will relocate many people",
            "Cemeteries and crematoriums",
            "Large industrial activities",
            "Any development contrary to the redevelopment plan",
            "Gas filling stations",
        ),
        prohibited_keywords=("heavy industr", "factory", *_NOXIOUS),
        aliases=("residential z", "redevelopment zone", "renewal zone", "upgrading zone"),
    ),
    Zone("Ed P", "Education Zone A: nursery, primary and JHS", "Educational", "#FFFF00"),
    Zone(
        "Ed S", "Education Zone B: senior high, vocational and technical", "Educational", "#FFFF00"
    ),
    Zone("Ed T", "Education Zone C: tertiary institutions", "Educational", "#FFFF00"),
    Zone("PW", "Places of worship zone", "Civic and culture", "#FF7F7F"),
    Zone("H Po", "Health Zone A: polyclinic", "Civic and culture", "#FF0000"),
    Zone("H D", "Health Zone B: district hospital", "Civic and culture", "#FF0000"),
    Zone("H R", "Health Zone C: regional hospital", "Civic and culture", "#FF0000"),
    Zone(
        "H T",
        "Health Zone D: specialised, teaching, national and international hospitals",
        "Civic and culture",
        "#EE0000",
    ),
    Zone("CBD", "Central business district", "Commercial", "#2E4DA7"),
    Zone("SBZ", "Sub-regional business zone", "Commercial", "#587EDE"),
    Zone(
        "BM",
        "Mixed business zone",
        "Commercial",
        "#73B2FF",
        "Orange stripes on a powder-blue background",
    ),
    Zone(
        "BI",
        "Informal business zone",
        "Commercial",
        "#73B2FF",
        "Dotted dark grey on very light blue",
    ),
    Zone(
        "BG",
        "Government business zone",
        "Civic and culture",
        "#FF7F7F",
        "Black dots on very light red",
    ),
    Zone("PS", "Public space zone", "Public space", "#00FF00"),
    Zone("CZ", "Protected coastal / waterfront zone", "Public space", "#20B2AA"),
    Zone("CA", "Conservation zone", "Public space", "#32CD32"),
    Zone(
        "TL",
        "Transportation and logistics zone",
        "Commercial",
        "#D6D6D6",
        "Dark grey checkerboard on light grey",
    ),
    Zone("LI", "Light industrial zone", "Industrial", "#E8BEFF"),
    Zone("SI", "Service industrial zone", "Industrial", "#EE82EE"),
    Zone("HI", "Heavy industrial zone", "Industrial", "#DF73FF"),
    Zone("EI", "Extractive industrial zone", "Industrial", "#800080"),
    Zone("T", "Tourist zone", "Civic and culture", "#FF0080"),
    Zone("HZ", "Heritage zone", "Civic and culture", "#FF0080"),
    Zone(
        "SU",
        "Special use / utility zone",
        "Civic and culture",
        "#FF7F7F",
        "Thick black diagonal stripes on very light red",
    ),
    Zone("SE", "Emergency zone", "Civic and culture", "#E60000"),
    Zone(
        "SZ",
        "Security zone",
        "Civic and culture",
        "#FF7F7F",
        "Thick black horizontal stripes on very light red",
    ),
    Zone("Ag A", "Urban agriculture zone", "Agriculture", "#FF8C00"),
    Zone("Ag B", "Peri-urban agriculture", "Agriculture", "#FFA500"),
    Zone("Ag C", "Rural agriculture", "Agriculture", "#ADFF2F", "Black dots on vivid green"),
    Zone("Ru A", "Rural A", "Agriculture", "#ADFF2F"),
    Zone("Ru B", "Rural B", "Agriculture", "#ADFF2F"),
)

ZONE_BY_CODE = {zone.code: zone for zone in ZONES}


def _key(text: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


_LOOKUP = {
    _key(name): zone.code
    for zone in ZONES
    for name in (zone.code, zone.name, zone.name.split(":")[0], *zone.aliases)
}


def match(value: Any) -> Zone | None:
    """The national zone a layer's value names: its code ("Re A", "ReA", "re a"),
    its name, or a common way of writing it. None when it isn't recognised."""
    if value in (None, ""):
        return None
    code = _LOOKUP.get(_key(value))
    return ZONE_BY_CODE[code] if code else None


def standard_values(zone: Zone) -> dict[str, Any]:
    """The zone's site standards as DevelopmentStandard field values."""
    site = zone.site
    if site is None:
        return {}
    return {
        "min_plot_m2": site.min_plot_m2,
        "min_width_m": site.min_width_m,
        "max_coverage_pct": site.max_coverage_pct,
        "min_floors": site.min_floors,
        "max_floors": site.max_floors,
        "front_setback_m": site.front_setback_m,
        "side_setback_m": site.side_setback_m,
        "rear_setback_m": site.rear_setback_m,
        "prohibited_uses": list(zone.prohibited_keywords),
    }


def zone_json(zone: Zone) -> dict[str, Any]:
    return {
        "code": zone.code,
        "name": zone.name,
        "group": zone.group,
        "colour": zone.colour,
        "pattern": zone.pattern,
        "height": zone.site.height if zone.site else "",
        "standard": standard_values(zone) or None,
        "permitted": list(zone.permitted),
        "prohibited": list(zone.prohibited),
    }
