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

3. **Rule-based gets us to 85-95% accuracy fast.** Sufficient for well-structured contracts (90% of commercial contracts). But we'll hit a ceiling on clause classification, party extraction, and messy documents.

4. **ML/AI layer pushes us to 93-98%.** Fine-tuned classifiers for clause types, NER models for parties, LLM fallback for ambiguous cases. Added in Phase 4-5 after we have ground truth data from rule-based output.

5. **Real risk:** Edge cases in numbering schemes and non-standard formatting. Mitigated by testing against diverse real contracts early.

---

## Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│                            lexparse                                   │
│                                                                       │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────┐   ┌───────────┐  │
│  │   Ingestor   │──▶│ Rule Engine  │──▶│ ML Layer │──▶│  Output   │  │
│  │              │   │              │   │ (optional)│   │           │  │
│  │ DoclingBack  │   │ SectionTree  │   │          │   │ JSON      │  │
│  │ MarkerBack   │   │ ClauseDetect │   │ Clause   │   │ Markdown  │  │
│  │ PlainText    │   │ DefExtract   │   │ Classifr │   │ Chunks    │  │
│  │              │   │ ExhibitDetect│   │ NER Party│   │ DefIndex  │  │
│  │              │   │ SignDetect   │   │ Risk     │   │           │  │
│  │              │   │ CrossRefLink │   │ Scorer   │   │           │  │
│  │              │   │ PartyExtract │   │ LLM      │   │           │  │
│  │              │   │              │   │ Fallback │   │           │  │
│  └─────────────┘   └──────────────┘   └──────────┘   └───────────┘  │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
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
4. Implement `PartyExtractor` (rule-based, preamble patterns)
5. Implement `MetadataExtractor` (title, dates, governing law)
6. Wire all into `LexParser`
7. Test against 5 diverse contract PDFs

**Deliverable:** Full `Contract` object with all fields populated

### Phase 3 — Output & Polish (Week 3)

**Goal:** Multiple output formats, clause classification (rule-based), cross-refs.

1. Implement `ClauseType` classification (keyword patterns)
2. Implement `CrossRefLinker`
3. Implement `json_export.py` — ContractJSON output
4. Implement `markdown_export.py` — structured legal markdown
5. Implement `chunker.py` — clause-aware RAG chunks
6. DOCX support via Docling (already supported, just test)
7. Write examples, polish README

**Deliverable:** Full feature set, published to PyPI

### Phase 4 — Benchmarking: Rule-Based Baseline (Week 4)

**Goal:** Measure rule-based accuracy across all components. This becomes our baseline.

1. Build evaluation harness (`lexparse/eval/`)
2. Annotate 30 contracts as ground truth (from EDGAR + public sources)
3. Run rule-based pipeline, compute metrics per component
4. Publish baseline results
5. Identify where rules fail — these become ML targets

**Deliverable:** Published baseline metrics, identified ML opportunities

### Phase 5 — ML Layer: Clause Classifier (Week 5-6)

**Goal:** Replace keyword-based clause classification with a fine-tuned model.

1. Build training dataset from legal-clause-library + CUAD annotations
2. Fine-tune a text classifier (options below)
3. Integrate as optional ML layer: `LexParser(use_ml=True)`
4. A/B test: rule-based vs ML classification
5. Publish comparison metrics

**Model options for clause classification:**
| Model | Size | Approach | Pros | Cons |
|-------|------|----------|------|------|
| Legal-BERT | 110M | Fine-tune on clause types | Domain-specific, fast inference | Needs training data |
| SetFit | 110M | Few-shot fine-tuning | Works with ~50 examples per class | Less accurate at scale |
| sentence-transformers + logistic regression | ~30M | Embed → classify | Simple, fast, debuggable | No contextual understanding |
| GPT/Claude via API | — | Zero-shot / few-shot prompt | No training needed, highest accuracy | Cost, latency, API dependency |

**Recommended:** Start with SetFit (few-shot) for offline, add LLM fallback for low-confidence cases.

### Phase 6 — ML Layer: NER & Party Extraction (Week 7)

**Goal:** Replace regex party extraction with NER model.

