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
    assert "This week" in html and "Coming up" in html and "In the field" in html
    assert "How to read this" in (out / "drugs.html").read_text()
    for c in changes:
        assert c.url in html
    assert 'href="drugs/verve102.html"' in html  # relative links work on any host


def test_drug_page_has_updates_history_and_trials(tmp_path):
    out, _ = _build(tmp_path)
    html = (out / "drugs/verve102.html").read_text()
    assert "moved from Phase 2 to Phase 3" in html          # update
    assert "Phase 2</dd>" in html and "Phase 3</dd>" in html  # stage history across weeks
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
    assert "Cholesterol Drugs Pipeline" in (out / "index.html").read_text()
    assert "No weekly runs yet" in (out / "weeks/index.html").read_text()


def test_pipeline_rows_carry_filter_data(tmp_path):
    out, _ = _build(tmp_path)
    html = (out / "drugs.html").read_text()
    assert "data-filter" in html and 'data-k="lowers"' not in html  # one option only: no dropdown
    assert '<option value="monthly">Monthly</option>' in html
    assert 'value="daily"' not in html  # filter options only for values on the watchlist
    assert html.count('class="drug"') == len(WL["drugs"])
    for d in WL["drugs"]:
        assert d.get("route") and d.get("frequency") and d.get("proven"), d["id"]
    assert 'data-lowers="ldl"' in html
    assert (out / "assets/filter.js").exists() and (out / "assets/site.css").exists()


def test_rows_show_evidence_and_only_unusual_stage_words(tmp_path):
    out, _ = _build(tmp_path)
    html = (out / "drugs.html").read_text()
    assert "Prevents heart attacks" in html and "Heart-attack trial underway" in html
    assert "LDL ↓ 60%" in html and "Twice a year" in html and "Heart attacks?" in html
    close = html[html.index("Getting close"):html.index("How to read this")]
    assert "Final-stage trials" not in close  # same as the group, so not repeated

def test_watchlist_rejects_unknown_route(tmp_path):
    import pytest, yaml
    data = yaml.safe_load(open("watchlist.yaml"))
    data["drugs"][0]["route"] = "patch"
    p = tmp_path / "w.yaml"
    p.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="route"):
        load(p)


def test_dropped_drugs_and_retired_sources_are_hidden(tmp_path):
    rec = {"date": "2026-11-06", "headline": "h", "baseline": True, "moved": [], "stages": {},
           "changes": [{"id": "x", "kind": "news", "drug": "obicetrapib", "what": "gone", "url": "u", "source": "s", "why": ""}],
           "horizon": [{"date": "2026-11", "drug": "Obicetrapib", "what": "gone", "url": "u", "when": "NOV 2026"},
                       {"date": "2026-12", "drug": "Inclisiran", "what": "kept", "url": "u", "when": "DEC 2026"},
                       {"date": "2026-12", "drug": "Inclisiran", "what": "old-style routine", "url": "u"}],
           "errors": ["FDA press announcements", "openFDA"]}
    out = site.build(tmp_path / "s", weeks=[rec], snapshot={"drugs": {}, "trials": {}}, watchlist=WL)
    html = (out / "weeks/2026-11-06.html").read_text()  # a past week shows what was stored, filtered
    assert "Obicetrapib" not in html and "gone" not in html and "kept" in html and "DEC 2026" in html
    assert "old-style routine" not in html
    assert "FDA press announcements" not in html and "openFDA" in html


def test_drug_page_has_back_link(tmp_path):
    out, _ = _build(tmp_path)
    assert 'class="back" href="../drugs.html"' in (out / "drugs/inclisiran.html").read_text()


def test_drugs_grouped_by_closeness(tmp_path):
    out, _ = _build(tmp_path)
    html = (out / "drugs.html").read_text()
    a, c = html.index("Available now"), html.index("Getting close")  # sample moves VERVE-102 to final stage
    assert a < c and "Further out" not in html  # empty groups aren't shown
    assert html.index("Lerochol") < c  # approved -> available now

def test_past_weeks_button_and_back_links(tmp_path):
    out, _ = _build(tmp_path)
    assert 'class="btn" href="weeks/index.html"' in (out / "index.html").read_text()
    assert 'class="back" href="../index.html"' in (out / "weeks/index.html").read_text()
    week = (out / "weeks/2026-11-03.html").read_text()
    assert 'class="back" href="../weeks/index.html"' in week
    # past weeks sit under the same header and tabs, with News selected
    assert 'class="folder f-news on"' in week and 'class="slab tabbed"' in week
    assert 'class="folder f-news on"' in (out / "weeks/index.html").read_text()


def test_approved_drugs_show_brand_first(tmp_path):
    out, _ = _build(tmp_path)
    html = (out / "drugs.html").read_text()
    assert '<span class="drug-name">Repatha</span><span class="generic">evolocumab</span>' in html
    assert '<span class="drug-name">VERVE-102</span>' in html  # no brand yet: unchanged
    assert "Leqvio" in (out / "drugs/inclisiran.html").read_text()


def test_news_and_drugs_tabs_and_compact_coming_up(tmp_path):
    out, _ = _build(tmp_path)
    news, drugs = (out / "index.html").read_text(), (out / "drugs.html").read_text()
    assert 'class="folder f-news on"' in news and 'class="folder f-drugs on"' in drugs
    assert 'class="slab tabbed"' in news and 'class="slab"' in (out / "drugs/inclisiran.html").read_text()
    # one page, two panels: each file just opens a different one (tabs.js switches in place)
    assert '<div class="panel" data-panel="news">' in news and '<div class="panel" data-panel="drugs" hidden>' in news
    assert '<div class="panel" data-panel="news" hidden>' in drugs and '<div class="panel" data-panel="drugs">' in drugs
    assert (out / "assets/tabs.js").exists()
    # Coming up: a short line that opens to the full sentence, the drug's facts and links
    assert '<details class="tl-item">' in news and "Heart-attack trial results" in news
    more = news[news.index('class="tl-more"'):]
    assert "If positive" in more and "Twice a year" in more and 'href="drugs/inclisiran.html"' in more
    assert "no changes" not in news.lower()
