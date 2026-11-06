# Cholesterol pipeline digest

A small personal tool. Once a week, GitHub Actions checks ClinicalTrials.gov, openFDA, FDA press announcements, and news searches for the drugs in `watchlist.yaml`, and compares the results with last week's snapshot. It then:

- updates a **static site** (this week, past weeks, and a page per drug with its updates, stage history and trials), committed to `site/` and deployed by Vercel, and
- optionally **emails** a short digest of only what changed. If nothing changed, the email is one line.

```
watchlist.yaml          drugs, aliases, company, target, form, current stage (a floor)
digest/sources/         ctgov.py · openfda.py · news.py (Google News RSS + extra feeds)
digest/snapshot.py      builds this week's state; a failed source keeps last week's data
digest/diff.py          last week vs this week -> list of changes (each with a source URL)
digest/summarize.py     Claude writes the headline + "why it matters" lines from the diff
digest/render.py        HTML email + plain-text fallback, incl. the pipeline strip
digest/site.py          static site (templates in digest/templates/site/, CSS/fonts in digest/static/)
digest/send.py          SMTP (Gmail or Resend), skipped if not configured
state/snapshot.json     last week's state, committed back by the workflow
history/*.json          one record per week, the site's archive
site/                   the built site; Vercel serves this folder
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
python -m digest preview              # dummy data -> out/preview.html + out/site/ (to review the look)
python -m digest site                 # rebuild site/ from history/ + state, no fetching
python -m digest fetch                # hit the real sources, print what was found
python -m digest run --dry-run        # full run, writes out/digest.html, sends nothing, saves nothing
python -m digest run                  # the weekly job (needs the env vars below)
```

## Setup

1. **Site on Vercel:** in Vercel choose *Add New → Project*, then import `zubinksi/pipeline` with the default settings (Root Directory left at the repo root). `vercel.json` tells Vercel to serve the prebuilt `site/` folder as static files, with no Python and no build step. Every commit the workflow makes then deploys automatically. The production branch is the repo's default branch.
2. **Secrets** (GitHub → Settings → Secrets and variables → Actions). All are optional:
   - `ANTHROPIC_API_KEY`: without it, the "why it matters" lines fall back to each drug's `plain` description.
   - `SITE_URL`: your Vercel URL. The email then links to the site.
   - `READER_CONTEXT`: overrides `reader_context` in `watchlist.yaml`, so your personal details don't have to sit in a public repo.
   - Email via **Gmail**: `SMTP_USER` (your address), `SMTP_PASSWORD` (a Gmail [app password](https://myaccount.google.com/apppasswords)), `DIGEST_TO`. Via **Resend**: `SMTP_HOST=smtp.resend.com`, `SMTP_USER=resend`, `SMTP_PASSWORD` (API key), `DIGEST_FROM` (an address on your verified domain), `DIGEST_TO`. With no email secrets set, the run just updates the site.
3. **First run:** go to Actions → *Weekly digest* → *Run workflow*. Mode **dry-run** builds everything and saves nothing (download the `digest-N` artifact to look). Mode **send** saves the baseline and publishes the site.
4. After that it runs Mondays at 12:23 UTC. To change the time, edit the `cron` line in `.github/workflows/weekly-digest.yml`. Editing `watchlist.yaml` or the site templates triggers *Rebuild site*, which redeploys without fetching anything.

The site is public, though pages ask search engines not to index them. The first week is a baseline: the pipeline strip and what's coming up. Change reporting starts the following week.

## Design

Dark slate with cool neutral tones and a faint graph-paper grid. Fonts are Geist Serif and Geist Mono (SIL Open Font License, see `digest/static/fonts/OFL.txt`). Colors are set at the top of `digest/static/site.css`. You can filter the pipeline on the home page by how each drug is taken and how often, using the `route` and `frequency` fields in `watchlist.yaml`. The filter is kept in the URL (e.g. `?type=pill&freq=daily`), so a filtered view can be bookmarked.

## Maintaining the watchlist

- To add a drug, add an entry with `id`, `name`, `aliases` (code names and brand names), `company`, `stage`, `route` (pill / injection / infusion), `frequency` (daily / monthly / infrequent / once), and ideally `form`, `target`, `plain`, `sources`. Its first week is treated as a baseline.
- `stage` is a floor. The digest takes the highest of the floor, the highest phase on ClinicalTrials.gov, and an FDA approval found on openFDA. Set it by hand for things the APIs can't see: `filed`, or an approval outside the US. (Hand edits aren't reported as changes.)
- `events:` takes dated items you know about, such as a PDUFA date, each with a source URL. They show up under "On the horizon" when they're inside the window.
- `feeds:` takes extra RSS feeds, scanned for any watchlist drug name.

## Cost

GitHub Actions is free for this usage. The Claude call sends one small request per week (only when something changed), costing a few cents at most. Set `DIGEST_MODEL` to use a different model.
