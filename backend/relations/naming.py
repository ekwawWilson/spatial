# ruff: noqa: E501 - the steps read better unbroken
"""Street names from proposal to signs: proposed, consulted on with the
community, approved or refused by the Spatial Planning Committee, then
published and the signs put up. On approval the name is written to the
street on the map. (L.I. 2384 r.28 applies the National Street Naming and
Property Numbering Operational Manual; these steps follow what Assemblies
do under it, and can be aligned with the manual's own wording.)"""

from datetime import date
from typing import Any

from django.core.exceptions import ValidationError

from core.models import User
from projects.models import Feature, PlanProject

from . import services
from .models import StreetName

Status = StreetName.Status


def name_field(project: PlanProject) -> str:
    role = services.roles_of(project).get("streets")
    return str(role.config.get("name_field", "name")) if role else "name"


def taken(project: PlanProject, name: str, but: StreetName | None = None) -> list[str]:
    """Where the name is already used in the district: approved names, and streets so named."""
    clash = []
    others = StreetName.objects.filter(
        district_id=project.district_id, name__iexact=name, status=Status.APPROVED
    )
    if but is not None:
        others = others.exclude(pk=but.pk)
    clash += [
        f"approved for a street in {s.project.name}" for s in others.select_related("project")
    ]
    role = services.roles_of(project).get("streets")
    if role is not None:
        field = name_field(project)
        streets = Feature.objects.filter(layer=role.layer, **{f"properties__{field}__iexact": name})
        if but is not None and but.street_id is not None:
            streets = streets.exclude(pk=but.street_id)
        clash += [f"already the name of street #{f.pk}" for f in streets[:5]]
    return clash


def propose(
    project: PlanProject,
    street: Feature,
    name: str,
    basis: str,
    proposed_by: str,
    on: date,
    user: User,
) -> StreetName:
    name = " ".join(name.split())
    if not name:
        raise ValidationError({"name": ["Give the name."]})
    if StreetName.objects.filter(
        street=street, status__in=(Status.PROPOSED, Status.CONSULTED)
    ).exists():
        raise ValidationError({"street": ["This street already has a name being considered."]})
    return StreetName.objects.create(
        district_id=project.district_id,
        project=project,
        street=street,
        name=name,
        basis=basis,
        proposed_by=proposed_by,
        proposed_on=on,
        created_by=user,
    )


def _not_before(on: date, earlier: date | None, what: str) -> None:
    if on > date.today():
        raise ValidationError({"on": ["That date is in the future."]})
    if earlier is not None and on < earlier:
        raise ValidationError({"on": [f"That is before {what} ({earlier.isoformat()})."]})


def consult(item: StreetName, on: date, note: str) -> None:
    if item.status not in (Status.PROPOSED, Status.CONSULTED):
        raise ValidationError("It has already been decided.")
    _not_before(on, item.proposed_on, "the proposal")
    item.consulted_on = on
    item.consultation = note
    item.status = Status.CONSULTED
    item.save(update_fields=["consulted_on", "consultation", "status"])


def decide(item: StreetName, approve: bool, on: date, note: str, user: User) -> dict[str, Any]:
    """The Committee's decision. Approved: the name goes onto the street on the map."""
    if item.status != Status.CONSULTED:
        raise ValidationError("Consult the community on the name first.")
    _not_before(on, item.consulted_on, "the consultation")
    if approve:
        clash = taken(item.project, item.name, but=item)
        if clash:
            raise ValidationError(
                {
                    "name": [
                        f"{item.name} is {clash[0]}: a district's street names should be unique."
                    ]
                }
            )
    item.decided_on = on
    item.decision_note = note
    item.status = Status.APPROVED if approve else Status.REFUSED
    written = False
    if approve and item.street is not None:
        field = name_field(item.project)
        street = item.street
        item.previous_name = str(street.properties.get(field) or "")
        if street.properties.get(field) != item.name:
            street.properties = {**street.properties, field: item.name}
            street.version += 1
            street.updated_by = user
            street.save(update_fields=["properties", "version", "updated_by", "updated_at"])
            written = True
    item.save(update_fields=["decided_on", "decision_note", "status", "previous_name"])
    return {"written_to_map": written}


def mark(item: StreetName, step: str, on: date) -> None:
    """Published (in the Gazette, on the notice board, in the Data Room), or the signs put up."""
    if item.status != Status.APPROVED:
        raise ValidationError("Only an approved name is published or signed.")
    if step not in ("published", "signs"):
        raise ValidationError({"step": ["published or signs."]})
    _not_before(on, item.decided_on, "the approval")
    setattr(item, f"{step}_on", on)
    item.save(update_fields=[f"{step}_on"])
