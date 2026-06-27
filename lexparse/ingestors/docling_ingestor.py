"""Docling-based document ingestor."""

from __future__ import annotations

from lexparse.ingestors.base import BaseIngestor, BBox, Block, BlockType

_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".epub"}

_LABEL_MAP = {
    "section_header": BlockType.HEADING,
    "title": BlockType.HEADING,
    "paragraph": BlockType.PARAGRAPH,
    "text": BlockType.PARAGRAPH,
    "list_item": BlockType.LIST_ITEM,
    "table": BlockType.TABLE,
    "page_break": BlockType.PAGE_BREAK,
}


class DoclingIngestor(BaseIngestor):
    def __init__(self) -> None:
        try:
            from docling.document_converter import DocumentConverter
        except ImportError:
            raise ImportError(
                "Docling is required for DoclingIngestor. "
                'Install it with: pip install "lexparse[docling]"'
            )
        self._converter = DocumentConverter()

    def supports(self, file_path: str) -> bool:
        return any(file_path.lower().endswith(ext) for ext in _SUPPORTED_EXTENSIONS)

    def ingest(self, file_path: str) -> list[Block]:
        result = self._converter.convert(file_path)
        doc = result.document
        blocks: list[Block] = []

        for item, level in doc.iterate_items(doc.body):
            label = str(getattr(item, "label", "unknown")).lower()
            block_type = _LABEL_MAP.get(label, BlockType.UNKNOWN)

            text = ""
            if hasattr(item, "text"):
                text = item.text
            elif hasattr(item, "export_to_markdown"):
                text = item.export_to_markdown()

            bbox = None
            if hasattr(item, "prov") and item.prov:
                prov = item.prov[0]
                if hasattr(prov, "bbox") and prov.bbox:
                    b = prov.bbox
                    bbox = BBox(x0=b.l, y0=b.t, x1=b.r, y1=b.b)

            page = 0
            if hasattr(item, "prov") and item.prov:
                page = getattr(item.prov[0], "page_no", 0)

            blocks.append(
                Block(
                    text=text,
                    block_type=block_type,
                    level=level,
                    page=page,
                    bbox=bbox,
                    raw_label=label,
                )
            )

        return blocks
