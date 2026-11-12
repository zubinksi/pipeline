"""CLI.

  python -m digest fetch            # fetch all sources and print what was found
  python -m digest preview          # dummy data -> out/preview.html + out/site/
  python -m digest site             # rebuild site/ from history/ + state (no fetching)
  python -m digest daily            # the daily job: fetch, diff, filter, add to the week in progress, build site
  python -m digest run              # the weekly close (Mondays): the daily step, then the week's lead,
                                    #   email, history record, and a fresh week
  python -m digest run --no-send    # same, but only write out/digest.html / .txt
  python -m digest run --dry-run    # don't send and don't save state
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from . import STAGE_LABEL, diff, history, render, site, snapshot, summarize, week, watchlist as wl
from .sources.ctgov import phase_label


def _write(out: Path, name: str, d: render.Digest) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.html").write_text(d.html)
    (out / f"{name}.txt").write_text(d.text)
    print(f"Subject: {d.subject}\nWrote {out / name}.html and .txt")


def cmd_fetch(args) -> int:
    w = wl.load(args.watchlist)
    snap = snapshot.build(w, snapshot.load(args.state))
    for d in w["drugs"]:
        s = snap["drugs"][d["id"]]
        print(f"\n== {d['name']} ({d['company']}) — {STAGE_LABEL[s['stage']]} [basis: {s['basis']}]")
        for t in sorted((t for t in snap["trials"].values() if t["drug"] == d["id"]),
                        key=lambda t: -t["phase_rank"]):
            print(f"   {t['nct']}  {phase_label(t['phases']):<16} {t['status']:<24} "
                  f"PCD {t['primary_completion'] or '?':<10} {'RESULTS ' if t['has_results'] else ''}"
                  f"{(t['acronym'] or t['title'])[:60]}")
        f = snap["fda"].get(d["id"], {})
        if f.get("approved"):
            print(f"   FDA: {f.get('application')} {f.get('brand')} approved {f.get('date')}")
        for n in (n for n in snap["news"].values() if n["drug"] == d["id"]):
            print(f"   news: {n['published'][:10]} {n['title'][:90]} ({n['outlet']})")
    if snap["discovery"]:
        print("\n== New industry Phase 2/3 trials in watched conditions")
        for t in snap["discovery"].values():
            print(f"   {t['nct']} {', '.join(t.get('interventions', []))[:60]} — {t['sponsor']}")
    if snap["errors"]:
        print("\nErrors:", ", ".join(snap["errors"]))
    return 0


def cmd_preview(args) -> int:
    """Dummy data: an email preview plus a two-week site in out/site/."""
    from .sample import before_after
    w = wl.load(args.watchlist)
    before, after = before_after(w)
    wk1, wk2 = date(2026, 10, 27), date(2026, 11, 3)
    changes = diff.compute(before, after, w)
    headline, changes = summarize.summarize(changes, w)
    horizon = diff.horizon(after, w, today=wk2)
    d = render.render(headline=headline, changes=changes, horizon=horizon,
                      snapshot=after, watchlist=w, today=wk2)
    _write(Path(args.out), "preview", d)
    weeks = [
        history.record(day=wk2, headline=headline, changes=changes, horizon=horizon,
                       snapshot=after, baseline=False),
        history.record(day=wk1, headline=render.baseline_headline(before, w), changes=[],
                       horizon=diff.horizon(before, w, today=wk1), snapshot=before, baseline=True),
    ]
    out = site.build(Path(args.out) / "site", weeks=weeks, snapshot=after, watchlist=w)
    print(f"Wrote {out}/index.html")
    return 0


def _daily_step(args, w: dict) -> tuple[dict, dict, bool]:
    """Fetch, diff against the last run, filter and summarise what's new, and add it to
    the week in progress. Returns (snapshot, week, first_run)."""
    prev = snapshot.load(args.state)
    curr = snapshot.build(w, prev)
    wk = week.load(args.week) or week.new(date.today())
    if prev is None:  # the very first run is a baseline
        return curr, wk, True
    changes = diff.compute(prev, curr, w)
    _, _, kept = summarize.summarize_full(changes, w)
    week.add(wk, kept, curr["generated_at"], curr.get("errors", []))
    return curr, wk, False


def _current_view(wk: dict, curr: dict, w: dict) -> dict:
    """The week in progress, shaped like a history record for the site."""
    changes = week.changes(wk)
    return history.record(day=date.today(), headline=summarize.fallback_headline(changes) if changes else "",
                          changes=changes, horizon=diff.horizon(curr, w), snapshot=curr,
                          baseline=False) | {"in_progress": True, "started": wk.get("started", "")}


def cmd_daily(args) -> int:
    w = wl.load(args.watchlist)
    curr, wk, first = _daily_step(args, w)
    weeks = history.load_all(args.history)
    site.build(args.site, weeks=weeks, snapshot=curr, watchlist=w,
               current=None if first or not wk["changes"] else _current_view(wk, curr, w))
    print(f"Week so far: {len(wk['changes'])} items. Built site in {args.site}/")
    if not args.dry_run:
        snapshot.save(snapshot.finalize(curr), args.state)
        week.save(wk, args.week)
    return 0


def cmd_run(args) -> int:
    """The weekly close: today's daily step, then the whole week becomes one record."""
    w = wl.load(args.watchlist)
    curr, wk, baseline = _daily_step(args, w)
    changes = week.changes(wk)
    headline, lead, changes = summarize.summarize_full(changes, w, keep_all=True)
    horizon = diff.horizon(curr, w)
    d = render.render(headline=headline, lead=lead, changes=changes, horizon=horizon,
                      snapshot=curr, watchlist=w, baseline=baseline)
    _write(Path(args.out), "digest", d)

    rec = history.record(day=date.today(), lead=lead, changes=changes, horizon=horizon, snapshot=curr,
                         baseline=baseline,
                         headline=render.baseline_headline(curr, w) if baseline else headline)
    weeks = history.load_all(args.history)
    weeks = [rec] + [x for x in weeks if x["date"] != rec["date"]]
    site.build(args.site, weeks=weeks, snapshot=curr, watchlist=w)
    print(f"Built site in {args.site}/")

    from . import send as mail
    if args.no_send or args.dry_run:
        pass
    elif mail.configured():
        mail.send(d)
        print("Email sent.")
    else:
        print("Email not configured (SMTP_USER / SMTP_PASSWORD / DIGEST_TO); skipped.")
    if not args.dry_run:  # only after a successful send
        history.save(rec, args.history)
        snapshot.save(snapshot.finalize(curr), args.state)
        week.save(week.new(date.today()), args.week)
        print(f"Saved {args.state} and {args.history}/{rec['date']}.json; started a new week")
    return 0


