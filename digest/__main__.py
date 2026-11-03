"""CLI.

  python -m digest fetch            # fetch all sources and print what was found
  python -m digest preview          # render a digest from dummy data -> out/preview.html
  python -m digest run              # the weekly job: fetch, diff, summarize, render, send, save
  python -m digest run --no-send    # same, but only write out/digest.html / .txt
  python -m digest run --dry-run    # don't send and don't update state/snapshot.json
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from . import STAGE_LABEL, diff, render, snapshot, summarize, watchlist as wl
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
    from .sample import before_after
    w = wl.load(args.watchlist)
    before, after = before_after(w)
    changes = diff.compute(before, after, w)
    headline, changes = summarize.summarize(changes, w)
    d = render.render(headline=headline, changes=changes,
                      horizon=diff.horizon(after, w, today=date(2026, 11, 3)),
                      snapshot=after, watchlist=w, today=date(2026, 11, 3))
    _write(Path(args.out), "preview", d)
    return 0


def cmd_run(args) -> int:
    w = wl.load(args.watchlist)
    prev = snapshot.load(args.state)
    curr = snapshot.build(w, prev)
    changes = diff.compute(prev, curr, w)
    headline, changes = summarize.summarize(changes, w)
    d = render.render(headline=headline, changes=changes, horizon=diff.horizon(curr, w),
                      snapshot=curr, watchlist=w, baseline=prev is None)
    _write(Path(args.out), "digest", d)
    if not (args.no_send or args.dry_run):
        from .send import send
        send(d)
        print("Email sent.")
    if not args.dry_run:
        snapshot.save(snapshot.finalize(curr), args.state)  # only after a successful send
        print(f"Saved {args.state}")
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="digest")
    p.add_argument("--watchlist", default="watchlist.yaml")
    p.add_argument("--state", default="state/snapshot.json")
    p.add_argument("--out", default="out")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch").set_defaults(fn=cmd_fetch)
    sub.add_parser("preview").set_defaults(fn=cmd_preview)
    r = sub.add_parser("run")
    r.add_argument("--no-send", action="store_true")
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(fn=cmd_run)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
