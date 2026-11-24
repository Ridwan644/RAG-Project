"""
Download CVS Health SEC filings for the Financial RAG project.

What it downloads for each company:
  - The 3 most recent 10-Ks (yearly reports: FY2023, FY2024, FY2025)
  - 10-Qs (quarterly reports) filed since Jan 2025
  - 8-K earnings press releases (Item 2.02) filed since Jan 2024
  - The XBRL "company facts" JSON (the answer key for evaluation)

Files are saved to:
  data/raw/<TICKER>/...        <- documents your RAG system will search
  data/answer_key/<TICKER>_facts.json   <- official numbers, used only for evaluation

Usage:
  1. Put your real name and email in .env as SEC_USER_AGENT (the SEC requires it).
  2. From the project folder, run:  python src/download_filings.py
"""

import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# The SEC requires your name and a real email; it's read from .env (never committed)
load_dotenv()
USER_AGENT = os.getenv("SEC_USER_AGENT", "")

TICKERS = ["CVS"]   # add "UNH", "CI", "PFE", "JNJ" later to scale up

NUM_10K = 3                      # most recent yearly reports
TENQ_SINCE = "2025-01-01"        # quarterly reports filed on/after this date
EARNINGS_SINCE = "2024-01-01"    # earnings releases filed on/after this date

RAW_DIR = Path("data/raw")
KEY_DIR = Path("data/answer_key")

HEADERS = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}


def get(url):
    """GET with the required header, a polite pause, and a few retries."""
    for attempt in range(3):
        resp = requests.get(url, headers=HEADERS, timeout=30)
        time.sleep(0.2)  # stay well under the SEC's 10 requests/second limit
        if resp.status_code == 200:
            return resp
        print(f"  ! {url} -> HTTP {resp.status_code} (attempt {attempt + 1})")
        time.sleep(2)
    resp.raise_for_status()


def ticker_to_cik():
    """Map tickers like 'CVS' to the SEC's company ID (CIK)."""
    data = get("https://www.sec.gov/files/company_tickers.json").json()
    return {row["ticker"]: int(row["cik_str"]) for row in data.values()}


def load_filings(cik):
    """Return a list of filings (dicts) for a company, newest first."""
    sub = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()
    blocks = [sub["filings"]["recent"]]

    # "recent" only holds about the last 1,000 filings. Big companies file a lot,
    # so load older pages until we reach back past EARNINGS_SINCE.
    for extra in sub["filings"].get("files", []):
        if min(blocks[-1]["filingDate"]) <= EARNINGS_SINCE:
            break
        blocks.append(get(f"https://data.sec.gov/submissions/{extra['name']}").json())

    filings = []
    for b in blocks:
        for i in range(len(b["form"])):
            filings.append({
                "form": b["form"][i],
                "filingDate": b["filingDate"][i],
                "reportDate": b["reportDate"][i] or b["filingDate"][i],
                "accession": b["accessionNumber"][i],
                "primaryDoc": b["primaryDocument"][i],
                "items": b.get("items", [""] * len(b["form"]))[i] or "",
            })
    return sorted(filings, key=lambda f: f["filingDate"], reverse=True)


def filing_folder_url(cik, accession):
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}"


def find_press_release(cik, accession):
    """In an 8-K, the earnings press release is an attached exhibit (EX-99.1)."""
    index = get(f"{filing_folder_url(cik, accession)}/index.json").json()
    names = [item["name"] for item in index["directory"]["item"]]
    for name in names:
        lower = name.lower()
        if lower.endswith((".htm", ".html")) and ("99" in lower and "ex" in lower):
            return name
    return None


def save(url, path):
    if path.exists():
        print(f"  = already have {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(get(url).content)
    print(f"  + saved {path}")


def main():
    if not USER_AGENT:
        raise SystemExit("Set SEC_USER_AGENT in .env first (your name + real email).")

    ciks = ticker_to_cik()
    manifest = []  # a record of every document we saved (useful later for citations)

    for ticker in TICKERS:
        cik = ciks[ticker]
        print(f"\n{ticker} (CIK {cik})")
        filings = load_filings(cik)

        tenks = [f for f in filings if f["form"] == "10-K"][:NUM_10K]
        tenqs = [f for f in filings if f["form"] == "10-Q" and f["filingDate"] >= TENQ_SINCE]
        earnings = [f for f in filings
                    if f["form"] == "8-K" and "2.02" in f["items"]
                    and f["filingDate"] >= EARNINGS_SINCE]

        for f in tenks + tenqs:
            kind = f["form"].replace("-", "")
            path = RAW_DIR / ticker / f"{ticker}_{kind}_{f['reportDate']}.htm"
            url = f"{filing_folder_url(cik, f['accession'])}/{f['primaryDoc']}"
            save(url, path)
            manifest.append({"ticker": ticker, "form": f["form"], "period": f["reportDate"],
                             "filed": f["filingDate"], "url": url, "path": str(path)})

        for f in earnings:
            doc = find_press_release(cik, f["accession"]) or f["primaryDoc"]
            path = RAW_DIR / ticker / f"{ticker}_earnings_{f['filingDate']}.htm"
            url = f"{filing_folder_url(cik, f['accession'])}/{doc}"
            save(url, path)
            manifest.append({"ticker": ticker, "form": "8-K earnings", "period": f["reportDate"],
                             "filed": f["filingDate"], "url": url, "path": str(path)})

        # Answer key: official tagged numbers (never searched by the RAG system)
        save(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
             KEY_DIR / f"{ticker}_facts.json")

    Path("data").mkdir(exist_ok=True)
    Path("data/manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nDone. {len(manifest)} documents saved. List is in data/manifest.json")


if __name__ == "__main__":
    main()
