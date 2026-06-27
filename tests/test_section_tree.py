"""Tests for section tree builder."""

from lexparse.engine.section_tree import (
    _detect_numbering,
    _extract_title,
    _is_heading_text,
    build_section_tree,
)
from lexparse.ingestors.base import Block, BlockType


def test_detect_numbering_article():
    result = _detect_numbering("ARTICLE I")
    assert result is not None
    number, style, level = result
    assert number == "I"
    assert style == "article"
    assert level == 1


def test_detect_numbering_section():
    result = _detect_numbering("Section 3.2")
    assert result is not None
    number, style, level = result
    assert number == "3.2"
    assert style == "section"
    assert level == 2


def test_detect_numbering_dotted():
    result = _detect_numbering("1.1. Some clause text")
    assert result is not None
    number, style, level = result
    assert number == "1.1"
    assert style == "numbered"
    assert level == 2


def test_detect_numbering_deep():
    result = _detect_numbering("1.2.3. Deep clause")
    assert result is not None
    _, _, level = result
    assert level == 3


def test_detect_numbering_alpha():
    result = _detect_numbering("(a) first item")
    assert result is not None
    number, style, level = result
    assert number == "a"
    assert style == "alpha"
    assert level == 4


def test_detect_numbering_roman():
    result = _detect_numbering("(ii) second item")
    assert result is not None
    number, style, _ = result
    assert number == "ii"
    assert style == "roman_paren"


def test_detect_numbering_none():
    assert _detect_numbering("Just some text") is None
    assert _detect_numbering("") is None


def test_is_heading_text():
    assert _is_heading_text("DEFINITIONS")
    assert _is_heading_text("ARTICLE I - SCOPE OF WORK")
    assert not _is_heading_text("This is a normal sentence.")
    assert not _is_heading_text("AB")  # too short
    assert not _is_heading_text("")


def test_extract_title_numbered():
    number, title = _extract_title("1.1. Definitions")
    assert number == "1.1"
    assert title == "Definitions"


def test_extract_title_article():
    number, title = _extract_title("ARTICLE I - DEFINITIONS")
    assert number == "I"
    assert title == "DEFINITIONS"


def test_extract_title_section():
    number, title = _extract_title("Section 4.2: Payment Terms")
    assert number == "4.2"
    assert title == "Payment Terms"


def test_extract_title_plain():
    number, title = _extract_title("Just a heading")
    assert number == ""
    assert title == "Just a heading"


def test_build_simple_flat():
    blocks = [
        Block(text="1. DEFINITIONS", block_type=BlockType.HEADING, level=1),
        Block(text="Terms used herein.", block_type=BlockType.PARAGRAPH),
        Block(text="2. SERVICES", block_type=BlockType.HEADING, level=1),
        Block(text="Provider shall deliver.", block_type=BlockType.PARAGRAPH),
    ]
    sections = build_section_tree(blocks)
    assert len(sections) == 2
    assert sections[0].number == "1"
    assert sections[0].title == "DEFINITIONS"
    assert sections[1].number == "2"
    assert sections[1].title == "SERVICES"


def test_build_nested():
    blocks = [
        Block(text="ARTICLE I - GENERAL", block_type=BlockType.HEADING, level=1),
        Block(text="1.1. Definitions", block_type=BlockType.HEADING, level=2),
        Block(text="The following terms apply.", block_type=BlockType.PARAGRAPH),
        Block(text="1.2. Interpretation", block_type=BlockType.HEADING, level=2),
        Block(text="Headings are for convenience.", block_type=BlockType.PARAGRAPH),
    ]
    sections = build_section_tree(blocks)
    assert len(sections) == 1
    parent = sections[0]
    assert parent.number == "I"
    assert parent.title == "GENERAL"
    assert len(parent.children) == 2
    assert parent.children[0].number == "1.1"
    assert parent.children[0].title == "Definitions"
    assert parent.children[1].number == "1.2"


def test_build_attaches_text_as_clause():
    blocks = [
        Block(text="1. SCOPE", block_type=BlockType.HEADING, level=1),
        Block(text="This agreement covers X.", block_type=BlockType.PARAGRAPH),
        Block(text="Additional scope details.", block_type=BlockType.PARAGRAPH),
    ]
    sections = build_section_tree(blocks)
    assert len(sections) == 1
    assert len(sections[0].clauses) == 1
    assert "This agreement covers X." in sections[0].clauses[0].text
    assert "Additional scope details." in sections[0].clauses[0].text


def test_build_all_caps_detected_as_heading():
    blocks = [
        Block(text="CONFIDENTIALITY", block_type=BlockType.PARAGRAPH),
        Block(text="Each party shall keep info secret.", block_type=BlockType.PARAGRAPH),
    ]
    sections = build_section_tree(blocks)
    assert len(sections) == 1
    assert sections[0].title == "CONFIDENTIALITY"


def test_build_numbered_without_heading_label():
    blocks = [
        Block(text="1. Definitions", block_type=BlockType.PARAGRAPH),
        Block(text="Terms defined below.", block_type=BlockType.PARAGRAPH),
        Block(text="2. Obligations", block_type=BlockType.PARAGRAPH),
        Block(text="Parties must comply.", block_type=BlockType.PARAGRAPH),
    ]
    sections = build_section_tree(blocks)
    assert len(sections) == 2
    assert sections[0].number == "1"
    assert sections[1].number == "2"


def test_build_empty():
    sections = build_section_tree([])
    assert sections == []


def test_build_no_headings():
    blocks = [
        Block(text="Some random text.", block_type=BlockType.PARAGRAPH),
        Block(text="More text here.", block_type=BlockType.PARAGRAPH),
    ]
    sections = build_section_tree(blocks)
    assert sections == []


def test_build_deep_nesting():
    blocks = [
        Block(text="ARTICLE I - TERMS", block_type=BlockType.HEADING, level=1),
        Block(text="Section 1.1", block_type=BlockType.HEADING, level=2),
        Block(text="1.1.1. Sub-clause detail.", block_type=BlockType.PARAGRAPH),
        Block(text="Explanation text.", block_type=BlockType.PARAGRAPH),
    ]
    sections = build_section_tree(blocks)
    assert len(sections) == 1
    article = sections[0]
    assert len(article.children) == 1
    sec = article.children[0]
    assert len(sec.children) == 1
    subsec = sec.children[0]
    assert subsec.number == "1.1.1"
