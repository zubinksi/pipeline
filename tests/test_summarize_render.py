import json
from datetime import date
from types import SimpleNamespace

from digest import diff, render, summarize
from digest.sample import before_after
from digest.send import build_message
from digest.watchlist import load

WL = load("watchlist.yaml")


class FakeClient:
    """Stands in for anthropic.Anthropic(); returns a canned structured response."""

    def __init__(self, payload, stop_reason="end_turn"):
        self.calls = []
        msg = SimpleNamespace(stop_reason=stop_reason,
                              content=[SimpleNamespace(type="text", text=json.dumps(payload))])
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: (self.calls.append(kw), msg)[1]))


def _changes():
    before, after = before_after(WL)
    return diff.compute(before, after, WL), after


def test_llm_can_drop_news_but_not_facts():
    changes, _ = _changes()
    payload = {"headline": "One Lp(a) drug reached Phase 3.",
               "items": [{"id": c.id, "include": False, "why": "x"} for c in changes]
               + [{"id": "invented", "include": True, "why": "made up"}]}
    client = FakeClient(payload)
    headline, kept = summarize.summarize(changes, WL, client=client)
    assert headline == "One Lp(a) drug reached Phase 3."
    assert "news" not in [c.kind for c in kept]                 # news dropped
    assert len(kept) == len(changes) - 2                        # facts kept despite include=false
    assert "field" not in [c.kind for c in kept]                # field news dropped too
    assert all(c.id != "invented" for c in kept)                # can't add items
    # structured output + server-side refusal fallback are requested
    kw = client.calls[0]
    assert kw["output_config"]["format"]["type"] == "json_schema" and kw["fallbacks"] == "default"


def test_llm_why_lines_used_and_untrusted_text_is_only_data():
    changes, _ = _changes()
    payload = {"headline": "h", "items": [{"id": c.id, "include": True, "why": f"why {c.id}"} for c in changes]}
    _, kept = summarize.summarize(changes, WL, client=FakeClient(payload))
    assert all(c.why == f"why {c.id}" for c in kept)


def test_refusal_or_error_falls_back():
    changes, _ = _changes()
    headline, kept = summarize.summarize(changes, WL, client=FakeClient({}, stop_reason="refusal"))
    assert headline == "3 updates this week."  # smaller updates are dropped
    assert all(c.why for c in kept if c.kind != "field")  # field news gets no stock "why"


def test_all_news_dropped_means_nothing_changed():
    before, after = before_after(WL)
    before["drugs"], before["trials"] = after["drugs"], after["trials"]  # only the news items differ
    changes = diff.compute(before, after, WL)
    assert sorted(c.kind for c in changes) == ["field", "news"]
    payload = {"headline": "h", "items": [{"id": c.id, "include": False, "why": ""} for c in changes]}
    headline, kept = summarize.summarize(changes, WL, client=FakeClient(payload))
    assert kept == []
    d = render.render(headline=headline, changes=kept, horizon=[], snapshot=after, watchlist=WL,
                      today=date(2026, 11, 3))
    assert d.text.strip().count("\n") == 0 and "Nothing changed" in d.text


def test_render_full_digest():
    changes, after = _changes()
    headline, changes = summarize.apply_fallback(changes, {d["id"]: d for d in WL["drugs"]})
    d = render.render(headline=headline, changes=changes,
                      horizon=diff.horizon(after, WL, today=date(2026, 11, 3)),
                      snapshot=after, watchlist=WL, today=date(2026, 11, 3))
    for section in ("WHAT MOVED", "WATCHING FOR", "THE DRUGS", "AVAILABLE NOW", "GETTING CLOSE"):
        assert section in d.text
    assert "▲ moved" in d.text and "&#9650; MOVED" in d.html
    for c in changes:
        if c.tier != "more":
            assert c.url.replace("&", "&amp;") in d.html
    assert "not medical advice" in d.text


def test_html_escapes_untrusted_titles():
    changes, after = _changes()
    changes[-1].what = "<script>alert(1)</script>"
    d = render.render(headline="h", changes=changes, horizon=[], snapshot=after, watchlist=WL,
                      today=date(2026, 11, 3))
    assert "<script>" not in d.html


def test_nothing_changed_mentions_errors():
    _, after = _changes()
    after["errors"] = ["openFDA"]
    d = render.render(headline="", changes=[], horizon=[], snapshot=after, watchlist=WL,
                      today=date(2026, 11, 3))
    assert "Couldn't reach: openFDA" in d.text


