"""Compare last week's snapshot with this week's. This is the core of the digest:
only what changed gets reported, and every change carries its source URL."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from . import STAGE_LABEL, STAGE_RANK
from .sources.ctgov import HALTED, STATUS_PLAIN, phase_label

# Display order in the digest: biggest news first.
KIND_ORDER = ["fda_approval", "stage_change", "trial_halted", "trial_results",
              "trial_status", "trial_new", "news", "discovery", "field"]
KIND_LABEL = {  # (singular, plural)
    "fda_approval": ("FDA approval", "FDA approvals"),
    "stage_change": ("phase change", "phase changes"),
    "trial_halted": ("halted trial", "halted trials"),
    "trial_results": ("trial result posted", "trial results posted"),
    "trial_status": ("trial status change", "trial status changes"),
    "trial_new": ("new trial", "new trials"),
    "news": ("news item", "news items"),
    "discovery": ("new candidate", "new candidates"),
    "field": ("in the field", "in the field"),
}


@dataclass
class Change:
    id: str
    kind: str
    drug: str | None          # watchlist id (None for discovery)
    what: str                 # factual one-liner, built by code (never by the LLM)
    url: str
    source: str               # e.g. "ClinicalTrials.gov"
    why: str = ""             # filled by the summarizer
    extra: dict = field(default_factory=dict)


@dataclass
class HorizonItem:
    date: str
    drug: str
    what: str
    url: str
    when: str = ""     # plain timing label, e.g. "DUE NOW" or "MAY 2027"


def _trial_name(t: dict) -> str:
    name = t.get("acronym") or t.get("title", "")
    return f"{name} ({t['nct']})"


def compute(prev: dict | None, curr: dict, watchlist: dict) -> list[Change]:
    if not prev:
        return []  # first run is a baseline
    names = {d["id"]: d["name"] for d in watchlist["drugs"]}
    min_phase = watchlist["settings"].get("min_trial_phase", 2)
    known_drugs = set(prev.get("drugs", {}))
    # Snapshots without a "baselined" record (old format, test data) count as fully baselined.
    b = prev.get("baselined") or {"ctgov": known_drugs, "fda": known_drugs, "news": True, "discovery": True,
                                  "field": True}
    ct_ok, fda_ok = set(b.get("ctgov", [])) & known_drugs, set(b.get("fda", [])) & known_drugs
    changes: list[Change] = []

    # --- FDA approvals ---
    approved_now = set()
    for drug_id, f in curr.get("fda", {}).items():
        before = prev.get("fda", {}).get(drug_id, {})
        if f.get("approved") and not before.get("approved") and drug_id in fda_ok:
            approved_now.add(drug_id)
            brand = f" as {f['brand']}" if f.get("brand") else ""
            changes.append(Change(
                id=f"fda-{drug_id}", kind="fda_approval", drug=drug_id,
                what=f"{names.get(drug_id, drug_id)} approved by the FDA{brand} ({f.get('date', '')}).",
                url=f.get("url", ""), source="Drugs@FDA"))

    # --- stage changes (forward moves only) ---
    stage_trials: set[str] = set()
    for drug_id, s in curr.get("drugs", {}).items():
        before = prev.get("drugs", {}).get(drug_id)
        if not before or drug_id in approved_now:
            continue
        basis = s.get("basis", "")
        if basis == "watchlist" or (basis == "FDA" and drug_id not in fda_ok) or \
                (basis.startswith("NCT") and drug_id not in ct_ok):
            continue  # manual edit, or evidence from a source with no baseline yet
        if STAGE_RANK[s["stage"]] > STAGE_RANK[before["stage"]]:
            trial = curr.get("trials", {}).get(s.get("basis", ""))
            via = ""
            if trial and trial["nct"] not in prev.get("trials", {}):
                stage_trials.add(trial["nct"])  # reported here, not again as "new trial"
                via = f" with a new trial, {_trial_name(trial)}"
            changes.append(Change(
                id=f"stage-{drug_id}", kind="stage_change", drug=drug_id,
                what=f"{names.get(drug_id, drug_id)} moved from {STAGE_LABEL[before['stage']]} "
                     f"to {STAGE_LABEL[s['stage']]}{via}.",
                url=s.get("url", ""),
                source="ClinicalTrials.gov" if s.get("basis", "").startswith("NCT") else s.get("basis", "")))

    # --- trials ---
    # Approved drugs have hundreds of routine trials. For them, only their watched
    # trials (milestones) report status changes, halts and results, and only new
    # final-stage trials are reported. Drugs still in testing get every Phase 2+ change.
    watched = {m.get("nct") for d in watchlist["drugs"] for m in (d.get("milestones") or []) if m.get("nct")}
    approved = {k for k, v in curr.get("drugs", {}).items() if v.get("stage") == "approved"}
    prev_trials = prev.get("trials", {})
    for nct, t in curr.get("trials", {}).items():
        drug_id = t.get("drug")
        if drug_id not in ct_ok:
            continue  # new to the watchlist, or never fetched successfully: this is its baseline
        drug = names.get(drug_id, drug_id)
        old = prev_trials.get(nct)
        routine = drug_id in approved and nct not in watched
        big_enough = t["phase_rank"] >= (3 if routine else min_phase)
        if old is None:
            if big_enough and nct not in stage_trials:
                changes.append(Change(
                    id=f"new-{nct}", kind="trial_new", drug=drug_id,
                    what=f"New {phase_label(t['phases'])} trial registered for {drug}: {_trial_name(t)}"
                         f", sponsor {t['sponsor']}.",
                    url=t["url"], source="ClinicalTrials.gov"))
            continue
        if routine:
            continue  # a routine trial of an approved drug: only its registration is news
        if t["status"] != old.get("status"):
            halted = t["status"] in HALTED
            if halted or big_enough:
                changes.append(Change(
                    id=f"status-{nct}-{t['status']}", kind="trial_halted" if halted else "trial_status",
                    drug=drug_id,
                    what=f"{drug} {phase_label(t['phases'])} trial {_trial_name(t)} is now "
                         f"{STATUS_PLAIN.get(t['status'], t['status'].lower())} "
                         f"(was {STATUS_PLAIN.get(old.get('status', ''), str(old.get('status', '')).lower())}).",
                    url=t["url"], source="ClinicalTrials.gov"))
        if t["has_results"] and not old.get("has_results"):
            changes.append(Change(
                id=f"results-{nct}", kind="trial_results", drug=drug_id,
                what=f"Results posted on ClinicalTrials.gov for {drug} {phase_label(t['phases'])} trial "
                     f"{_trial_name(t)}.",
                url=t["url"] + "?tab=results", source="ClinicalTrials.gov"))

    # --- news (unseen items only) ---
    seen = set(prev.get("news_seen", []))
    for item_id, n in (curr.get("news", {}) if b.get("news") else {}).items():
        if item_id in seen or n.get("drug") not in known_drugs:
            continue
        changes.append(Change(
            id=item_id, kind="news", drug=n["drug"], what=n["title"], url=n["link"], source=n["outlet"],
            extra={"summary": n.get("summary", ""), "published": n.get("published", "")}))

    # --- in the field: broader LDL-treatment news (unseen items only) ---
    fseen = set(prev.get("field_seen", []))
    if b.get("field"):
        for item_id, n in curr.get("field", {}).items():
            if item_id in fseen or item_id in seen:
                continue
            changes.append(Change(
                id=item_id, kind="field", drug=None, what=n["title"], url=n["link"], source=n["outlet"],
                extra={"summary": n.get("summary", ""), "published": n.get("published", "")}))

    # --- discovery: new candidates not on the watchlist ---
    dseen = set(prev.get("discovery_seen", []))
    watched = set(curr.get("trials", {}))
    max_disc = (watchlist["settings"].get("discovery") or {}).get("max_items", 5)
    disc = [t for nct, t in (curr.get("discovery", {}) if b.get("discovery") else {}).items()
            if nct not in dseen and nct not in watched]
    for t in sorted(disc, key=lambda t: t.get("first_posted", ""), reverse=True)[:max_disc]:
        ivs = ", ".join(i for i in t.get("interventions", []) if i) or "unnamed intervention"
        changes.append(Change(
            id=f"disc-{t['nct']}", kind="discovery", drug=None,
            what=f"New {phase_label(t['phases'])} trial not on your watchlist: {ivs} "
                 f"({t['sponsor']}): {_trial_name(t)}.",
            url=t["url"], source="ClinicalTrials.gov"))

    changes.sort(key=lambda c: KIND_ORDER.index(c.kind))
    return changes


def horizon(curr: dict, watchlist: dict, today: date | None = None) -> list[HorizonItem]:
    """"Watching for": the hand-picked milestones in the watchlist (each drug's
    `milestones`), dated live from ClinicalTrials.gov when tied to a trial, plus any
    dated `events`. Routine trial completion dates are deliberately left out."""
    today = today or date.today()
    trials = curr.get("trials", {})
    items = []
    for d in watchlist["drugs"]:
        label = d.get("brand") or d["name"]
        for m in d.get("milestones", []) or []:
            t = trials.get(m.get("nct", ""))
            if t:
                if t["status"] in HALTED:
                    when, iso = "Stopped", t.get("primary_completion") or "0000"
                elif t["status"] == "COMPLETED" or t.get("has_results"):
                    when, iso = "Finished", t.get("primary_completion") or "0000"
                else:
                    iso = t.get("primary_completion", "")
                    pd = _parse_partial_date(iso)
                    when = "DUE NOW" if pd and pd <= today else (fmt_horizon_date(iso[:7]) if iso else "")
                url = t["url"]
            else:
                iso = str(m.get("when", ""))
                pd = _parse_partial_date(iso)
                when = ("DUE NOW" if pd <= today else fmt_horizon_date(iso[:7])) if pd else iso
                url = m.get("source", "")
            if url:
                items.append(HorizonItem(date=iso, drug=label, what=m["what"], url=url, when=when))
    for ev in watchlist.get("events", []):
        d = _parse_partial_date(str(ev.get("date", "")))
        if d and d >= today and ev.get("url"):
            items.append(HorizonItem(date=str(ev["date"]), drug=ev["drug"], what=ev["what"],
                                     url=ev["url"], when=fmt_horizon_date(str(ev["date"]))))
    return sorted(items, key=lambda h: h.date)


def _parse_partial_date(s: str) -> date | None:
    """CT.gov dates are 'YYYY-MM' or 'YYYY-MM-DD'. A month-only date counts as the 15th."""
    try:
        parts = [int(p) for p in s.split("-")]
        if len(parts) == 2:
            return date(parts[0], parts[1], 15)
        if len(parts) == 3:
            return date(*parts)
    except (ValueError, TypeError):
        pass
    return None


def fmt_horizon_date(s: str) -> str:
    """'2026-11' -> 'NOV 2026'; '2027-01-04' -> '4 JAN 2027'."""
    parts = s.split("-")
    try:
        if len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), 1).strftime("%b %Y").upper()
        if len(parts) == 3:
            d = date(*map(int, parts))
            return f"{d.day} {d:%b %Y}".upper()
    except ValueError:
        pass
    return s
