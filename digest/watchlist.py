from __future__ import annotations

from pathlib import Path

import yaml

from . import STAGE_RANK

ROUTES = ("pill", "injection", "infusion")
FREQUENCIES = ("daily", "monthly", "infrequent", "once")

DEFAULT_SETTINGS = {
    "horizon_days": 60,
    "min_trial_phase": 2,
    "max_news_per_drug": 5,
    "discovery": {"enabled": False, "conditions": [], "max_items": 5},
}


def load(path: str | Path = "watchlist.yaml") -> dict:
    data = yaml.safe_load(Path(path).read_text())
    settings = {**DEFAULT_SETTINGS, **(data.get("settings") or {})}
    data["settings"] = settings
    data.setdefault("feeds", [])
    data.setdefault("events", [])
    data.setdefault("reader_context", "")
    seen = set()
    for d in data["drugs"]:
        for key in ("id", "name", "company", "stage"):
            if not d.get(key):
                raise ValueError(f"watchlist drug missing '{key}': {d}")
        if d["id"] in seen:
            raise ValueError(f"duplicate drug id {d['id']}")
        seen.add(d["id"])
        if d["stage"] not in STAGE_RANK:
            raise ValueError(f"{d['id']}: unknown stage {d['stage']!r}")
        if d.get("route") and d["route"] not in ROUTES:
            raise ValueError(f"{d['id']}: route must be one of {ROUTES}")
        if d.get("frequency") and d["frequency"] not in FREQUENCIES:
            raise ValueError(f"{d['id']}: frequency must be one of {FREQUENCIES}")
        d.setdefault("aliases", [])
        d["aliases"] = [str(a) for a in d["aliases"]]
        d.setdefault("sources", [])
    return data


def search_terms(drug: dict) -> list[str]:
    return [drug["name"], *drug["aliases"]]
