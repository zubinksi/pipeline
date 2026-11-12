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
    assert "Readout" in (out / "index.html").read_text() and "Your panel" in (out / "index.html").read_text()
    assert "No weekly runs yet" in (out / "weeks/index.html").read_text()


def test_pipeline_rows_carry_filter_data(tmp_path):
    out, _ = _build(tmp_path)
    html = (out / "drugs.html").read_text()
    assert "data-filter" in html and 'data-k="lowers"' not in html  # LDL vs Lp(a) is chosen on Your panel
    assert 'data-k="tp" data-v="cancer"' in html and 'data-k="st" data-v="close"' in html  # topic and stage filters
    assert 'data-tp="heart" data-st="now"' in html
    assert 'data-k="freq" data-v="monthly" aria-pressed="false">Monthly</button>' in html
    assert 'data-v="infrequent"' in html and 'data-v="weekly"' in html
    assert html.count('class="drug"') == len(WL["drugs"])
    for d in WL["drugs"]:
        assert d.get("route") and d.get("proven") and d.get("topic"), d["id"]
    assert 'data-lowers="ldl"' in html
    assert (out / "assets/filter.js").exists() and (out / "assets/site.css").exists()


def test_rows_show_evidence_and_only_unusual_stage_words(tmp_path):
    out, _ = _build(tmp_path)
    html = (out / "drugs.html").read_text()
    assert "Prevents heart attacks" in html and "Heart-attack trial underway" in html
    assert "LDL ↓ 60%" in html and "Twice a year" in html and "Heart attacks?" in html
    now = html[html.index("Available now"):html.index("Getting close")]
    close = html[html.index("Getting close"):html.index("How to read this")]
    assert 'class="mini' not in now                 # all approved: no stage dots
    assert 'class="mini' in close and "Final-stage trials" in close  # dots with a label

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
    assert '<a class="back" href="../drugs.html">&larr; Drugs</a>' in (out / "drugs/inclisiran.html").read_text()


def test_drugs_grouped_by_closeness(tmp_path):
    out, _ = _build(tmp_path)
    html = (out / "drugs.html").read_text()
    html = html[html.index('data-topic-sec="heart"'):html.index('data-topic-sec="obesity"')]
    a, c, f = html.index("Available now"), html.index("Getting close"), html.index("Further out")
    assert a < c < f
    assert html.index("Lerochol") < c < html.index("VERVE-102") < f  # sample moves VERVE-102 to final stage
    assert html.index("Zerlasiran") > f
    cancer = (out / "drugs.html").read_text().split('data-topic-sec="cancer"')[1]
    assert "Further out" not in cancer  # empty groups aren't shown

def test_past_weeks_button_and_back_links(tmp_path):
    out, _ = _build(tmp_path)
    assert 'class="btn" href="weeks/index.html"' in (out / "index.html").read_text()
    assert '<a class="back" href="../index.html">&larr; News</a>' in (out / "weeks/index.html").read_text()
    week = (out / "weeks/2026-11-03.html").read_text()
    assert '<a class="back" href="../index.html">&larr; News</a>' in week
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
    assert 'class="slab tabbed"' in news
    # one page, two panels: each file just opens a different one (tabs.js switches in place)
    assert '<div class="panel" data-panel="news">' in news and '<div class="panel" data-panel="drugs" hidden>' in news
    assert '<div class="panel" data-panel="news" hidden>' in drugs and '<div class="panel" data-panel="drugs">' in drugs
    assert (out / "assets/tabs.js").exists()
    # Coming up: a calendar across topics; each entry links to the drug's overview
    assert '<a class="cal-item first" href="drugs/inclisiran.html" data-drug="inclisiran">' in news and "Any week now" in news
    assert '<span class="pill pill-heart">Heart</span>' in news and '<span class="pill pill-cancer">Cancer</span>' in news
    assert 'data-cal-toggle' not in news
    assert "Heart-attack trial results" in news and "twice-a-year shot proven to prevent them" in news
    assert "Twice a year" not in news[news.index("Coming up"):news.index('data-panel="drugs"')]  # no dosing facts in the list
    assert "no changes" not in news.lower()


def test_drug_page_is_consolidated_for_a_layperson(tmp_path):
    out, _ = _build(tmp_path)
    html = (out / "drugs/inclisiran.html").read_text()
    # under the same header and tabs, with Drugs selected
    assert 'class="slab tabbed"' in html and 'class="folder f-drugs on"' in html
    # stage and sponsor under the name; key results in one strip
    assert "A shot twice a year" in html
    assert '<span class="sponsor">Novartis</span>' in html
    head = html[html.index('class="strip-head"'):html.index('class="strip"')]
    assert "Approved" in head and 'class="mini' not in head  # stage titles the strip, no dots
    strip = html[html.index('class="strip"'):html.index("</dl>")]
    for label in ("LDL reduction", "<dt>Shot</dt>", "CV outcomes"):
        assert label in strip
    assert "↓ 50%" in strip and "Trial underway" in strip and ">Profile<" not in html and "strip-note" not in html
    assert "Upcoming readouts" in html and "twice-a-year shot proven" in html
    assert 'href="https://clinicaltrials.gov/study/NCT03705234"' in html   # drug page links the source
    assert ">Notes<" in html and "At a glance" not in html and "In plain terms" not in html
    assert "Trials and technical details" in html                   # detail tucked away


