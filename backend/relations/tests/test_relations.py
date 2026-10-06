# ruff: noqa: E501 - long assertions read better on one line
"""Phase 12: the relationship layer and its procedures, against the fixture
community (fixtures/README.md): six buildings on six parcels either side of
Main Street; B-006 stands in the flood-prone area; B-003 is 0.5 m from its
parcel boundary where 3 m is required."""

from pathlib import Path

import pytest
from django.urls import reverse

from core.models import AuditLog, Role
from core.tenancy import tenant_context
from relations import tasks
from relations.models import Relationship, Run
from relations.registry import LINK_TYPES

pytestmark = pytest.mark.django_db

LAYERS = {
    "buildings": "polygon",
    "parcels": "polygon",
    "streets": "line",
    "communities": "polygon",
    "drains": "line",
    "flood_zones": "polygon",
}
ROLE_OF = {
    "buildings": "properties",
    "parcels": "parcels",
    "streets": "streets",
    "communities": "communities",
    "drains": "drains",
    "flood_zones": "flood_risk",
}
FOOT = 0.3047997101815088


@pytest.fixture
def planner(api, members_a, district_a):
    return api(members_a[Role.PLANNER], district_a)


@pytest.fixture
def admin(api, members_a, district_a):
    return api(members_a[Role.DISTRICT_ADMIN], district_a)


class World:
    """A project holding the fixture community, with helpers to read it."""

    def __init__(self, client, project_id, layers):
        self.client, self.project, self.layers = client, project_id, layers

    def features(self, layer, key):
        url = reverse("layer-features", args=[self.layers[layer]]) + "?geometry=native"
        return {f["properties"][key]: f for f in self.client.get(url).json()["features"]}

    def set_roles(self, mapping=None, client=None, **config):
        roles = [
            {"role": role, "layer": self.layers[layer], "config": config.get(role, {})}
            for layer, role in (mapping or ROLE_OF).items()
        ]
        return (client or self.client).put(
            reverse("project-layer-roles", args=[self.project]), {"roles": roles}, format="json"
        )

    def run(self, client=None):
        response = (client or self.client).post(
            reverse("project-relations-run", args=[self.project])
        )
        assert response.status_code == 201, response.content
        return response.json()

    def links(self, **params):
        response = self.client.get(
            reverse("relationship-list"), {"project": self.project, **params}
        )
        assert response.status_code == 200, response.content
        return response.json()["results"]

    def pairs(self, link_type, **params):
        return sorted(
            (link["subject"]["label"], link["object"]["label"] if link["object"] else link["rule"])
            for link in self.links(type=link_type, **params)
        )

    def add_layer(self, name, geometry_type, schema, domain="other"):
        response = self.client.post(
            reverse("layer-list"),
            {
                "project": self.project,
                "name": name,
                "domain": domain,
                "geometry_type": geometry_type,
                "schema": schema,
            },
            format="json",
        )
        assert response.status_code == 201, response.content
        self.layers[name] = response.json()["id"]
        return response.json()["id"]

    def add(self, layer, geometry, **properties):
        response = self.client.post(
            reverse("layer-features", args=[self.layers[layer]]),
            {"geometry": geometry, "properties": properties},
            format="json",
        )
        assert response.status_code == 201, response.content
        return response.json()


def centre(feature):
    ring = feature["geometry"]["coordinates"][0][:-1]
    if feature["geometry"]["type"] == "MultiPolygon":
        ring = feature["geometry"]["coordinates"][0][0][:-1]
    return [sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)]


def point(xy, east_m=0.0, north_m=0.0):
    return {"type": "Point", "coordinates": [xy[0] + east_m / FOOT, xy[1] + north_m / FOOT]}


@pytest.fixture
def world(planner, fixtures_dir, django_capture_on_commit_callbacks):
    project = planner.post(
        reverse("project-list"), {"name": "Relations plan"}, format="json"
    ).json()
    with open(Path(fixtures_dir) / "generated" / "sample.gpkg", "rb") as fh:
        job = planner.post(
            reverse("datajob-upload"), {"project": project["id"], "file": fh}, format="multipart"
        ).json()
    by_name = {layer["name"]: layer for layer in job["inspection"]["layers"]}
    plan = [
        {
            "source": name,
            "crs": "EPSG:2136",
            "crs_confirmed": True,
            "new_layer": {"name": name, "domain": "other", "geometry_type": geometry},
            "fields": [
                {"source": f["name"], "target": f["suggested_name"], "type": f["type"]}
                for f in by_name[name]["fields"]
            ],
        }
        for name, geometry in LAYERS.items()
    ]
    with django_capture_on_commit_callbacks(execute=True):
        started = planner.post(
            reverse("datajob-run", args=[job["id"]]), {"layers": plan}, format="json"
        )
    assert started.status_code == 202, started.content
    done = planner.get(reverse("datajob-detail", args=[job["id"]])).json()
    assert done["status"] == "done", done
    layers = {
        layer["name"]: layer["id"]
        for layer in planner.get(reverse("layer-list"), {"project": project["id"]}).json()
    }
    return World(planner, project["id"], layers)


