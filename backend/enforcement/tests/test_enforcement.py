# ruff: noqa: E501 - long assertions read better on one line
"""Phase 17: enforcement cases and notices (Act 925 s.160-167; L.I. 2384
r.55-58), and finding new development by comparing two orthophotos."""

from datetime import date, timedelta
from pathlib import Path

import pytest
from django.urls import reverse
from osgeo import gdal

from core.models import AuditLog, Role
from core.tenancy import tenant_context
from enforcement import change
from enforcement.models import Case
from projects.models import Feature

pytestmark = pytest.mark.django_db
gdal.UseExceptions()

TODAY = date.today()
CASES = "enforcement-case-list"
# The fixture orthophoto: 200 m square, 1 m pixels, UTM 30N; this corner is its top left.
LEFT, TOP = 806_450.0, 618_100.0
ORIGIN_E, ORIGIN_N = 806_000.0, 617_000.0


def days(n):
    return str(TODAY + timedelta(days=n))


def open_case(client, world, **extra):
    body = {
        "project": world.project,
        "contravention": "no_permit",
        "description": "A block wall going up without a permit",
        "owner_name": "Kwesi Appiah",
        "owner_address": "Plot 14, Main Street",
        **extra,
    }
    return client.post(reverse(CASES), body, format="json")


def case_url(name, case):
    return reverse(f"enforcement-case-{name}", args=[case["id"]])


def notice_url(name, notice):
    return reverse(f"enforcement-notice-{name}", args=[notice["id"]])


def issue(client, case, kind, **extra):
    return client.post(
        case_url("notices", case),
        {
            "kind": kind,
            "grounds": "Building without a permit\nOn the road reservation",
            "remedy": "Stop work\nRemove the wall",
            **extra,
        },
        format="json",
    )


def test_what_the_law_fixes(planner):
    data = planner.get(reverse("enforcement-registry")).json()
    assert {n["code"]: n["form"] for n in data["notices"]} == {
        "stop": "48A",
        "rectification": "49",
        "enforcement": "47",
        "revocation": "48B",
        "entry": "50",
        "contravention": "",
        "breach": "",
        "untidy": "",
        "dangerous": "",
    }
    assert len(data["service_methods"]) == 8  # r.56(1)(a)-(h)
    assert data["days"] == {
        "enforcement_after": 14,
        "act_after": 14,
        "entry_notice": 3,
        "show_cause": 21,
    }


