"""Clause detector — identifies clause boundaries and classifies clause types."""

from __future__ import annotations

import re

from lexparse.ingestors.base import Block, BlockType
from lexparse.models import Clause, Section, get_clause_types

CLAUSE_BOUNDARY_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\d+\.\d+"),
    re.compile(r"^\([a-z]\)\s"),
    re.compile(r"^\([ivxlcdm]+\)\s", re.IGNORECASE),
]


def _build_keyword_patterns() -> dict[str, list[re.Pattern]]:
    """Build regex patterns from the clause type registry keywords."""
    patterns: dict[str, list[re.Pattern]] = {}
    for name, info in get_clause_types().items():
        compiled = []
        for kw in info.get("keywords", []):
            compiled.append(re.compile(re.escape(kw), re.IGNORECASE))
        if compiled:
            patterns[name] = compiled
    return patterns


def classify_clause(text: str, keyword_patterns: dict[str, list[re.Pattern]] | None = None) -> str:
    """Classify a clause's type based on keyword matching.

    Returns the clause type with the highest number of keyword hits.
    Falls back to "unknown" if no keywords match.
    """
    if keyword_patterns is None:
        keyword_patterns = _build_keyword_patterns()

    scores: dict[str, int] = {}
    text_lower = text.lower()

    for clause_type, patterns in keyword_patterns.items():
        hits = sum(1 for p in patterns if p.search(text_lower))
        if hits > 0:
            scores[clause_type] = hits

    if not scores:
        return "unknown"

    return max(scores, key=scores.get)  # type: ignore[arg-type]


def detect_clauses_in_section(
    section: Section,
    keyword_patterns: dict[str, list[re.Pattern]] | None = None,
) -> None:
    """Classify existing clauses in a section and its children.

    Modifies clauses in-place by setting their clause_type.
    """
    if keyword_patterns is None:
        keyword_patterns = _build_keyword_patterns()

    for clause in section.clauses:
        if clause.clause_type == "unknown":
            clause.clause_type = classify_clause(clause.text, keyword_patterns)
        _classify_children(clause, keyword_patterns)

    for child in section.children:
        detect_clauses_in_section(child, keyword_patterns)


def _classify_children(
    clause: Clause, keyword_patterns: dict[str, list[re.Pattern]]
) -> None:
    for child in clause.children:
        if child.clause_type == "unknown":
            child.clause_type = classify_clause(child.text, keyword_patterns)
        _classify_children(child, keyword_patterns)


def split_section_into_clauses(
    section: Section,
    blocks: list[Block],
    keyword_patterns: dict[str, list[re.Pattern]] | None = None,
) -> None:
    """Split paragraph blocks within a section into individual clauses.

    Looks for clause boundary patterns (numbered sub-sections) within the
    text blocks and creates separate Clause objects for each.
    """
    if keyword_patterns is None:
        keyword_patterns = _build_keyword_patterns()

    if section.clauses:
        for clause in section.clauses:
            if clause.clause_type == "unknown":
                clause.clause_type = classify_clause(clause.text, keyword_patterns)
        return

    current_number = section.number
    current_parts: list[str] = []
    current_page = 0
    clauses: list[Clause] = []

    relevant_blocks = [
        b for b in blocks
        if b.block_type in (BlockType.PARAGRAPH, BlockType.LIST_ITEM)
    ]

    for block in relevant_blocks:
        boundary_match = None
        for pattern in CLAUSE_BOUNDARY_PATTERNS:
            m = pattern.match(block.text.strip())
            if m:
                boundary_match = m
                break

        if boundary_match:
            if current_parts:
                text = "\n".join(current_parts).strip()
                if text:
                    clauses.append(Clause(
                        number=current_number,
                        text=text,
                        clause_type=classify_clause(text, keyword_patterns),
                        page_start=current_page,
                        page_end=block.page or current_page,
                    ))
                current_parts = []

            current_number = boundary_match.group(0).rstrip(". ")
            current_page = block.page or 0

            remainder = block.text.strip()[boundary_match.end():]
            if remainder.strip():
                current_parts.append(remainder.strip())
        else:
            if not current_page:
                current_page = block.page or 0
            current_parts.append(block.text)

    if current_parts:
        text = "\n".join(current_parts).strip()
        if text:
            clauses.append(Clause(
                number=current_number,
                text=text,
                clause_type=classify_clause(text, keyword_patterns),
                page_start=current_page,
                page_end=current_page,
            ))

    section.clauses = clauses
