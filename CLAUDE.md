# CLAUDE.md — CVS Financial Filings RAG (fin-rag)

## Who I am and how to work with me
- I'm Ridwan, a CS student (UT Dallas) building this project to **learn RAG deeply** and to show it to recruiters for AI backend roles.
- **Act as a senior AI engineer teaching a student.** Explain the concept first (plain language, an analogy), then show code, then explain what each part does.
- **Do NOT create, edit, overwrite or delete any file unless I explicitly say so.** Show me the code and the commands; I run them. Ask before any change.
- Keep explanations short and plain. I push back when answers are too long or jargon-heavy.
- When I need to create files/folders or run something, give me the exact terminal commands (I'm practicing the terminal).
- For plumbing (e.g. parsing), focus on the principles and decisions. Go deep, line by line, on the RAG parts: chunking, embeddings, search, reranking, citations, evaluation.

## What the project is
An AI research assistant for **CVS Health's finances**. A user asks a question (e.g. "What was Aetna's revenue in Q2 2026?"); the system:
1. Searches ~35 real CVS documents (SEC filings as HTML + PDFs) with **hybrid search** (keyword + vector)
2. Reranks the results with a cross-encoder
3. Has Claude answer **only from the retrieved passages**, citing each claim (document, period, section/page)
4. Does any math in **Python**, never in the LLM
5. Says "not in the documents" when evidence is missing
6. Is **graded by an eval set** of ~40 hand-written questions; numbers are checked automatically against the SEC's official XBRL data

The differentiator vs. typical student RAG projects: **measured results** (e.g. "hybrid + reranking raised Recall@5 from X% to Y%").

## Tech stack
| Piece | Tool |
|---|---|
| Language | Python (venv at `.venv`) |
| Downloading | requests + SEC EDGAR APIs (done) |
| HTML parsing | BeautifulSoup + lxml |
| PDF parsing | **Docling** (IBM, open source, layout + TableFormer table models) — currently being tested to replace a hand-built PyMuPDF parser |
| Database | **PostgreSQL + pgvector** in Docker (chosen over OpenSearch: I already know Postgres; pgvector is the common default for <10M vectors) |
| Keyword search | Postgres full-text search, plus `rank_bm25` (true BM25) as a comparison experiment |
| Vector search | pgvector |
| Embeddings | sentence-transformers (open-source BGE model) |
| Reranker | Cross-encoder (BGE reranker) |
| Query rewriting | a small, fast Claude model |
| Answers | Claude via the Anthropic API |
| API / UI | FastAPI / Streamlit |
| Evaluation | own Python scripts (Ragas optional) |
| Framework | **None on purpose** — build each piece by hand to understand it |

## Roadmap (current status)
1. ✅ Get the documents
2. ✅ Learn to read an income statement (revenue, operating income, net income; traps: two "net income" lines, three- vs nine-month columns, GAAP vs adjusted)
3. 🔄 **Parsing** ← WE ARE HERE
   - 3a HTML: ✅ done (`src/parse_html.py` → `data/parsed/*.json` + `data/parsed/preview/*.md`)
   - 3b PDF: a hand-built PyMuPDF parser exists (`src/parse_pdf.py`) but was too complex to learn from and fails on borderless tables. **Now testing Docling** with `src/test_docling.py` (output goes to `data/docling_test/`).
4. ⬜ Chunking — fixed-size, overlapping, and by section; every chunk carries labels (doc type, period, section/page, source URL)
5. ⬜ Write ~40 test questions with known answers BEFORE building search. Types: exact lookup, calculation, right period, segment, GAAP vs adjusted, text, multi-hop, unanswerable
6. ⬜ Set up Postgres + pgvector, load chunks + embeddings
7. ⬜ Keyword + vector search, measured separately (Recall@5, MRR)
8. ⬜ Hybrid (Reciprocal Rank Fusion) + cross-encoder reranking, measured
9. ⬜ Query rewriting, measured with vs. without
10. ⬜ Answers with citations + Python math + Streamlit page + README results table

## Folder layout (project root: ~/Desktop/PC/fin-rag)
```
data/
  raw/CVS/                  21 SEC HTML filings (.htm)
  raw/CVS_pdf/decks/        11 earnings slide decks: CVS_deck_2024Q1.pdf ... CVS_deck_2026Q3.pdf
  raw/CVS_pdf/reports/      CVS_proxy_2026.pdf, CVS_impact_appendix_2025.pdf, CVS_factsheet_2026Q1.pdf
  answer_key/CVS_facts.json SEC XBRL "company facts" — answer key for eval only, NEVER searched
  manifest.json             every downloaded SEC file: form, period, filed date, source URL, path
  excluded/                 3 files set aside (see Data notes)
  parsed/                   parsed JSON per document + preview/*.md
  docling_test/             Docling test output
src/
  download_filings.py       SEC EDGAR downloader (CVS only; needs USER_AGENT with my name + email)
  parse_html.py             HTML parser (stations: load_clean_soup, walk_blocks, clean_table, drop_noise, save)
  parse_pdf.py              hand-built PDF parser (likely to be replaced by Docling)
  test_docling.py           Docling test: python src/test_docling.py <pdf path>
```

## The documents
- **10-K** (yearly): FY2023, FY2024, FY2025 — full financial statements, segments, risks, management's discussion (MD&A)
- **10-Q** (quarterly): Q1–Q3 2025, Q1–Q3 2026 — note: columns are "three months ended" AND "nine months ended"
- **Earnings releases** (8-K Exhibit 99.1): 12 quarters, Q4 2023 – Q3 2026 — headline results, GAAP + adjusted, guidance
- **Earnings decks** (PDF): Q1 2024 – Q3 2026 — slides, numbers in big fonts
- **Proxy 2026** (PDF, 144 pages): executive pay (Summary Compensation Table), board, shareholder proposals
- **Impact report appendix 2025** (PDF): non-financial data, Healthy 2030 goals
- **Fact sheet** (PDF, Feb 2026): stock price, market cap, dividend

CVS has 3 segments: **Health Care Benefits** (= Aetna, insurance), **Health Services** (= Caremark, pharmacy benefits, clinics), **Pharmacy & Consumer Wellness** (= the stores).

## Data notes / known issues
- Excluded: `CVS_earnings_2024-01-05.htm` (leadership announcement, not earnings), `CVS_earnings_2024-10-18.htm` (CEO change + PRELIMINARY Q3 2024 numbers that conflict with the final ones — maybe re-add later as a "preliminary vs final" test), `CVS_impact_appendix_2024.pdf` (was a 404 error page, not a PDF).
- FY2025 (in millions): total revenues 402,067; operating income 4,660; net income 1,728; **net income attributable to CVS Health 1,768** (the XBRL answer key uses `NetIncomeLoss` = the 1,768 figure).
- Q3 2025 had a 5,725M goodwill impairment → GAAP operating loss (3,207) vs adjusted operating income +3,459.
- PDF table problem: in the proxy's Summary Compensation Table (borderless), the hand-built parser lost column positions (e.g. J. David Joyner's 2024 row has 6 values for 8 columns). **The Docling test is checking whether this is fixed.**

## Next action
Finish the Docling test: run `python src/test_docling.py data/raw/CVS_pdf/reports/CVS_proxy_2026.pdf`, then
`grep -n -A 12 "J. David Joyner" data/docling_test/CVS_proxy_2026.md | head -40` and check whether the pay table keeps its columns. Then decide: Docling vs. the hand-built parser for PDFs, and move on to step 4 (chunking).
