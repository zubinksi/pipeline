"""One JSON file per weekly run in history/, committed to the repo.
The site is rebuilt from these each week, so past weeks stay browsable."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .diff import Change, HorizonItem


def record(*, day: date, headline: str, lead: str = "", changes: list[Change], horizon: list[HorizonItem],
           snapshot: dict, baseline: bool) -> dict:
    return {
        "date": day.isoformat(),
        "headline": headline,
        "lead": lead,
        "baseline": baseline,
        "changes": [{k: v for k, v in asdict(c).items() if k != "extra"} for c in changes],
        "horizon": [asdict(h) for h in horizon],
        "stages": {k: v["stage"] for k, v in snapshot["drugs"].items()},
        "moved": sorted({c.drug for c in changes if c.kind in ("stage_change", "fda_approval") and c.drug}),
        "errors": snapshot.get("errors", []),
    }


def save(rec: dict, directory: str | Path = "history") -> Path:
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{rec['date']}.json"
    p.write_text(json.dumps(rec, indent=2) + "\n")
    return p


def load_all(directory: str | Path = "history") -> list[dict]:
    """Newest first."""
    d = Path(directory)
    if not d.exists():
        return []
    return [json.loads(p.read_text()) for p in sorted(d.glob("*.json"), reverse=True)]
