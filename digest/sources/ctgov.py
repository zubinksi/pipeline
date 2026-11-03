"""ClinicalTrials.gov API v2 fetcher (no key needed)."""
from __future__ import annotations

import re
from datetime import date, timedelta

import httpx

BASE = "https://clinicaltrials.gov/api/v2/studies"

PHASE_RANK = {"EARLY_PHASE1": 1, "PHASE1": 1, "PHASE2": 2, "PHASE3": 3, "PHASE4": 4}
PHASE_LABEL = {"EARLY_PHASE1": "Early Phase 1", "PHASE1": "Phase 1", "PHASE2": "Phase 2",
               "PHASE3": "Phase 3", "PHASE4": "Phase 4", "NA": "N/A"}

HALTED = {"TERMINATED", "SUSPENDED", "WITHDRAWN"}
STATUS_PLAIN = {
    "NOT_YET_RECRUITING": "not yet recruiting",
    "RECRUITING": "recruiting",
    "ENROLLING_BY_INVITATION": "enrolling by invitation",
    "ACTIVE_NOT_RECRUITING": "fully enrolled, no longer recruiting",
    "COMPLETED": "completed",
    "TERMINATED": "terminated",
    "SUSPENDED": "suspended",
    "WITHDRAWN": "withdrawn",
    "UNKNOWN": "status unknown",
}


def _paged(client: httpx.Client, params: dict, max_pages: int = 5):
    params = dict(params)
    for _ in range(max_pages):
        r = client.get(BASE, params=params)
        r.raise_for_status()
        data = r.json()
        yield from data.get("studies", [])
        token = data.get("nextPageToken")
        if not token:
            return
        params["pageToken"] = token


def parse_study(s: dict) -> dict:
    ps = s.get("protocolSection", {})
    ident = ps.get("identificationModule", {})
    status = ps.get("statusModule", {})
    design = ps.get("designModule", {})
    sponsor = ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {})
    phases = design.get("phases", []) or []
    pcd = status.get("primaryCompletionDateStruct", {}) or {}
    nct = ident.get("nctId", "")
    return {
        "nct": nct,
        "title": ident.get("briefTitle", ""),
        "acronym": ident.get("acronym", ""),
        "status": status.get("overallStatus", "UNKNOWN"),
        "phases": phases,
        "phase_rank": max((PHASE_RANK.get(p, 0) for p in phases), default=0),
        "primary_completion": pcd.get("date", ""),
        "primary_completion_type": pcd.get("type", ""),
        "has_results": bool(s.get("hasResults", False)),
        "sponsor": sponsor.get("name", ""),
        "sponsor_class": sponsor.get("class", ""),
        "first_posted": (status.get("studyFirstPostDateStruct") or {}).get("date", ""),
        "last_update": (status.get("lastUpdatePostDateStruct") or {}).get("date", ""),
        "url": f"https://clinicaltrials.gov/study/{nct}",
    }


def _searchable_text(s: dict) -> str:
    ps = s.get("protocolSection", {})
    ident = ps.get("identificationModule", {})
    parts = [ident.get("briefTitle", ""), ident.get("officialTitle", "")]
    for iv in ps.get("armsInterventionsModule", {}).get("interventions", []) or []:
        parts.append(iv.get("name", ""))
        parts.extend(iv.get("otherNames", []) or [])
    return " ".join(parts)


def mentions(text: str, terms: list[str]) -> bool:
    norm = lambda x: re.sub(r"[\s\-]", "", x.lower())  # "AMG 890" == "AMG-890" == "amg890"
    t = norm(text)
    return any(norm(term) in t for term in terms)


def fetch_trials_for_drug(client: httpx.Client, drug_id: str, terms: list[str]) -> dict[str, dict]:
    """Trials whose interventions/titles actually name the drug (the API search is fuzzy)."""
    query = " OR ".join(f'"{t}"' for t in terms)
    out = {}
    for s in _paged(client, {"query.intr": query, "pageSize": 100}):
        if not mentions(_searchable_text(s), terms):
            continue
        t = parse_study(s)
        if t["nct"]:
            t["drug"] = drug_id
            out[t["nct"]] = t
    return out


def fetch_discovery(client: httpx.Client, conditions: list[str], days: int = 21) -> dict[str, dict]:
    """Recently registered industry Phase 2/3 trials in the watched conditions."""
    since = (date.today() - timedelta(days=days)).isoformat()
    params = {
        "query.cond": " OR ".join(f'"{c}"' for c in conditions),
        "filter.advanced": (
            f"AREA[StudyFirstPostDate]RANGE[{since},MAX] AND AREA[LeadSponsorClass]INDUSTRY "
            "AND (AREA[Phase]PHASE2 OR AREA[Phase]PHASE3)"
        ),
        "pageSize": 50,
    }
    out = {}
    for s in _paged(client, params, max_pages=2):
        t = parse_study(s)
        ivs = s.get("protocolSection", {}).get("armsInterventionsModule", {}).get("interventions", []) or []
        t["interventions"] = [iv.get("name", "") for iv in ivs][:4]
        if t["nct"]:
            out[t["nct"]] = t
    return out


def phase_label(phases: list[str]) -> str:
    return "/".join(PHASE_LABEL.get(p, p) for p in phases) or "phase n/a"
