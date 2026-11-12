import copy
from datetime import date

from digest import diff, snapshot
from digest.sample import _trial, before_after
from digest.watchlist import load

WL = load("watchlist.yaml")


def kinds(changes):
    return sorted(c.kind for c in changes)


def test_first_run_is_baseline():
    _, after = before_after(WL)
    assert diff.compute(None, after, WL) == []


def test_no_changes_when_identical():
    before, _ = before_after(WL)
    same = copy.deepcopy(before)
    same["news"], same["discovery"] = {}, {}
    assert diff.compute(before, same, WL) == []


def test_sample_week():
    before, after = before_after(WL)
    changes = diff.compute(before, after, WL)
    assert kinds(changes) == ["field", "news", "stage_change", "trial_results", "trial_status"]
    stage = next(c for c in changes if c.kind == "stage_change")
    # the new Phase 3 trial is folded into the stage change, not reported twice
    assert "EXAMPLE-3" in stage.what and stage.url.endswith("NCT90000010")
    assert all(c.url for c in changes), "every item must link to a source"
    assert changes[0].kind == "stage_change"  # biggest news first


def test_halt_is_reported_even_for_phase1():
    before, after = before_after(WL)
    before["trials"]["NCT1"] = _trial("NCT1", "verve102", ["PHASE1"], "RECRUITING", 1)
    after["trials"]["NCT1"] = _trial("NCT1", "verve102", ["PHASE1"], "SUSPENDED", 1)
    halted = [c for c in diff.compute(before, after, WL) if c.kind == "trial_halted"]
    assert len(halted) == 1 and halted[0].what == "VERVE-102's early-stage trial was paused."


def test_phase1_noise_is_ignored():
    before, after = before_after(WL)
    after["trials"]["NCT2"] = _trial("NCT2", "verve102", ["PHASE1"], "RECRUITING", 1)
    assert not [c for c in diff.compute(before, after, WL) if "NCT2" in c.id]


def test_new_phase2_trial_reported():
    before, after = before_after(WL)
    after["trials"]["NCT3"] = _trial("NCT3", "verve102", ["PHASE2"], "NOT_YET_RECRUITING", 2)  # still in testing
    new = [c for c in diff.compute(before, after, WL) if c.kind == "trial_new"]
    assert len(new) == 1 and new[0].what == "A new mid-stage trial of VERVE-102 was registered, run by Example Pharma." and new[0].url.endswith("NCT3")


def test_fda_approval_suppresses_duplicate_stage_change():
    before, after = before_after(WL)
    after["fda"]["verve102"] = {"approved": True, "brand": "Example", "date": "2026-11-01",
                                    "url": "https://fda.example/1"}
    after["drugs"]["verve102"] = {"stage": "approved", "basis": "FDA", "url": "https://fda.example/1"}
    lar = [c for c in diff.compute(before, after, WL) if c.drug == "verve102"]
    assert [c.kind for c in lar if c.kind in ("fda_approval", "stage_change")] == ["fda_approval"]


def test_seen_news_not_repeated():
    before, after = before_after(WL)
    before["news_seen"] = ["news-aaaaaaaaaaaa"]
    assert "news" not in kinds(diff.compute(before, after, WL))


def test_new_drug_on_watchlist_is_baseline():
    before, after = before_after(WL)
    del before["drugs"]["alirocumab"]
    after["trials"]["NCT4"] = _trial("NCT4", "alirocumab", ["PHASE3"], "RECRUITING", 3)
    new = [c for c in diff.compute(before, after, WL) if c.drug == "alirocumab"]
    # its trials are a baseline; only its news from the last week comes through
    assert new and all(c.kind == "news" for c in new)
    for n in after["news"].values():
        if n["drug"] == "alirocumab":
            n["published"] = "2026-10-01T09:00:00+00:00"   # older than a week: treated as seen
    assert not [c for c in diff.compute(before, after, WL) if c.drug == "alirocumab"]


def test_new_drug_news_is_capped():
    before, after = before_after(WL)
    del before["drugs"]["alirocumab"]
    base = next(n for n in after["news"].values() if n["drug"] == "alirocumab")
    for i in range(5):
        after["news"][f"news-x{i}"] = {**base, "id": f"news-x{i}", "title": f"t{i}"}
    assert len([c for c in diff.compute(before, after, WL) if c.drug == "alirocumab"]) == diff.NEW_DRUG_NEWS_MAX


def test_discovery_skips_seen_and_watched():
    before, after = before_after(WL)
    t = _trial("NCT5", None, ["PHASE2"], "RECRUITING", 2)
    t["interventions"] = ["XYZ-123"]
    after["discovery"] = {"NCT5": t, "NCT90000002": dict(t, nct="NCT90000002")}
    disc = [c for c in diff.compute(before, after, WL) if c.kind == "discovery"]
    assert [c.id for c in disc] == ["disc-NCT5"] and "XYZ-123" in disc[0].what
    before["discovery_seen"] = ["NCT5"]
    assert not [c for c in diff.compute(before, after, WL) if c.kind == "discovery"]


def test_resolve_stage_uses_highest_evidence():
    drug = {"id": "x", "stage": "phase1", "sources": ["https://w"]}
    trials = {"N1": {"drug": "x", "phase_rank": 2, "status": "RECRUITING", "nct": "N1", "url": "u1"},
              "N2": {"drug": "x", "phase_rank": 3, "status": "WITHDRAWN", "nct": "N2", "url": "u2"},
              "N3": {"drug": "x", "phase_rank": 4, "status": "RECRUITING", "nct": "N3", "url": "u3"}}
    assert snapshot.resolve_stage(drug, trials, {})["stage"] == "phase2"
    assert snapshot.resolve_stage(drug, trials, {"approved": True, "url": "f"})["stage"] == "approved"
    assert snapshot.resolve_stage(dict(drug, stage="filed"), trials, {})["stage"] == "filed"


