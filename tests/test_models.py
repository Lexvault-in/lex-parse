"""Tests for lexparse data models."""

from lexparse.models import (
    UNKNOWN_CLAUSE_TYPE,
    Clause,
    Contract,
    ContractMetadata,
    CrossRef,
    Definition,
    DocumentType,
    ExtractionMethod,
    Party,
    RiskLevel,
    Section,
    get_clause_types,
    is_valid_clause_type,
    register_clause_type,
)


def test_builtin_clause_types_registered():
    types = get_clause_types()
    assert "confidentiality" in types
    assert "indemnification" in types
    assert "termination" in types
    assert "governing_law" in types
    assert len(types) >= 20


def test_clause_type_has_keywords():
    types = get_clause_types()
    for name, info in types.items():
        assert "keywords" in info, f"{name} missing keywords"
        assert len(info["keywords"]) > 0, f"{name} has empty keywords"


def test_register_custom_clause_type():
    register_clause_type(
        "data_protection",
        label="Data Protection",
        description="GDPR and data privacy obligations",
        keywords=["personal data", "data controller", "GDPR"],
    )
    assert is_valid_clause_type("data_protection")
    types = get_clause_types()
    assert types["data_protection"]["label"] == "Data Protection"


def test_is_valid_clause_type():
    assert is_valid_clause_type("confidentiality")
    assert not is_valid_clause_type("made_up_type_xyz")


def test_definition_defaults():
    d = Definition(term="Confidential Information", text="means any info...")
    assert d.section_ref == ""
    assert d.page == 0
    assert d.confidence == 1.0
    assert d.extraction_method == ExtractionMethod.RULE


def test_party_model():
    p = Party(name="Acme Corp", alias="Company", entity_type="corporation")
    assert p.name == "Acme Corp"
    assert p.alias == "Company"
    assert p.jurisdiction is None


def test_clause_with_risk():
    c = Clause(
        number="7.1",
        text="Uncapped liability...",
        clause_type="limitation_of_liability",
        risk_score=RiskLevel.CRITICAL,
        risk_reason="Uncapped liability with no carve-outs",
    )
    assert c.risk_score == "critical"
    assert c.clause_type == "limitation_of_liability"


def test_clause_defaults_to_unknown():
    c = Clause(number="1.1", text="some text")
    assert c.clause_type == UNKNOWN_CLAUSE_TYPE


def test_section_all_clauses():
    child_clause = Clause(number="1.1.1", text="sub-clause")
    child_section = Section(number="1.1", title="Sub", clauses=[child_clause])
    parent_clause = Clause(number="1.0", text="parent clause")
    parent = Section(number="1", title="Parent", clauses=[parent_clause], children=[child_section])

    all_clauses = parent.all_clauses()
    assert len(all_clauses) == 2
    assert all_clauses[0].number == "1.0"
    assert all_clauses[1].number == "1.1.1"


def test_contract_all_clauses():
    c1 = Clause(number="1.1", text="first")
    c2 = Clause(number="2.1", text="second")
    contract = Contract(
        sections=[
            Section(number="1", title="One", clauses=[c1]),
            Section(number="2", title="Two", clauses=[c2]),
        ]
    )
    assert len(contract.all_clauses()) == 2


def test_contract_definition_index():
    contract = Contract(
        definitions=[
            Definition(term="Term A", text="means X"),
            Definition(term="Term B", text="means Y"),
        ]
    )
    idx = contract.definition_index()
    assert idx == {"Term A": "means X", "Term B": "means Y"}


def test_contract_to_json():
    contract = Contract(
        metadata=ContractMetadata(title="Test NDA", document_type=DocumentType.NDA, page_count=5),
        parties=[Party(name="Acme", alias="Company")],
    )
    json_str = contract.to_json()
    assert "Test NDA" in json_str
    assert "NDA" in json_str
    assert "Acme" in json_str


def test_contract_to_markdown():
    contract = Contract(
        metadata=ContractMetadata(title="Test Agreement"),
        parties=[Party(name="Acme Corp", alias="Company")],
        definitions=[Definition(term="Services", text="means consulting")],
        sections=[
            Section(
                number="1",
                title="SERVICES",
                clauses=[Clause(number="1.1", text="Provider shall deliver Services.")],
            )
        ],
    )
    md = contract.to_markdown()
    assert "# Test Agreement" in md
    assert "**Acme Corp**" in md
    assert '"Services"' in md
    assert "## 1. SERVICES" in md
    assert "Provider shall deliver" in md


def test_contract_to_chunks():
    contract = Contract(
        definitions=[Definition(term="Services", text="means consulting")],
        sections=[
            Section(
                number="7",
                title="CONFIDENTIALITY",
                clauses=[
                    Clause(
                        number="7.1",
                        text="Each party agrees to hold in confidence all Services information.",
                        clause_type="confidentiality",
                        page_start=5,
                        page_end=5,
                        cross_references=[CrossRef(source_clause="7.1", target="Section 1.3")],
                    )
                ],
            )
        ],
    )
    chunks = contract.to_chunks(max_tokens=512)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["clause_number"] == "7.1"
    assert chunk["clause_type"] == "confidentiality"
    assert chunk["section"] == "7. CONFIDENTIALITY"
    assert chunk["page_start"] == 5
    assert "Services" in chunk["definitions_referenced"]
    assert "Section 1.3" in chunk["cross_references"]


def test_contract_to_chunks_long_clause():
    long_text = " ".join(["word"] * 1000)
    contract = Contract(
        sections=[
            Section(
                number="1",
                title="Long",
                clauses=[Clause(number="1.1", text=long_text)],
            )
        ],
    )
    chunks = contract.to_chunks(max_tokens=512)
    assert len(chunks) == 2
    assert chunks[0]["chunk_index"] == 0
    assert chunks[1]["chunk_index"] == 1


def test_contract_empty():
    contract = Contract()
    assert contract.all_clauses() == []
    assert contract.definition_index() == {}
    assert contract.to_chunks() == []
    assert "# " not in contract.to_markdown()
    json_str = contract.to_json()
    assert "metadata" in json_str
