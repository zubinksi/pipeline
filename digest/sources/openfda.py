"""openFDA Drugs@FDA fetcher: detects US NDA/BLA approvals."""
from __future__ import annotations

import httpx

URL = "https://api.fda.gov/drug/drugsfda.json"


def _fmt(d: str) -> str:
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d


def parse(results: list[dict], terms: list[str]) -> dict:
    lowered = [t.lower() for t in terms]
    best = None
    for res in results:
        appl = res.get("application_number", "")
        if not appl.startswith(("NDA", "BLA")):
            continue
        names = " ".join(
            [*res.get("openfda", {}).get("generic_name", []), *res.get("openfda", {}).get("brand_name", [])]
            + [p.get("brand_name", "") for p in res.get("products", [])]
            + [i.get("name", "") for p in res.get("products", []) for i in p.get("active_ingredients", [])]
        ).lower()
        if not any(t in names for t in lowered):
            continue
        orig = [s for s in res.get("submissions", [])
                if s.get("submission_type") == "ORIG" and s.get("submission_status") == "AP"]
        if not orig:
            continue
        brand = next((p.get("brand_name") for p in res.get("products", []) if p.get("brand_name")), "")
        rec = {
            "approved": True,
            "application": appl,
            "brand": brand.title() if brand.isupper() else brand,
            "date": _fmt(min(s.get("submission_status_date", "") for s in orig)),
            "url": "https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm"
                   f"?event=overview.process&ApplNo={appl[3:]}",
        }
        if best is None or rec["date"] < best["date"]:
            best = rec
    return best or {"approved": False}


def fetch_approval(client: httpx.Client, terms: list[str]) -> dict:
    fields = ("openfda.generic_name", "openfda.brand_name", "products.brand_name",
              "products.active_ingredients.name")
    search = " ".join(f'{f}:"{t}"' for f in fields for t in terms)
    r = client.get(URL, params={"search": search, "limit": 20})
    if r.status_code == 404:  # openFDA's "no matches"
        return {"approved": False}
    r.raise_for_status()
    return parse(r.json().get("results", []), terms)
