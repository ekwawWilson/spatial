"""What the Regulations fix about making a local plan: the steps from the
direction to prepare it to the notice of its approval (L.I. 2384 r.23, r.25,
r.26; Act 925 s.72-80), what a local plan must specify (r.24), and the record
of public consultation (r.65)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    code: str
    label: str
    rule: str
    form: str = ""
    # The time allowed, counted from `after`: a step's code, "structure_plan"
    # or "application" (dates the Assembly gives), or "comments_close".
    days: int | None = None
    months: int | None = None
    after: str = ""
    # "": every plan. "applicant": only a plan prepared by someone other than
    # the District Spatial Planning Committee (r.25(6), r.26).
    only: str = ""
    # Recorded by those who may decide (the approval and the confirmation).
    decision: bool = False


STEPS: tuple[Step, ...] = (
    Step(
        "direct",
        "The planning authority directs the Spatial Planning Committee to prepare the local plan",
        "r.23(1)",
        months=12,
        after="structure_plan",
    ),
    Step("commence", "Notice of commencement of the local plan published", "r.23(2)", form="27"),
    Step("draft", "Draft local plan completed", "r.23(3)"),
    Step(
        "notice",
        "Draft opened for inspection in the Public Data Room, and the public invited to comment",
        "r.23(3)-(5)",
        form="28",
    ),
    Step(
        "approve",
        "Local plan approved",
        "r.25(1)",
        # Only for a plan prepared by another person: r.25(6).
        days=90,
        after="application",
        decision=True,
    ),
    Step(
        "publish_approval",
        "Notice of approval published and displayed in the Public Data Room",
        "r.25(3)-(5)",
        form="29",
        days=7,
        after="approve",
    ),
    Step(
        "request_confirmation",
        "Submitted to the Regional Spatial Planning Committee for confirmation",
        "r.26(1)-(3)",
        form="30",
        after="approve",
        only="applicant",
    ),
    Step(
        "confirm",
        "Confirmed by the Regional Spatial Planning Committee as conforming to the structure plan",
        "r.26(4)",
        days=28,
        after="request_confirmation",
        only="applicant",
        decision=True,
    ),
    Step(
        "publish_confirmation",
        "Notice of confirmation published and displayed in the Public Data Room",
        "r.26(8)-(10)",
        form="31",
        days=7,
        after="confirm",
        only="applicant",
    ),
)
STEP_BY_CODE = {s.code: s for s in STEPS}

# r.23(3) and (5): the draft is open for inspection, and the public may
# comment, for sixty days.
COMMENT_DAYS = 60
COMMENT_RULE = "r.23(5)"

# r.24(1): a local plan shall specify, among others ...
CONTENT: tuple[tuple[str, str], ...] = (
    ("a", "Population size and density for residential neighbourhoods"),
    ("b", "Basic social services requirements"),
    ("c", "Required land use"),
    ("d", "Overall form of physical development"),
    ("e", "Permissible built area to non-built area on a plot in each zone"),
    ("f", "Height of buildings"),
    ("g", "Preservation of existing structures"),
    ("h", "Landscaping, including the preservation of existing trees"),
    ("i", "Sanitation requirements for all developments"),
    ("j", "Environmental protection requirements"),
    ("k", "Road network and circulation, including parking and pedestrian walkways"),
    ("l", "Utility services (water, electricity, telecommunications) and their distribution"),
    ("m", "Drainage system"),
    ("n", "Essential sewage networks"),
    ("o", "Solid and liquid waste collection and disposal"),
    ("p", "Composite spatial design or organisation of the plan area"),
    ("q", "Management of the development of the plan area"),
)
CONTENT_BY_CODE = dict(CONTENT)
CONTENT_RULE = "r.24(1)"

# r.27(1): conditions the Spatial Planning Committee may impose.
CONDITIONS: tuple[str, ...] = (
    "A time frame for the validity of the local plan",
    "The facilities to be provided within the area, and where necessary on adjoining land",
    "The orientation and siting of physical developments",
    "Drainage and other systems that comply with and complement the object of the plan",
    "Any other condition the Committee may require",
)

# r.65: when a consultation was held.
STAGES: tuple[tuple[str, str], ...] = (
    ("before", "Before the preparation of the plan"),
    ("draft", "On the draft plan"),
)
STAGE_BY_CODE = dict(STAGES)
