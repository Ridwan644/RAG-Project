"""
Parse PDFs (earnings decks + reports) with Docling into the SAME JSON shape
that parse_html.py produces, so the chunker reads one format.

Usage:
  python src/parse_pdf_docling.py                  # every PDF in data/raw/CVS_pdf
  python src/parse_pdf_docling.py <pdf path>       # just one PDF
"""

import json
import re
import sys
from pathlib import Path

from docling.document_converter import DocumentConverter

PDF_DIR = Path("data/raw/CVS_pdf")
OUT_DIR = Path("data/parsed")

KNOWN_URLS = {
    "CVS_proxy_2026": "https://s206.q4cdn.com/752775519/files/doc_financials/2025/ar/2026-Proxy-Statement.pdf",
    "CVS_impact_appendix_2025": "https://www.cvshealth.com/content/dam/enterprise/cvs-enterprise/images/impact-2026/pdfs/2025_Impact_Report_Appendix.pdf",
    "CVS_factsheet_2026Q1": "https://s206.q4cdn.com/752775519/files/doc_downloads/2026/CVS_Q4_FactSheet.pdf",
}

# Docling label -> our block type. Anything NOT listed (pictures, page headers/footers) is skipped.
LABEL_TO_TYPE = {
    "title": "heading",
    "section_header": "heading",
    "text": "text",
    "paragraph": "text",
    "list_item": "text",
    "caption": "text",
    "footnote": "text",
    "table": "table",
}

# Slide footer/logo text that Docling labels as normal text
JUNK_STARTS = ("©", "CVSHealth")
JUNK_CONTAINS = ("affiliates. Confidential",)


def is_junk(text):
    t = text.strip()
    return len(t) < 2 or t.startswith(JUNK_STARTS) or any(j in t for j in JUNK_CONTAINS)


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


def table_rows(item, doc):
    """A Docling table -> list of lines like 'Revenue | 102.9 | 95.4' (header first)."""
    df = item.export_to_dataframe(doc=doc).fillna("")
    rows = [" | ".join(str(c).strip() for c in df.columns)]
    for _, row in df.iterrows():
        rows.append(" | ".join(str(v).strip() for v in row))
    return rows


def parse(pdf_path, converter):
    doc = converter.convert(str(pdf_path)).document
    doc_type, period_label = describe(pdf_path.stem)

    blocks = []
    heading = None  # the most recent heading we've walked past

    for item, _level in doc.iterate_items():
        kind = LABEL_TO_TYPE.get(item.label.value)
        if kind is None:
            continue
        page = item.prov[0].page_no if item.prov else None

        if kind == "table":
            rows = table_rows(item, doc)
            if len(rows) > 1:  # skip empty tables (header only)
                blocks.append({"type": "table", "rows": rows, "page": page,
                               "section": heading, "heading": heading})
            continue

        text = item.text.strip()
        if is_junk(text):
            continue
        if kind == "heading":
            heading = text
        blocks.append({"type": kind, "text": text, "page": page,
                       "section": heading, "heading": heading})

    return {
        "doc_id": pdf_path.stem,
        "company": "CVS Health",
        "format": "pdf",
        "doc_type": doc_type,
        "period_label": period_label,
        "period_end": None,
        "filed": None,
        "source_url": KNOWN_URLS.get(pdf_path.stem, "https://investors.cvshealth.com/"),
        "source_file": str(pdf_path),
        "pages": len(doc.pages),
        "blocks": blocks,
    }


def main():
    pdfs = [Path(p) for p in sys.argv[1:]] or sorted(PDF_DIR.rglob("*.pdf"))
    converter = DocumentConverter()  # loads the AI models once; reused for every PDF
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for pdf in pdfs:
        out = OUT_DIR / f"{pdf.stem}.json"
        if out.exists():
            print(f"  = already have {out} (delete it to re-parse)")
            continue
        data = parse(pdf, converter)
        out.write_text(json.dumps(data, indent=2))
        types = [b["type"] for b in data["blocks"]]
        print(f"  + {out}  pages={data['pages']}  headings={types.count('heading')}  "
              f"text={types.count('text')}  tables={types.count('table')}")


if __name__ == "__main__":
    main()
