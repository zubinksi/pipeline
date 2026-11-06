from datetime import date

from digest import diff, history, render, site
from digest.sample import before_after
from digest.summarize import apply_fallback
from digest.watchlist import load

WL = load("watchlist.yaml")


def _build(tmp_path, mutate=None):
    before, after = before_after(WL)
    changes = diff.compute(before, after, WL)
    headline, changes = apply_fallback(changes, {d["id"]: d for d in WL["drugs"]})
    if mutate:
        mutate(changes)
    weeks = [
        history.record(day=date(2026, 11, 3), headline=headline, changes=changes,
                       horizon=diff.horizon(after, WL, today=date(2026, 11, 3)), snapshot=after, baseline=False),
        history.record(day=date(2026, 10, 27), headline=render.baseline_headline(before, WL), changes=[],
                       horizon=[], snapshot=before, baseline=True),
    ]
    return site.build(tmp_path / "site", weeks=weeks, snapshot=after, watchlist=WL), changes


def test_site_pages_exist(tmp_path):
    out, _ = _build(tmp_path)
    assert (out / "index.html").exists() and (out / "weeks/index.html").exists()
    assert (out / "weeks/2026-11-03.html").exists() and (out / "weeks/2026-10-27.html").exists()
    for d in WL["drugs"]:
        assert (out / f"drugs/{d['id']}.html").exists()


def test_index_shows_latest_week_and_sources(tmp_path):
    out, changes = _build(tmp_path)
    html = (out / "index.html").read_text()
    assert "What moved" in html and "On the horizon" in html and "Recent weeks" in html
    for c in changes:
        assert c.url in html
    assert 'href="drugs/zerlasiran.html"' in html  # relative links work on any host


def test_drug_page_has_updates_history_and_trials(tmp_path):
    out, _ = _build(tmp_path)
    html = (out / "drugs/zerlasiran.html").read_text()
    assert "moved from Phase 2 to Phase 3" in html          # update
    assert "Stage history" in html                           # phase 2 -> phase 3 across weeks
    assert "NCT90000010" in html                             # trial table
    assert 'href="../weeks/2026-11-03.html"' in html


def test_week_pages_link_to_each_other(tmp_path):
    out, _ = _build(tmp_path)
    assert 'href="2026-10-27.html"' in (out / "weeks/2026-11-03.html").read_text()
    assert 'href="2026-11-03.html"' in (out / "weeks/2026-10-27.html").read_text()


def test_untrusted_text_is_escaped(tmp_path):
    def evil(changes):
        changes[-1].what = "<script>alert(1)</script>"
    out, _ = _build(tmp_path, evil)
    assert "<script>alert" not in (out / "index.html").read_text()


def test_empty_site_builds(tmp_path):
    out = site.build(tmp_path / "s", weeks=[], snapshot={"drugs": {}, "trials": {}}, watchlist=WL)
    assert "No weekly runs yet" in (out / "index.html").read_text()
