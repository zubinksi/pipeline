"""Static site: latest week, archive of past weeks, and a page per drug.

Built from history/*.json + state/snapshot.json + watchlist.yaml into site/,
which the workflow publishes to GitHub Pages.
"""
from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import STAGE_LABEL, STAGE_RANK, STAGES
from dataclasses import asdict

from . import diff, display
from .diff import KIND_LABEL, fmt_horizon_date
from .sources.ctgov import STATUS_PLAIN, phase_label

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
FREQ_LABEL = {"daily": "Daily", "monthly": "Monthly", "infrequent": "Less often", "once": "Once"}
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
                        "kind_label": KIND_LABEL[c["kind"]][0]})
    # a baseline week's stored headline counts drugs at the time; say it plainly instead
    headline = ("Tracking started this week. Changes show up here from next week." if rec.get("baseline")
                else rec["headline"] or "Nothing changed this week.")
    quiet = ""
    return {**rec, "headline": headline, "changes": changes, "quiet": quiet,
            # only hand-picked milestones (new style, with a `when`); older weeks stored routine trial dates
            "horizon": [h for h in rec.get("horizon", []) if h["drug"] in names and h.get("when")],
            "errors": [e for e in rec.get("errors", []) if e.split(" (")[0] in sources]}


def build(out: str | Path, *, weeks: list[dict], snapshot: dict, watchlist: dict,
          site_title: str = "Your Drugs Pipeline") -> Path:
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
                          "freq": [(k, v) for k, v in FREQ_LABEL.items() if k in present("frequency")]},
              "has_lpa": any("lpa" in display.lowers_keys(d.get("lowers", "")) for d in watchlist["drugs"])}

    def write(path: str, template: str, root: str, sel: str = "", **ctx):
        html = _env.get_template(template).render(**common, root=root, sel=sel, **ctx)
        (out / path).write_text(html)

    rows_now = _rows(watchlist, stages, moved)
    home = dict(latest=latest, n_weeks=len(views), groups=_groups(rows_now), n_drugs=len(watchlist["drugs"]),
                drug_rows={r["id"]: r for r in rows_now})
    # News and Drugs are one page with both panels; the two files differ only in which is open
    write("index.html", "home.html.j2", "", sel="news", active="news", **home)
    write("drugs.html", "home.html.j2", "", sel="drugs", active="drugs", **home)
    upcoming_all = diff.horizon(snapshot, watchlist)
    for i, w in enumerate(views):
        newer = views[i - 1]["date"] if i > 0 else None
        older = views[i + 1]["date"] if i + 1 < len(views) else None
        write(f"weeks/{w['date']}.html", "week.html.j2", "../", sel="weeks", week=w, newer=newer, older=older,
              drug_rows={r["id"]: r for r in rows_now},
              groups=_groups(_rows(watchlist, w.get("stages", stages), set(w["moved"]))),
              n_drugs=len(watchlist["drugs"]))
    write("weeks/index.html", "archive.html.j2", "../", sel="weeks", weeks=views)
    write("cabinet.html", "cabinet.html.j2", "", sel="cabinet", groups=_groups(rows_now))

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
              row=_rows({"drugs": [d]}, {d["id"]: stage}, moved)[0],
              stage_basis=snapshot.get("drugs", {}).get(d["id"], {}),
              milestones=[h for h in upcoming_all if h.drug_id == d["id"]],
              updates=updates, history=history, trials=trials)

    return out
