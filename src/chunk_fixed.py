"""
BASELINE CHUNKER: fixed-size chunks with overlap.

What it does:
  Reads every parsed document in data/parsed/*.json (HTML and PDF, same shape)
  and cuts each one into chunks of CHUNK_WORDS words. Each chunk repeats the
  last OVERLAP_WORDS words of the previous one, so text cut at an edge still
  appears whole in at least one chunk.

How it works (per document):
  1. Flatten: turn all blocks (headings, text, tables) into one long list of
     words. Every word remembers which block it came from, so we know its
     section, heading and page.
  2. Slide a window: take words [0:250], then [200:450], then [400:650]...
     (each step = CHUNK_WORDS - OVERLAP_WORDS = 200 words).
  3. Label: each chunk copies the document's labels (doc type, period,
     source URL) and the section/heading of its FIRST word, plus every page
     it touches (PDFs only).

This chunker is deliberately "dumb": it ignores structure, so it can cut a
table in half or mix two sections. That's the point. It's the baseline we
measure the smarter chunkers against.

Output: data/chunks/fixed.jsonl (one chunk per line, as JSON)

Usage:
  python src/chunk_fixed.py
"""

import json
from pathlib import Path

PARSED_DIR = Path("data/parsed")
OUT_FILE = Path("data/chunks/fixed.jsonl")

CHUNK_WORDS = 250    # ~330 tokens; fits the embedding model's 512-token limit
OVERLAP_WORDS = 50   # words repeated from the end of the previous chunk

# Document-level labels copied onto every chunk (needed for filtering + citations)
DOC_FIELDS = ["doc_id", "company", "format", "doc_type", "period_label",
              "period_end", "filed", "source_url"]


def block_text(block):
    """A block as plain text. Tables become their rows joined together."""
    if block["type"] == "table":
        return "\n".join(block["rows"])
    return block["text"]

#turn the document in one long list of words 
#each word remembers whic hblock it came form 
#we remember to the blcok so we can look up the page and section later 
#without it the labels wuld be lost 
def flatten(blocks):
    """All blocks -> one list of (word, block_index) pairs."""
    words = []
    for i, block in enumerate(blocks):
        for word in block_text(block).split():
            words.append((word, i))
    return words


def chunk_document(doc):
    blocks = doc["blocks"]
    words = flatten(blocks)
    step = CHUNK_WORDS - OVERLAP_WORDS

    chunks = []
    start = 0
    while start < len(words):
        window = words[start:start + CHUNK_WORDS]
        first_block = blocks[window[0][1]]
        pages = sorted({blocks[i]["page"] for _, i in window if blocks[i].get("page")})

        chunk = {
            "chunk_id": f"{doc['doc_id']}#fixed-{len(chunks):04d}",
            "strategy": "fixed",
            **{field: doc.get(field) for field in DOC_FIELDS},
            "section": first_block.get("section"),
            "heading": first_block.get("heading"),
            "pages": pages,
            "n_words": len(window),
            "text": " ".join(word for word, _ in window),
        }
        chunks.append(chunk)

        if start + CHUNK_WORDS >= len(words):  # this window reached the end
            break
        start += step

    return chunks


def main():
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    total = 0

    with OUT_FILE.open("w") as out:
        for path in sorted(PARSED_DIR.glob("*.json")):
            doc = json.loads(path.read_text())
            chunks = chunk_document(doc)
            for chunk in chunks:
                out.write(json.dumps(chunk) + "\n")
            total += len(chunks)
            print(f"  {doc['doc_id']:<32} {len(chunks):>5} chunks")

    print(f"\nDone. {total} chunks saved to {OUT_FILE}")


if __name__ == "__main__":
    main()