1. Fine-tune spaCy NER or use a legal NER model on:
   - `PARTY_NAME` — entity names
   - `PARTY_ALIAS` — defined aliases ("Company", "Buyer")
   - `ENTITY_TYPE` — corporation, LLC, partnership
   - `JURISDICTION` — state/country of incorporation
   - `DATE` — effective dates, expiration dates
   - `MONETARY` — caps, fees, thresholds
2. Train on preamble text from annotated contracts
3. Integrate: rule-based as primary, NER as enhancement
4. Benchmark rule-based vs NER extraction

**Model options:**
| Model | Approach | Pros | Cons |
|-------|----------|------|------|
| spaCy NER (fine-tuned) | Token classification | Fast, local, well-supported | Needs ~200+ annotated examples |
| GLiNER | Zero-shot NER | No training data needed | Lower accuracy on legal entities |
| Legal-BERT + token classification | Fine-tune on legal NER | Domain-specific | More complex setup |

### Phase 7 — ML Layer: Risk Scoring & LLM Fallback (Week 8-9)

**Goal:** Add semantic understanding where rules can't reach.

1. **Risk scorer** — classify clauses as `low / medium / high / critical` risk
   - Use LLM (Claude/GPT) with structured output for risk assessment
   - Score dimensions: party fairness, enforceability, common vs unusual language
   - Cache results to reduce API costs

2. **LLM fallback for low-confidence extractions**
   - When rule-based confidence < threshold, send to LLM
   - Structured prompt: "Extract the following from this contract section..."
   - Works for: ambiguous definitions, complex party structures, unusual formatting

3. **Document type classifier**
   - Fine-tune on contract types: NDA, MSA, Employment, License, SaaS, Lease, etc.
   - Use first 2 pages + title as input

```python
# User-facing API
parser = LexParser(
    backend="docling",
    use_ml=True,              # Enable ML classifiers
    llm_fallback=True,        # Use LLM for low-confidence cases
    llm_provider="anthropic", # or "openai"
    risk_scoring=True,        # Add risk scores to clauses
)

contract = parser.parse("agreement.pdf")

for clause in contract.all_clauses():
    print(f"{clause.number} [{clause.clause_type}]")
    print(f"  Confidence: {clause.confidence}")        # 0.0-1.0
    print(f"  Method: {clause.extraction_method}")      # "rule" | "ml" | "llm"
    print(f"  Risk: {clause.risk_score}")               # low | medium | high | critical
    print(f"  Risk reason: {clause.risk_reason}")       # "Uncapped liability with no carve-outs"
```

### Phase 8 — Multi-backend & Hardening (Week 10)

**Goal:** Marker backend, edge cases, batch processing, production readiness.

1. Implement `MarkerIngestor`
2. Backend selection in `LexParser(backend="marker")`
3. Test against 50+ contracts from EDGAR
4. Handle edge cases: nested numbering, inconsistent formatting
5. Batch processing API
6. Performance benchmarks (speed, memory, cost)
7. Final metrics comparison: rule-based vs hybrid

**Deliverable:** Production-ready v1.0

---

## Expected Metrics: Rule-Based vs Hybrid (ML + Rules)

This is the core experiment. We measure each component with rules only, then with ML, to quantify the improvement.

### Test Setup
- **Test set:** 30 annotated contracts from EDGAR (NDA, MSA, Employment, License, SaaS, Lease)
- **Annotation:** Manual ground truth for each component
- **Metrics:** Precision, Recall, F1 per component

### Projected Metrics

