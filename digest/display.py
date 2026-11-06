"""Plain-language presentation shared by the site and the email: stage words,
groups by how close a drug is to a pharmacy, heart-attack evidence labels."""
from __future__ import annotations

from . import STAGE_LABEL, STAGE_RANK

STAGE_PLAIN = {
    "phase1": ("Early safety tests", "First tests in people, mainly for safety."),
    "phase2": ("Mid-stage testing", "Testing whether it works and finding the right dose."),
    "phase3": ("Final-stage trials", "Large trials, often testing whether it prevents heart attacks. "
                                     "The last step before applying for approval."),
    "filed": ("FDA reviewing", "The company has applied; the FDA is deciding."),
    "approved": ("Approved", "Doctors can prescribe it."),
}
# (key, title, stages in the group, the stage most of the group is at)
GROUPS = [
    ("now", "Available now", ("approved",), "approved"),
    ("close", "Getting close", ("phase3", "filed"), "phase3"),
    ("later", "Further out", ("phase1", "phase2"), "phase2"),
]
# Did it prevent heart attacks and strokes in a large trial?
PROVEN_LABEL = {
    "yes": "Prevents heart attacks",
    "testing": "Heart-attack trial underway",
    "failed": "Didn't prevent heart attacks",
    "untested": "No heart-attack trial yet",
}
LOWERS_LABEL = {"ldl": "LDL", "lpa": "Lp(a)", "tg": "Triglycerides"}


def lowers_keys(text: str) -> list[str]:
    t = (text or "").lower()
    keys = []
    if "ldl" in t:
        keys.append("ldl")
    if "lp(a)" in t:
        keys.append("lpa")
    if "triglyceride" in t:
        keys.append("tg")
    return keys


def rows(watchlist: dict, stages: dict, moved: set[str]) -> list[dict]:
    out = []
    for d in watchlist["drugs"]:
        stage = stages.get(d["id"], d["stage"])
        out.append({**d, "rank": STAGE_RANK[stage], "stage_label": STAGE_LABEL[stage],
                    "stage_plain": STAGE_PLAIN[stage][0], "stage_explain": STAGE_PLAIN[stage][1],
                    "stage": stage, "moved": d["id"] in moved,
                    "lowers_keys": lowers_keys(d.get("lowers", "")),
                    "proven_label": PROVEN_LABEL.get(d.get("proven", ""), "")})
    return out


def groups(all_rows: list[dict]) -> list[dict]:
    """Drugs grouped by how close they are to a pharmacy, closest first. Within a
    group, a row's stage words are only shown when it differs from the group's."""
    out = []
    for key, title, stages, usual in GROUPS:
        members = sorted((r for r in all_rows if r["stage"] in stages), key=lambda r: -r["rank"])
        if members:
            out.append({"key": key, "title": title, "usual": usual,
                        "rows": [{**r, "show_stage": r["stage"] != usual} for r in members]})
    return out