def test_a_case_from_notice_to_rectification(world, api, members_a, district_a):
    """Gate: the notices, how they are served, and the days between steps."""
    planner = world.client
    viewer = api(members_a[Role.VIEWER], district_a)
    officer = api(members_a[Role.FIELD_OFFICER], district_a)
    assert open_case(viewer, world).status_code == 403
    assert open_case(planner, world, contravention="parking").status_code == 400
    assert open_case(planner, world, opened_on=days(1)).status_code == 400

    # A field officer reports it; planners serve notices.
    made = open_case(officer, world, opened_on=days(-40))
    assert made.status_code == 201, made.content
    case = made.json()
    assert case["number"] == f"DA/EN/{TODAY.year}/0001" and case["status"] == "open"
    assert (case["contravention_label"], case["section"]) == (
        "Development without a permit",
        "section 117 of Act 925",
    )
    assert case["next_action"] == {"label": "Serve a notice", "due_on": None, "overdue": False}
    assert issue(officer, case, "rectification", comply_by=days(5)).status_code == 403

    # Form 49: a date to rectify by. Issued 30 days ago, to be done within 10.
    assert issue(planner, case, "rectification").status_code == 400  # by when?
    assert issue(planner, case, "ticket", comply_by=days(5)).status_code == 400
    assert (
        issue(planner, case, "rectification", comply_by=days(-35), on=days(-30)).status_code == 400
    )  # before it is issued
    case = issue(planner, case, "rectification", comply_by=days(-20), on=days(-30)).json()
    notice = case["notices"][0]
    assert (notice["label"], notice["form"], notice["served_on"]) == (
        "Notice for Rectification of Contravention",
        "49",
        None,
    )
    paper = viewer.get(notice_url("paper", notice))
    assert paper.status_code == 200 and paper.content.startswith(b"%PDF")

    # r.56: served by one of the ways the Regulations recognise.
    assert (
        planner.post(notice_url("serve", notice), {"method": "whatsapp"}, format="json").status_code
        == 400
    )
    assert (
        planner.post(
            notice_url("serve", notice), {"method": "on_land", "on": days(-31)}, format="json"
        ).status_code
        == 400
    )
    case = planner.post(
        notice_url("serve", notice),
        {"method": "on_land", "on": days(-30), "note": "Fixed to the gate"},
        format="json",
    ).json()
    assert (
        case["status"] == "notice"
        and case["notices"][0]["served_by_label"]
        == "Posted in a conspicuous place on the land or building"
    )

    # r.57(2): not rectified by the date, so an enforcement notice within 14 days. That was 6 days ago.
    dates = case["notices"][0]["dates"]
    assert dates == {"enforcement_notice_due_on": days(-6), "overdue": True, "past_comply_by": True}
    assert case["next_action"] == {
        "label": "Serve an enforcement notice (r.57(2))",
        "due_on": days(-6),
        "overdue": True,
    }
    assert planner.get(reverse(CASES), {"project": world.project}).json()["summary"] == {
        "total": 1,
        "open": 1,
        "overdue": 1,
    }

    # Form 47, served five days ago. r.57(4): the Assembly may act 14 days after service.
    case = issue(planner, case, "enforcement", comply_by=days(3), on=days(-5)).json()
    enforcement = case["notices"][1]
    case = planner.post(
        notice_url("serve", enforcement), {"method": "post", "on": days(-5)}, format="json"
    ).json()
    assert "enforcement_notice_due_on" not in case["notices"][0]["dates"]
    assert case["notices"][1]["dates"] == {
        "assembly_may_act_from": days(9),
        "past_comply_by": False,
    }
    early = planner.post(
        case_url("close", case), {"status": "enforced", "cost": "5000"}, format="json"
    )
    assert early.status_code == 400 and days(9) in str(early.json())

    # r.58: three days' notice before entering.
    case = issue(planner, case, "entry").json()
    case = planner.post(
        notice_url("serve", case["notices"][2]), {"method": "at_address"}, format="json"
    ).json()
    assert case["notices"][2]["dates"]["entry_not_before"] == days(3)

    # The owner pulls the wall down: rectified, and the notices are met.
    closed = planner.post(
        case_url("close", case),
        {"status": "rectified", "outcome": "Wall removed by the owner."},
        format="json",
    ).json()
    assert (
        closed["status"] == "rectified"
        and closed["closed_on"] == str(TODAY)
        and closed["next_action"] is None
    )
    assert all(n["complied_on"] == str(TODAY) for n in closed["notices"])
    assert issue(planner, closed, "stop").status_code == 400  # closed
    assert (
        planner.post(case_url("close", closed), {"status": "dropped"}, format="json").status_code
        == 400
    )
    assert (
        planner.patch(case_url("detail", closed), {"description": "x"}, format="json").status_code
        == 400
    )
    assert AuditLog.objects.filter(table_name="enforcement_notice", action="INSERT").count() == 3
    assert (
        AuditLog.objects.filter(
            table_name="enforcement_case", row_id=str(case["id"]), action="UPDATE"
        ).count()
        >= 2
    )


