"""The local plan's steps and their dates, what the plan covers, and the
public's comments on the draft."""

import calendar
from datetime import date, timedelta
from typing import Any

from django.core.exceptions import ValidationError

from core.models import User
from projects.models import PlanProject

from . import registry
from .models import PlanComment, PlanProcess


def process_of(project: PlanProject) -> PlanProcess:
    """The project's plan-making record; an unsaved blank one if nothing is recorded yet."""
    found = PlanProcess.objects.filter(project=project).first()
    return found or PlanProcess(district_id=project.district_id, project=project)


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def step_date(process: PlanProcess, code: str) -> date | None:
    entry = process.steps.get(code)
    return date.fromisoformat(entry["on"]) if entry else None


def comments_close(process: PlanProcess) -> date | None:
    """The last day for the public's comments on the draft (r.23(5))."""
    start = step_date(process, "notice")
    return start + timedelta(days=registry.COMMENT_DAYS) if start else None


def comments_open(process: PlanProcess, today: date | None = None) -> bool:
    today = today or date.today()
    start, close = step_date(process, "notice"), comments_close(process)
    return bool(start and close and start <= today <= close and "approve" not in process.steps)


def _anchor(process: PlanProcess, name: str) -> date | None:
    if name == "structure_plan":
        return process.structure_plan_on
    if name == "application":
        return process.application_on
    return step_date(process, name) if name else None


def steps_for(process: PlanProcess) -> list[registry.Step]:
    return [s for s in registry.STEPS if not s.only or s.only == process.origin]


def clocks(process: PlanProcess, today: date | None = None) -> list[dict[str, Any]]:
    """Each step of this plan: when it is due (where the Regulations set a
    time and it has started to run), when it was done, and whether it is late."""
    today = today or date.today()
    out: list[dict[str, Any]] = []
    for step in steps_for(process):
        start = _anchor(process, step.after)
        if step.after == "application" and process.origin != PlanProcess.Origin.APPLICANT:
            start = None  # r.25(6): no time limit on the Committee's own plan
        due: date | None = None
        if start is not None and step.months is not None:
            due = add_months(start, step.months)
        elif start is not None and step.days is not None:
            due = start + timedelta(days=step.days)
        done = step_date(process, step.code)
        out.append(
            {
                "code": step.code,
                "label": step.label,
                "rule": step.rule,
                "form": step.form,
                "limit": f"{step.months} months"
                if step.months
                else (f"{step.days} days" if step.days else ""),
                "decision": step.decision,
                "due_on": due.isoformat() if due else None,
                "done_on": done.isoformat() if done else None,
                "note": process.steps.get(step.code, {}).get("note", ""),
                "late": bool(done and due and done > due),
                "overdue": bool(done is None and due and today > due),
            }
        )
    return out


def next_due(process: PlanProcess, today: date | None = None) -> dict[str, Any] | None:
    waiting = [c for c in clocks(process, today) if c["done_on"] is None]
    return next((c for c in waiting if c["overdue"]), waiting[0] if waiting else None)


def record_step(process: PlanProcess, code: str, on: date, note: str, user: User) -> None:
    step = registry.STEP_BY_CODE.get(code)
    if step is None or step not in steps_for(process):
        raise ValidationError({"step": ["Not a step of this local plan."]})
    if on > date.today():
        raise ValidationError({"on": ["That date is in the future."]})
    # A step follows the one it is counted from.
    before = step.after if step.after in registry.STEP_BY_CODE else ""
    if code == "notice":
        before = "draft"
    if before:
        earlier = step_date(process, before)
        if earlier is None:
            raise ValidationError(
                {"step": [f"First: {registry.STEP_BY_CODE[before].label.lower()}."]}
            )
        if on < earlier:
            raise ValidationError({"on": ["That is before the step it follows."]})
    if code == "approve":
        close = comments_close(process)
        if close is None:
            raise ValidationError(
                {"step": ["The public has not been invited to comment on the draft (r.23(4))."]}
            )
        if on <= close:
            raise ValidationError(
                {"on": [f"The public may comment until {close.isoformat()} (r.23(5))."]}
            )
    process.steps = {**process.steps, code: {"on": on.isoformat(), "note": note}}
    process.updated_by = user
    process.save()


def content(process: PlanProcess) -> list[dict[str, Any]]:
    """Each item of r.24(1), and whether the plan covers it."""
    return [
        {
            "code": code,
            "label": label,
            "covered": bool(process.content.get(code, {}).get("covered")),
            "note": process.content.get(code, {}).get("note", ""),
        }
        for code, label in registry.CONTENT
    ]


def set_content(process: PlanProcess, items: dict[str, Any], user: User) -> None:
    merged = dict(process.content)
    for code, answer in items.items():
        if code not in registry.CONTENT_BY_CODE:
            raise ValidationError({"items": [f"Not an item of r.24(1): {code}."]})
        if not isinstance(answer, dict) or not isinstance(answer.get("covered"), bool):
            raise ValidationError({"items": [f"Say whether the plan covers ({code})."]})
        merged[code] = {"covered": answer["covered"], "note": str(answer.get("note") or "")}
    process.content = merged
    process.updated_by = user
    process.save()


def add_comment(
    project: PlanProject,
    *,
    name: str,
    contact: str,
    topic: str,
    text: str,
    on: date,
    online: bool,
) -> PlanComment:
    if topic and topic not in registry.CONTENT_BY_CODE:
        raise ValidationError({"topic": ["Not an item of r.24(1)."]})
    if on > date.today():
        raise ValidationError({"on": ["That date is in the future."]})
    return PlanComment.objects.create(
        district_id=project.district_id,
        project=project,
        name=name,
        contact=contact,
        topic=topic,
        text=text,
        received_on=on,
        online=online,
    )
