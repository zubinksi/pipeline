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
from .diff import KIND_LABEL
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
STATIC = Path(__file__).parent / "static"
STAGE_SHORT = {"phase1": "P1", "phase2": "P2", "phase3": "P3", "filed": "FILED", "approved": "APPR"}
ACTIVE = {"NOT_YET_RECRUITING", "RECRUITING", "ENROLLING_BY_INVITATION", "ACTIVE_NOT_RECRUITING"}


def _rows(watchlist: dict, stages: dict, moved: set[str]) -> list[dict]:
    rows = []
    for d in watchlist["drugs"]:
        stage = stages.get(d["id"], d["stage"])
        rows.append({**d, "rank": STAGE_RANK[stage], "stage_label": STAGE_LABEL[stage],
                     "stage_short": STAGE_SHORT[stage], "moved": d["id"] in moved})
    return rows


def _week_view(rec: dict, drugs: dict) -> dict:
    changes = []
    for c in rec["changes"]:
        d = drugs.get(c.get("drug"))
        changes.append({**c, "drug_name": d["name"] if d else "", "company": d["company"] if d else "",
                        "kind_label": KIND_LABEL[c["kind"]][0]})
    headline = rec["headline"] or "Nothing changed this week."
    return {**rec, "headline": headline, "changes": changes}


def build(out: str | Path, *, weeks: list[dict], snapshot: dict, watchlist: dict,
          site_title: str = "Cholesterol pipeline") -> Path:
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    (out / "weeks").mkdir(parents=True)
    (out / "drugs").mkdir()
    shutil.copytree(STATIC, out / "assets")
    drugs = {d["id"]: d for d in watchlist["drugs"]}
    views = [_week_view(w, drugs) for w in weeks]  # newest first
    latest = views[0] if views else None
    stages = {k: v["stage"] for k, v in snapshot.get("drugs", {}).items()}
    moved = set(latest["moved"]) if latest else set()
    trials_all = snapshot.get("trials", {})
    if latest:
        n = len(latest["changes"])
        sub = (f"BASELINE · {_fmt_short(latest['date']).upper()}" if latest["baseline"] else
               f"{n} CHANGE{'S' if n != 1 else ''} · WEEK OF {_fmt_short(latest['date']).upper()}")
    else:
        sub = "NO RUNS YET"
    common = {"site_title": site_title, "stages": [label for _, label in STAGES],
              "horizon_days": watchlist["settings"].get("horizon_days", 60),
              "updated": snapshot.get("generated_at", "")[:10],
              "side": {"rows": _rows(watchlist, stages, moved), "sub": sub, "n_weeks": len(views)},
              "n_trials": len(trials_all),
              "n_approved": sum(1 for d in watchlist["drugs"]
                                if stages.get(d["id"], d["stage"]) == "approved")}

    def write(path: str, template: str, root: str, sel: str = "", **ctx):
        html = _env.get_template(template).render(**common, root=root, sel=sel, **ctx)
        (out / path).write_text(html)

    write("index.html", "index.html.j2", "", latest=latest, weeks=views[:12], n_weeks=len(views),
          rows=_rows(watchlist, stages, moved))
    for i, w in enumerate(views):
        newer = views[i - 1]["date"] if i > 0 else None
        older = views[i + 1]["date"] if i + 1 < len(views) else None
        write(f"weeks/{w['date']}.html", "week.html.j2", "../", sel="weeks", week=w, newer=newer, older=older,
              rows=_rows(watchlist, w.get("stages", stages), set(w["moved"])))
    write("weeks/index.html", "archive.html.j2", "../", sel="weeks", weeks=views)

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
        write(f"drugs/{d['id']}.html", "drug.html.j2", "../", sel=d["id"], drug=d,
              n_active=sum(1 for t in trials if t["status"] in ACTIVE), next_pcd=next_pcd,
              row=_rows({"drugs": [d]}, {d["id"]: stage}, moved)[0],
              stage_basis=snapshot.get("drugs", {}).get(d["id"], {}),
              updates=updates, history=history, trials=trials)

    return out
