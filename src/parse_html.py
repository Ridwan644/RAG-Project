"""
Step 3a: Parse SEC HTML filings into clean, structured JSON.

Pipeline (one function per station):
  1. load_clean_soup()  - open the file, delete the hidden XBRL section
  2. walk_blocks()      - go through the document in order: headings, text, tables
  3. clean_table()      - turn messy table rows into 'Label | value | value'
  4. drop_noise()       - remove page numbers, nav lines, underscores, table of contents
  5. save()             - write data/parsed/<doc>.json + a readable preview .md

Run:  python src/parse_html.py
"""
import json
import re
import warnings
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

RAW_DIR = Path("data/raw/CVS")
OUT_DIR = Path("data/parsed")
MANIFEST = Path("data/manifest.json")


# ---------------------------------------------------------------- station 1
def load_clean_soup(path):
    """Open an SEC filing and remove the hidden section at the top."""
    with open(path, encoding="utf-8", errors="ignore") as f:
        html = f.read()

    soup = BeautifulSoup(html, "lxml")

    hidden_parts = soup.find_all(style=re.compile(r"display:\s*none"))
    for hidden in hidden_parts:
        hidden.decompose()

    return soup


# ---------------------------------------------------------------- station 2
BLOCK_TAGS = ["div", "p", "table"]


def is_heading(element, text):
    """Guess whether a piece of text is a heading: short, no period, all bold."""
    if len(text) > 120 or text.endswith("."):
        return False

    spans = [s for s in element.find_all(["span", "font"]) if s.get_text(strip=True)]
    if not spans:
        return False

    return all(
        re.search(r"font-weight:\s*(700|bold)", s.get("style", ""))
        for s in spans
    )


def walk_blocks(element):
    """Go through the document in order, yielding headings, text and tables."""
    for child in element.children:
        if not isinstance(child, Tag):
            continue

        if child.name == "table":
            yield {"type": "table", "element": child}

        elif child.find(BLOCK_TAGS):
            yield from walk_blocks(child)

        elif child.name in ("div", "p"):
            text = child.get_text(" ", strip=True).replace("\xa0", " ")
            if text:
                kind = "heading" if is_heading(child, text) else "text"
                yield {"type": kind, "text": text}


# ---------------------------------------------------------------- station 3
def clean_table(table):
    """Turn a messy HTML table into clean rows like 'Total revenues | 108,399 | 102,871'."""
    rows = []

    for tr in table.find_all("tr"):
        cells = []

        for td in tr.find_all(["td", "th"]):
            text = td.get_text(" ", strip=True).replace("\xa0", " ")
            text = re.sub(r"\(\s+", "(", text)
            text = re.sub(r"\s+\)", ")", text)

            if text in ("", "$"):
                continue

            if text in (")", "%", ")%") and cells:
                cells[-1] += text
                continue

            cells.append(text)

        if cells:
            rows.append(" | ".join(cells))

    return rows


# ---------------------------------------------------------------- station 4
NAV_LINE = re.compile(r"^(index to .*financial statements|form 10-[kq] table of contents|table of contents)$", re.I)
PAGE_NUMBER = re.compile(r"^(page\s*)?\d{1,3}$", re.I)
JUST_LINES = re.compile(r"^[_\-–—=\s]+$")


def is_table_of_contents(rows):
    """A table of contents is mostly rows ending in a page number, mentioning Items/Pages."""
    if not rows:
        return False
    ends_in_page = sum(bool(re.search(r"\|\s*\d{1,3}$", r)) for r in rows)
    mentions_item = any(re.match(r"^(item|page|part)\b", r, re.I) for r in rows)
    return mentions_item and ends_in_page >= 0.5 * len(rows)


def drop_noise(blocks):
    """Remove page numbers, repeated navigation lines, underscore lines and the table of contents."""
    clean = []
    for b in blocks:
        if b["type"] == "table":
            if not b["rows"] or is_table_of_contents(b["rows"]):
                continue
        else:
            t = b["text"]
            if PAGE_NUMBER.match(t) or JUST_LINES.match(t) or NAV_LINE.match(t):
                continue
            if t.startswith("Indicate by check mark"):
                continue
        clean.append(b)
    return clean


