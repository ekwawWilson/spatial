"""The parts layers can play in a project, and the kinds of link between them.

Layers are generic (a domain, a geometry type, a schema), so a project says
which of its layers holds the properties, the streets, the flood-prone areas
and so on. The procedures work on those roles.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Role:
    code: str
    label: str
    domain: str  # the data domain a layer in this role usually has
    geometry: tuple[str, ...]
    # Words in a layer's name that suggest this role.
    hints: tuple[str, ...]
    # Attribute settings a role can have: name -> (label, default field name)
    fields: tuple[tuple[str, str, str], ...] = ()


ROLES: tuple[Role, ...] = (
    Role(
        "properties",
        "Properties (buildings)",
        "C",
        ("polygon", "point"),
        ("building", "propert", "structure"),
        (
            ("id_field", "Property id", "property_id"),
            ("floors_field", "Number of floors", "floors"),
        ),
    ),
    Role(
        "parcels",
        "Parcels",
        "B",
        ("polygon",),
        ("parcel", "plot", "cadastr"),
        (("id_field", "Parcel id", "parcel_id"), ("zone_field", "Land use or zone", "land_use")),
    ),
    Role(
        "streets",
        "Streets",
        "D",
        ("line",),
        ("street", "road"),
        (("name_field", "Street name", "name"),),
    ),
    Role(
        "communities",
        "Communities",
        "A",
        ("polygon",),
        ("communit", "neighbourhood", "localit"),
        (("name_field", "Community name", "name"),),
    ),
    Role(
        "local_plans",
        "Local plans",
        "J",
        ("polygon",),
        ("local plan", "layout", "scheme"),
        (("name_field", "Plan name", "name"),),
    ),
    Role(
        "structure_plans",
        "Structure plans",
        "J",
        ("polygon",),
        ("structure plan", "sdf"),
        (("name_field", "Plan name", "name"),),
    ),
    Role(
        "zoning",
        "Zoning",
        "J",
        ("polygon",),
        ("zoning", "zones plan"),
        (("zone_field", "Zone", "zone"),),
    ),
    Role(
        "flood_risk",
        "Flood-prone areas",
        "F",
        ("polygon",),
        ("flood",),
        (("risk_field", "Risk level", "risk"),),
    ),
    Role("drains", "Drains", "E", ("line",), ("drain", "culvert", "gutter"), ()),
    Role(
        "permits",
        "Development permits",
        "G",
        ("point", "polygon"),
        ("permit", "application"),
        (
            ("property_field", "Property id on the permit", "property_id"),
            ("status_field", "Permit status", "status"),
        ),
    ),
    Role(
        "facilities",
        "Infrastructure and facilities",
        "E",
        ("point", "polygon"),
        ("facilit", "school", "clinic", "health", "market", "infrastructure"),
        (("type_field", "Facility type", "type"),),
    ),
    Role(
        "population",
        "Population",
        "H",
        ("polygon", "point"),
        ("population", "household", "census", "enumeration"),
        (("population_field", "Population", "population"),),
    ),
    Role(
        "needs",
        "Development needs",
        "H",
        ("point", "polygon"),
        ("need",),
        (("type_field", "Kind of need", "type"),),
    ),
    Role(
        "projects",
        "Projects and investment",
        "I",
        ("point", "polygon", "line"),
        ("project", "investment"),
        (("type_field", "Sector or kind", "type"),),
    ),
)
ROLE_BY_CODE = {role.code: role for role in ROLES}
# For the API schema, which needs its own name for this list (see settings).
ROLE_CHOICES = [(role.code, role.label) for role in ROLES]


@dataclass(frozen=True)
class LinkType:
    code: str
    subject: str  # role of the feature the link starts from
    verb: str
    object: str  # role of the feature it points to ("" for a planning standard)
    procedure: str
    # What the link is called when read from the object's side.
    inverse: str


# The twelve relationships of the data architecture, in the order they are worked out.
LINK_TYPES: tuple[LinkType, ...] = (
    LinkType("belongs_to", "properties", "belongs to", "communities", "containment", "contains"),
    LinkType(
        "within_local_plan", "properties", "falls within", "local_plans", "containment", "covers"
    ),
    LinkType(
        "within_structure_plan",
        "properties",
        "falls within",
        "structure_plans",
        "containment",
        "covers",
    ),
    LinkType(
        "contains_infrastructure", "communities", "contains", "facilities", "containment", "is in"
    ),
    LinkType("located_on", "properties", "is located on", "streets", "access", "fronts"),
    LinkType("served_by", "properties", "is served by", "streets", "access", "serves"),
    LinkType("affected_by", "properties", "is affected by", "flood_risk", "flood", "affects"),
    LinkType("connected_to", "properties", "is connected to", "drains", "drainage", "drains"),
    LinkType("has_permit", "properties", "has", "permits", "permits", "is for"),
    LinkType("violates", "properties", "violates", "", "rules", "is violated by"),
    LinkType("serves", "facilities", "serves", "population", "catchments", "is served by"),
    LinkType("addresses", "projects", "addresses", "needs", "needs", "is addressed by"),
)
TYPE_BY_CODE = {t.code: t for t in LINK_TYPES}

# The order procedures run in. "aggregation" makes no links: it summarises them.
PROCEDURES: tuple[tuple[str, str], ...] = (
    (
        "containment",
        "The community and plans each property falls in; the facilities each community has",
    ),
    ("access", "The street each property is on, and whether a road serves it"),
    ("flood", "Properties in flood-prone areas"),
    ("drainage", "The drain each property probably uses (to be confirmed in the field)"),
    ("permits", "The permit each property has"),
    ("rules", "Developments that break the district's planning standards"),
    ("catchments", "The population each facility serves"),
    ("needs", "The development need each project addresses"),
    ("aggregation", "Totals for each community"),
)