# --- Setting up ------------------------------------------------------------------------------------


def test_registry_lists_the_twelve_relationships(planner):
    data = planner.get(reverse("relations-registry")).json()
    assert len(data["link_types"]) == len(LINK_TYPES) == 12
    assert [p["code"] for p in data["procedures"]] == [
        "containment",
        "access",
        "flood",
        "drainage",
        "permits",
        "rules",
        "catchments",
        "needs",
        "aggregation",
    ]
    assert {"properties", "streets", "flood_risk", "permits", "needs"} <= {
        r["code"] for r in data["roles"]
    }


def test_layers_are_suggested_for_roles_and_checked(world, api, members_a, district_a):
    url = reverse("project-layer-roles", args=[world.project])
    suggested = {r["role"]: r["suggested"] for r in world.client.get(url).json()["roles"]}
    for layer, role in ROLE_OF.items():
        assert suggested[role] == world.layers[layer], role
    assert suggested["permits"] is None

    wrong = world.set_roles({"streets": "properties"})  # a line layer can't hold properties
    assert wrong.status_code == 400 and "needs a polygon or point layer" in str(wrong.json())
    viewer = api(members_a[Role.VIEWER], district_a)
    assert world.set_roles(client=viewer).status_code == 403
    assert viewer.get(url).status_code == 200

    # Nothing is mapped yet, so there is nothing to run.
    assert (
        world.client.post(reverse("project-relations-run", args=[world.project])).status_code == 400
    )
    saved = world.set_roles()
    assert saved.status_code == 200
    assert {r["role"]: r["layer"] for r in saved.json()["roles"]}["flood_risk"] == world.layers[
        "flood_zones"
    ]
    assert AuditLog.objects.filter(table_name="relations_layerrole").count() == 6


# --- The procedures, against known answers ------------------------------------------------------


def test_containment_and_streets(world):
    world.set_roles()
    run = world.run()
    assert run["status"] == "done" and run["report"]["containment"]["belongs_to"]["added"] == 6
    buildings = [f"B-00{n}" for n in range(1, 7)]
    assert world.pairs("belongs_to") == [(b, "Community A") for b in buildings]
    assert world.pairs("located_on") == [(b, "Main Street") for b in buildings]
    assert world.pairs("served_by") == [(b, "Main Street") for b in buildings]
    link = world.links(type="located_on")[0]
    assert link["method"] == "calculated" and link["details"]["distance_m"] == pytest.approx(
        13.0, abs=0.3
    )
    assert link["verb"] == "is located on" and link["subject"]["layer"] == "buildings"
    # Layers that aren't mapped are reported, not guessed.
    assert "Development permits" in run["report"]["permits"]["skipped"]


def test_the_building_in_the_flood_zone_is_found(world):
    """Gate: the seeded building in the flood-prone area is detected."""
    world.set_roles()
    world.run()
    assert world.pairs("affected_by") == [("B-006", "F-001")]
    (link,) = world.links(type="affected_by")
    assert link["details"]["risk"] == "high" and link["details"]["share"] == pytest.approx(
        17 / 24, abs=0.02
    )


def test_the_setback_breach_is_flagged(world):
    """Gate: the seeded setback breach is flagged, and only that one."""
    world.set_roles()
    world.run()
    assert world.pairs("violates") == [("B-003", "setback")]
    (link,) = world.links(type="violates")
    assert link["details"]["measured_m"] == pytest.approx(0.5, abs=0.05)
    assert link["details"]["required_m"] == 3.0 and link["object"] is None
    assert link["details"]["zone"] == "default"


