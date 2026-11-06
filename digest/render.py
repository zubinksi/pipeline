"""Render the digest as HTML email + plain-text fallback."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import STAGE_RANK, STAGES
from .diff import Change, HorizonItem

TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]),
                   trim_blocks=True, lstrip_blocks=True)
_text_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=False,
                        trim_blocks=True, lstrip_blocks=True)


@dataclass
class Digest:
    subject: str
    html: str
    text: str


def strip_rows(snapshot: dict, watchlist: dict, changes: list[Change]) -> list[dict]:
    moved = {c.drug for c in changes if c.kind in ("stage_change", "fda_approval")}
    rows = []
    for d in watchlist["drugs"]:
        s = snapshot["drugs"][d["id"]]
        rank = STAGE_RANK[s["stage"]]
        rows.append({
            "name": d["name"], "company": d["company"], "form": d.get("form", ""),
            "target": d.get("target", ""), "badge": d.get("badge", ""), "rank": rank, "moved": d["id"] in moved,
            "url": s.get("url", ""),
            "text_dots": "──".join("◉" if i + 1 == rank else ("●" if i + 1 < rank else "○")
                                   for i in range(len(STAGES))),
        })
    return rows


def render(*, headline: str, changes: list[Change], horizon: list[HorizonItem], snapshot: dict,
           watchlist: dict, baseline: bool = False, today: date | None = None) -> Digest:
    today = today or date.today()
    names = {d["id"]: d for d in watchlist["drugs"]}
    errors = snapshot.get("errors", [])
    n_drugs = len(watchlist["drugs"])

    if not changes and not baseline:
        line = f"Nothing changed this week across the {n_drugs} drugs you follow."
        if errors:
            line += f" (Couldn't reach: {', '.join(errors)}; they'll be checked again next week.)"
        return Digest(subject=f"Cholesterol pipeline: nothing changed ({today:%b %-d})",
                      html=f"<p style=\"font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;"
                           f"font-size:15px;color:#1f2933\">{_esc(line)}</p>",
                      text=line + "\n")

    if baseline:
        headline = baseline_headline(snapshot, watchlist)

    ctx = {
        "headline": headline,
        "changes": [{
            "drug": names[c.drug]["name"] if c.drug in names else "",
            "company": names[c.drug]["company"] if c.drug in names else "",
            "what": c.what, "why": c.why, "url": c.url, "source": c.source,
            "kind": c.kind,
        } for c in changes],
        "horizon": horizon,
        "horizon_days": watchlist["settings"].get("horizon_days", 60),
        "stages": [label for _, label in STAGES],
        "rows": strip_rows(snapshot, watchlist, changes),
        "errors": errors,
        "today": today,
        "baseline": baseline,
        "site_url": os.environ.get("SITE_URL", ""),
    }
    subject = f"Cholesterol pipeline: {headline}" if len(headline) < 90 else "Cholesterol pipeline weekly"
    return Digest(subject=subject,
                  html=_env.get_template("digest.html.j2").render(**ctx),
                  text=_text_env.get_template("digest.txt.j2").render(**ctx))


def baseline_headline(snapshot: dict, watchlist: dict) -> str:
    return (f"First run: now tracking {len(watchlist['drugs'])} drugs and "
            f"{len(snapshot.get('trials', {}))} trials. From next week, only changes are reported.")


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
