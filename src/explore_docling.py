import sys
from docling.document_converter import DocumentConverter

doc = DocumentConverter().convert(sys.argv[1]).document

for item, level in doc.iterate_items():
    page = item.prov[0].page_no if item.prov else None
    text = getattr(item, "text", "")[:60]
    print(page, item.label, "|", text)