def cmd_site(args) -> int:
    """Rebuild the site from saved history + state (no fetching)."""
    w = wl.load(args.watchlist)
    snap = snapshot.load(args.state) or {"drugs": {}, "trials": {}}
    wk = week.load(args.week)
    # until the new week has something in it, the home page shows the last closed week
    current = _current_view(wk, snap, w) if wk and wk.get("changes") and snap.get("generated_at") else None
    out = site.build(args.site, weeks=history.load_all(args.history), snapshot=snap, watchlist=w, current=current)
    print(f"Wrote {out}/index.html")
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="digest")
    p.add_argument("--watchlist", default="watchlist.yaml")
    p.add_argument("--state", default="state/snapshot.json")
    p.add_argument("--out", default="out")
    p.add_argument("--history", default="history")
    p.add_argument("--site", default="site")
    p.add_argument("--week", default="state/week.json")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch").set_defaults(fn=cmd_fetch)
    sub.add_parser("preview").set_defaults(fn=cmd_preview)
    sub.add_parser("site").set_defaults(fn=cmd_site)
    dly = sub.add_parser("daily")
    dly.add_argument("--dry-run", action="store_true")
    dly.set_defaults(fn=cmd_daily)
    r = sub.add_parser("run")
    r.add_argument("--no-send", action="store_true")
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(fn=cmd_run)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
