"""What the law fixes about enforcement: the kinds of contravention, the
notices and the forms they are served on, how a notice may be served, and the
days between steps. Land Use and Spatial Planning Act, 2016 (Act 925)
s.117-121 and s.160-167; Regulations (L.I. 2384) r.30 and r.55-58, with the
wording of Forms 47 to 50 of the Schedule."""

from dataclasses import dataclass

CONTRAVENTIONS: tuple[tuple[str, str, str], ...] = (
    ("no_permit", "Development without a permit", "section 117 of Act 925"),
    ("breach_of_condition", "Breach of a condition of a permit", "section 160 of Act 925"),
    ("zoning", "Does not conform to the approved zoning scheme", "section 84 of Act 925"),
    ("public_space", "Encroaches on public space or a right of way", "section 121 of Act 925"),
    ("untidy_land", "Untidy land", "section 160 of Act 925"),
    ("dangerous_building", "Dangerous building", "section 160 of Act 925"),
    ("other", "Other contravention", "section 160 of Act 925"),
)
CONTRAVENTION_BY_CODE = {code: (label, section) for code, label, section in CONTRAVENTIONS}


@dataclass(frozen=True)
class NoticeKind:
    code: str
    label: str
    form: str  # the Schedule form, or "" where the Regulations name the notice without one
    rule: str
    # Whether the notice gives a date to comply by.
    dated: bool = True


NOTICES: tuple[NoticeKind, ...] = (
    NoticeKind(
        "stop",
        "Stop Notice or Order for Discontinuance",
        "48A",
        "r.55(1); Act 925 s.160",
        dated=False,
    ),
    NoticeKind("rectification", "Notice for Rectification of Contravention", "49", "r.57(1)"),
    NoticeKind("enforcement", "Enforcement Notice", "47", "r.30(2), r.55(1), r.57(3)"),
    NoticeKind("revocation", "Notice of Revocation of Permit", "48B", "r.55(1); Act 925 s.160(d)"),
    NoticeKind(
        "entry", "Notice to Enter Land for Enforcement Purposes", "50", "r.58; Act 925 s.164"
    ),
    NoticeKind("contravention", "Planning Contravention Notice", "", "r.55(2)(a)"),
    NoticeKind("breach", "Breach of Condition Notice", "", "r.55(2)(b)"),
    NoticeKind("untidy", "Untidy Land Notice", "", "r.55(2)(c)"),
    NoticeKind("dangerous", "Dangerous Buildings Notice", "", "r.55(2)(d)"),
)
NOTICE_BY_CODE = {n.code: n for n in NOTICES}

# r.56(1): a notice is deemed served where it is ...
SERVICE_METHODS: tuple[tuple[str, str], ...] = (
    ("on_land", "Posted in a conspicuous place on the land or building"),
    ("data_room", "Posted on the notice board of the Public Data Room"),
    ("assembly_board", "Posted on the notice board of the District Assembly"),
    ("post", "Sent by post to the last known address"),
    ("at_address", "Posted at the last known address"),
    ("newspaper", "Published in a newspaper of national circulation"),
    ("email", "Emailed to the last known email address"),
    ("written", "Sent through another form of written communication"),
)
SERVICE_BY_CODE = dict(SERVICE_METHODS)

ENFORCEMENT_AFTER_DAYS = 14  # r.57(2): after the time to rectify runs out
ACT_AFTER_DAYS = 14  # r.57(4): after the enforcement notice is served
ENTRY_NOTICE_DAYS = 3  # r.58: before entering
SHOW_CAUSE_DAYS = 21  # Form 48B: to show cause why the permit should not be revoked
