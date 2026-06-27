# lexparse — Implementation Plan

## Feasibility Assessment

### Can we actually build this?

**Yes.** Here's why:

1. **Docling gives us 80% for free.** Its `DocumentConverter` handles PDF/DOCX → structured elements (headings, paragraphs, tables, lists) with layout info, page numbers, and a body tree. We don't need to touch OCR, layout detection, or text extraction.

2. **Legal structure detection is mostly rule-based.** Contracts follow rigid patterns:
   - Clause numbering: `1.`, `1.1`, `(a)`, `(i)` — regex handles this
   - Definitions: `"X" means...`, `"X" shall mean...` — regex handles this
   - Section headers: `ARTICLE I`, `SECTION 1`, all-caps headings — pattern matching
   - Signature blocks: `By:`, `Name:`, `Title:`, `Date:` — pattern matching
   - Cross-references: `Section 4.2`, `Article III`, `Exhibit A` — regex + linking

3. **No ML needed for v0.1-v0.3.** Rule-based extraction is sufficient for well-structured contracts (which is 90% of commercial contracts). ML can be added later for messy/scanned docs.

4. **Real risk:** Edge cases in numbering schemes and non-standard formatting. Mitigated by testing against diverse real contracts early.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        lexparse                               │
│                                                               │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐  │
│  │   Ingestor   │───▶│  Legal Engine │───▶│  Output Layer   │  │
│  │              │    │              │    │                 │  │
│  │ DoclingBack  │    │ ClauseDetect │    │ ContractJSON    │  │
│  │ MarkerBack   │    │ DefExtract   │    │ LegalMarkdown   │  │
│  │ PlainText    │    │ SectionTree  │    │ ClauseChunks    │  │
│  │              │    │ ExhibitDetect│    │ DefinitionIndex │  │
│  │              │    │ SignDetect   │    │                 │  │
│  │              │    │ CrossRefLink │    │                 │  │
│  │              │    │ PartyExtract │    │                 │  │
│  └─────────────┘    └──────────────┘    └─────────────────┘  │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### Layer 1: Ingestor (Parsing Backend)

Takes a file, returns a normalized intermediate representation (list of `Block` objects with text, type, level, page number, bounding box).

**Why an abstraction layer?** Docling and Marker have different output formats. We normalize to a common `Block` format so the Legal Engine doesn't care which backend is used.

```python
# lexparse/ingestors/base.py
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class BlockType(Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    PAGE_BREAK = "page_break"
    UNKNOWN = "unknown"

@dataclass
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

@dataclass
class Block:
    text: str
    block_type: BlockType
    level: int  # heading level (1-6), 0 for non-headings
    page: int
    bbox: Optional[BBox] = None
    children: list["Block"] | None = None
    raw_label: str = ""  # original label from backend

class BaseIngestor:
    def ingest(self, file_path: str) -> list[Block]:
        raise NotImplementedError
```

```python
# lexparse/ingestors/docling_ingestor.py
from docling.document_converter import DocumentConverter

class DoclingIngestor(BaseIngestor):
    def __init__(self):
        self.converter = DocumentConverter()

    def ingest(self, file_path: str) -> list[Block]:
        result = self.converter.convert(file_path)
        doc = result.document
        blocks = []
        # Walk doc.body tree, map TextItem/TableItem → Block
        # Docling labels: section_header, paragraph, list_item, table, etc.
        for item, level in doc.iterate_items(doc.body):
            block = Block(
                text=item.text if hasattr(item, 'text') else str(item),
                block_type=self._map_label(item.label),
                level=level,
                page=item.prov[0].page_no if item.prov else 0,
                bbox=self._map_bbox(item),
                raw_label=str(item.label),
            )
            blocks.append(block)
        return blocks
```

```python
# lexparse/ingestors/marker_ingestor.py
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict

class MarkerIngestor(BaseIngestor):
    def __init__(self):
        self.converter = PdfConverter(
            artifact_dict=create_model_dict(),
            config={"output_format": "json"}
        )

    def ingest(self, file_path: str) -> list[Block]:
        rendered = self.converter(file_path)
        # Walk Marker's JSON tree, map block_type → Block
        return self._walk_tree(rendered.children)
```

### Layer 2: Legal Structure Engine

Takes `list[Block]` → produces a `Contract` object with clauses, definitions, sections, exhibits, signatures.

This is **where all our value lives.** Each component is a self-contained detector/extractor.

#### Component 1: Section Tree Builder

Reconstructs the hierarchical section structure from flat blocks.

