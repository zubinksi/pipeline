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
    assert len(halted) == 1 and "suspended" in halted[0].what


def test_phase1_noise_is_ignored():
    before, after = before_after(WL)
    after["trials"]["NCT2"] = _trial("NCT2", "verve102", ["PHASE1"], "RECRUITING", 1)
    assert not [c for c in diff.compute(before, after, WL) if "NCT2" in c.id]


def test_new_phase2_trial_reported():
    before, after = before_after(WL)
    after["trials"]["NCT3"] = _trial("NCT3", "alirocumab", ["PHASE2"], "NOT_YET_RECRUITING", 2)
    new = [c for c in diff.compute(before, after, WL) if c.kind == "trial_new"]
    assert len(new) == 1 and "NCT3" in new[0].what


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
    assert not [c for c in diff.compute(before, after, WL) if c.drug == "alirocumab"]


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
    h = diff.horizon(after, WL, today=date(2026, 11, 3))
    # only the hand-picked milestone trial in the data; routine trial dates (NCT90000004 etc.) are left out
    assert [(i.drug, i.when) for i in h] == [("Leqvio", "DUE NOW")]  # ORION-4 was due Oct 2026
    assert "heart-attack prevention trial (ORION-4)" in h[0].what
    assert diff.horizon(after, WL, today=date(2026, 9, 1))[0].when == "OCT 2026"
    after["trials"]["NCT03705234"]["status"] = "COMPLETED"
    assert diff.horizon(after, WL, today=date(2026, 11, 3))[0].when == "Finished"

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