def test_district_standards_change_what_counts_as_a_breach(world, admin):
    world.set_roles()
    url = reverse("standard-list")
    body = {"zone": "residential", "min_setback_m": 3, "max_floors": 1, "max_coverage_pct": 60}
    assert (
        world.client.post(url, body, format="json").status_code == 403
    )  # planners don't set standards
    created = admin.post(url, body, format="json")
    assert created.status_code == 201, created.content
    assert admin.post(url, body, format="json").status_code == 400  # one per zone
    assert admin.post(url, {"zone": "x", "max_coverage_pct": 140}, format="json").status_code == 400

    world.run()
    found = world.pairs("violates")
    # Two-storey buildings (the odd-numbered ones) are over the limit of one.
    assert [b for b, rule in found if rule == "floors"] == ["B-001", "B-003", "B-005"]
    # 24 x 24 m on a 900 m2 plot is 64%: every plot is over 60%.
    assert len([b for b, rule in found if rule == "coverage"]) == 6
    assert [b for b, rule in found if rule == "setback"] == ["B-003"]
    cover = next(
        link
        for link in world.links(type="violates", rule="coverage")
        if link["subject"]["label"] == "B-001"
    )
    assert (
        cover["details"]["measured_pct"] == pytest.approx(64.0, abs=0.5)
        and cover["details"]["zone"] == "residential"
    )

    # Relaxing the standard removes the breaches it made.
    admin.patch(
        reverse("standard-detail", args=[created.json()["id"]]),
        {"max_floors": None, "max_coverage_pct": 70},
        format="json",
    )
    world.run()
    assert world.pairs("violates") == [
        ("B-003", "coverage"),
        ("B-003", "setback"),
    ]  # 26.5 x 24 m is 70.7%


def test_drainage_is_inferred_then_confirmed_by_people(world):
    world.set_roles()
    world.run()
    # The drain runs along the north side of Main Street: 7 m from the north row, 19 m from the south.
    assert world.pairs("connected_to") == [
        ("B-001", "D-001"),
        ("B-002", "D-001"),
        ("B-003", "D-001"),
    ]
    links = {link["subject"]["label"]: link for link in world.links(type="connected_to")}
    assert all(
        link["method"] == "inferred" and 0.5 < link["confidence"] < 0.9 for link in links.values()
    )

    confirmed = world.client.post(
        reverse("relationship-confirm", args=[links["B-001"]["id"]]),
        {"note": "Seen on site"},
        format="json",
    )
    assert confirmed.status_code == 200 and confirmed.json()["method"] == "confirmed"
    assert (
        confirmed.json()["confidence"] == 1.0 and confirmed.json()["details"]["was"] == "inferred"
    )
    rejected = world.client.post(
        reverse("relationship-reject", args=[links["B-002"]["id"]]),
        {"note": "Drains to the back"},
        format="json",
    )
    assert rejected.json()["status"] == "rejected"

    # Running again leaves what people decided alone, and doesn't churn the rest.
    report = world.run()["report"]["drainage"]["connected_to"]
    assert report == {"found": 3, "added": 0, "updated": 0, "removed": 0, "kept": 2}
    after = {link["subject"]["label"]: link for link in world.links(type="connected_to")}
    assert after["B-001"]["method"] == "confirmed" and after["B-001"]["note"] == "Seen on site"
    assert after["B-002"]["status"] == "rejected" and after["B-003"]["id"] == links["B-003"]["id"]
    assert len(after) == 3
    # A wider reach brings in the south row; the rejected link still isn't remade.
    world.set_roles(drains={"max_m": 25})
    world.run()
    assert len(world.links(type="connected_to")) == 6
    assert len(world.links(type="connected_to", status="rejected")) == 1

    reopened = world.client.post(reverse("relationship-reopen", args=[links["B-002"]["id"]])).json()
    assert reopened["status"] == "active" and reopened["decided_at"] is None
    assert AuditLog.objects.filter(
        table_name="relations_relationship", row_id=str(links["B-001"]["id"]), action="UPDATE"
    ).exists()


def test_permits_match_by_id_first_then_by_place(world, admin):
    world.set_roles()
    buildings = world.features("buildings", "property_id")
    world.add_layer(
        "Permits",
        "point",
        [
            {"name": "permit_no", "type": "text"},
            {"name": "property_id", "type": "text"},
            {"name": "status", "type": "text"},
        ],
        domain="G",
    )
    far = point(centre(buildings["B-006"]), east_m=400)
    world.add(
        "Permits", far, permit_no="PA-1", property_id="B-001", status="approved"
    )  # names B-001, filed elsewhere
    world.add(
        "Permits", point(centre(buildings["B-002"])), permit_no="PA-2", status="pending"
    )  # no id: on B-002
    world.add(
        "Permits",
        point(centre(buildings["B-005"])),
        permit_no="PA-3",
        property_id="B-004",
        status="approved",
    )  # sits on B-005, names B-004
    world.set_roles({**ROLE_OF, "Permits": "permits"})
    world.run()
    links = {link["subject"]["label"]: link for link in world.links(type="has_permit")}
    assert sorted(links) == ["B-001", "B-002", "B-004"]
    assert (links["B-001"]["method"], links["B-001"]["details"]["matched_by"]) == (
        "calculated",
        "id",
    )
    assert (links["B-002"]["method"], links["B-002"]["confidence"]) == ("inferred", 0.8)
    assert links["B-004"]["details"]["status"] == "approved"

    # Where permits are required, building without one is a breach.
    admin.post(reverse("standard-list"), {"zone": "", "permit_required": True}, format="json")
    world.run()
    assert [b for b, rule in world.pairs("violates") if rule == "no_permit"] == [
        "B-003",
        "B-005",
        "B-006",
    ]