```python
# lexparse/engine/section_tree.py
import re

# Common legal numbering patterns
NUMBERING_PATTERNS = [
    # "ARTICLE I", "ARTICLE II"
    (r'^ARTICLE\s+([IVXLCDM]+)', 'article'),
    # "SECTION 1", "Section 1.2"
    (r'^SECTION\s+(\d+(?:\.\d+)*)', 'section'),
    # "1.", "1.1", "1.1.1"
    (r'^(\d+(?:\.\d+)*)\.\s', 'numbered'),
    # "(a)", "(b)", "(i)", "(ii)"
    (r'^\(([a-z]|[ivx]+)\)\s', 'lettered'),
]

class SectionTreeBuilder:
    def build(self, blocks: list[Block]) -> SectionNode:
        """
        Walk blocks, detect numbering, build tree.

        Strategy:
        1. Identify heading blocks (from backend label OR all-caps text)
        2. Parse numbering scheme
        3. Determine hierarchy from numbering depth
        4. Attach paragraph blocks as content under nearest heading
        """
        ...
```

**Feasibility:** High. Contract numbering is highly standardized. The main challenge is handling mixed numbering schemes (e.g., "Article I" → "Section 1.1" → "(a)") — solved by tracking numbering context.

#### Component 2: Clause Detector

Identifies clause boundaries within sections.

```python
# lexparse/engine/clause_detector.py

CLAUSE_BOUNDARY_SIGNALS = [
    # Numbered sub-sections are clause boundaries
    r'^\d+\.\d+',
    # Lettered sub-clauses
    r'^\([a-z]\)',
    # Roman numeral sub-clauses
    r'^\([ivx]+\)',
]

CLAUSE_TYPE_PATTERNS = {
    "confidentiality": [
        r'confidential\s+information',
        r'non-disclosure',
        r'shall\s+not\s+disclose',
    ],
    "indemnification": [
        r'indemnif',
        r'hold\s+harmless',
        r'defend\s+and\s+indemnify',
    ],
    "termination": [
        r'terminat(?:e|ion)',
        r'cancel(?:lation)?',
        r'right\s+to\s+terminate',
    ],
    "limitation_of_liability": [
        r'limit(?:ation)?\s+of\s+liability',
        r'aggregate\s+liability',
        r'consequential\s+damages',
    ],
    "governing_law": [
        r'govern(?:ing|ed\s+by)\s+(?:the\s+)?law',
        r'jurisdiction',
        r'laws\s+of\s+the\s+state',
    ],
    "force_majeure": [
        r'force\s+majeure',
        r'act\s+of\s+god',
        r'beyond\s+(?:the\s+)?(?:reasonable\s+)?control',
    ],
    "ip_assignment": [
        r'intellectual\s+property',
        r'work\s+(?:made\s+)?for\s+hire',
        r'assigns?\s+(?:all\s+)?rights?',
    ],
    "non_compete": [
        r'non-?compet(?:e|ition)',
        r'shall\s+not\s+(?:directly\s+or\s+indirectly\s+)?compete',
        r'restrictive\s+covenant',
    ],
    "representations_warranties": [
        r'represent(?:s|ation)',
        r'warrant(?:s|y|ies)',
        r'represents?\s+and\s+warrants?',
    ],
    "entire_agreement": [
        r'entire\s+agreement',
        r'supersedes?\s+(?:all\s+)?prior',
        r'constitutes?\s+the\s+entire',
    ],
}

class ClauseDetector:
    def detect(self, section: SectionNode) -> list[Clause]:
        """
        1. Use section boundaries as primary clause boundaries
        2. Classify each clause by matching text against patterns
        3. Return list of Clause objects with type, text, location
        """
        ...
```

**Feasibility:** High for well-structured contracts. Clause boundaries align with section numbering 95%+ of the time. Classification via keyword patterns gives ~80% accuracy — good enough for v1, ML improves later.

#### Component 3: Definition Extractor

Pulls defined terms from the contract.

```python
# lexparse/engine/definition_extractor.py
import re

DEFINITION_PATTERNS = [
    # "Confidential Information" means ...
    r'"([^"]+)"\s+(?:means?|shall\s+mean|refers?\s+to|is\s+defined\s+as)',
    # "Confidential Information" has the meaning ...
    r'"([^"]+)"\s+has\s+the\s+meaning',
    # As used herein, "X" means ...
    r'[Aa]s\s+used\s+(?:herein|in\s+this\s+Agreement),?\s+"([^"]+)"',
    # "X" (each, a "Y")
    r'"([^"]+)"\s*\((?:each,?\s+)?(?:a|an)\s+"([^"]+)"\)',
]

class DefinitionExtractor:
    def extract(self, blocks: list[Block]) -> list[Definition]:
        definitions = []
        for block in blocks:
            for pattern in DEFINITION_PATTERNS:
                matches = re.finditer(pattern, block.text, re.IGNORECASE)
                for match in matches:
                    definitions.append(Definition(
                        term=match.group(1),
                        text=self._extract_full_definition(block.text, match),
                        section_ref=block.section_ref,
                        page=block.page,
                    ))
        return definitions
```