| Component | Metric | Rule-Based (est.) | + ML (est.) | Delta | ML Method |
|-----------|--------|-------------------|-------------|-------|-----------|
| **Section hierarchy** | F1 | 0.93-0.96 | 0.95-0.97 | +2% | Minimal gain — rules already strong |
| **Clause boundaries** | F1 | 0.90-0.94 | 0.94-0.97 | +4% | Token classifier for ambiguous boundaries |
| **Definition extraction** | F1 | 0.90-0.93 | 0.93-0.96 | +3% | NER catches inline definitions rules miss |
| **Clause classification** | Macro-F1 | 0.75-0.82 | 0.89-0.94 | +12% | **Biggest ML win** — fine-tuned classifier |
| **Party extraction** | F1 | 0.80-0.87 | 0.91-0.95 | +8% | NER model for entity boundaries |
| **Exhibit detection** | F1 | 0.95-0.98 | 0.96-0.98 | +1% | Minimal gain — rules already strong |
| **Signature detection** | F1 | 0.93-0.97 | 0.95-0.98 | +2% | Minimal gain — rules already strong |
| **Cross-ref linking** | Accuracy | 0.85-0.90 | 0.90-0.94 | +4% | LLM resolves ambiguous references |
| **Document type** | Accuracy | 0.82-0.88 | 0.93-0.97 | +9% | Classifier on title + first 2 pages |
| **Risk scoring** | — | N/A | 0.78-0.85 | — | LLM-only feature |

### Where ML matters most (worth the complexity)

```
ML Improvement by Component:

Clause classification  ████████████████████  +12%   ← HIGHEST ROI
Document type          ██████████████        +9%
Party extraction       ████████████          +8%
Cross-ref linking      ████████              +4%
Clause boundaries      ████████              +4%
Definition extraction  ██████                +3%
Section hierarchy      ████                  +2%
Signature detection    ████                  +2%
Exhibit detection      ██                    +1%
```

### Key takeaway

**Rules dominate structure tasks** (section tree, exhibits, signatures) — ML adds <3%.
**ML dominates understanding tasks** (clause classification, party extraction, risk) — +8-12%.

This validates the hybrid approach: build rules first for fast, free, explainable extraction. Layer ML only where it measurably improves accuracy.

### How we'll actually measure this

```python
# lexparse/eval/benchmark.py

class LexParseBenchmark:
    def __init__(self, ground_truth_dir: str):
        self.ground_truth = self._load_annotations(ground_truth_dir)

    def run(self, parser: LexParser, contracts: list[str]) -> BenchmarkResults:
        """Run parser on contracts, compare against ground truth."""
        results = {}
        for contract_path in contracts:
            predicted = parser.parse(contract_path)
            truth = self.ground_truth[contract_path]

            results[contract_path] = {
                "section_hierarchy": self._eval_sections(predicted, truth),
                "clause_boundaries": self._eval_clauses(predicted, truth),
                "definitions": self._eval_definitions(predicted, truth),
                "clause_classification": self._eval_classification(predicted, truth),
                "party_extraction": self._eval_parties(predicted, truth),
                "exhibits": self._eval_exhibits(predicted, truth),
                "signatures": self._eval_signatures(predicted, truth),
                "cross_references": self._eval_cross_refs(predicted, truth),
            }
        return BenchmarkResults(results)

    def compare(self, results_a: BenchmarkResults, results_b: BenchmarkResults):
        """Print side-by-side comparison table."""
        ...
```

```bash
# Run benchmark: rule-based vs hybrid
python -m lexparse.eval.benchmark \
    --ground-truth ./eval/ground_truth/ \
    --contracts ./eval/contracts/ \
    --modes rule_based hybrid \
    --output ./eval/results/comparison.json
```

Output:
```
┌───────────────────────┬────────────┬────────────┬─────────┐
│ Component             │ Rule-Based │ Hybrid     │ Delta   │
├───────────────────────┼────────────┼────────────┼─────────┤
│ Section hierarchy     │ F1: 0.95   │ F1: 0.96   │ +0.01   │
│ Clause boundaries     │ F1: 0.92   │ F1: 0.95   │ +0.03   │
│ Definition extraction │ F1: 0.91   │ F1: 0.94   │ +0.03   │
│ Clause classification │ F1: 0.78   │ F1: 0.91   │ +0.13 ↑ │
│ Party extraction      │ F1: 0.83   │ F1: 0.93   │ +0.10 ↑ │
│ Exhibit detection     │ F1: 0.97   │ F1: 0.97   │ +0.00   │
│ Signature detection   │ F1: 0.95   │ F1: 0.97   │ +0.02   │
│ Cross-ref linking     │ Acc: 0.87  │ Acc: 0.92  │ +0.05   │
│ Document type         │ Acc: 0.85  │ Acc: 0.95  │ +0.10 ↑ │
├───────────────────────┼────────────┼────────────┼─────────┤
│ Overall (weighted)    │ 0.89       │ 0.94       │ +0.05   │
└───────────────────────┴────────────┴────────────┴─────────┘

↑ = ML improvement > 5% (worth the complexity)
```