def test_facilities_catchments_needs_and_projects(world):
    parcels = world.features("parcels", "parcel_id")
    community = world.features("communities", "code")["SMA-A"]
    spot = centre(parcels["P-001"])
    world.add_layer(
        "Facilities",
        "point",
        [{"name": "name", "type": "text"}, {"name": "type", "type": "text"}],
        domain="E",
    )
    world.add("Facilities", point(spot), name="Kasoa Primary", type="school")
    world.add_layer(
        "Population",
        "polygon",
        [{"name": "name", "type": "text"}, {"name": "population", "type": "integer"}],
        domain="H",
    )
    world.add("Population", community["geometry"], name="EA 12", population=1200)
    world.add_layer(
        "Needs",
        "point",
        [{"name": "name", "type": "text"}, {"name": "type", "type": "text"}],
        domain="H",
    )
    world.add("Needs", point(spot, east_m=60), name="Classroom block", type="school")
    world.add_layer(
        "Projects",
        "point",
        [{"name": "name", "type": "text"}, {"name": "type", "type": "text"}],
        domain="I",
    )
    world.add("Projects", point(spot, east_m=90), name="6-unit classroom", type="School")
    world.add("Projects", point(spot, east_m=30), name="Culvert", type="road")
    world.add("Projects", point(spot, north_m=40), name="Unlabelled works")
    world.add("Projects", point(spot, east_m=5000), name="Far away", type="school")
    mapping = {
        **ROLE_OF,
        "Facilities": "facilities",
        "Population": "population",
        "Needs": "needs",
        "Projects": "projects",
    }
    assert world.set_roles(mapping).status_code == 200
    summary = world.run()["summary"]

    assert world.pairs("contains_infrastructure") == [("Community A", "Kasoa Primary")]
    (serves,) = world.links(type="serves")
    assert (serves["subject"]["label"], serves["object"]["label"]) == ("Kasoa Primary", "EA 12")
    assert serves["details"]["population"] == 1200 and serves["details"]["distance_m"] == 0

    addressed = {link["subject"]["label"]: link for link in world.links(type="addresses")}
    assert sorted(addressed) == [
        "6-unit classroom",
        "Unlabelled works",
    ]  # not the road project, not the far one
    assert (
        addressed["6-unit classroom"]["confidence"] == 0.8
        and addressed["Unlabelled works"]["confidence"] == 0.5
    )
    assert all(link["method"] == "inferred" for link in addressed.values())
    assert summary["project"]["population_served"] == 1200
    assert (summary["project"]["needs"], summary["project"]["needs_addressed"]) == (1, 1)


def test_totals_for_the_project_and_each_community(world):
    """The aggregation: the baseline a plan starts from, also on the checklist."""
    world.set_roles()
    summary = world.run()["summary"]
    assert summary["project"] == {
        "properties": 6,
        "in_flood_area": 1,
        "without_road_access": 0,
        "without_drain": 3,
        "with_violations": 1,
        "violations": {"setback": 1},
        "in_no_community": 0,
    }
    rows = {row["name"]: row for row in summary["communities"]}
    assert rows["Community A"]["properties"] == 6 and rows["Community A"]["in_flood_area"] == 1
    assert rows["Community B"]["properties"] == 0

    checklist = world.client.get(reverse("project-checklist", args=[world.project])).json()
    assert (
        checklist["baseline"]["in_flood_area"] == 1
        and checklist["baseline"]["with_violations"] == 1
    )
    latest = world.client.get(reverse("project-relations-run", args=[world.project])).json()
    assert (
        latest["latest"]["trigger"] == "manual" and latest["summary"]["project"]["properties"] == 6
    )


# --- Keeping up with edits ----------------------------------------------------------------------


