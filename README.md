# Cholesterol pipeline digest

A small personal tool. Once a week, GitHub Actions checks ClinicalTrials.gov, openFDA, FDA press announcements, and news searches for the drugs in `watchlist.yaml`, and compares the results with last week's snapshot. It then emails a short digest of **only what changed**. If nothing changed, the email is one line.

```
watchlist.yaml          drugs, aliases, company, target, form, current stage (a floor)
digest/sources/         ctgov.py · openfda.py · news.py (Google News RSS + extra feeds)
digest/snapshot.py      builds this week's state; a failed source keeps last week's data
digest/diff.py          last week vs this week -> list of changes (each with a source URL)
digest/summarize.py     Claude writes the headline + "why it matters" lines from the diff
digest/render.py        HTML email + plain-text fallback, incl. the pipeline strip
digest/send.py          SMTP (Gmail or Resend)
state/snapshot.json     last week's state, committed back by the workflow
```

## Guardrails, as implemented

- **Nothing can be invented.** Code builds every "what happened" line from source data, and each line carries its source link. Claude only writes the headline and the "why it matters" text, and it can drop news items that aren't real developments. It can't add items, edit facts, or touch links. Without an API key, or if the API call fails, a plain fallback summary is used.
- **Web content is data.** Claude sees only the diff (titles and short snippets), and the prompt marks that content as untrusted. Untrusted text is HTML-escaped in the email.
- **Outages don't look like news.** If a source fails, last week's data for it is kept and the email says what couldn't be reached. A source is only diffed after its first successful fetch, so a bad first run can't later flood you with "new" trials.
- Secrets live in GitHub Actions secrets only.

## Commands

```bash
pip install -r requirements-dev.txt
python -m pytest -q                   # tests use fake before/after data, no network
python -m digest preview              # dummy data -> out/preview.html (to review the look)
python -m digest fetch                # hit the real sources, print what was found
python -m digest run --dry-run        # full run, writes out/digest.html, sends nothing, saves nothing
python -m digest run                  # the weekly job (needs the env vars below)
```

## Setup

1. Push this repo to GitHub.
2. Add repository secrets (Settings → Secrets and variables → Actions):
   - `ANTHROPIC_API_KEY`: optional. Without it, the "why it matters" lines fall back to each drug's `plain` description.
   - Email via **Gmail**: `SMTP_USER` = your Gmail address, `SMTP_PASSWORD` = a Gmail [app password](https://myaccount.google.com/apppasswords) (2-step verification required), `DIGEST_TO` = where to send it.
   - Or via **Resend**: `SMTP_HOST=smtp.resend.com`, `SMTP_USER=resend`, `SMTP_PASSWORD` = Resend API key, `DIGEST_FROM` = an address on your verified domain, `DIGEST_TO`.
3. Actions → *Weekly digest* → *Run workflow* with mode **dry-run**, then download the `digest-N` artifact to check the output. Run it again with **send** to get the first (baseline) email and save the first snapshot.
4. After that, it runs Mondays at 12:23 UTC. To change the time, edit the `cron` line in `.github/workflows/weekly-digest.yml`.

The first sent email is a baseline: it shows the pipeline strip and what's coming up, with no "what moved" section. Change reporting starts the following week.

## Maintaining the watchlist

- To add a drug, add an entry with `id`, `name`, `aliases` (code names and brand names), `company`, `stage`, and ideally `form`, `target`, `plain`, `sources`. Its first week is treated as a baseline.
- `stage` is a floor. The digest takes the highest of the floor, the highest phase on ClinicalTrials.gov, and an FDA approval found on openFDA. Set it by hand for things the APIs can't see: `filed`, or an approval outside the US. (Hand edits aren't reported as changes.)
- `events:` takes dated items you know about, such as a PDUFA date, each with a source URL. They show up under "On the horizon" when they're inside the window.
- `feeds:` takes extra RSS feeds, scanned for any watchlist drug name.

## Cost

GitHub Actions is free for this usage. The Claude call sends one small request per week (only when something changed), costing a few cents at most. Set `DIGEST_MODEL` to use a different model.