def test_the_assembly_rectifies_and_recovers_the_cost(
    world, admin, api, members_a, district_a, district_b, make_member
):
    planner = world.client
    case = open_case(planner, world, opened_on=days(-30), contravention="public_space").json()
    # A stop notice (Form 48A) takes effect at once: it has no date to comply by.
    stop = issue(planner, case, "stop", comply_by=days(10), on=days(-30)).json()["notices"][0]
    assert stop["comply_by"] is None and stop["form"] == "48A"
    assert (
        planner.post(case_url("close", case), {"status": "enforced"}, format="json").status_code
        == 400
    )  # no enforcement notice
    served = issue(planner, case, "enforcement", comply_by=days(-18), on=days(-25)).json()[
        "notices"
    ][1]
    planner.post(notice_url("serve", served), {"method": "on_land", "on": days(-25)}, format="json")
    done = planner.post(
        case_url("close", case),
        {
            "status": "enforced",
            "outcome": "Kiosk removed by the Assembly.",
            "cost": "5000",
            "cost_recovered": "2000.50",
        },
        format="json",
    )
    assert done.status_code == 200, done.content
    assert (done.json()["status"], done.json()["cost"], done.json()["cost_recovered"]) == (
        "enforced",
        "5000.00",
        "2000.50",
    )

    # Revoking a permit (Form 48B) needs the permit; 21 days to show cause.
    breach = open_case(planner, world, contravention="breach_of_condition").json()
    assert issue(planner, breach, "revocation").status_code == 400
    parcel = world.features("parcels", "parcel_id")["P-001"]
    permit = planner.post(
        reverse("permit-application-list"),
        {
            "project": world.project,
            "kind": "development",
            "category": "building",
            "applicant_name": "Ama Mensah",
            "site_feature": parcel["id"],
        },
        format="json",
    ).json()
    linked = planner.patch(
        case_url("detail", breach), {"permit": permit["id"]}, format="json"
    ).json()
    assert linked["permit_number"] == permit["number"]
    revocation = issue(planner, linked, "revocation").json()["notices"][0]
    shown = planner.post(notice_url("serve", revocation), {"method": "email"}, format="json").json()
    assert shown["notices"][0]["dates"]["show_cause_by"] == days(21)
    assert planner.get(notice_url("paper", revocation)).content.startswith(b"%PDF")
    complied = planner.post(notice_url("complied", revocation)).json()
    assert complied["notices"][0]["complied_on"] == str(TODAY)

    # The owner's details are personal; other districts see nothing.
    viewer = api(members_a[Role.VIEWER], district_a)
    seen = viewer.get(case_url("detail", case)).json()
    assert (
        seen["owner_name"] == "restricted"
        and seen["description"]
        and planner.get(case_url("detail", case)).json()["owner_name"] == "Kwesi Appiah"
    )
    other = api(make_member(district_b, Role.DISTRICT_ADMIN, "b.admin@example.test"), district_b)
    assert (
        other.get(reverse(CASES)).json()["results"] == []
        and other.get(case_url("detail", case)).status_code == 404
    )
    assert (
        other.post(notice_url("serve", stop), {"method": "post"}, format="json").status_code == 404
    )
    assert open_case(other, world).status_code == 404
    with tenant_context(district_b.id):
        assert Case.objects.count() == 0


# --- Finding changes between two images ---------------------------------------------------------------


def later_image(source: Path, target: Path, squares, brighter=0):
    """A copy of the image with squares painted in: (west, south, east, north in
    metres from the fixture's origin, grey value), and the whole image lighter."""
    ds = gdal.GetDriverByName("GTiff").CreateCopy(str(target), gdal.Open(str(source)))
    for b in range(1, 4):
        band = ds.GetRasterBand(b)
        pixels = bytearray(band.ReadRaster(0, 0, 200, 200))
        for i, value in enumerate(pixels):
            pixels[i] = min(255, value + brighter)
        for west, south, east, north, grey in squares:
            for y in range(int(south), int(north)):
                row = int(TOP - (ORIGIN_N + y) - 1)
                for x in range(int(west), int(east)):
                    pixels[row * 200 + int(ORIGIN_E + x - LEFT)] = grey
        band.WriteRaster(0, 0, 200, 200, bytes(pixels))
    ds.SetMetadata({"CAPTURE_DATE": "2026-10-01"})
    ds.Close()
    return target


NEW = (470, 1050, 482, 1062, 235)  # 12 x 12 m on open ground
WITH_PERMIT = (620, 1060, 632, 1072, 235)  # 12 x 12 m where a permit is granted
AT_BUILDING = (530, 1020, 540, 1030, 40)  # 10 x 10 m on building B-001


def test_the_comparison_finds_what_changed_and_only_that(fixtures_dir, tmp_path):
    before = Path(fixtures_dir) / "generated" / "drone_ortho.tif"
    # Nothing built, only a brighter day: nothing found.
    assert (
        change.detect(before, later_image(before, tmp_path / "bright.tif", [], brighter=12)) == []
    )
    after = later_image(
        before,
        tmp_path / "after.tif",
        [NEW, WITH_PERMIT, AT_BUILDING, (500, 950, 502, 952, 235)],
        brighter=12,
    )
    found = change.detect(before, after)
    # Three changes; the 2 x 2 m speck is too small to be a structure.
    assert sorted(round(f["area_m2"]) for f in found) == pytest.approx([100, 144, 144], abs=8)
    assert all(f["geometry"]["type"] == "Polygon" and f["change"] > 60 for f in found)
    lon, lat = found[0]["geometry"]["coordinates"][0][0]
    assert -1 < lon < 1 and 5 < lat < 6  # WGS 84, near Accra
    with pytest.raises(Exception, match="same ground"):
        far = tmp_path / "far.tif"
        ds = gdal.GetDriverByName("GTiff").CreateCopy(str(far), gdal.Open(str(before)))
        ds.SetGeoTransform((LEFT + 5000, 1.0, 0.0, TOP, 0.0, -1.0))
        ds.Close()
        change.detect(before, far)


