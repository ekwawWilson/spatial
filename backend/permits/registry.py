"""What the Regulations fix about permits: the kinds of permit and what needs
them, the documents an application carries, the deadlines, and what a site
inspection looks at. Land Use and Spatial Planning Regulations, 2019
(L.I. 2384) r.43-46, and LUSPA's Guidelines on Development Permitting.

Fees are not here: they come from each Assembly's fee-fixing resolution
(permits.models.Fee)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    code: str
    label: str
    kind: str  # "planning" (r.44(1)) or "development" (r.45(1))


CATEGORIES: tuple[Category, ...] = (
    # r.45(1): physical development that requires a development permit.
    Category("building", "Erection of a building or structure", "development"),
    Category("alteration", "Structural alteration, transformation or renovation", "development"),
    Category("works", "Works or installation of fittings in a building", "development"),
    Category("civil", "Civil and engineering works", "development"),
    Category("hoarding_dev", "Hoarding of a property", "development"),
    Category("regularisation", "Regularisation of an existing structure", "development"),
    Category("redevelopment", "Redevelopment", "development"),
    # r.44(1): physical development that requires a planning permit.
    Category("temporary", "Temporary structure", "planning"),
    Category("public_space", "Temporary activity using public space", "planning"),
    Category("demolition", "Demolition", "planning"),
    Category("change_of_use", "Change of use", "planning"),
    Category("advertisement", "Advertisement", "planning"),
    Category("consolidation", "Consolidation of land", "planning"),
    Category("subdivision", "Subdivision of land", "planning"),
    Category("hoarding", "Hoarding", "planning"),
    Category("extraction", "Sand winning, quarrying or minerals extraction", "planning"),
    Category("waste_disposal", "Disposal of industrial or chemical waste on land", "planning"),
    Category("excavation", "Excavation", "planning"),
    Category("colour_scheme", "Change in colour scheme", "planning"),
    Category("tree_removal", "Tree removal", "planning"),
)
CATEGORY_BY_CODE = {c.code: c for c in CATEGORIES}


@dataclass(frozen=True)
class Requirement:
    code: str
    label: str
    # Which applications must carry it: a kind, "multi_storey", or "where_applicable".
    applies: tuple[str, ...]
    rule: str


# r.44(3) and r.45(9): what accompanies an application (four sets of each).
REQUIREMENTS: tuple[Requirement, ...] = (
    Requirement(
        "land_right",
        "Evidence of the right to use the land (indenture, lease, title certificate or"
        " allocation note)",
        ("planning", "development"),
        "r.44(3)(a), r.45(9)(e)",
    ),
    Requirement(
        "site_plan",
        "Site plan at 1:2500, conforming to the local plan",
        ("planning", "development"),
        "r.44(3)(b), r.45(9)(a)",
    ),
    Requirement(
        "block_plan",
        "Block plan at 1:100 or 1:200",
        ("planning", "development"),
        "r.44(3)(c), r.45(9)(b)",
    ),
    Requirement(
        "architectural", "Architectural drawings at 1:20 or 1:40", ("development",), "r.45(9)(c)"
    ),
    Requirement(
        "structural", "Structural drawings at 1:20 or 1:40", ("multi_storey",), "r.45(9)(d)"
    ),
    Requirement(
        "zoning_report",
        "Zoning assessment and justification report",
        ("change_of_use",),
        "r.44(3)(d)",
    ),
    Requirement(
        "consultation", "Report on stakeholder consultation", ("where_applicable",), "r.45(9)(f)"
    ),
    Requirement(
        "environmental",
        "Environmental protection report or permit",
        ("where_applicable",),
        "r.44(3)(f), r.45(9)(g)",
    ),
    Requirement(
        "fire", "Fire safety report or permit", ("where_applicable",), "r.44(3)(f), r.45(9)(g)"
    ),
    Requirement(
        "traffic", "Traffic impact report", ("where_applicable",), "r.44(3)(f), r.45(9)(g)"
    ),
    Requirement(
        "geotechnical",
        "Geo-technical impact report",
        ("where_applicable",),
        "r.44(3)(f), r.45(9)(g)",
    ),
    Requirement(
        "hydrological",
        "Hydrological impact report",
        ("where_applicable",),
        "r.44(3)(f), r.45(9)(g)",
    ),
    Requirement(
        "structural_integrity",
        "Structural impact or integrity report",
        ("where_applicable",),
        "r.44(3)(f), r.45(9)(g)",
    ),
    Requirement(
        "aviation", "Air or aviation safety report", ("where_applicable",), "r.44(3)(f), r.45(9)(g)"
    ),
    Requirement(
        "radiation", "Radiation protection report", ("where_applicable",), "r.44(3)(f), r.45(9)(g)"
    ),
    Requirement(
        "petroleum", "Petroleum operations report", ("where_applicable",), "r.44(3)(f), r.45(9)(g)"
    ),
    Requirement(
        "standards", "Standard verification report", ("where_applicable",), "r.44(3)(f), r.45(9)(g)"
    ),
)
REQUIREMENT_BY_CODE = {r.code: r for r in REQUIREMENTS}
# A building of this many storeys or more is "multi-storey" for the documents it needs.
MULTI_STOREY_FROM = 2


def required_documents(kind: str, category: str, floors: int | None) -> list[str]:
    """The documents this application must carry (the "where applicable" ones
    are asked for by the officer, not required of every application)."""
    tags = {kind}
    if category == "change_of_use":
        tags.add("change_of_use")
    if kind == "development" and floors is not None and floors >= MULTI_STOREY_FROM:
        tags.add("multi_storey")
    return [r.code for r in REQUIREMENTS if tags & set(r.applies)]


@dataclass(frozen=True)
class Clock:
    code: str
    label: str
    days: int  # after the application is received
    rule: str
    # The application field that records it was done.
    done: str


# r.44(6)-(10); r.45(10) applies the same procedure to development permits.
CLOCKS: tuple[Clock, ...] = (
    Clock("acknowledge", "Acknowledge receipt in writing", 7, "r.44(6)", "acknowledged_on"),
    Clock(
        "inspect",
        "Technical Sub-Committee: zoning checks and site inspection",
        14,
        "r.44(7)",
        "inspected_on",
    ),
    Clock(
        "report",
        "Technical Sub-Committee report to the Spatial Planning Committee",
        21,
        "r.44(8)",
        "reported_on",
    ),
    Clock("issue", "Decision, and the certificate where granted", 30, "r.44(10)", "decided_on"),
)
PERMIT_VALID_YEARS = (
    5  # LUSPA Guidelines on Development Permitting: validity of a development permit
)
HABITATION_DAYS = 14  # r.45(18): after the inspection of the completed development
APPEAL_WITHIN_DAYS = 30  # Act 925 s.172(2): to lodge
APPEAL_DECISION_DAYS = 21  # Act 925 s.168(8), r.62(3): to decide
# r.62-63: a review (Form 53) goes to the body that decided; an appeal against
# the Assembly (Form 54) to the Regional Coordinating Council, and against the
# Council to the Authority. Each is decided and served within 21 days.
CHALLENGE_BODIES = {
    "review": (("assembly", "The District Assembly"),),
    "appeal": (
        ("rcc", "The Regional Coordinating Council"),
        ("luspa", "The Land Use and Spatial Planning Authority"),
    ),
}
CHALLENGE_FORMS = {"review": ("53", "r.62"), "appeal": ("54", "r.63")}

# r.44(7)(f): what the site inspection ascertains.
INSPECTION_POINTS: tuple[tuple[str, str], ...] = (
    ("veracity", "The submission's issues and proposals are true and feasible"),
    ("plot_size", "The plot size"),
    ("plot_location", "The plot location"),
    ("access", "Access size and alignment"),
    ("started", "Whether development has started"),
    ("adjoining_development", "Adjoining development: type, size and scope"),
    ("adjoining_uses", "Adjoining uses"),
    ("incompatibility", "Outright incompatibility caused or suffered by the proposal"),
    ("filth", "Whether the land is covered by hazardous, faecal or other offensive matter"),
    ("fire", "Fire safety issues"),
    ("environment", "General environmental concerns"),
    ("coordinates", "The coordinates of the parcel"),
    ("other", "Any other relevant consideration"),
)

# r.44(2), r.45(4): what the Spatial Planning Committee considers.
CONSIDERATIONS: tuple[str, ...] = (
    "Land use",
    "Orientation of physical development",
    "Size and plot coverage",
    "Height zoning",
    "Building densities",
    "Building lines and setbacks",
    "Colour schemes",
    "Physical accessibility to the site, facilities and utilities",
    "Population threshold",
    "Facility size threshold",
    "Minimum facility requirements",
    "Land size requirement",
)
