"""Phase 13: restricted (personal) attribute values are hidden from roles
that may not see them, everywhere attributes leave the server."""

import uuid

import pytest
from django.urls import reverse

from core.auth import SENSITIVE_ROLES
from core.models import Role
from core.permissions import PERMISSIONS
from field import mbtiles

pytestmark = pytest.mark.django_db

OWNER = "Ama Serwaa Mensah"
SQUARE = [
    [1190600.0, 337700.0],
    [1190800.0, 337700.0],
    [1190800.0, 337900.0],
    [1190600.0, 337900.0],
    [1190600.0, 337700.0],
]
SCHEMA = [
    {"name": "parcel_id", "type": "text"},
    {"name": "owner", "type": "text", "sensitive": True},
]


@pytest.fixture
def clients(api, members_a, district_a):
    return {role: api(members_a[role], district_a) for role in Role}


@pytest.fixture
def parcel(clients):
    planner = clients[Role.PLANNER]
    project = planner.post(reverse("project-list"), {"name": "Privacy plan"}, format="json").json()
    layer = planner.post(
        reverse("layer-list"),
        {"project": project["id"], "name": "Parcels", "geometry_type": "polygon", "schema": SCHEMA},
        format="json",
    )
    assert layer.status_code == 201, layer.content
    feature = planner.post(
        reverse("layer-features", args=[layer.json()["id"]]),
        {
            "geometry": {"type": "Polygon", "coordinates": [SQUARE]},
            "properties": {"parcel_id": "P-1", "owner": OWNER},
        },
        format="json",
    )
    assert feature.status_code == 201, feature.content
    return {"project": project["id"], "layer": layer.json()["id"], **feature.json()}


def test_the_roles_that_see_restricted_values_match_the_permission_matrix():
    assert SENSITIVE_ROLES == PERMISSIONS["data.sensitive"]


def test_a_restricted_field_cannot_be_required(clients, parcel):
    response = clients[Role.PLANNER].patch(
        reverse("layer-detail", args=[parcel["layer"]]),
        {"schema": [{"name": "owner", "type": "text", "sensitive": True, "required": True}]},
        format="json",
    )
    assert response.status_code == 400 and "can't be required" in str(response.json())


@pytest.mark.parametrize(
    "role,sees",
    [
        (Role.DISTRICT_ADMIN, True),
        (Role.PLANNER, True),
        (Role.FIELD_OFFICER, False),
        (Role.VIEWER, False),
    ],
)
def test_feature_details_lists_history_and_tiles(clients, parcel, role, sees):
    client = clients[role]
    detail = client.get(reverse("feature-detail", args=[parcel["id"]])).json()
    listed = client.get(reverse("layer-features", args=[parcel["layer"]])).json()["features"][0]
    history = client.get(reverse("feature-history", args=[parcel["id"]])).json()
    for properties in (detail["properties"], listed["properties"], history[0]["properties"]):
        assert properties["parcel_id"] == "P-1"
        assert (properties.get("owner") == OWNER) is sees
        assert ("owner" in properties) is sees
    assert detail["meta"]["restricted"] == ([] if sees else ["owner"])

    # Map tiles carry attributes too: find the tile over the parcel.
    lon, lat = listed["geometry"]["coordinates"][0][0]
    x, y = mbtiles.tile_xy(lon, lat, 15)
    tile = client.get(reverse("layer-tile", args=[parcel["layer"], 15, x, y]))
    assert tile.status_code == 200
    assert (OWNER.encode() in tile.content) is sees
    assert b"P-1" in tile.content


def test_the_field_package_and_sync_leave_restricted_values_out(clients, parcel):
    officer = clients[Role.FIELD_OFFICER]
    package = officer.get(reverse("project-field-package", args=[parcel["project"]])).json()
    assert OWNER not in str(package)
    layer = package["layers"][0]
    assert [f["name"] for f in layer["schema"]] == ["parcel_id"]  # no form field for it either
    pulled = officer.get(reverse("sync-pull"), {"project": parcel["project"]}).json()
    assert OWNER not in str(pulled) and pulled["features"][0]["properties"] == {"parcel_id": "P-1"}
    # A planner's device does get it.
    assert OWNER in str(
        clients[Role.PLANNER].get(reverse("sync-pull"), {"project": parcel["project"]}).json()
    )


def test_a_field_edit_keeps_the_value_it_could_not_see(clients, parcel):
    officer = clients[Role.FIELD_OFFICER]

    def push(change):
        body = {"device_id": "d1", "changes": [{"change_id": str(uuid.uuid4()), **change}]}
        return officer.post(reverse("sync-push"), body, format="json").json()["results"][0]

    edit = {"op": "update", "feature_uuid": parcel["meta"]["uuid"], "base_version": 1}
    applied = push({**edit, "properties": {"parcel_id": "P-1A"}})
    assert applied["status"] == "applied"
    seen = clients[Role.PLANNER].get(reverse("feature-detail", args=[parcel["id"]])).json()
    assert seen["properties"] == {"parcel_id": "P-1A", "owner": OWNER}

    # Writing to a field you can't see is refused, on an edit and on a new capture.
    refused = push({**edit, "base_version": 2, "properties": {"owner": "Someone else"}})
    assert refused["status"] == "rejected" and "restricted" in str(refused["errors"])
    lon, lat = (
        clients[Role.PLANNER]
        .get(reverse("layer-features", args=[parcel["layer"]]))
        .json()["features"][0]["geometry"]["coordinates"][0][0]
    )
    ring = [[lon, lat], [lon + 0.0001, lat], [lon + 0.0001, lat + 0.0001], [lon, lat]]
    new = {
        "op": "create",
        "layer": parcel["layer"],
        "feature_uuid": str(uuid.uuid4()),
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }
    assert push({**new, "properties": {"parcel_id": "P-2", "owner": "X"}})["status"] == "rejected"
    assert push({**new, "properties": {"parcel_id": "P-2"}})["status"] == "applied"


def test_restricted_values_never_become_labels(clients, parcel):
    """Relationship labels fall back to a feature's text values: not this one."""
    planner, viewer = clients[Role.PLANNER], clients[Role.VIEWER]
    # A layer whose only text value is the restricted one.
    layer = planner.post(
        reverse("layer-list"),
        {
            "project": parcel["project"],
            "name": "Owners' buildings",
            "geometry_type": "polygon",
            "schema": [{"name": "owner", "type": "text", "sensitive": True}],
        },
        format="json",
    ).json()
    planner.post(
        reverse("layer-features", args=[layer["id"]]),
        {"geometry": {"type": "Polygon", "coordinates": [SQUARE]}, "properties": {"owner": OWNER}},
        format="json",
    )
    roles = [
        {"role": "properties", "layer": layer["id"]},
        {"role": "parcels", "layer": parcel["layer"]},
    ]
    assert (
        planner.put(
            reverse("project-layer-roles", args=[parcel["project"]]),
            {"roles": roles},
            format="json",
        ).status_code
        == 200
    )
    assert (
        planner.post(reverse("project-relations-run", args=[parcel["project"]])).status_code == 201
    )
    params = {"project": parcel["project"]}
    assert OWNER not in str(viewer.get(reverse("relationship-list"), params).json())
