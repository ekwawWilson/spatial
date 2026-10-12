"""What the Regulations fix about applications that change the land itself:
re-zoning (L.I. 2384 r.33; Act 925 s.93), change of use (r.34) and the
subdivision or consolidation of land (r.54; Act 925 s.139). For each kind:
the form, the steps the Assembly takes, the days each is given, and what the
days run from."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    code: str
    label: str
    rule: str
    # The days allowed, counted from `after`: "received", "comments_close",
    # "decided", or another step's code. None: the Regulations set no time.
    days: int | None = None
    after: str = "received"
    # Only where: "" (always), "comments" (something was received from the
    # public), "objection" (an objection was), "approved".
    when: str = ""


@dataclass(frozen=True)
class Kind:
    code: str
    label: str
    form: str
    rule: str
    prefix: str  # in the application's number
    steps: tuple[Step, ...]
    # The public may comment for this long after `comment_from` (a step).
    comment_from: str
    comment_days: int
    comment_rule: str
    # The decision: so many days after `decide_after`.
    decide_days: int
    decide_after: str
    decide_rule: str


REZONING = Kind(
    "rezoning",
    "Re-zoning",
    "33A and 33B",
    "r.33; Act 925 s.93",
    "RZ",
    (
        Step(
            "display",
            "Displayed in the Public Data Room and on the Assembly's notice board",
            "r.33(5)(a)-(b)",
            7,
        ),
        Step("publish_1", "First publication in a local daily newspaper", "r.33(5)(c)", 7),
        Step(
            "direct_notice",
            "Applicant directed to give notice to the owners of abutting land (Form 35)",
            "r.33(8)",
            7,
        ),
        Step(
            "publish_2",
            "Second publication in the newspaper",
            "r.33(5)(c)",
            28,
            after="publish_1",
        ),
        Step("posted", "Notice posted at three places near the land", "r.33(12)"),
        Step(
            "refer_objections",
            "Objections referred to the applicant",
            "r.33(14)",
            14,
            after="comments_close",
            when="objection",
        ),
        Step(
            "response",
            "Applicant's response to the objections received",
            "r.33(15)",
            when="objection",
        ),
        Step(
            "gazette",
            "Recorded, published in the Gazette and lodged in the Public Data Room",
            "r.33(19)",
            7,
            after="decided",
            when="approved",
        ),
    ),
    comment_from="display",
    comment_days=28,
    comment_rule="r.33(7)",
    decide_days=60,
    # r.33(15): after the applicant's comments on the objections. Where no
    # objection came, the platform counts from the end of the comment period.
    decide_after="response",
    decide_rule="r.33(15)",
)

LAND_STEPS = (
    Step("acknowledge", "Receipt acknowledged", "r.54(2)(a)", 7),
    Step(
        "advertise",
        "Advertised in a newspaper circulating in the District, inviting comments",
        "r.54(2)(b)-(c)",
        21,
    ),
    Step("lands_commission", "Copy sent to the Lands Commission for comment", "r.54(3)"),
    Step("display", "Advertisement displayed in the Public Data Room", "r.54(6)"),
    Step(
        "notify_applicant",
        "Applicant told of the comments and objections received",
        "r.54(7)",
        when="comments",
    ),
    Step(
        "response",
        "Applicant's response",
        "r.54(7)",
        14,
        after="notify_applicant",
        when="comments",
    ),
    Step(
        "publish_approval",
        "Approval published in a newspaper and lodged in the Public Data Room",
        "r.54(10)",
        when="approved",
    ),
    Step(
        "notify_lands",
        "Notice of the approval served on the Lands Commission",
        "r.54(12)",
        30,
        after="decided",
        when="approved",
    ),
)


def _land(code: str, label: str, prefix: str) -> Kind:
    return Kind(
        code,
        label,
        "46",
        "r.54; Act 925 s.139",
        prefix,
        LAND_STEPS,
        comment_from="advertise",
        comment_days=14,
        comment_rule="r.54(4)",
        decide_days=60,
        decide_after="received",
        decide_rule="r.54(9)",
    )


CHANGE_OF_USE = Kind(
    "change_of_use",
    "Change of use",
    "",
    "r.34; r.44(1)",
    "CU",
    (),
    comment_from="",
    comment_days=0,
    comment_rule="",
    # A change of use needs a planning permit, decided within thirty days.
    decide_days=30,
    decide_after="received",
    decide_rule="r.44(10)",
)

KINDS: tuple[Kind, ...] = (
    REZONING,
    CHANGE_OF_USE,
    _land("subdivision", "Subdivision of land", "SD"),
    _land("consolidation", "Consolidation of land", "CN"),
)
KIND_BY_CODE = {k.code: k for k in KINDS}

DEFERRED_DECISION_DAYS = 30  # r.33(17): after a decision is deferred

# r.33(2): what a re-zoning application must state.
GROUNDS: tuple[tuple[str, str], ...] = (
    ("structure_plan", "To make the zoning of the land comply with the structure plan"),
    ("special", "A special circumstance has arisen that necessitates the change"),
)
# r.33(3): special circumstances include ...
CIRCUMSTANCES: tuple[tuple[str, str], ...] = (
    ("industry_moved", "The main centre for industrial activity has relocated"),
    ("minerals_exhausted", "Minerals in a mining area have been exhausted"),
    ("land_use_changed", "A disproportionate change in the dominant land use of the area"),
    ("demographics", "A change in the demographic pattern in the area"),
    ("other", "Another special circumstance"),
)

# r.34: a person may apply for a change of use where the type of development ...
USE_TESTS: tuple[tuple[str, str, str], ...] = (
    ("permissible", "Is within the permissible uses of the zoning scheme", "r.34(1)(a)"),
    (
        "intention",
        "Does not significantly alter the original intention of the plan or zone",
        "r.34(1)(b)",
    ),
    ("services", "Has minimal impact on existing services and infrastructure", "r.34(1)(c)"),
    ("traffic", "Does not significantly increase traffic generation", "r.34(1)(d)(i)"),
    ("noise", "Does not significantly increase noise and odour", "r.34(1)(d)(ii)"),
    ("fire", "Does not increase the risk of fire or explosion", "r.34(1)(d)(iii)"),
    ("image", "Does not undermine the image of the area", "r.34(1)(d)(iv)"),
    (
        "privacy",
        "Intrudes on no one's privacy, or the intrusion is of net benefit to the community",
        "r.34(2)",
    ),
)
USE_TEST_CODES = tuple(code for code, _label, _rule in USE_TESTS)

# Form 59 (r.33(6), r.54(5)): what the public and the Lands Commission send in.
COMMENT_KINDS: tuple[tuple[str, str], ...] = (
    ("comment", "Comment"),
    ("objection", "Objection"),
    ("representation", "Representation"),
    ("lands_commission", "Comment of the Lands Commission"),
)
COMMENT_KIND_BY_CODE = dict(COMMENT_KINDS)
