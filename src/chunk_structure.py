"""
STRUCTURE-AWARE CHUNKER: cut documents at their natural edges.

What it does:
  Instead of cutting every 250 words blindly (like chunk_fixed.py), this cuts
  where the document itself has edges:
    1. Decks: one slide = one chunk (a slide is already one topic)
    2. Everything else: blocks under the same heading stay together
    3. Tables are never cut mid-row; a too-big table is split by rows and
       its header row is repeated in every piece

Built in steps:
  Step 1 (this version): group the blocks into slides / sections, print stats
  Step 2: turn each group into text
  Step 3: split groups that are too big
  Step 4: label each chunk and save to data/chunks/structure.jsonl

Usage:
  python src/chunk_structure.py
"""

import json
from pathlib import Path

PARSED_DIR = Path("data/parsed")


def group_blocks(doc):
    """Sort a document's blocks into groups (piles):
    - decks: one group per slide (page)
    - everything else: a new group starts at every heading
    """
    groups = [] #groups is the shelf where finished piles go 
    current = [] #current is the pile in your hands right now 
    
    #a document is a dictionary 
    #its "blocks" is a list of blocks, in order top to bottom 
    #this takes the blocks one at a time, in order. 
    #each time around, block is the next: block 0, then block 1 and so on 
    for block in doc["blocks"]:
        if doc["doc_type"] == "earnings_deck":
            new_group = bool(current) and block.get("page") != current[-1].get("page")
        else:
            new_group = bool(current) and block["type"] == "heading"

        if new_group:
            groups.append(current)
            current = []
        current.append(block)

    if current:
        groups.append(current)
    return groups


def main():
    # Step 1 check: how many groups per document, and how big are they?
    for path in sorted(PARSED_DIR.glob("*.json")):
        doc = json.loads(path.read_text())
        groups = group_blocks(doc)
        sizes = [sum(len((b.get("text") or " ".join(b.get("rows", []))).split()) for b in g)
                 for g in groups]
        print(f"  {doc['doc_id']:<32} {len(groups):>5} groups   "
              f"words per group: min {min(sizes):>4}  max {max(sizes):>5}")


if __name__ == "__main__":
    main()