# ---------------------------------------------------------------- labels
QUARTER_WORDS = {"FIRST": 1, "SECOND": 2, "THIRD": 3, "FOURTH": 4}


def fiscal_label(meta, blocks):
    """A human label for the period, e.g. 'FY2025', 'Q3 2026'."""
    form = meta["form"]
    if form == "10-K":
        return "FY" + meta["period"][:4]
    if form == "10-Q":
        year, month = int(meta["period"][:4]), int(meta["period"][5:7])
        return f"Q{(month - 1) // 3 + 1} {year}"
    # earnings release: read the headline, e.g. "REPORTS THIRD QUARTER 2026 RESULTS"
    for b in blocks[:15]:
        if b["type"] != "table":
            m = re.search(r"(FIRST|SECOND|THIRD|FOURTH) QUARTER(?: AND FULL-YEAR)? (\d{4})", b["text"].upper())
            if m:
                return f"Q{QUARTER_WORDS[m.group(1)]} {m.group(2)}"
    return meta["period"]


def add_sections(blocks):
    """Tag every block with the section it sits in: the latest 'Item ...' heading and the nearest heading."""
    item, heading = None, None
    for b in blocks:
        if b["type"] == "heading":
            heading = b["text"]
            if re.match(r"^item\s+\d+[a-c]?\.", b["text"], re.I):
                item = b["text"]
        b["section"] = item
        b["heading"] = heading
    return blocks


# ---------------------------------------------------------------- station 5
def to_markdown(doc):
    """A readable preview so a human can spot-check the output."""
    lines = [f"# {doc['doc_id']}", f"{doc['doc_type']} | {doc['period_label']} | {doc['source_url']}", ""]
    for b in doc["blocks"]:
        if b["type"] == "heading":
            lines += ["", f"## {b['text']}"]
        elif b["type"] == "text":
            lines.append(b["text"])
        else:
            lines += ["", "```"] + b["rows"] + ["```", ""]
    return "\n".join(lines)


def save(doc):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "preview").mkdir(exist_ok=True)
    (OUT_DIR / f"{doc['doc_id']}.json").write_text(json.dumps(doc, indent=1))
    (OUT_DIR / "preview" / f"{doc['doc_id']}.md").write_text(to_markdown(doc))


# ---------------------------------------------------------------- run all
DOC_TYPES = {"10-K": "10-K", "10-Q": "10-Q", "8-K earnings": "earnings_release"}


def parse_file(path, meta):
    soup = load_clean_soup(path)

    blocks = []
    for b in walk_blocks(soup.body):
        if b["type"] != "table":
            blocks.append(b)
            continue
        rows = clean_table(b["element"])
        # Some "tables" are just layout boxes holding paragraphs (one cell per row).
        # Those are really text, so treat each row as a text block.
        if rows and all(" | " not in r for r in rows):
            blocks += [{"type": "text", "text": r} for r in rows]
        else:
            blocks.append({"type": "table", "rows": rows})

    blocks = add_sections(drop_noise(blocks))

    return {
        "doc_id": path.stem,
        "company": "CVS Health",
        "format": "html",
        "doc_type": DOC_TYPES[meta["form"]],
        "period_label": fiscal_label(meta, blocks),
        "period_end": meta["period"],
        "filed": meta["filed"],
        "source_url": meta["url"],
        "source_file": str(path),
        "blocks": blocks,
    }


def main():
    manifest = {m["path"]: m for m in json.loads(MANIFEST.read_text())}

    for path in sorted(RAW_DIR.glob("*.htm")):
        meta = manifest.get(str(path))
        if meta is None:
            print(f"  ! skipping {path.name} (not in manifest)")
            continue
        doc = parse_file(path, meta)
        save(doc)
        counts = Counter(b["type"] for b in doc["blocks"])
        print(f"  + {path.name:32} {doc['period_label']:8} "
              f"{counts['heading']:4} headings {counts['text']:5} text {counts['table']:4} tables")

    print(f"\nDone. Output in {OUT_DIR}/ (open the .md files in {OUT_DIR}/preview/ to spot-check)")


if __name__ == "__main__":
    main()