def test_changes_are_classed_by_permits_and_known_buildings(
    world,
    admin,
    fixtures_dir,
    tmp_path,
    django_capture_on_commit_callbacks,
    api,
    members_a,
    district_a,
):
    """Gate: the new building is found; the one with a permit isn't flagged as new."""
    world.set_roles()
    planner = world.client
    before_file = Path(fixtures_dir) / "generated" / "drone_ortho.tif"
    after_file = later_image(
        before_file, tmp_path / "after.tif", [NEW, WITH_PERMIT, AT_BUILDING], brighter=12
    )

    def upload(path, name, captured):
        with open(path, "rb") as fh, django_capture_on_commit_callbacks(execute=True):
            made = planner.post(
                reverse("imagery-list"),
                {"project": world.project, "file": fh, "name": name, "capture_date": captured},
                format="multipart",
            )
        assert made.status_code == 201, made.content
        item = planner.get(reverse("imagery-detail", args=[made.json()["id"]])).json()
        assert item["status"] == "ready", item["error"]
        return item

    september = upload(before_file, "September flight", "2026-09-01")
    october = upload(after_file, "October flight", "2026-10-01")

    # A granted application where one of the new squares stands (given in the image's own grid).
    w, s, e, n = (ORIGIN_E + 615, ORIGIN_N + 1055, ORIGIN_E + 640, ORIGIN_N + 1080)
    site = {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}
    app = planner.post(
        reverse("permit-application-list"),
        {
            "project": world.project,
            "kind": "development",
            "category": "building",
            "applicant_name": "Ama Mensah",
            "site_geometry": site,
            "site_crs": "EPSG:32630",
        },
        format="json",
    )
    assert app.status_code == 201, app.content
    for name, body in (
        ("acknowledge", {}),
        ("inspect", {"summary": "Seen."}),
        ("report", {"recommendation": "grant"}),
    ):
        assert (
            planner.post(
                reverse(f"permit-application-{name}", args=[app.json()["id"]]), body, format="json"
            ).status_code
            == 200
        )
    assert (
        admin.post(
            reverse("permit-application-decide", args=[app.json()["id"]]),
            {"decision": "grant"},
            format="json",
        ).status_code
        == 200
    )

    detections = reverse("project-detections", args=[world.project])
    viewer = api(members_a[Role.VIEWER], district_a)
    assert (
        viewer.post(
            detections, {"before": september["id"], "after": october["id"]}, format="json"
        ).status_code
        == 403
    )
    assert (
        planner.post(
            detections, {"before": september["id"], "after": september["id"]}, format="json"
        ).status_code
        == 400
    )
    # Given the wrong way round: the earlier image is still the "before".
    run = planner.post(
        detections, {"before": october["id"], "after": september["id"]}, format="json"
    )
    assert run.status_code == 201, run.content
    run = run.json()
    assert (run["before"], run["after"], run["found"]) == ("September flight", "October flight", 3)
    assert run["summary"] == {"permitted": 1, "existing": 1, "new": 1}
    assert viewer.get(detections).json()["results"][0]["id"] == run["id"]

    # Each change is on the map, in its own layer, saying what it looks like.
    features = {f.properties["kind"]: f for f in Feature.objects.filter(layer_id=run["layer"])}
    assert set(features) == {
        "New: no permit and no building on the map",
        "At a building already on the map",
        "Where a permit has been granted",
    }
    new = features["New: no permit and no building on the map"]
    assert (
        new.properties["area_m2"] == pytest.approx(144, abs=8)
        and new.properties["between"] == "2026-09-01 and 2026-10-01"
    )
    assert new.origin == "derived"

    # A case opened on the new one carries its number back to the map.
    case = open_case(planner, world, origin="detection", feature=new.pk)
    assert case.status_code == 201, case.content
    assert (
        case.json()["origin_label"] == "Found by comparing images"
        and case.json()["feature"] == new.pk
    )
    new.refresh_from_db()
    assert new.properties["case_no"] == case.json()["number"]
