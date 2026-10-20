"""What L.I. 2384 fixes about the District Spatial Planning Committee and
its Technical Sub-Committee: their meetings' notice (r.6, Form 5) and quorum
(r.7), with the offices that must be present."""

NOTICE_DAYS = 3  # r.6(2): served on members not later than three days before

COMMITTEES = {
    "dspc": "District Spatial Planning Committee",
    "tsc": "Technical Sub-Committee",
}

OFFICES: tuple[tuple[str, str], ...] = (
    ("dce", "District Chief Executive"),
    ("dcd", "District Coordinating Director"),
    ("physical_planning", "Head of the Physical Planning Department"),
    ("development_planning", "District Development Planning Officer"),
    ("works", "Head of the Works Department"),
    ("disaster", "Head of the Disaster Prevention Department"),
    ("lands", "Representative of the Lands Commission"),
    ("epa", "Representative of the Environmental Protection Agency"),
    ("roads", "Head of the Roads Unit or Urban Roads Department"),
    ("other", "Other member"),
)
OFFICE_LABELS = dict(OFFICES)

# r.7(2): for the Spatial Planning Committee, these present (the DCE, or the
# Coordinating Director in the DCE's absence), and nine members in all.
DSPC_REQUIRED: tuple[tuple[str, ...], ...] = (
    ("dce", "dcd"),
    ("physical_planning",),
    ("development_planning",),
    ("works",),
    ("disaster",),
    ("lands",),
    ("epa",),
    ("roads",),
)
DSPC_QUORUM = 9
# r.7(4): for the Technical Sub-Committee, these present, and half its members.
TSC_REQUIRED: tuple[tuple[str, ...], ...] = (
    ("physical_planning",),
    ("development_planning",),
    ("works",),
    ("lands",),
    ("epa",),
    ("roads",),
)

OUTCOMES = {
    "": "Not yet considered",
    "recommend_grant": "Recommended for grant",
    "recommend_refuse": "Recommended for refusal",
    "granted": "Granted",
    "refused": "Refused",
    "approved": "Approved",
    "deferred": "Deferred",
    "noted": "Noted",
}