**Feasibility:** Very high. Legal definitions follow extremely rigid patterns. The quoted-term-followed-by-"means" pattern catches 90%+ of definitions in commercial contracts.

#### Component 4: Exhibit Detector

```python
# lexparse/engine/exhibit_detector.py

EXHIBIT_PATTERNS = [
    r'^(?:EXHIBIT|SCHEDULE|APPENDIX|ANNEX|ATTACHMENT)\s+([A-Z0-9]+)',
]

class ExhibitDetector:
    def detect(self, blocks: list[Block]) -> list[Exhibit]:
        """Scan for exhibit headers, capture page range."""
        ...
```

**Feasibility:** Very high. Exhibit headers are always all-caps and follow standard naming.

#### Component 5: Signature Detector

```python
# lexparse/engine/signature_detector.py

SIGNATURE_SIGNALS = [
    r'IN\s+WITNESS\s+WHEREOF',
    r'EXECUTED\s+(?:as\s+of|on)',
    r'AGREED\s+(?:AND\s+ACCEPTED|TO)',
]

SIGNER_FIELDS = [
    r'(?:By|Signature)\s*:\s*[_\s]*\n?\s*(.*)',
    r'(?:Name|Print\s+Name)\s*:\s*(.*)',
    r'(?:Title)\s*:\s*(.*)',
    r'(?:Date)\s*:\s*(.*)',
]
```

**Feasibility:** Very high. Signature blocks are the most formulaic part of any contract.

#### Component 6: Cross-Reference Linker

```python
# lexparse/engine/cross_ref_linker.py

CROSS_REF_PATTERNS = [
    r'(?:Section|Article|Clause)\s+(\d+(?:\.\d+)*)',
    r'(?:Exhibit|Schedule|Appendix|Annex)\s+([A-Z0-9]+)',
    r'(?:paragraph|subsection)\s+\(([a-z]|[ivx]+)\)',
]

class CrossRefLinker:
    def link(self, clauses: list[Clause], sections: SectionNode) -> list[CrossRef]:
        """Find cross-references in clause text, resolve to section IDs."""
        ...
```

**Feasibility:** High. Pattern matching finds the references; resolution requires the section tree (which we build in step 1).

#### Component 7: Party Extractor

```python
# lexparse/engine/party_extractor.py

PARTY_PATTERNS = [
    # "Acme Corp, a Delaware corporation ("Company")"
    r'([A-Z][^,]+),\s+a\s+[A-Za-z\s]+(?:corporation|LLC|company|partnership|entity)\s*\(\s*"([^"]+)"\s*\)',
    # "between X ("Buyer") and Y ("Seller")"
    r'between\s+(.+?)\s*\(\s*"([^"]+)"\s*\)\s*and\s+(.+?)\s*\(\s*"([^"]+)"\s*\)',
    # Preamble: "This Agreement is entered into by and between"
    r'(?:by\s+and\s+between|between|among)\s+(.+?)(?:\s+and\s+|\s*$)',
]

class PartyExtractor:
    def extract(self, blocks: list[Block]) -> list[Party]:
        """
        Strategy:
        1. Focus on first 2 pages (preamble)
        2. Find party introduction patterns
        3. Extract entity name + defined alias
        """
        ...
```

**Feasibility:** Medium-high. Preamble patterns are standard, but entity name boundaries can be tricky. Limiting to the first 2 pages keeps accuracy high.

### Layer 3: Output

