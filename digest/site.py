"""Static site: latest week, archive of past weeks, and a page per drug.

Built from history/*.json + state/snapshot.json + watchlist.yaml into site/,
which the workflow publishes to GitHub Pages.
"""
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import STAGE_LABEL, STAGE_RANK, STAGES
from dataclasses import asdict

from . import diff, display
from .diff import KIND_LABEL, fmt_horizon_date
from .sources.ctgov import STATUS_PLAIN, phase_label
from .watchlist import companies_of, topics_by_id, topics_of

TEMPLATES = Path(__file__).parent / "templates" / "site"
_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]),
                   trim_blocks=True, lstrip_blocks=True)


def _fmt_date(s: str) -> str:
    try:
        return date.fromisoformat(s).strftime("%b %-d, %Y")
    except ValueError:
        return s


def _fmt_short(s: str) -> str:
    try:
        return date.fromisoformat(s).strftime("%b %-d")
    except ValueError:
        return s


_env.filters["nice_date"] = _fmt_date
_env.filters["nice_date_short"] = _fmt_short
_env.filters["horizon_date"] = fmt_horizon_date
STATIC = Path(__file__).parent / "static"
FREQ_LABEL = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly", "infrequent": "Less often", "once": "Once"}
ACTIVE = {"NOT_YET_RECRUITING", "RECRUITING", "ENROLLING_BY_INVITATION", "ACTIVE_NOT_RECRUITING"}


_rows = display.rows
_groups = display.groups


def _week_view(rec: dict, drugs: dict, sources: set[str]) -> dict:
    """A week's record as shown today: drugs since dropped from the watchlist are
    left out, and so are errors from sources no longer used."""
    names = {d["name"] for d in drugs.values()} | {d["brand"] for d in drugs.values() if d.get("brand")}
    changes = []
    for c in rec["changes"]:
        if c.get("drug") and c["drug"] not in drugs:
            continue
        d = drugs.get(c.get("drug"))
        changes.append({**c, "drug_name": d["name"] if d else "", "company": d["company"] if d else "",
                        "topic": (d or {}).get("topic") or c.get("topic", ""),
                        "kind_label": KIND_LABEL[c["kind"]][0]})
    # a baseline week's stored headline counts drugs at the time; say it plainly instead
    headline = ("Tracking started this week. Changes show up here from next week." if rec.get("baseline")
                else rec["headline"] or "Nothing changed this week.")
    quiet = ""
    return {**rec, "headline": headline, "changes": changes, "quiet": quiet,
            # only hand-picked milestones (new style, with a `when`); older weeks stored routine trial dates
            "horizon": [h for h in rec.get("horizon", []) if h["drug"] in names and h.get("when")],
            "errors": [e for e in rec.get("errors", []) if e.split(" (")[0] in sources]}