def test_baseline_email():
    _, after = _changes()
    d = render.render(headline="", changes=[], horizon=[], snapshot=after, watchlist=WL,
                      baseline=True, today=date(2026, 11, 3))
    assert "Tracking started" in d.text and "THE DRUGS" in d.text and "prevents heart attacks" in d.text


def test_email_message_has_both_parts():
    _, after = _changes()
    d = render.render(headline="", changes=[], horizon=[], snapshot=after, watchlist=WL,
                      baseline=True, today=date(2026, 11, 3))
    msg = build_message(d, "a@example.com", "b@example.com")
    types = [p.get_content_type() for p in msg.iter_parts()]
    assert types == ["text/plain", "text/html"]


def test_field_news_without_claude_is_screened_and_capped():
    from digest.diff import Change
    field = [Change(id=f"f{i}", kind="field", drug=None, what=t, url="u", source="s") for i, t in enumerate([
        "New PCSK9 shot meets primary endpoint in Phase 3 trial",
        "5 foods that lower cholesterol naturally",
        "FDA approves new cholesterol drug",
        "Cholesterol drug Phase 3 trial results announced",
        "Statin maker stock jumps",
    ])]
    headline, kept = summarize.apply_fallback(field, {}, WL, screen_field=True)
    assert [c.id for c in kept] == ["f0", "f2", "f3"]  # diet and stock stories dropped; at most 3
    assert all(c.why == "" for c in kept)


def test_field_news_needs_claudes_yes():
    changes, _ = _changes()
    payload = {"headline": "h", "items": [{"id": c.id, "include": True, "why": "w"}
                                          for c in changes if c.kind != "field"]}
    _, kept = summarize.summarize(changes, WL, client=FakeClient(payload))
    assert "field" not in [c.kind for c in kept]


def test_field_section_in_site_and_email(tmp_path):
    changes, after = _changes()
    headline, changes = summarize.apply_fallback(changes, {d["id"]: d for d in WL["drugs"]})
    for c in changes:
        if c.kind == "field":
            c.tier = "top"  # as Claude would mark a strong field story
    d = render.render(headline=headline, changes=changes, horizon=[], snapshot=after, watchlist=WL,
                      today=date(2026, 11, 3))
    assert "In the field" in d.html and "IN THE FIELD" in d.text and "Example Wire" in d.html
    from digest import history, site
    rec = history.record(day=date(2026, 11, 3), headline=headline, changes=changes, horizon=[],
                         snapshot=after, baseline=False)
    out = site.build(tmp_path / "s", weeks=[rec], snapshot=after, watchlist=WL)
    html = (out / "index.html").read_text()
    assert "In the field" in html and "PCSK9 shot meets primary endpoint" in html


def test_lead_paragraph_flows_to_email_history_and_site(tmp_path):
    from digest import history, site
    changes, after = _changes()
    payload = {"headline": "h", "lead": "Leqvio's big trial is due; a new Lp(a) trial started.",
               "items": [{"id": c.id, "include": True, "why": "w"} for c in changes]}
    headline, lead, kept = summarize.summarize_full(changes, WL, client=FakeClient(payload))
    assert lead.startswith("Leqvio's big trial")
    assert "lead" in summarize.SCHEMA["required"]
    d = render.render(headline=headline, lead=lead, changes=kept, horizon=[], snapshot=after, watchlist=WL)
    assert lead.replace("'", "&#39;") in d.html or lead in d.html
    assert lead in d.text
    rec = history.record(day=date(2026, 11, 16), headline=headline, lead=lead, changes=kept, horizon=[],
                         snapshot=after, baseline=False)
    out = site.build(tmp_path / "site", weeks=[rec], snapshot=after, watchlist=WL)
    assert 'class="w-lead"' in (out / "index.html").read_text()
    # without Claude there's no lead
    _, no_lead, _ = summarize.summarize_full(changes, WL, client=FakeClient({}, stop_reason="refusal"))
    assert no_lead == ""


