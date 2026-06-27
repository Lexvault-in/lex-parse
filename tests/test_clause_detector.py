"""Tests for clause detector."""

from lexparse.engine.clause_detector import (
    classify_clause,
    detect_clauses_in_section,
    split_section_into_clauses,
)
from lexparse.ingestors.base import Block, BlockType
from lexparse.models import Clause, Section


def test_classify_confidentiality():
    text = "Each party agrees to hold in confidence all Confidential Information."
    assert classify_clause(text) == "confidentiality"


def test_classify_indemnification():
    text = "Company shall indemnify and hold harmless the Client."
    assert classify_clause(text) == "indemnification"


def test_classify_termination():
    text = "Either party may terminate this Agreement upon 30 days notice."
    assert classify_clause(text) == "termination"


def test_classify_limitation_of_liability():
    text = "In no event shall aggregate liability exceed the fees paid."
    assert classify_clause(text) == "limitation_of_liability"


def test_classify_governing_law():
    text = "This Agreement shall be governed by the laws of the State of Delaware."
    assert classify_clause(text) == "governing_law"


def test_classify_force_majeure():
    text = "Neither party shall be liable for force majeure events."
    assert classify_clause(text) == "force_majeure"


def test_classify_non_compete():
    text = "Employee shall not compete with the Company for two years."
    assert classify_clause(text) == "non_compete"


def test_classify_entire_agreement():
    text = "This constitutes the entire agreement and supersedes all prior agreements."
    assert classify_clause(text) == "entire_agreement"


def test_classify_unknown():
    text = "The sky is blue and water is wet."
    assert classify_clause(text) == "unknown"


def test_classify_empty():
    assert classify_clause("") == "unknown"


def test_detect_clauses_in_section():
    section = Section(
        number="7",
        title="CONFIDENTIALITY",
        clauses=[
            Clause(number="7.1", text="All Confidential Information shall be protected."),
            Clause(number="7.2", text="The obligations shall survive termination."),
        ],
    )
    detect_clauses_in_section(section)
    assert section.clauses[0].clause_type == "confidentiality"
    assert section.clauses[1].clause_type == "termination"


def test_detect_clauses_preserves_existing_type():
    section = Section(
        number="1",
        title="TEST",
        clauses=[
            Clause(number="1.1", text="Some text", clause_type="payment"),
        ],
    )
    detect_clauses_in_section(section)
    assert section.clauses[0].clause_type == "payment"


def test_detect_clauses_nested():
    section = Section(
        number="1",
        title="GENERAL",
        children=[
            Section(
                number="1.1",
                title="Confidentiality",
                clauses=[
                    Clause(number="1.1.1", text="Do not disclose confidential information."),
                ],
            ),
        ],
    )
    detect_clauses_in_section(section)
    assert section.children[0].clauses[0].clause_type == "confidentiality"


def test_split_section_into_clauses():
    section = Section(number="5", title="OBLIGATIONS")
    blocks = [
        Block(text="5.1. Provider shall deliver services.", block_type=BlockType.PARAGRAPH, page=3),
        Block(
            text="5.2. Client shall pay invoices within 30 days.",
            block_type=BlockType.PARAGRAPH, page=3,
        ),
        Block(text="Net 30 payment terms apply.", block_type=BlockType.PARAGRAPH, page=4),
    ]
    split_section_into_clauses(section, blocks)
    assert len(section.clauses) == 2
    assert section.clauses[0].number == "5.1"
    assert "deliver services" in section.clauses[0].text
    assert section.clauses[1].number == "5.2"
    assert "pay invoices" in section.clauses[1].text
    assert "Net 30" in section.clauses[1].text


def test_split_section_with_lettered_clauses():
    section = Section(number="3", title="WARRANTIES")
    blocks = [
        Block(text="(a) Company represents that it has authority.", block_type=BlockType.PARAGRAPH),
        Block(text="(b) Company warrants compliance with laws.", block_type=BlockType.PARAGRAPH),
    ]
    split_section_into_clauses(section, blocks)
    assert len(section.clauses) == 2
    assert section.clauses[0].number == "(a)"
    assert section.clauses[1].number == "(b)"


def test_split_section_no_boundaries():
    section = Section(number="1", title="INTRO")
    blocks = [
        Block(text="This is introductory text.", block_type=BlockType.PARAGRAPH),
        Block(text="More intro.", block_type=BlockType.PARAGRAPH),
    ]
    split_section_into_clauses(section, blocks)
    assert len(section.clauses) == 1
    assert "introductory text" in section.clauses[0].text


def test_split_skips_if_clauses_exist():
    existing = Clause(number="1.1", text="Already here")
    section = Section(number="1", title="TEST", clauses=[existing])
    blocks = [
        Block(text="1.2. New clause", block_type=BlockType.PARAGRAPH),
    ]
    split_section_into_clauses(section, blocks)
    assert len(section.clauses) == 1
    assert section.clauses[0].text == "Already here"
