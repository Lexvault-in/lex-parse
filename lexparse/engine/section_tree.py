"""Section tree builder — reconstructs hierarchical structure from flat blocks."""

from __future__ import annotations

import re

from lexparse.ingestors.base import Block, BlockType
from lexparse.models import Section

NUMBERING_PATTERNS: list[tuple[re.Pattern, str, int]] = [
    # "ARTICLE I", "ARTICLE II" → level 1
    (re.compile(r"^ARTICLE\s+([IVXLCDM]+)\b", re.IGNORECASE), "article", 1),
    # "SECTION 1", "Section 1.2" → level 2
    (re.compile(r"^SECTION\s+(\d+(?:\.\d+)*)\b", re.IGNORECASE), "section", 2),
    # "1." or "1.1" or "1.1.1" → level = dot count + 1
    (re.compile(r"^(\d+(?:\.\d+)*)\.\s"), "numbered", 0),
    # "(a)", "(b)" → level based on context
    (re.compile(r"^\(([a-z])\)\s"), "alpha", 0),
    # "(i)", "(ii)", "(iv)" → level based on context
    (re.compile(r"^\(([ivxlcdm]+)\)\s", re.IGNORECASE), "roman_paren", 0),
]


def _detect_numbering(text: str) -> tuple[str, str, int] | None:
    """Try to match text against known numbering patterns.

    Returns (number, style, level) or None.
    """
    stripped = text.strip()
    for pattern, style, fixed_level in NUMBERING_PATTERNS:
        match = pattern.match(stripped)
        if match:
            number = match.group(1)
            if style == "numbered":
                level = number.count(".") + 1
            elif fixed_level > 0:
                level = fixed_level
            elif style == "alpha":
                level = 4
            elif style == "roman_paren":
                level = 5
            else:
                level = 3
            return number, style, level
    return None


def _is_heading_text(text: str) -> bool:
    """Heuristic: all-caps short text is likely a heading."""
    stripped = text.strip()
    if len(stripped) < 3 or len(stripped) > 200:
        return False
    alpha_chars = [c for c in stripped if c.isalpha()]
    if not alpha_chars:
        return False
    return all(c.isupper() for c in alpha_chars)


def _extract_title(text: str) -> tuple[str, str]:
    """Split block text into (number, title).

    "1.1 Definitions" → ("1.1", "Definitions")
    "ARTICLE I - DEFINITIONS" → ("I", "DEFINITIONS")
    """
    stripped = text.strip()

    numbering = _detect_numbering(stripped)
    if numbering is None:
        return ("", stripped)

    number, style, _ = numbering

    if style == "article":
        rest = re.sub(r"^ARTICLE\s+[IVXLCDM]+\s*[-:.]\s*", "", stripped, flags=re.IGNORECASE)
        return (number, rest.strip())

    if style == "section":
        rest = re.sub(r"^SECTION\s+\d+(?:\.\d+)*\s*[-:.]\s*", "", stripped, flags=re.IGNORECASE)
        return (number, rest.strip())

    if style == "numbered":
        rest = re.sub(r"^\d+(?:\.\d+)*\.\s*", "", stripped)
        return (number, rest.strip())

    if style in ("alpha", "roman_paren"):
        rest = re.sub(r"^\([a-z]+\)\s*", "", stripped, flags=re.IGNORECASE)
        return (number, rest.strip())

    return (number, stripped)


def build_section_tree(blocks: list[Block]) -> list[Section]:
    """Build a hierarchical section tree from a flat list of blocks.

    Strategy:
    1. Identify heading blocks (from backend label OR numbering/all-caps heuristic)
    2. Parse numbering to determine hierarchy level
    3. Build tree by nesting sections based on level
    4. Attach non-heading blocks as clause text under the nearest section
    """
    sections: list[Section] = []
    section_stack: list[tuple[int, Section]] = []
    current_text_parts: list[str] = []

    def _flush_text() -> None:
        if current_text_parts and section_stack:
            _, current_section = section_stack[-1]
            combined = "\n".join(current_text_parts)
            if combined.strip():
                from lexparse.models import Clause

                clause = Clause(
                    number=current_section.number,
                    text=combined.strip(),
                    page_start=0,
                    page_end=0,
                )
                current_section.clauses.append(clause)
            current_text_parts.clear()

    for block in blocks:
        is_heading = block.block_type == BlockType.HEADING
        numbering = _detect_numbering(block.text)

        if not is_heading and numbering is None and not _is_heading_text(block.text):
            current_text_parts.append(block.text)
            continue

        _flush_text()

        if numbering:
            number, _, level = numbering
        elif is_heading:
            number = ""
            level = max(1, block.level)
        else:
            number = ""
            level = 1

        num, title = _extract_title(block.text)
        if num:
            number = num

        section = Section(
            number=number,
            title=title,
            level=level,
        )

        while section_stack and section_stack[-1][0] >= level:
            section_stack.pop()

        if section_stack:
            _, parent = section_stack[-1]
            parent.children.append(section)
        else:
            sections.append(section)

        section_stack.append((level, section))

    _flush_text()

    return sections