```python
# lexparse/models.py
from pydantic import BaseModel
from typing import Optional
from enum import Enum

class ClauseType(str, Enum):
    CONFIDENTIALITY = "confidentiality"
    INDEMNIFICATION = "indemnification"
    TERMINATION = "termination"
    LIMITATION_OF_LIABILITY = "limitation_of_liability"
    GOVERNING_LAW = "governing_law"
    FORCE_MAJEURE = "force_majeure"
    IP_ASSIGNMENT = "ip_assignment"
    NON_COMPETE = "non_compete"
    REPRESENTATIONS_WARRANTIES = "representations_warranties"
    ENTIRE_AGREEMENT = "entire_agreement"
    UNKNOWN = "unknown"

class Definition(BaseModel):
    term: str
    text: str
    section_ref: str
    page: int

class Party(BaseModel):
    name: str
    alias: str  # e.g., "Company", "Buyer"
    entity_type: Optional[str] = None  # corporation, LLC, etc.

class CrossRef(BaseModel):
    source_clause: str  # clause number containing the reference
    target: str         # "Section 4.2", "Exhibit A"
    target_type: str    # "section", "exhibit", "schedule"
    resolved: bool      # whether we found the target

class Clause(BaseModel):
    number: str
    title: Optional[str] = None
    text: str
    clause_type: ClauseType
    level: int
    page_start: int
    page_end: int
    cross_references: list[CrossRef] = []
    children: list["Clause"] = []

class Section(BaseModel):
    number: str
    title: str
    level: int
    clauses: list[Clause] = []
    children: list["Section"] = []

class Exhibit(BaseModel):
    label: str
    title: Optional[str] = None
    page_start: int
    page_end: int

class Signature(BaseModel):
    party: Optional[str] = None
    signer_name: Optional[str] = None
    title: Optional[str] = None
    page: int

class ContractMetadata(BaseModel):
    title: Optional[str] = None
    document_type: Optional[str] = None  # MSA, NDA, Employment, etc.
    effective_date: Optional[str] = None
    governing_law: Optional[str] = None
    page_count: int

class Contract(BaseModel):
    metadata: ContractMetadata
    parties: list[Party]
    definitions: list[Definition]
    sections: list[Section]
    exhibits: list[Exhibit]
    signatures: list[Signature]

    def to_json(self) -> str: ...
    def to_markdown(self) -> str: ...
    def to_chunks(self, max_tokens: int = 512) -> list[dict]: ...
```

---

## Public API

```python
# lexparse/__init__.py
from lexparse.parser import LexParser

# Simple usage
parser = LexParser()
contract = parser.parse("agreement.pdf")

# Access structured data
print(contract.metadata.title)
print(contract.parties)
for defn in contract.definitions:
    print(f"{defn.term}: {defn.text[:80]}...")

# Get clause-aware chunks for RAG
chunks = contract.to_chunks(max_tokens=512)

# Export
contract.to_json()       # ContractJSON
contract.to_markdown()   # Legal Markdown with structure preserved

# Choose backend
parser = LexParser(backend="marker")
contract = parser.parse("scanned_contract.pdf")

# Parse with options
contract = parser.parse(
    "agreement.pdf",
    extract_definitions=True,
    extract_signatures=True,
    classify_clauses=True,
    resolve_cross_refs=True,
)
```

---

## Repo Structure

```
lexparse/
├── README.md
├── LICENSE                      # Apache-2.0
├── pyproject.toml
├── lexparse/
│   ├── __init__.py              # Public API: LexParser
│   ├── parser.py                # LexParser orchestrator
│   ├── models.py                # Pydantic models (Contract, Clause, etc.)
│   ├── ingestors/
│   │   ├── __init__.py
│   │   ├── base.py              # Block, BaseIngestor
│   │   ├── docling_ingestor.py
│   │   └── marker_ingestor.py
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── section_tree.py
│   │   ├── clause_detector.py
│   │   ├── definition_extractor.py
│   │   ├── exhibit_detector.py
│   │   ├── signature_detector.py
│   │   ├── cross_ref_linker.py
│   │   ├── party_extractor.py
│   │   └── metadata_extractor.py
│   └── output/
│       ├── __init__.py
│       ├── json_export.py
│       ├── markdown_export.py
│       └── chunker.py           # Clause-aware chunking
├── tests/
│   ├── conftest.py
│   ├── fixtures/                # Sample contract PDFs
│   │   ├── nda_simple.pdf
│   │   ├── msa_standard.pdf
│   │   ├── employment_agreement.pdf
│   │   └── ...
│   ├── test_section_tree.py
│   ├── test_clause_detector.py
│   ├── test_definition_extractor.py
│   ├── test_exhibit_detector.py
│   ├── test_signature_detector.py
│   ├── test_cross_ref_linker.py
│   ├── test_party_extractor.py
│   ├── test_integration.py      # End-to-end PDF → Contract
│   └── test_output.py
├── examples/
│   ├── basic_usage.py
│   ├── rag_chunking.py
│   └── batch_processing.py
└── docs/
    └── contract_json_schema.json
```

---

## Implementation Order

