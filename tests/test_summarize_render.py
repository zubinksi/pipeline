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
    assert headline.startswith("5 updates this week")  # the sample field headline passes the keyword screen
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
    for section in ("WHAT MOVED", "ON THE HORIZON", "THE DRUGS", "AVAILABLE NOW", "GETTING CLOSE"):
        assert section in d.text
    assert "▲ moved" in d.text and "&#9650; MOVED" in d.html
    for c in changes:
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
    d = render.render(headline=headline, changes=changes, horizon=[], snapshot=after, watchlist=WL,
                      today=date(2026, 11, 3))
    assert "In the field" in d.html and "IN THE FIELD" in d.text and "Example Wire" in d.html
    from digest import history, site
    rec = history.record(day=date(2026, 11, 3), headline=headline, changes=changes, horizon=[],
                         snapshot=after, baseline=False)
    out = site.build(tmp_path / "s", weeks=[rec], snapshot=after, watchlist=WL)
    html = (out / "index.html").read_text()
    assert "In the field" in html and "PCSK9 shot meets primary endpoint" in html