---

## Repo Structure (updated with ML + eval)

```
lexparse/
├── README.md
├── LICENSE                        # Apache-2.0
├── pyproject.toml
├── lexparse/
│   ├── __init__.py                # Public API: LexParser
│   ├── parser.py                  # LexParser orchestrator
│   ├── models.py                  # Pydantic models (Contract, Clause, etc.)
│   ├── ingestors/
│   │   ├── __init__.py
│   │   ├── base.py                # Block, BaseIngestor
│   │   ├── docling_ingestor.py
│   │   └── marker_ingestor.py
│   ├── engine/                    # Rule-based extractors
│   │   ├── __init__.py
│   │   ├── section_tree.py
│   │   ├── clause_detector.py
│   │   ├── definition_extractor.py
│   │   ├── exhibit_detector.py
│   │   ├── signature_detector.py
│   │   ├── cross_ref_linker.py
│   │   ├── party_extractor.py
│   │   └── metadata_extractor.py
│   ├── ml/                        # ML-enhanced extractors
│   │   ├── __init__.py
│   │   ├── clause_classifier.py   # Fine-tuned clause type classifier
│   │   ├── ner_extractor.py       # Legal NER (parties, dates, monetary)
│   │   ├── doc_type_classifier.py # Document type classification
│   │   ├── risk_scorer.py         # LLM-based risk scoring
│   │   ├── llm_fallback.py        # LLM fallback for low-confidence
│   │   └── models/                # Saved model weights
│   │       └── .gitkeep
│   ├── output/
│   │   ├── __init__.py
│   │   ├── json_export.py
│   │   ├── markdown_export.py
│   │   └── chunker.py
│   └── eval/                      # Benchmarking
│       ├── __init__.py
│       ├── benchmark.py           # Evaluation harness
│       ├── metrics.py             # Precision, Recall, F1 calculators
│       ├── annotator.py           # Annotation helper tool
│       └── report.py              # Generate comparison tables
├── eval/                          # Evaluation data (outside package)
│   ├── contracts/                 # Test contract PDFs
│   ├── ground_truth/              # Manual annotations (JSON)
│   └── results/                   # Benchmark outputs
├── training/                      # ML training scripts
│   ├── train_clause_classifier.py
│   ├── train_ner.py
│   ├── train_doc_type.py
│   └── data/                      # Training data
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   ├── test_section_tree.py
│   ├── test_clause_detector.py
│   ├── test_definition_extractor.py
│   ├── test_exhibit_detector.py
│   ├── test_signature_detector.py
│   ├── test_cross_ref_linker.py
│   ├── test_party_extractor.py
│   ├── test_ml_classifier.py
│   ├── test_ml_ner.py
│   ├── test_integration.py
│   ├── test_integration_ml.py
│   └── test_output.py
├── examples/
│   ├── basic_usage.py
│   ├── with_ml.py
│   ├── rag_chunking.py
│   └── batch_processing.py
└── docs/
    └── contract_json_schema.json
```

---

