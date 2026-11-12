from __future__ import annotations

from pathlib import Path

import yaml

from . import STAGE_RANK

ROUTES = ("pill", "injection", "infusion")
FREQUENCIES = ("daily", "weekly", "monthly", "infrequent", "once")
PROVEN = ("yes", "testing", "failed", "untested")

DEFAULT_SETTINGS = {
    "horizon_days": 60,
    "min_trial_phase": 2,
    "max_news_per_drug": 5,
    "discovery": {"enabled": False, "conditions": [], "max_items": 5},
}
# Used when a watchlist has no `topics` (older files, tests): everything is one topic.
DEFAULT_TOPIC = {"id": "heart", "title": "Heart & cholesterol", "effect_label": "LDL reduction",
                 "effect_col": "Lowers", "discovery": [], "field_queries": [], "explain": "",
                 "outcome": {"col": "Heart attacks?", "title": "CV outcomes",
                             "yes": "Prevents heart attacks", "testing": "Heart-attack trial underway",
                             "failed": "Didn't prevent heart attacks", "untested": "No heart-attack data yet",
                             "short": {"yes": "Proven", "testing": "Trial underway",
                                       "failed": "Didn't prevent", "untested": "No data yet"}}}


def load(path: str | Path = "watchlist.yaml") -> dict:
    data = yaml.safe_load(Path(path).read_text())
    settings = {**DEFAULT_SETTINGS, **(data.get("settings") or {})}
    data["settings"] = settings
    data.setdefault("feeds", [])
    data.setdefault("events", [])
    data.setdefault("reader_context", "")
    data.setdefault("companies", [])
    topics = data["topics"] = topics_of(data)
    topic_ids = [t["id"] for t in topics]
    if len(set(topic_ids)) != len(topic_ids):
        raise ValueError("duplicate topic id")
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
        if d.get("proven") and d["proven"] not in PROVEN:
            raise ValueError(f"{d['id']}: proven must be one of {PROVEN}")
        d.setdefault("topic", topic_ids[0])
        if d["topic"] not in topic_ids:
            raise ValueError(f"{d['id']}: unknown topic {d['topic']!r}")
        groups = [g["id"] for g in next(t for t in topics if t["id"] == d["topic"]).get("groups") or []]
        if groups and d.get("group") not in groups:
            raise ValueError(f"{d['id']}: group must be one of {groups} for topic {d['topic']}")
        d.setdefault("aliases", [])
        d["aliases"] = [str(a) for a in d["aliases"]]
        d.setdefault("sources", [])
    return data


def search_terms(drug: dict) -> list[str]:
    return [drug["name"], *drug["aliases"]]


def topics_of(watchlist: dict) -> list[dict]:
    """The watchlist's topics. Older files (and test fixtures) have none: then
    everything is one topic, with discovery conditions and field queries taken
    from settings, where they used to live."""
    if watchlist.get("topics"):
        return watchlist["topics"]
    settings = watchlist.get("settings") or {}
    return [{**DEFAULT_TOPIC,
             "discovery": list((settings.get("discovery") or {}).get("conditions", [])),
             "field_queries": list((settings.get("field_news") or {}).get("queries", []))}]


def topics_by_id(watchlist: dict) -> dict[str, dict]:
    return {t["id"]: t for t in topics_of(watchlist)}


def companies_of(drug: dict, watchlist: dict) -> list[str]:
    """Ids of the watchlist companies a drug belongs to (by its `company` text)."""
    text = (drug.get("company") or "").lower()
    return [c["id"] for c in watchlist.get("companies", [])
            if any(m.lower() in text for m in c.get("match", [c.get("title", c["id"])]))]
