"""Dummy before/after data, used by `python -m digest preview` and the tests.
Everything here is fake and exists only to show the layout."""
from __future__ import annotations

import copy


def _trial(nct, drug, phases, status, rank, pcd="2031-03", has_results=False, acronym=""):
    return {"nct": nct, "drug": drug, "title": f"Example study of {drug}", "acronym": acronym,
            "status": status, "phases": phases, "phase_rank": rank, "primary_completion": pcd,
            "primary_completion_type": "ESTIMATED", "has_results": has_results,
            "sponsor": "Example Pharma", "sponsor_class": "INDUSTRY", "first_posted": "2026-01-01",
            "last_update": "2026-10-01", "url": f"https://clinicaltrials.gov/study/{nct}"}


def before_after(watchlist: dict, today_iso: str = "2026-11-03") -> tuple[dict, dict]:
    drugs = {d["id"]: {"stage": d["stage"], "basis": "watchlist", "url": (d["sources"] or [""])[0]}
             for d in watchlist["drugs"]}
    before = {
        "generated_at": "2026-10-27T12:00:00+00:00",
        "drugs": drugs,
        "trials": {
            "NCT90000001": _trial("NCT90000001", "zerlasiran", ["PHASE2"], "COMPLETED", 2),
            "NCT90000002": _trial("NCT90000002", "laroprovstat", ["PHASE3"], "RECRUITING", 3,
                                  acronym="AZURE-LDL"),
            "NCT90000003": _trial("NCT90000003", "solbinsiran", ["PHASE2"], "RECRUITING", 2),
            "NCT90000004": _trial("NCT90000004", "olpasiran", ["PHASE3"], "ACTIVE_NOT_RECRUITING", 3,
                                  pcd="2026-12", acronym="OCEAN(a)-Outcomes"),
        },
        "fda": {d["id"]: {"approved": False} for d in watchlist["drugs"]},
        "news_seen": [],
        "discovery_seen": [],
        "errors": [],
    }
    after = copy.deepcopy(before)
    after["generated_at"] = "2026-11-03T12:00:00+00:00"
    # zerlasiran: a new Phase 3 trial appears -> stage change + new trial
    after["trials"]["NCT90000010"] = _trial("NCT90000010", "zerlasiran", ["PHASE3"], "NOT_YET_RECRUITING",
                                            3, acronym="EXAMPLE-3")
    after["drugs"]["zerlasiran"] = {"stage": "phase3", "basis": "NCT90000010",
                                    "url": "https://clinicaltrials.gov/study/NCT90000010"}
    # laroprovstat: enrollment closes
    after["trials"]["NCT90000002"]["status"] = "ACTIVE_NOT_RECRUITING"
    # solbinsiran: results posted
    after["trials"]["NCT90000003"]["has_results"] = True
    after["news"] = {
        "news-aaaaaaaaaaaa": {"id": "news-aaaaaaaaaaaa", "drug": "muvalaplin",
                              "title": "Example headline: muvalaplin trial expands to new sites",
                              "summary": "", "outlet": "Example News", "link": "https://example.com/a",
                              "published": "2026-11-01T09:00:00+00:00"},
    }
    after["discovery"] = {}
    return before, after
