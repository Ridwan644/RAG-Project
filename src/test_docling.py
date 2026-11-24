import sys
from pathlib import Path
from docling.document_converter import DocumentConverter

pdf_path = sys.argv[1]

converter = DocumentConverter()
result = converter.convert(pdf_path)
markdown = result.document.export_to_markdown()

out = Path("data/docling_test") / (Path(pdf_path).stem + ".md")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(markdown)

print(f"Saved {out} ({len(markdown):,} characters)")