def calendar(items: list[dict], drugs: dict, topics: dict, today: date | None = None,
             shades: dict | None = None) -> list[dict]:
    """The look-ahead as a calendar across topics: groups by period (any week now,
    a month, or a looser label like "EARLY 2027"), each item tagged with its topic."""
    today = today or date.today()
    groups: list[dict] = []
    for h in items:
        when = h.get("when") or fmt_horizon_date(h.get("date", ""))
        parts = when.split()
        if when == "DUE NOW":
            key, label, day = "due", "Any week now", ""
        elif len(parts) == 3 and parts[0].isdigit():      # "14 NOV 2026": file under its month
            key, label, day = f"{parts[1]} {parts[2]}", f"{parts[1]} {parts[2]}", f"{parts[0]} {parts[1]}"
        else:
            key, label, day = when, when, ""
        rel = ""
        try:
            d = date.fromisoformat(h.get("date", ""))
            days = (d - today).days
            if 0 <= days <= 90:
                rel = "today" if days == 0 else ("in 1 day" if days == 1 else
                      f"in {days} days" if days < 14 else f"in {round(days / 7)} weeks")
        except ValueError:
            pass
        drug = drugs.get(h.get("drug_id", ""), {})
        t = topics.get(drug.get("topic", ""), {})
        # how precise the date is, for the month grids
        iso = h.get("date", "")
        if key == "due":
            precision, ym = "due", (today.year, today.month)
        elif day:
            precision, ym = "day", (int(iso[:4]), int(iso[5:7]))
        elif len(parts) == 2 and parts[0][:1].isalpha() and parts[1].isdigit() and parts[0] in _MONTHS:
            precision, ym = "month", (int(parts[1]), _MONTHS.index(parts[0]) + 1)
        elif len(iso) >= 7 and iso[:4].isdigit() and iso[5:7].isdigit():
            precision, ym = "approx", (int(iso[:4]), int(iso[5:7]))   # e.g. "EARLY 2027", filed under its sort date
        else:
            precision, ym = "loose", None
        shade = (shades or {}).get(drug.get("topic", ""), {"alpha": 1, "dark": True})
        item = {**h, "day": day, "rel": rel, "topic": drug.get("topic", ""), "shade": shade,
                "topic_short": t.get("short") or t.get("title", ""), "precision": precision, "ym": ym,
                "dom": int(iso[8:10]) if precision == "day" else 0}
        if groups and groups[-1]["key"] == key:
            groups[-1]["items"].append(item)
        else:
            groups.append({"key": key, "label": label, "items": [item]})
    return groups


