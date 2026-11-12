"""The week in progress: what the daily runs have found since the last weekly close.

Kept in state/week.json. Each daily run adds its new (already filtered and summarised)
changes, stamped with when they were found; the Monday run closes the week into a
history record, sends the email and starts a new week.
"""
from __future__ import annotations

import json
from dataclasses import asdict, fields
from datetime import date
from pathlib import Path

from .diff import Change

_CHANGE_FIELDS = {f.name for f in fields(Change)}


def load(path: str | Path) -> dict | None:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def save(week: dict, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(week, indent=2) + "\n")


def new(started: date) -> dict:
    return {"started": started.isoformat(), "updated": "", "changes": [], "errors": []}


def add(week: dict, changes: list[Change], found_at: str, errors: list[str]) -> dict:
    """Append this run's changes (skipping any already in the week), stamped `found`."""
    have = {c["id"] for c in week["changes"]}
    for c in changes:
        if c.id in have:
            continue
        c.found = c.found or found_at
        week["changes"].append({k: v for k, v in asdict(c).items() if k != "extra"} |
                               {"extra": {k: v for k, v in c.extra.items() if k in ("summary", "published")}})
    week["updated"] = found_at
    week["errors"] = errors
    return week


def changes(week: dict) -> list[Change]:
    return [Change(**{k: v for k, v in c.items() if k in _CHANGE_FIELDS}) for c in week.get("changes", [])]
