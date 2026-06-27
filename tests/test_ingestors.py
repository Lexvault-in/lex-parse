"""Tests for ingestor base classes and factory."""

import pytest

from lexparse.ingestors.base import BaseIngestor, BBox, Block, BlockType


def test_block_type_values():
    assert BlockType.HEADING.value == "heading"
    assert BlockType.PARAGRAPH.value == "paragraph"
    assert BlockType.TABLE.value == "table"


def test_bbox():
    bbox = BBox(x0=0.0, y0=0.0, x1=100.0, y1=50.0)
    assert bbox.x0 == 0.0
    assert bbox.x1 == 100.0


def test_block_defaults():
    block = Block(text="hello", block_type=BlockType.PARAGRAPH)
    assert block.level == 0
    assert block.page == 0
    assert block.bbox is None
    assert block.children == []
    assert block.raw_label == ""


def test_block_with_all_fields():
    bbox = BBox(x0=10, y0=20, x1=200, y1=50)
    block = Block(
        text="Section 1",
        block_type=BlockType.HEADING,
        level=1,
        page=3,
        bbox=bbox,
        raw_label="section_header",
    )
    assert block.text == "Section 1"
    assert block.block_type == BlockType.HEADING
    assert block.level == 1
    assert block.page == 3
    assert block.bbox.x0 == 10


def test_base_ingestor_not_implemented():
    ingestor = BaseIngestor()
    with pytest.raises(NotImplementedError):
        ingestor.ingest("test.pdf")
    with pytest.raises(NotImplementedError):
        ingestor.supports("test.pdf")


def test_get_ingestor_invalid_backend():
    from lexparse.ingestors import get_ingestor

    with pytest.raises(ValueError, match="Unknown backend"):
        get_ingestor("nonexistent")


def test_get_ingestor_docling_import_error():
    """Docling not installed — should raise ImportError with install hint."""
    from lexparse.ingestors import get_ingestor

    with pytest.raises(ImportError, match="lexparse\\[docling\\]"):
        get_ingestor("docling")


def test_get_ingestor_marker_import_error():
    """Marker not installed — should raise ImportError with install hint."""
    from lexparse.ingestors import get_ingestor

    with pytest.raises(ImportError, match="lexparse\\[marker\\]"):
        get_ingestor("marker")


def test_block_children():
    child = Block(text="sub item", block_type=BlockType.LIST_ITEM, level=2)
    parent = Block(
        text="Section 1",
        block_type=BlockType.HEADING,
        level=1,
        children=[child],
    )
    assert len(parent.children) == 1
    assert parent.children[0].text == "sub item"