### Phase 1 — Foundation (Week 1)

**Goal:** `parser.parse("contract.pdf")` returns a `Contract` with sections and clauses.

1. Set up repo: pyproject.toml, CI, linting
2. Implement `models.py` — all Pydantic models
3. Implement `DoclingIngestor` — PDF → `list[Block]`
4. Implement `SectionTreeBuilder` — blocks → section hierarchy
5. Implement `ClauseDetector` — sections → clauses with boundaries
6. Implement `LexParser` — orchestrator wiring it together
7. Write integration test with 1 real contract PDF

**Deliverable:** `pip install lexparse` → parse a PDF → get sections + clauses

### Phase 2 — Extractors (Week 2)

**Goal:** Definitions, exhibits, signatures, parties extracted.

1. Implement `DefinitionExtractor`
2. Implement `ExhibitDetector`
3. Implement `SignatureDetector`
4. Implement `PartyExtractor`
5. Implement `MetadataExtractor` (title, dates, governing law)
6. Wire all into `LexParser`
7. Test against 5 diverse contract PDFs

**Deliverable:** Full `Contract` object with all fields populated

### Phase 3 — Output & Polish (Week 3)

**Goal:** Multiple output formats, clause classification, cross-refs.

1. Implement `ClauseType` classification (keyword patterns)
2. Implement `CrossRefLinker`
3. Implement `json_export.py` — ContractJSON output
4. Implement `markdown_export.py` — structured legal markdown
5. Implement `chunker.py` — clause-aware RAG chunks
6. DOCX support via Docling (already supported, just test)
7. Write examples, polish README

**Deliverable:** Full feature set, published to PyPI

### Phase 4 — Multi-backend & Hardening (Week 4)

**Goal:** Marker backend, edge cases, batch processing.

1. Implement `MarkerIngestor`
2. Backend selection in `LexParser(backend="marker")`
3. Test against 20+ contracts from EDGAR
4. Handle edge cases: nested numbering, inconsistent formatting
5. Add confidence scores to extractions
6. Batch processing API
7. Performance benchmarks

**Deliverable:** Production-ready v0.4

---

## Key Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Docling API changes between versions | Medium | Medium | Pin version, use thin adapter layer |
| Non-standard numbering breaks section tree | High | Medium | Build a numbering pattern registry, fall back to heading-based detection |
| Definition extraction misses inline definitions | Medium | Low | Start with quoted-term patterns (high precision), expand later |
| Clause classification accuracy too low | Low | Low | Keyword patterns work well for standard clauses; ML classifier is a future add |
| Scanned PDFs produce poor text | Medium | High | Defer to Phase 4, rely on Docling's built-in OCR |
| Docling is too slow for large contracts | Medium | Medium | Add caching, lazy loading; Marker as fast alternative |

---

## Dependencies

```toml
[project]
name = "lexparse"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2.0",
]

[project.optional-dependencies]
docling = ["docling>=2.0"]
marker = ["marker-pdf>=1.0"]
all = ["docling>=2.0", "marker-pdf>=1.0"]
dev = ["pytest", "ruff", "mypy"]
```

**Design choice:** Core lexparse has minimal deps (just pydantic). Parsing backends are optional extras. This keeps install fast and lets users pick their backend.

---

## Test Strategy

1. **Unit tests:** Each engine component tested in isolation with hand-crafted `Block` lists
2. **Integration tests:** Real PDF → full `Contract` pipeline, assertions on extracted data
3. **Fixture contracts:** 5 real public contracts (NDA, MSA, Employment, License, SaaS) from EDGAR
4. **Regression tests:** When a bug is found, add the failing contract as a fixture
5. **No mocks for backends:** Integration tests hit real Docling/Marker — we need to know if they break

---

## What "Done" Looks Like (v0.4)

```bash
pip install "lexparse[docling]"
```

```python
from lexparse import LexParser

parser = LexParser()
contract = parser.parse("nda.pdf")

assert contract.metadata.document_type == "NDA"
assert len(contract.parties) == 2
assert len(contract.definitions) > 0
assert all(c.clause_type != "unknown" for c in contract.all_clauses())
assert len(contract.exhibits) >= 0
assert len(contract.signatures) == 2

# RAG-ready
chunks = contract.to_chunks(max_tokens=512)
assert all(chunk["clause_type"] for chunk in chunks)
assert all(chunk["section_ref"] for chunk in chunks)
```

A developer can install lexparse, point it at any commercial contract PDF, and get back structured, clause-level data ready for RAG, review, or analysis — in under 30 seconds.