def test_everything_linked_to_one_feature(world):
    world.set_roles()
    world.run()
    b6 = world.features("buildings", "property_id")["B-006"]
    links = world.links(feature=b6["id"])
    assert sorted(link["type"] for link in links) == [
        "affected_by",
        "belongs_to",
        "located_on",
        "served_by",
    ]
    # From the other side: what the flood area affects.
    zone = world.features("flood_zones", "zone_id")["F-001"]
    (inverse,) = world.links(feature=zone["id"])
    assert inverse["inverse"] == "affects" and inverse["subject"]["label"] == "B-006"


def test_an_edit_refreshes_that_propertys_links(world, django_capture_on_commit_callbacks):
    world.set_roles()
    world.run()
    buildings = world.features("buildings", "property_id")
    b1, b6 = buildings["B-001"], buildings["B-006"]
    before = {link["id"] for link in world.links(type="belongs_to")}
    # B-001 is redrawn where B-006 stands: in the flood-prone area.
    with django_capture_on_commit_callbacks(execute=True):
        moved = world.client.patch(
            reverse("feature-detail", args=[b1["id"]]),
            {"version": b1["meta"]["version"], "geometry": b6["geometry"]},
            format="json",
        )
    assert moved.status_code == 200, moved.content
    assert world.pairs("affected_by") == [("B-001", "F-001"), ("B-006", "F-001")]
    run = Run.objects.filter(project_id=world.project).first()
    assert run.trigger == "edit" and run.status == "done"
    # Links that didn't change are the same rows: a refresh doesn't churn them.
    assert {link["id"] for link in world.links(type="belongs_to")} == before
    assert Run.objects.filter(project_id=world.project).count() == 2


def test_nightly_run_covers_every_mapped_project(world, planner):
    world.set_roles()
    planner.post(reverse("project-list"), {"name": "Nothing mapped"}, format="json")
    assert tasks.nightly() == 1
    run = Run.objects.filter(project_id=world.project).first()
    assert run.trigger == "nightly" and run.report["flood"]["affected_by"]["added"] == 1


def test_links_a_person_made_and_unmapped_layers(world):
    world.set_roles()
    world.run()
    buildings = world.features("buildings", "property_id")
    drain = world.features("drains", "drain_id")["D-001"]
    manual = world.client.post(
        reverse("relationship-list"),
        {
            "type": "connected_to",
            "subject": buildings["B-006"]["id"],
            "object": drain["id"],
            "note": "Piped under the road",
        },
        format="json",
    )
    assert manual.status_code == 201 and manual.json()["method"] == "confirmed"
    street = world.features("streets", "name")["Main Street"]
    wrong = world.client.post(
        reverse("relationship-list"),
        {"type": "connected_to", "subject": buildings["B-006"]["id"], "object": street["id"]},
        format="json",
    )
    assert wrong.status_code == 400 and "Drains" in str(wrong.json())

    # Drains are unmapped: the links procedures made go; the one a person made stays.
    cleared = world.client.put(
        reverse("project-layer-roles", args=[world.project]),
        {"roles": [{"role": "drains", "layer": None}]},
        format="json",
    )
    assert cleared.status_code == 200
    report = world.run()["report"]
    assert report["unmapped"]["connected_to"] == 3 and "skipped" in report["drainage"]
    assert world.pairs("connected_to") == [("B-006", "D-001")]


# --- Roles and tenancy ---------------------------------------------------------------------------


def test_roles_and_tenancy(world, api, members_a, district_a, district_b, make_member):
    world.set_roles()
    world.run()
    link = world.links(type="affected_by")[0]
    viewer = api(members_a[Role.VIEWER], district_a)
    assert viewer.get(reverse("relationship-list"), {"project": world.project}).status_code == 200
    assert viewer.post(reverse("project-relations-run", args=[world.project])).status_code == 403
    assert viewer.post(reverse("relationship-reject", args=[link["id"]])).status_code == 403

    other = api(make_member(district_b, Role.DISTRICT_ADMIN, "b.admin@example.test"), district_b)
    assert (
        other.get(reverse("relationship-list"), {"project": world.project}).json()["results"] == []
    )
    assert other.get(reverse("project-layer-roles", args=[world.project])).status_code == 404
    assert other.post(reverse("project-relations-run", args=[world.project])).status_code == 404
    assert other.post(reverse("relationship-confirm", args=[link["id"]])).status_code == 404
    assert other.get(reverse("standard-list")).json() == []
    with tenant_context(district_b.id):
        assert Relationship.objects.count() == 0 and Run.objects.count() == 0