def test_panel_page_chooses_what_to_follow(tmp_path):
    out, _ = _build(tmp_path)
    news = (out / "index.html").read_text()
    assert '<a class="hcab" href="panel.html">' in news  # the header label opens the panel
    assert 'href="../panel.html"' in (out / "drugs/inclisiran.html").read_text()
    cab = (out / "panel.html").read_text()
    assert 'class="hcab on p-only" aria-current="page"' in cab and "data-panel-form" in cab
    # topics, each with its drugs; a company to follow across topics
    for t in ("heart", "obesity", "alzheimers", "cancer"):
        assert f'data-topic-box="{t}"' in cab
    for d in WL["drugs"]:
        assert f'data-drug-box="{d["id"]}"' in cab
    assert 'data-company-box="lilly"' in cab and "By company" in cab
    assert '"verve102":{"t":"heart","c":["lilly"]}' in news  # each page knows topics and companies
    assert (out / "assets/panel.js").exists() and "assets/panel.js" in news
    # rows carry their drug so untracked ones can be hidden
    assert 'data-drug="evolocumab"' in (out / "drugs.html").read_text()


def test_drugs_page_is_split_by_topic_with_topic_words(tmp_path):
    out, _ = _build(tmp_path)
    html = (out / "drugs.html").read_text()
    order = [html.index(f'data-topic-sec="{t}"') for t in ("heart", "obesity", "alzheimers", "cancer")]
    assert order == sorted(order)
    obesity = html[order[1]:order[2]]
    assert "<span>Weight loss</span>" in obesity and "Zepbound" in obesity and "Heart & cholesterol" not in obesity
    assert "<span>Slows decline?</span>" in html[order[2]:order[3]]
    drug = (out / "drugs/donanemab.html").read_text()
    assert "<dt>Slowing of decline</dt>" in drug and "<dt>Clinical effect</dt>" in drug
    assert "<dt>LDL reduction</dt>" in (out / "drugs/inclisiran.html").read_text()


def test_welcome_lpa_groups_and_sponsor_tag(tmp_path):
    out, _ = _build(tmp_path)
    news, cab = (out / "index.html").read_text(), (out / "panel.html").read_text()
    assert 'location.replace("panel.html?welcome")' in news  # first visit starts with the welcome
    assert "Welcome" in cab and "data-done" in cab and "data-wgo" in cab and 'classList.add("is-welcome")' in cab
    # Heart & cholesterol splits into LDL and Lp(a) in the panel
    assert 'id="g-heart-ldl"' in cab and 'id="g-heart-lpa"' in cab and ">Lp(a)-lowering<" in cab
    lp = (out / "drugs/lepodisiran.html").read_text()
    assert "<dt>Lp(a) reduction</dt>" in lp and '<span class="sponsor">Eli Lilly</span>' in lp


def test_calendar_groups_by_period_with_topics(tmp_path):
    from digest import site as site_mod
    import datetime as dt
    wl = WL
    cal = site_mod.calendar([{"date": "2026-11-14", "when": "14 NOV 2026", "drug": "X", "drug_id": "ivonescimab",
                              "short": "FDA decision", "what": "", "url": "u"}],
                            {d["id"]: d for d in wl["drugs"]}, {t["id"]: t for t in wl["topics"]}, dt.date(2026, 11, 12))
    assert cal[0]["label"] == "NOV 2026" and cal[0]["items"][0]["day"] == "14 NOV" and cal[0]["items"][0]["rel"] == "in 2 days"


def test_drug_page_explains_how_it_works(tmp_path):
    out, _ = _build(tmp_path)
    html = (out / "drugs/inclisiran.html").read_text()
    assert '<details class="more how">' in html and "Silencing the PCSK9 message" in html  # collapsed by default
    assert html.count('class="flow-step') == 4 and 'class="flow-step acts"' in html
    for d in WL["drugs"]:
        assert d.get("approach"), d["id"]  # every drug has a diagram


def test_labs_page_is_private_by_design(tmp_path):
    out, _ = _build(tmp_path)
    html = (out / "labs.html").read_text()
    assert "Stored only in this browser" in html and 'assets/labs.js' in html
    js = (out / "assets/labs.js").read_text()
    assert "localStorage" in js and "fetch(" not in js and "XMLHttpRequest" not in js  # never sent anywhere
    assert 'href="labs.html"' in (out / "panel.html").read_text()