def test_daily_runs_build_the_week_and_monday_closes_it(tmp_path):
    from digest import week, site
    from digest.__main__ import _current_view
    changes, after = _changes()
    payload = {"headline": "h", "lead": "", "items": [{"id": c.id, "include": True, "why": "w"} for c in changes]}
    _, _, kept = summarize.summarize_full(changes, WL, client=FakeClient(payload))
    wk = week.new(date(2026, 11, 10))
    week.add(wk, kept[:2], "2026-11-11T13:07:00+00:00", [])
    week.add(wk, kept, "2026-11-12T13:07:00+00:00", [])          # repeats are skipped
    assert len(wk["changes"]) == len(kept)
    assert [c["found"][:10] for c in wk["changes"][:3]] == ["2026-11-11", "2026-11-11", "2026-11-12"]
    p = tmp_path / "week.json"; week.save(wk, p); wk = week.load(p)
    # the site shows the week in progress, each item with the day it was found
    cur = _current_view(wk, after, WL)
    out = site.build(tmp_path / "site", weeks=[], snapshot=after, watchlist=WL, current=cur)
    news = (out / "index.html").read_text()
    assert "This week so far" in news and "Wed 11 Nov" in news and 'data-found="2026-11-12' in news
    assert (out / "assets/newmark.js").exists()
    # Monday: the whole week, nothing dropped, the daily why lines kept, plus a lead
    close = {"headline": "Week", "lead": "A lead.", "items": [{"id": c["id"], "include": False, "why": "x"} for c in wk["changes"]]}
    headline, lead, all_ = summarize.summarize_full(week.changes(wk), WL, client=FakeClient(close), keep_all=True)
    assert lead == "A lead." and len(all_) == len(kept) and all(c.why == "w" for c in all_)


def test_without_claude_drug_news_must_look_like_a_development():
    from digest.diff import Change
    mk = lambda i, t: Change(id=i, kind="news", drug="evolocumab", what=t, url="u", source="s")
    news = [mk("a", "Repatha Market Forecast to 2030: Analysis of Market Size"),
            mk("b", "Evolocumab Cuts First-Stroke Risk in 8-Year Data"),
            mk("c", "Novo Nordisk partners with a DJ for Wegovy campaign")]
    _, kept = summarize.apply_fallback(news, {d["id"]: d for d in WL["drugs"]}, WL, screen_field=True)
    assert [c.id for c in kept] == ["b"]


def test_top_stories_and_smaller_updates():
    from digest.diff import Change
    mk = lambda i, t, k="news", d="orforglipron": Change(id=i, kind=k, drug=d, what=t, url="u", source="s")
    items = [
        mk("a", "Lilly's Foundayo cuts sleep apnea severity 44% in Phase 3 trial published in JAMA"),
        mk("b", "Foundayo cuts sleep apnea severity by 44% in Phase 3 trial, published in JAMA"),  # same story
        mk("c", "Orforglipron market size forecast to 2032"),                                        # noise
        mk("d", "Real-world study looks at Foundayo adherence"),
        mk("e", "VERVE-102's mid-stage trial (HEART-3) started enrolling patients.", "trial_status", "verve102"),
    ]
    _, _, kept = summarize.summarize_full(items, WL, client=FakeClient({}, stop_reason="refusal"))
    assert [c.id for c in kept] == ["a", "e"]  # noise, the repeat and the smaller update are gone
    assert {c.id: c.tier for c in kept} == {"a": "top", "e": "top"}  # a mid-stage trial starting is top
    # with Claude: its tier and same_as decide
    payload = {"headline": "h", "lead": "", "items": [
        {"id": "a", "include": True, "tier": "top", "same_as": "", "why": "w"},
        {"id": "d", "include": True, "tier": "top", "same_as": "a", "why": "w"},
        {"id": "e", "include": True, "tier": "top", "same_as": "", "why": "w"}]}
    _, _, kept = summarize.summarize_full(items, WL, client=FakeClient(payload))
    assert [(c.id, c.tier) for c in kept] == [("a", "top"), ("e", "top")]
    assert "tier" in summarize.SCHEMA["properties"]["items"]["items"]["required"]


def test_smaller_updates_never_reach_the_site_or_email(tmp_path):
    from digest import history, site
    changes, after = _changes()
    for c in changes:
        c.tier = "more" if c.kind == "news" else "top"
    rec = history.record(day=date(2026, 11, 16), headline="h", changes=changes, horizon=[],
                         snapshot=after, baseline=False)
    news = (site.build(tmp_path / "s", weeks=[rec], snapshot=after, watchlist=WL) / "index.html").read_text()
    assert "Example headline: alirocumab trial expands" not in news and "Smaller updates" not in news
    d = render.render(headline="h", changes=changes, horizon=[], snapshot=after, watchlist=WL)
    assert "Example headline: alirocumab" not in d.html and "Smaller updates" not in d.html
