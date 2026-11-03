import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from digest import snapshot
from digest.sources import ctgov, news, openfda

FIX = Path(__file__).parent / "fixtures"


def _wl(drugs):
    return {"drugs": drugs, "feeds": [], "events": [], "reader_context": "",
            "settings": {"horizon_days": 60, "min_trial_phase": 2, "max_news_per_drug": 5,
                         "discovery": {"enabled": False}}}


OBI = {"id": "obicetrapib", "name": "Obicetrapib", "aliases": ["TA-8995"], "company": "NewAmsterdam",
       "stage": "phase3", "sources": ["https://example.com/obi"]}


def mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ctgov_filters_fuzzy_matches_and_parses():
    data = json.loads((FIX / "ctgov_obicetrapib.json").read_text())
    client = mock_client(lambda req: httpx.Response(200, json=data))
    trials = ctgov.fetch_trials_for_drug(client, "obicetrapib", ["Obicetrapib", "TA-8995"])
    assert set(trials) == {"NCT05202509", "NCT04753606"}  # anacetrapib study dropped
    prevail = trials["NCT05202509"]
    assert prevail["acronym"] == "PREVAIL" and prevail["phase_rank"] == 3
    assert prevail["primary_completion"] == "2026-12" and prevail["primary_completion_type"] == "ESTIMATED"
    tandem = trials["NCT04753606"]  # matched via "TA 8995" (space vs hyphen)
    assert tandem["has_results"] and tandem["phase_rank"] == 3
    assert ctgov.phase_label(tandem["phases"]) == "Phase 2/Phase 3"


def test_ctgov_follows_pagination():
    page1 = {"studies": json.loads((FIX / "ctgov_obicetrapib.json").read_text())["studies"][:1],
             "nextPageToken": "abc"}
    page2 = {"studies": json.loads((FIX / "ctgov_obicetrapib.json").read_text())["studies"][1:2]}
    seen = []

    def handler(req):
        seen.append(req.url.params.get("pageToken"))
        return httpx.Response(200, json=page2 if req.url.params.get("pageToken") else page1)

    trials = ctgov.fetch_trials_for_drug(mock_client(handler), "obicetrapib", ["Obicetrapib", "TA-8995"])
    assert seen == [None, "abc"] and len(trials) == 2


def test_openfda_parse_picks_original_nda_approval():
    data = json.loads((FIX / "openfda_enlicitide.json").read_text())
    rec = openfda.parse(data["results"], ["Enlicitide", "MK-0616", "Lipfendra"])
    assert rec["approved"] and rec["application"] == "NDA219999"
    assert rec["date"] == "2026-07-16" and rec["brand"] == "Lipfendra"
    assert "ApplNo=219999" in rec["url"]


def test_openfda_404_means_not_approved():
    client = mock_client(lambda req: httpx.Response(404, json={"error": {"code": "NOT_FOUND"}}))
    assert openfda.fetch_approval(client, ["Muvalaplin"]) == {"approved": False}


def test_news_parse_strips_outlet_and_html():
    items = news.parse_feed((FIX / "gnews.xml").read_bytes(), "Google News")
    first = items[0]
    assert first["title"] == "NewAmsterdam reports PREVAIL interim analysis for obicetrapib"
    assert first["outlet"] == "Business Wire"
    assert "<a" not in first["summary"]


def test_build_end_to_end_with_failures_carried_forward():
    ct = json.loads((FIX / "ctgov_obicetrapib.json").read_text())
    rss = (FIX / "gnews.xml").read_bytes()

    def handler(req):
        if "clinicaltrials.gov" in req.url.host:
            return httpx.Response(200, json=ct)
        if "api.fda.gov" in req.url.host:
            return httpx.Response(500)
        if "news.google.com" in req.url.host:
            return httpx.Response(200, content=rss)
        raise AssertionError(req.url)

    prev = {"fda": {"obicetrapib": {"approved": False, "marker": "kept"}}}
    snap = snapshot.build(_wl([OBI]), prev, client=mock_client(handler),
                          now=datetime(2026, 11, 3, tzinfo=timezone.utc))
    assert snap["errors"] == ["openFDA"]
    assert snap["fda"]["obicetrapib"]["marker"] == "kept"  # carried forward, not reset
    assert snap["drugs"]["obicetrapib"]["stage"] == "phase3"
    # only on-topic, recent news: not the stocks piece (no drug name), not the 2023 story
    titles = [n["title"] for n in snap["news"].values()]
    assert titles == ["NewAmsterdam reports PREVAIL interim analysis for obicetrapib"]


def test_ctgov_failure_keeps_previous_trials():
    prev_trial = {"nct": "NCT1", "drug": "obicetrapib", "phase_rank": 3, "status": "RECRUITING"}
    client = mock_client(lambda req: httpx.Response(503))
    snap = snapshot.build(_wl([OBI]), {"trials": {"NCT1": prev_trial}}, client=client)
    assert snap["trials"] == {"NCT1": prev_trial}
    assert snap["errors"][0] == "ClinicalTrials.gov"
    assert snap["baselined"]["ctgov"] == []