## Dependencies (updated)

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
ml = [
    "scikit-learn>=1.3",
    "setfit>=1.0",
    "sentence-transformers>=2.0",
    "spacy>=3.7",
]
llm = [
    "anthropic>=0.30",
    "openai>=1.0",
]
all = [
    "docling>=2.0",
    "marker-pdf>=1.0",
    "scikit-learn>=1.3",
    "setfit>=1.0",
    "sentence-transformers>=2.0",
    "spacy>=3.7",
    "anthropic>=0.30",
    "openai>=1.0",
]
dev = ["pytest", "ruff", "mypy"]
```

**Install tiers:**
- `pip install lexparse` — core only, pydantic models
- `pip install "lexparse[docling]"` — rule-based parsing (most users)
- `pip install "lexparse[docling,ml]"` — rule-based + ML classifiers
- `pip install "lexparse[docling,ml,llm]"` — full hybrid with LLM fallback

---

## Key Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Docling API changes between versions | Medium | Medium | Pin version, use thin adapter layer |
| Non-standard numbering breaks section tree | High | Medium | Build numbering pattern registry, fall back to heading-based detection |
| Definition extraction misses inline definitions | Medium | Low | Start with quoted-term patterns (high precision), NER catches rest in Phase 6 |
| Clause classification accuracy too low (rules) | High | Medium | Rules are baseline only — ML classifier in Phase 5 is the real solution |
| ML training data insufficient | Medium | High | Bootstrap from CUAD + legal-clause-library, use SetFit for few-shot |
| LLM costs too high for risk scoring | Medium | Medium | Cache aggressively, batch API calls, make it opt-in |
| Scanned PDFs produce poor text | Medium | High | Defer to Phase 8, rely on Docling/Marker OCR |
| Docling is too slow for large contracts | Medium | Medium | Add caching, lazy loading; Marker as fast alternative |

---

## Test Strategy

### Unit tests
Each engine component tested in isolation with hand-crafted `Block` lists.

### Integration tests
Real PDF → full `Contract` pipeline, assertions on extracted data.

### Fixture contracts
30 real public contracts (NDA, MSA, Employment, License, SaaS, Lease) from EDGAR.

### Regression tests
When a bug is found, add the failing contract as a fixture.

### No mocks for backends
Integration tests hit real Docling/Marker — we need to know if they break.

### A/B evaluation (rule-based vs hybrid)
Every component runs in both modes on the same test set. Results tracked in `eval/results/` with timestamps so we can see improvement over time.

```
eval/results/
├── 2026-07-01_rule_based.json
├── 2026-07-15_hybrid_v1.json
├── 2026-08-01_hybrid_v2.json
└── comparison_report.md
```

---

## Timeline Summary (10 weeks)

```
Week 1     Phase 1: Foundation (rule-based parsing)
Week 2     Phase 2: All extractors (rule-based)
Week 3     Phase 3: Output layer + clause classification (keyword)
Week 4     Phase 4: Benchmark rule-based baseline ← METRICS CHECKPOINT
Week 5-6   Phase 5: ML clause classifier (SetFit / fine-tuned)
Week 7     Phase 6: NER for parties, dates, entities
Week 8-9   Phase 7: Risk scoring + LLM fallback
Week 10    Phase 8: Multi-backend, hardening, final benchmark ← METRICS COMPARISON
```

---

## What "Done" Looks Like (v1.0)

```bash
pip install "lexparse[docling,ml]"
```

```python
from lexparse import LexParser

# Rule-based only (fast, free, offline)
parser = LexParser()
contract = parser.parse("nda.pdf")

# Hybrid mode (higher accuracy)
parser = LexParser(use_ml=True, risk_scoring=True)
contract = parser.parse("nda.pdf")

assert contract.metadata.document_type == "NDA"
assert len(contract.parties) == 2
assert len(contract.definitions) > 0
assert all(c.clause_type != "unknown" for c in contract.all_clauses())
assert all(c.confidence > 0.7 for c in contract.all_clauses())
assert len(contract.signatures) == 2

# Every clause has risk scoring
for clause in contract.all_clauses():
    print(f"{clause.number} [{clause.clause_type}] risk={clause.risk_score}")
    print(f"  method={clause.extraction_method} confidence={clause.confidence}")

# RAG-ready
chunks = contract.to_chunks(max_tokens=512)
assert all(chunk["clause_type"] for chunk in chunks)
assert all(chunk["section_ref"] for chunk in chunks)
assert all(chunk["confidence"] for chunk in chunks)
```

The user chooses their tier:
- **Rule-based** — fast, free, offline, ~89% overall accuracy
- **Hybrid (ML)** — better classification + NER, ~94% overall accuracy
- **Full (ML + LLM)** — risk scoring + fallback, ~96% accuracy + risk analysis