_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def build(out: str | Path, *, weeks: list[dict], snapshot: dict, watchlist: dict,
          site_title: str = "Readout") -> Path:
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    (out / "weeks").mkdir(parents=True)
    (out / "drugs").mkdir()
    shutil.copytree(STATIC, out / "assets")
    drugs = {d["id"]: d for d in watchlist["drugs"]}
    sources = {"ClinicalTrials.gov", "openFDA", "Google News", *(f["name"] for f in watchlist.get("feeds", []))}
    views = [_week_view(w, drugs, sources) for w in weeks]  # newest first
    latest = views[0] if views else None
    if latest:  # "Watching for" on the home page is always worked out from today's watchlist
        latest = {**latest, "horizon": [asdict(h) for h in diff.horizon(snapshot, watchlist)]}
    stages = {k: v["stage"] for k, v in snapshot.get("drugs", {}).items()}
    moved = set(latest["moved"]) if latest else set()
    present = lambda key: {d.get(key) for d in watchlist["drugs"]}
    common = {"site_title": site_title, "stages": [label for _, label in STAGES],
              "horizon_days": watchlist["settings"].get("horizon_days", 60),
              "updated": snapshot.get("generated_at", "")[:10],
              "filters": {"lowers": [(k, v) for k, v in display.LOWERS_LABEL.items()
                                     if any(k in display.lowers_keys(d.get("lowers", "")) for d in watchlist["drugs"])],
                          "freq": [(k, v) for k, v in FREQ_LABEL.items() if k in present("frequency")],
                          "tp": [(t["id"], t.get("title", t["id"])) for t in topics_of(watchlist)
                                 if t["id"] in present("topic")],
                          "st": [(key, title) for key, title, sts, _ in display.GROUPS
                                 if any(stages.get(d["id"], d["stage"]) in sts for d in watchlist["drugs"])]},
              "has_lpa": any("lpa" in display.lowers_keys(d.get("lowers", "")) for d in watchlist["drugs"]),
              "topics": topics_by_id(watchlist),
              # what panel.js needs to know on every page: each drug's topic and companies
              "panel_data": json.dumps({
                  "topics": [t["id"] for t in topics_of(watchlist)],
                  "drugs": {d["id"]: {"t": d.get("topic", ""), "c": companies_of(d, watchlist)}
                            for d in watchlist["drugs"]}}, separators=(",", ":"))}

    def write(path: str, template: str, root: str, sel: str = "", **ctx):
        html = _env.get_template(template).render(**common, root=root, sel=sel, **ctx)
        (out / path).write_text(html)

    rows_now = _rows(watchlist, stages, moved)
    topics = topics_by_id(watchlist)
    drug_map = {d["id"]: d for d in watchlist["drugs"]}
    rows_by_id = {r["id"]: r for r in rows_now}
    if latest:
        latest = {**latest, "calendar": calendar(latest["horizon"], drug_map, topics,
                                                 shades=display.topic_shades(watchlist))}
    home = dict(latest=latest, n_weeks=len(views), sections=display.sections(rows_now, watchlist),
                n_drugs=len(watchlist["drugs"]), drug_rows={r["id"]: r for r in rows_now})
    # News and Drugs are one page with both panels; the two files differ only in which is open
    write("index.html", "home.html.j2", "", sel="news", active="news", **home)
    write("drugs.html", "home.html.j2", "", sel="drugs", active="drugs", **home)
    upcoming_all = diff.horizon(snapshot, watchlist)
    for i, w in enumerate(views):
        newer = views[i - 1]["date"] if i > 0 else None
        older = views[i + 1]["date"] if i + 1 < len(views) else None
        w = {**w, "calendar": calendar(w["horizon"], drug_map, topics, date.fromisoformat(w["date"]),
                                       shades=display.topic_shades(watchlist))}
        write(f"weeks/{w['date']}.html", "week.html.j2", "../", sel="weeks", week=w, newer=newer, older=older,
              drug_rows={r["id"]: r for r in rows_now},
              sections=display.sections(_rows(watchlist, w.get("stages", stages), set(w["moved"])), watchlist),
              n_drugs=len(watchlist["drugs"]))
    write("weeks/index.html", "archive.html.j2", "../", sel="weeks", weeks=views)
    write("labs.html", "labs.html.j2", "", sel="labs")
    write("panel.html", "panel.html.j2", "", sel="panel", sections=display.sections(rows_now, watchlist),
          companies=[{**c, "rows": [r for r in rows_now if c["id"] in r["companies"]]}
                     for c in watchlist.get("companies", [])])

    trials_by_drug: dict[str, list] = {}
    for t in snapshot.get("trials", {}).values():
        trials_by_drug.setdefault(t["drug"], []).append({
            **t, "phase": phase_label(t["phases"]),
            "status_plain": STATUS_PLAIN.get(t["status"], t["status"].lower()),
        })
    for d in watchlist["drugs"]:
        updates = [{**c, "week": w["date"]} for w in views for c in w["changes"] if c.get("drug") == d["id"]]
        history = []  # first week each stage was seen, oldest first
        for w in reversed(views):
            s = w.get("stages", {}).get(d["id"])
            if s and (not history or history[-1]["stage"] != s):
                history.append({"stage": s, "label": STAGE_LABEL[s], "date": w["date"]})
        trials = sorted(trials_by_drug.get(d["id"], []),
                        key=lambda t: (-t["phase_rank"], t.get("primary_completion") or ""))
        stage = stages.get(d["id"], d["stage"])
        today = date.today().isoformat()[:7]
        upcoming = [t for t in trials if t["status"] in ACTIVE and t.get("primary_completion")
                    and t["primary_completion"][:7] >= today and t["phase_rank"] >= 2]
        next_pcd = min(upcoming, key=lambda t: t["primary_completion"], default=None)
        write(f"drugs/{d['id']}.html", "drug.html.j2", "../", sel="drugs", drug=d,
              n_active=sum(1 for t in trials if t["status"] in ACTIVE), next_pcd=next_pcd,
              row=next(r for r in _rows(watchlist, {**stages, d["id"]: stage}, moved) if r["id"] == d["id"]),
              topic=(t := topics_by_id(watchlist).get(d.get("topic")) or topics_of(watchlist)[0]),
              approach=next((a for a in watchlist.get("approaches", []) if a["id"] == d.get("approach")), None),
              effect_label=next((g.get("effect_label") for g in t.get("groups") or []
                                 if g["id"] == d.get("group") and g.get("effect_label")),
                                t.get("effect_label") or "Effect"),
              stage_basis=snapshot.get("drugs", {}).get(d["id"], {}),
              milestones=[h for h in upcoming_all if h.drug_id == d["id"]],
              updates=updates, history=history, trials=trials)

    return out
