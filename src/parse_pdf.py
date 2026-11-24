"""
Step 3b: Parse PDFs (earnings decks, proxy, impact report, fact sheet) into the
SAME JSON format as parse_html.py, so the rest of the pipeline doesn't care
which format a document started as.

Differences from HTML:
  - PDFs don't label headings or tables, so we infer them:
      headings = text noticeably bigger than the document's normal font size
      tables   = PyMuPDF's find_tables() (works on ruled tables; slides often have none)
  - Every block keeps its page number, for citations like "Q3 2026 deck, slide 5".
  - Footers repeated on most pages (copyright lines, page numbers) are removed.

Run:  python src/parse_pdf.py
"""
import json
import re
import statistics
from collections import Counter
from pathlib import Path

import pymupdf

PDF_DIR = Path("data/raw/CVS_pdf")
OUT_DIR = Path("data/parsed")

KNOWN_URLS = {
    "CVS_proxy_2026": "https://s206.q4cdn.com/752775519/files/doc_financials/2025/ar/2026-Proxy-Statement.pdf",
    "CVS_impact_appendix_2025": "https://www.cvshealth.com/content/dam/enterprise/cvs-enterprise/images/impact-2026/pdfs/2025_Impact_Report_Appendix.pdf",
    "CVS_factsheet_2026Q1": "https://s206.q4cdn.com/752775519/files/doc_downloads/2026/CVS_Q4_FactSheet.pdf",
}


def describe(stem):
    """Work out document type and period from the filename we gave it."""
    m = re.match(r"CVS_deck_(\d{4})Q(\d)", stem)
    if m:
        return "earnings_deck", f"Q{m.group(2)} {m.group(1)}"
    if stem.startswith("CVS_proxy_"):
        return "proxy_statement", stem[-4:]
    if stem.startswith("CVS_impact_appendix_"):
        return "impact_report", stem[-4:]
    if stem.startswith("CVS_factsheet_"):
        return "fact_sheet", "Feb 2026"
    return "other", ""


def read_lines(page):
    """Every line of text on a page, with its font size and position."""
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = " ".join(s["text"] for s in line["spans"]).strip()
            text = re.sub(r"\s+", " ", text)
            if text:
                size = max(s["size"] for s in line["spans"])
                lines.append({"text": text, "size": size, "bbox": line["bbox"], "block": id(block)})
    return lines


def inside(bbox, boxes):
    x0, y0, x1, y1 = bbox
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in boxes)


def clean_rows(raw_rows):
    rows = []
    for r in raw_rows:
        cells = [re.sub(r"\s+", " ", c or "").strip() for c in r]
        cells = [c for c in cells if c not in ("", "$")]
        if cells:
            rows.append(" | ".join(cells))
    return rows


def parse_pdf(path):
    doc = pymupdf.open(path)
    pages = [read_lines(p) for p in doc]

    # Footers/headers: lines that repeat on at least half the pages (e.g. "©2026 CVS Health ...").
    per_page = Counter(t for lines in pages for t in {l["text"] for l in lines})
    repeated = {t for t, n in per_page.items() if len(doc) >= 4 and n >= 0.5 * len(doc)}

    sizes = [l["size"] for lines in pages for l in lines]
    normal = statistics.median(sizes) if sizes else 10

    blocks = []
    for page_no, (page, lines) in enumerate(zip(doc, pages), start=1):
        table_boxes = []
        try:
            for t in page.find_tables().tables:
                rows = clean_rows(t.extract())
                if len(rows) >= 2 and any(" | " in r for r in rows):
                    table_boxes.append(t.bbox)
                    blocks.append({"type": "table", "rows": rows, "page": page_no})
        except Exception:
            pass

        paragraph, last_block = [], None

        def flush():
            if paragraph:
                blocks.append({"type": "text", "text": " ".join(paragraph), "page": page_no})
                paragraph.clear()

        for l in lines:
            t = l["text"]
            if t in repeated or re.fullmatch(r"\d{1,3}", t) or inside(l["bbox"], table_boxes):
                continue
            if l["size"] >= normal * 1.3 and len(t) <= 120:
                flush()
                blocks.append({"type": "heading", "text": t, "page": page_no})
            else:
                if l["block"] != last_block:
                    flush()
                paragraph.append(t)
            last_block = l["block"]
        flush()

    # nearest heading for every block, same idea as the HTML parser
    heading = None
    for b in blocks:
        if b["type"] == "heading":
            heading = b["text"]
        b["section"] = None
        b["heading"] = heading

    doc_type, period = describe(path.stem)
    return {
        "doc_id": path.stem,
        "company": "CVS Health",
        "format": "pdf",
        "doc_type": doc_type,
        "period_label": period,
        "period_end": None,
        "filed": None,
        "source_url": KNOWN_URLS.get(path.stem, "https://investors.cvshealth.com/"),
        "source_file": str(path),
        "pages": len(doc),
        "blocks": blocks,
    }


def to_markdown(doc):
    lines = [f"# {doc['doc_id']}", f"{doc['doc_type']} | {doc['period_label']} | {doc['source_url']}", ""]
    page = None
    for b in doc["blocks"]:
        if b["page"] != page:
            page = b["page"]
            lines += ["", f"---------- page {page} ----------"]
        if b["type"] == "heading":
            lines += [f"## {b['text']}"]
        elif b["type"] == "text":
            lines.append(b["text"])
        else:
            lines += ["```"] + b["rows"] + ["```"]
    return "\n".join(lines)


def main():
    (OUT_DIR / "preview").mkdir(parents=True, exist_ok=True)
    for path in sorted(PDF_DIR.rglob("*.pdf")):
        doc = parse_pdf(path)
        (OUT_DIR / f"{doc['doc_id']}.json").write_text(json.dumps(doc, indent=1))
        (OUT_DIR / "preview" / f"{doc['doc_id']}.md").write_text(to_markdown(doc))
        c = Counter(b["type"] for b in doc["blocks"])
        print(f"  + {path.name:30} {doc['period_label']:9} {doc['pages']:4} pages "
              f"{c['heading']:4} headings {c['text']:5} text {c['table']:4} tables")
    print(f"\nDone. Output in {OUT_DIR}/")


if __name__ == "__main__":
    main()
