"""Build this week's snapshot from all sources.

If a source fails, the previous week's data for it is carried forward and
the failure is recorded, so an outage never looks like "trial disappeared"
or "nothing changed" without saying so.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from . import RANK_STAGE, STAGE_RANK
from .sources import ctgov, news, openfda
from .watchlist import search_terms

log = logging.getLogger(__name__)
NEWS_SEEN_CAP = 2000


def load(path: str | Path) -> dict | None:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def save(snapshot: dict, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")


def http_client() -> httpx.Client:
    return httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "cholesterol-pipeline-digest/1.0 (personal weekly digest)"},
    )


def resolve_stage(drug: dict, trials: dict, fda: dict) -> dict:
    """Highest of: watchlist floor, highest CT.gov phase (1-3), FDA approval."""
    best = {"stage": drug["stage"], "basis": "watchlist", "url": (drug["sources"] or [""])[0]}
    rank = STAGE_RANK[drug["stage"]]
    for t in trials.values():
        if t["drug"] != drug["id"] or t["status"] == "WITHDRAWN":
            continue
        r = t["phase_rank"]
        if 1 <= r <= 3 and r > rank:
            rank = r
            best = {"stage": RANK_STAGE[r], "basis": t["nct"], "url": t["url"]}
    if fda.get("approved") and rank < STAGE_RANK["approved"]:
        best = {"stage": "approved", "basis": "FDA", "url": fda.get("url", "")}
    return best


def build(watchlist: dict, prev: dict | None, client: httpx.Client | None = None,
          now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    prev = prev or {}
    client = client or http_client()
    errors: list[str] = []
    drugs = watchlist["drugs"]
    settings = watchlist["settings"]
    # Which drugs/sources have had at least one successful fetch. Only those are
    # diffed, so a source that was down on its first run can't later make every
    # existing trial look "new".
    pb = prev.get("baselined") or {}
    baselined = {"ctgov": set(pb.get("ctgov", [])), "fda": set(pb.get("fda", [])),
                 "news": bool(pb.get("news")), "discovery": bool(pb.get("discovery"))}

    def fail(source: str):
        if source not in errors:
            errors.append(source)

    # --- ClinicalTrials.gov, per drug ---
    trials: dict[str, dict] = {}
    for d in drugs:
        try:
            trials.update(ctgov.fetch_trials_for_drug(client, d["id"], search_terms(d)))
            baselined["ctgov"].add(d["id"])
        except Exception as e:  # noqa: BLE001 - any failure: carry forward
            log.warning("ctgov %s failed: %s", d["id"], e)
            fail("ClinicalTrials.gov")
            trials.update({k: v for k, v in prev.get("trials", {}).items() if v.get("drug") == d["id"]})

    # --- discovery: new trials in watched conditions ---
    discovery: dict[str, dict] = {}
    disc = settings.get("discovery") or {}
    if disc.get("enabled") and disc.get("conditions"):
        try:
            discovery = ctgov.fetch_discovery(client, disc["conditions"])
            baselined["discovery"] = True
        except Exception as e:  # noqa: BLE001
            log.warning("ctgov discovery failed: %s", e)
            fail("ClinicalTrials.gov")

    # --- openFDA ---
    fda: dict[str, dict] = {}
    for d in drugs:
        try:
            fda[d["id"]] = openfda.fetch_approval(client, search_terms(d))
            baselined["fda"].add(d["id"])
        except Exception as e:  # noqa: BLE001
            log.warning("openfda %s failed: %s", d["id"], e)
            fail("openFDA")
            fda[d["id"]] = prev.get("fda", {}).get(d["id"], {"approved": False})

    # --- news ---
    news_items = collect_news(client, watchlist, errors, now)
    news_ok = "Google News" not in errors  # extra feeds failing shouldn't block news forever
    n_errors = len(errors)
    field_items = collect_field(client, watchlist, errors, now, exclude=set(news_items))
    field_ok = len(errors) == n_errors

    stages = {d["id"]: resolve_stage(d, trials, fda.get(d["id"], {})) for d in drugs}

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "drugs": stages,
        "trials": trials,
        "fda": fda,
        "news": news_items,  # this week's fetched items; diff filters to unseen ones
        "news_seen": prev.get("news_seen", []),  # updated by finalize()
        "discovery": discovery,
        "discovery_seen": prev.get("discovery_seen", []),
        "field": field_items,  # this week's field-wide news; diff filters to unseen ones
        "field_seen": prev.get("field_seen", []),
        "errors": errors,
        "baselined": {"ctgov": sorted(baselined["ctgov"]), "fda": sorted(baselined["fda"]),
                      "news": baselined["news"] or news_ok, "discovery": baselined["discovery"],
                      "field": bool(pb.get("field")) or field_ok},
    }


def collect_news(client: httpx.Client, watchlist: dict, errors: list[str],
                 now: datetime | None = None) -> dict[str, dict]:
    drugs = watchlist["drugs"]
    per_drug = watchlist["settings"].get("max_news_per_drug", 5)
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=10)
    items: dict[str, dict] = {}

    def add(item: dict, drug_id: str):
        if datetime.fromisoformat(item["published"]) < cutoff:
            return
        item = {**item, "drug": drug_id}
        items.setdefault(item["id"], item)

    for d in drugs:
        try:
            found = [i for i in news.fetch_google_news(client, search_terms(d))
                     if news.match_drug(i, [d], search_terms)]
            found.sort(key=lambda i: i["published"], reverse=True)
            for i in found[:per_drug]:
                add(i, d["id"])
        except Exception as e:  # noqa: BLE001
            log.warning("news %s failed: %s", d["id"], e)
            if "Google News" not in errors:
                errors.append("Google News")

    for feed in watchlist.get("feeds", []):
        try:
            for i in news.fetch_feed(client, feed["url"], feed["name"]):
                drug_id = news.match_drug(i, drugs, search_terms)
                if drug_id:
                    add(i, drug_id)
        except Exception as e:  # noqa: BLE001
            log.warning("feed %s failed: %s", feed["name"], e)
            errors.append(feed["name"])
    return items


def collect_field(client: httpx.Client, watchlist: dict, errors: list[str],
                  now: datetime | None = None, exclude: set[str] = frozenset()) -> dict[str, dict]:
    """Field-wide news: a few broad searches, minus anything naming a watchlist drug
    (that goes in the drug's own news) or already found as drug news."""
    cfg = watchlist["settings"].get("field_news") or {}
    if not cfg.get("enabled") or not cfg.get("queries"):
        return {}
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=10)
    drugs = watchlist["drugs"]
    items: dict[str, dict] = {}
    for q in cfg["queries"]:
        try:
            for i in news.fetch_google_news_query(client, q):
                if (i["id"] in exclude or datetime.fromisoformat(i["published"]) < cutoff
                        or news.match_drug(i, drugs, search_terms)):
                    continue
                items.setdefault(i["id"], {**i, "drug": None, "query": q})
        except Exception as e:  # noqa: BLE001
            log.warning("field news %r failed: %s", q, e)
            if "Google News" not in errors:
                errors.append("Google News")
    newest = sorted(items.values(), key=lambda i: i["published"], reverse=True)
    return {i["id"]: i for i in newest[: cfg.get("max_candidates", 15)]}


def finalize(snapshot: dict) -> dict:
    """Mark this week's news, discovery and field items as seen before saving."""
    seen = list(dict.fromkeys(snapshot["news_seen"] + list(snapshot["news"])))
    dseen = list(dict.fromkeys(snapshot["discovery_seen"] + list(snapshot["discovery"])))
    fseen = list(dict.fromkeys(snapshot.get("field_seen", []) + list(snapshot.get("field", {}))))
    out = {**snapshot, "news_seen": seen[-NEWS_SEEN_CAP:], "discovery_seen": dseen[-NEWS_SEEN_CAP:],
           "field_seen": fseen[-NEWS_SEEN_CAP:]}
    for k in ("news", "discovery", "field"):
        out.pop(k, None)
    return out