def test_watching_for_uses_milestones_only():
    _, after = before_after(WL)
    heart = {d["id"] for d in WL["drugs"] if d.get("topic", "heart") == "heart"}
    h = [i for i in diff.horizon(after, WL, today=date(2026, 11, 3)) if i.drug_id in heart]
    # only the hand-picked milestone trial in the data; routine trial dates (NCT90000004 etc.) are left out
    assert [(i.drug, i.when) for i in h] == [("Leqvio", "DUE NOW")]  # ORION-4 was due Oct 2026
    assert "heart-attack prevention trial (ORION-4)" in h[0].what
    leqvio = lambda today: next(i for i in diff.horizon(after, WL, today=today) if i.drug == "Leqvio")
    assert leqvio(date(2026, 9, 1)).when == "OCT 2026"
    after["trials"]["NCT03705234"]["status"] = "COMPLETED"
    assert leqvio(date(2026, 11, 3)).when == "Finished"


def test_milestone_with_a_label_and_a_date():
    _, after = before_after(WL)
    h = {i.drug_id: i for i in diff.horizon(after, WL, today=date(2026, 11, 3))}
    assert h["retatrutide"].when == "EARLY 2027" and h["ivonescimab"].when == "14 NOV 2026"
    assert diff.horizon(after, WL, today=date(2026, 11, 3))[-1].when != "EARLY 2027"  # sorted by its date

def test_finalize_marks_seen():
    _, after = before_after(WL)
    after["discovery"] = {"NCT9": {}}
    out = snapshot.finalize(after)
    assert "news-aaaaaaaaaaaa" in out["news_seen"] and "NCT9" in out["discovery_seen"]
    assert "news" not in out and "discovery" not in out


def test_source_down_on_first_run_does_not_flood_next_week():
    before, after = before_after(WL)
    # last week CT.gov and openFDA never succeeded for evolocumab, and news was down
    others = [d["id"] for d in WL["drugs"] if d["id"] != "evolocumab"]
    before["baselined"] = {"ctgov": others, "fda": others, "news": False, "discovery": True}
    after["trials"]["NCT6"] = _trial("NCT6", "evolocumab", ["PHASE3"], "RECRUITING", 3)
    after["fda"]["evolocumab"] = {"approved": True, "url": "u"}
    changes = diff.compute(before, after, WL)
    assert not [c for c in changes if c.drug == "evolocumab" and c.kind != "stage_change"]
    assert "news" not in kinds(changes)


def test_stage_change_needs_baselined_evidence():
    before, after = before_after(WL)
    others = [d["id"] for d in WL["drugs"] if d["id"] != "verve102"]
    before["baselined"] = {"ctgov": others, "fda": others, "news": True, "discovery": True}
    assert "stage_change" not in kinds(diff.compute(before, after, WL))


def test_horizon_date_format():
    assert diff.fmt_horizon_date("2026-11") == "NOV 2026"
    assert diff.fmt_horizon_date("2027-01-04") == "4 JAN 2027"
    assert diff.fmt_horizon_date("soon") == "soon"


def test_field_news_reported_once_and_only_after_baseline():
    before, after = before_after(WL)
    field = [c for c in diff.compute(before, after, WL) if c.kind == "field"]
    assert [c.id for c in field] == ["news-bbbbbbbbbbbb"] and field[0].drug is None
    before["field_seen"] = ["news-bbbbbbbbbbbb"]
    assert not [c for c in diff.compute(before, after, WL) if c.kind == "field"]
    # a snapshot from before field news existed: this week is the baseline
    before["field_seen"] = []
    before["baselined"] = {"ctgov": [d["id"] for d in WL["drugs"]], "fda": [d["id"] for d in WL["drugs"]],
                           "news": True, "discovery": True}
    assert not [c for c in diff.compute(before, after, WL) if c.kind == "field"]


def test_approved_drugs_only_report_watched_trials():
    before, after = before_after(WL)
    approved = {"stage": "approved", "basis": "watchlist", "url": "u"}
    before["drugs"]["evolocumab"] = after["drugs"]["evolocumab"] = approved
    # a routine Repatha trial changes status and posts results: not reported
    before["trials"]["NCT7"] = _trial("NCT7", "evolocumab", ["PHASE3"], "RECRUITING", 3)
    after["trials"]["NCT7"] = dict(_trial("NCT7", "evolocumab", ["PHASE3"], "TERMINATED", 3), has_results=True)
    # new routine trials: Phase 2 skipped, Phase 3 reported
    after["trials"]["NCT8"] = _trial("NCT8", "evolocumab", ["PHASE2"], "RECRUITING", 2)
    after["trials"]["NCT9"] = _trial("NCT9", "evolocumab", ["PHASE3"], "RECRUITING", 3)
    # the watched Leqvio trial (ORION-4) still reports
    after["trials"]["NCT03705234"] = dict(after["trials"]["NCT03705234"], status="COMPLETED")
    ids = {c.id for c in diff.compute(before, after, WL)}
    assert not {i for i in ids if "NCT7" in i or "NCT8" in i}
    assert "new-NCT9" in ids and "status-NCT03705234-COMPLETED" in ids


def test_topics_and_companies_load():
    from digest.watchlist import companies_of, topics_by_id
    topics = topics_by_id(WL)
    assert list(topics) == ["heart", "obesity", "alzheimers", "cancer"]
    lilly = [d["id"] for d in WL["drugs"] if "lilly" in companies_of(d, WL)]
    assert "verve102" in lilly and "tirzepatide" in lilly and "semaglutide" not in lilly
