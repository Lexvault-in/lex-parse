"""Marker-based document ingestor."""

from __future__ import annotations

from lexparse.ingestors.base import BaseIngestor, BBox, Block, BlockType

_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".epub"}

_BLOCK_TYPE_MAP = {
    "SectionHeader": BlockType.HEADING,
    "Title": BlockType.HEADING,
    "Text": BlockType.PARAGRAPH,
    "TextInlineMath": BlockType.PARAGRAPH,
    "ListItem": BlockType.LIST_ITEM,
    "Table": BlockType.TABLE,
    "PageBreak": BlockType.PAGE_BREAK,
    "Caption": BlockType.PARAGRAPH,
    "Footnote": BlockType.PARAGRAPH,
    "Equation": BlockType.PARAGRAPH,
    "Form": BlockType.TABLE,
    "Handwriting": BlockType.PARAGRAPH,
}


class MarkerIngestor(BaseIngestor):
    def __init__(self) -> None:
        try:
            from marker.converters.pdf import PdfConverter
            from marker.models import create_model_dict
        except ImportError:
            raise ImportError(
                "Marker is required for MarkerIngestor. "
                'Install it with: pip install "lexparse[marker]"'
            )
        self._pdf_converter_cls = PdfConverter
        self._create_model_dict = create_model_dict
        self._converter = None

    def _get_converter(self):
        if self._converter is None:
            from marker.config.parser import ConfigParser

            config = {"output_format": "json"}
            config_parser = ConfigParser(config)
            self._converter = self._pdf_converter_cls(
                config=config_parser.generate_config_dict(),
                artifact_dict=self._create_model_dict(),
                processor_list=config_parser.get_processors(),
                renderer=config_parser.get_renderer(),
            )
        return self._converter

    def supports(self, file_path: str) -> bool:
        return any(file_path.lower().endswith(ext) for ext in _SUPPORTED_EXTENSIONS)

    def ingest(self, file_path: str) -> list[Block]:
        converter = self._get_converter()
        rendered = converter(file_path)
        blocks: list[Block] = []
        self._walk_tree(rendered.children, blocks, level=0, page=1)
        return blocks

    def _walk_tree(
        self, children: list, blocks: list[Block], level: int, page: int
    ) -> None:
        if not children:
            return

        for child in children:
            block_type_str = getattr(child, "block_type", "")
            block_type = _BLOCK_TYPE_MAP.get(str(block_type_str), BlockType.UNKNOWN)

            if block_type == BlockType.PAGE_BREAK:
                page += 1

            text = ""
            if hasattr(child, "text"):
                text = child.text or ""
            elif hasattr(child, "html"):
                text = child.html or ""

            heading_level = level
            if block_type == BlockType.HEADING:
                heading_level = getattr(child, "level", level) or level

            bbox = None
            if hasattr(child, "polygon") and child.polygon:
                coords = child.polygon
                if len(coords) >= 4:
                    xs = [c[0] for c in coords]
                    ys = [c[1] for c in coords]
                    bbox = BBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))

            if text.strip():
                blocks.append(
                    Block(
                        text=text,
                        block_type=block_type,
                        level=heading_level,
                        page=page,
                        bbox=bbox,
                        raw_label=str(block_type_str),
                    )
                )

            if hasattr(child, "children") and child.children:
                self._walk_tree(child.children, blocks, level + 1, page)
