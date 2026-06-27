# LexVault Labs — Sprint 1 Plan

## Goal
Ship 3 foundational repos that work together and tell a coherent story:
**lexparse** (parse contracts) → **legal-clause-library** (curated data) → **lexbench** (measure quality)

---

## 1. lexparse — Contract-Aware Document Parser

### What it is
A Python library that converts legal documents (PDF, DOCX, scanned images) into structured, clause-level output. Not a general-purpose parser — purpose-built for contracts and legal documents.

### Why not just use Docling/Marker/MinerU?
| Tool | Strength | Gap for Legal |
|------|----------|---------------|
| Docling (IBM) | Best general doc parser, unified DoclingDocument format | No clause awareness, no legal structure extraction |
| MinerU | Great OCR + layout, 109 languages | No contract-specific logic |
| Marker | Fast PDF→Markdown, 95%+ accuracy | Flat markdown output, no semantic structure |
| OpenParse | Smart chunking, visual layout | No legal domain knowledge |
| Unstructured | Enterprise ETL pipeline | Generic elements, no clause/definition extraction |
| ColPali | OCR-free vision retrieval | Retrieval only, not parsing |

**The gap:** All of these parse documents. None of them understand contracts. They'll give you paragraphs — lexparse gives you clauses, definitions, exhibits, signatures, and cross-references.

### Architecture

```
Input (PDF / DOCX / Image)
    │
    ▼
┌─────────────────────────────┐
│  Document Ingestion Layer   │
│  (Docling or Marker backend)│  ← Don't reinvent OCR/layout
└─────────────┬───────────────┘
              │ Raw structured blocks
              ▼
┌─────────────────────────────┐
│  Legal Structure Engine     │
│  ┌───────────────────────┐  │
│  │ Clause Detector       │  │  ← Identify clause boundaries
│  │ Definition Extractor  │  │  ← Pull "means" / "shall mean"
│  │ Section Hierarchy     │  │  ← Numbering → tree structure
│  │ Exhibit Detector      │  │  ← Identify schedules/exhibits
│  │ Signature Detector    │  │  ← Find signature blocks
│  │ Cross-ref Resolver    │  │  ← Link "Section 4.2" references
│  │ Party Extractor       │  │  ← Identify contracting parties
│  └───────────────────────┘  │
└─────────────┬───────────────┘
              │ Legal document tree
              ▼
┌─────────────────────────────┐
│  Output Layer               │
│  • ContractJSON (structured)│
│  • Legal Markdown           │
│  • Clause-level chunks      │
│  • Definition index         │
└─────────────────────────────┘
```

### Key Design Decisions

1. **Don't reinvent OCR/layout** — Use Docling or Marker as the parsing backend. Our value is the legal structure layer on top.
2. **Pluggable backends** — Support multiple underlying parsers (Docling, Marker, MinerU) via adapter pattern.
3. **ContractJSON schema** — Define a standard JSON schema for parsed contracts. This becomes the interchange format across all LexVault tools.
4. **Clause-first chunking** — Chunks aligned to clause boundaries, not arbitrary token windows. This is what makes RAG actually work for legal.
5. **Rule-based + ML hybrid** — Start with regex/heuristics for structure detection (numbering patterns, "WHEREAS", "NOW THEREFORE", definition patterns). Add ML classifiers later.

### ContractJSON Schema (v0.1)

```json
{
  "metadata": {
    "title": "Master Services Agreement",
    "document_type": "MSA",
    "parties": ["Acme Corp", "Widget Inc"],
    "effective_date": "2024-01-15",
    "governing_law": "State of Delaware",
    "page_count": 12
  },
  "definitions": [
    {
      "term": "Confidential Information",
      "text": "means any information disclosed by either party...",
      "section_ref": "1.3",
      "page": 2
    }
  ],
  "sections": [
    {
      "number": "1",
      "title": "DEFINITIONS",
      "level": 1,
      "clauses": [
        {
          "number": "1.1",
          "title": "Agreement",
          "text": "...",
          "clause_type": "definition",
          "page_start": 1,
          "page_end": 1,
          "cross_references": ["Section 4.2", "Exhibit A"],
          "risk_indicators": []
        }
      ]
    }
  ],
  "exhibits": [
    {
      "label": "Exhibit A",
      "title": "Statement of Work",
      "page_start": 10,
      "page_end": 12
    }
  ],
  "signatures": [
    {
      "party": "Acme Corp",
      "signer_name": "John Smith",
      "title": "CEO",
      "page": 9
    }
  ]
}
```

### Tech Stack
- **Language:** Python 3.10+
- **Parsing backends:** Docling (primary), Marker (alternative)
- **Structure detection:** regex + spaCy for NER
- **Output:** Pydantic models → JSON/Markdown
- **Testing:** pytest + contracts from legal-clause-library
- **Packaging:** PyPI (`pip install lexparse`)

### Milestones

| Version | Scope | Target |
|---------|-------|--------|
| v0.1.0 | PDF→ContractJSON with clause detection, definition extraction, section hierarchy | Week 1-2 |
| v0.2.0 | DOCX support, exhibit detection, signature detection, cross-reference linking | Week 3-4 |
| v0.3.0 | Pluggable backends (Marker, MinerU), party extraction, clause classification | Week 5-6 |
| v0.4.0 | Scanned PDF support (OCR pipeline), confidence scores, batch processing | Week 7-8 |

---

## 2. legal-clause-library — Open Legal Clause Dataset

### What it is
A curated, annotated, open-source library of legal clauses sourced from public contracts. The dataset that powers lexparse testing and lexbench evaluation.

### Why it matters
- No good open clause dataset exists for legal AI
- CUAD has annotations but is research-focused, not builder-friendly
- Clause libraries are high-visibility, low-engineering-effort repos that attract stars and citations

### Data Sources (Public Domain / Open)
1. **SEC EDGAR** — Public company contracts (10-K/10-Q exhibits)
2. **Government contracts** — GSA, state procurement
3. **Open-source legal templates** — Creative Commons licensed templates
4. **Academic datasets** — CUAD, Atticus (with proper attribution)

### Schema

```json
{
  "clause_id": "conf-001",
  "clause_type": "confidentiality",
  "text": "Each party agrees to hold in confidence all Confidential Information...",
  "source": {
    "document": "EDGAR/0001234567-24-000123",
    "section": "7.1",
    "document_type": "MSA"
  },
  "annotations": {
    "risk_level": "standard",
    "jurisdiction": "US-DE",
    "party_favoring": "mutual",
    "key_terms": ["confidential information", "disclosure", "obligations"],
    "related_clauses": ["conf-002", "conf-003"]
  },
  "metadata": {
    "added_date": "2026-07-01",
    "contributor": "lexvault-team",
    "verified": true
  }
}
```

### Clause Types to Cover (v1)

| Category | Types | Target Count |
|----------|-------|--------------|
| Confidentiality | NDA, mutual NDA, carve-outs | 20 |
| Indemnification | Mutual, one-way, cap, carve-outs | 20 |
| Termination | For cause, convenience, notice periods | 15 |
| Limitation of Liability | Cap, exclusions, consequential | 15 |
| IP Assignment | Work-for-hire, license-back, joint ownership | 10 |
| Non-compete | Geographic, temporal, scope | 10 |
| Governing Law | Choice of law, jurisdiction, arbitration | 10 |
| Force Majeure | Standard, pandemic-era, carve-outs | 10 |
| Representations & Warranties | Authority, compliance, no conflicts | 10 |
| Miscellaneous | Entire agreement, severability, waiver, notices | 10 |

**Total v1 target: ~130 annotated clauses**

### Repo Structure

```
legal-clause-library/
├── README.md
├── LICENSE (CC-BY-4.0)
├── schema/
│   └── clause-schema.json        # JSON Schema for validation
├── clauses/
│   ├── confidentiality/
│   │   ├── conf-001.json
│   │   ├── conf-002.json
│   │   └── ...
│   ├── indemnification/
│   ├── termination/
│   └── ...
├── scripts/
│   ├── validate.py               # Validate all clauses against schema
│   └── stats.py                  # Dataset statistics
├── CONTRIBUTING.md
└── CHANGELOG.md
```

### Milestones

| Version | Scope | Target |
|---------|-------|--------|
| v0.1.0 | 50 clauses across 5 types, JSON schema, validation script | Week 1-2 |
| v0.2.0 | 130 clauses across 10 types, contributor guide | Week 3-4 |
| v0.3.0 | Risk annotations, jurisdiction tags, embeddings | Week 5-6 |
| v1.0.0 | 300+ clauses, community contributions, HuggingFace mirror | Week 8+ |

---

## 3. lexbench — Legal AI Evaluation Suite

### What it is
A benchmark suite for evaluating legal AI systems — parsers, retrievers, and contract review tools. The "GLUE/SuperGLUE for Legal AI."

### Why it matters
- Existing legal benchmarks (LegalBench, CUAD) focus on LLM evaluation, not tooling evaluation
- No benchmark exists for measuring parser quality on contracts
- A benchmark gives LexVault authority — everyone compares against your numbers

### Benchmark Tasks (v0.1)

#### Task 1: Clause Extraction Accuracy
- **Input:** Raw contract PDF
- **Expected:** List of clauses with boundaries
- **Metrics:** Precision, Recall, F1 at clause level
- **Test set:** 20 contracts from legal-clause-library

#### Task 2: Definition Extraction
- **Input:** Raw contract PDF
- **Expected:** List of defined terms + definitions
- **Metrics:** Exact match, partial match, F1
- **Test set:** 20 contracts with annotated definitions

#### Task 3: Section Hierarchy
- **Input:** Raw contract PDF
- **Expected:** Section tree with numbering
- **Metrics:** Tree edit distance, level accuracy
- **Test set:** 20 contracts with annotated structure

#### Task 4: Clause Classification
- **Input:** Extracted clause text
- **Expected:** Clause type label
- **Metrics:** Accuracy, macro-F1
- **Test set:** Clauses from legal-clause-library

#### Task 5: Contract QA (stretch)
- **Input:** Contract + question
- **Expected:** Answer with source clause
- **Metrics:** Answer accuracy, citation accuracy
- **Test set:** 50 QA pairs across 10 contracts

### Architecture

```
lexbench/
├── README.md
├── LICENSE (Apache-2.0)
├── lexbench/
│   ├── __init__.py
│   ├── runner.py                 # Run all benchmarks
│   ├── tasks/
│   │   ├── clause_extraction.py
│   │   ├── definition_extraction.py
│   │   ├── section_hierarchy.py
│   │   ├── clause_classification.py
│   │   └── contract_qa.py
│   ├── metrics/
│   │   ├── precision_recall.py
│   │   ├── tree_edit_distance.py
│   │   └── citation_accuracy.py
│   ├── adapters/                 # Plug in any parser
│   │   ├── base.py
│   │   ├── lexparse_adapter.py
│   │   ├── docling_adapter.py
│   │   └── marker_adapter.py
│   └── report.py                # Generate comparison tables
├── data/
│   ├── clause_extraction/
│   ├── definition_extraction/
│   └── ...
├── results/                     # Published benchmark results
│   └── leaderboard.json
└── pyproject.toml
```

### Usage (target API)

```python
from lexbench import LexBench
from lexbench.adapters import LexParseAdapter, DoclingAdapter

bench = LexBench(tasks=["clause_extraction", "definition_extraction"])

results = bench.run(
    adapters=[LexParseAdapter(), DoclingAdapter()],
    data_dir="./data"
)

bench.report(results)  # Prints comparison table
bench.export(results, "results/run_2026_07.json")
```

```
┌─────────────────────┬──────────┬─────────┬────────┐
│ Task                │ lexparse │ docling │ marker │
├─────────────────────┼──────────┼─────────┼────────┤
│ Clause Extraction   │ 0.89     │ 0.62    │ 0.58   │
│ Definition Extract  │ 0.92     │ 0.71    │ 0.65   │
│ Section Hierarchy   │ 0.85     │ 0.78    │ 0.72   │
│ Clause Classification│ 0.87    │ N/A     │ N/A    │
└─────────────────────┴──────────┴─────────┴────────┘
```

### Milestones

| Version | Scope | Target |
|---------|-------|--------|
| v0.1.0 | 2 tasks (clause extraction, definition extraction), lexparse adapter | Week 3-4 |
| v0.2.0 | All 5 tasks, Docling + Marker adapters, leaderboard JSON | Week 5-6 |
| v0.3.0 | CLI runner, HTML report, CI integration | Week 7-8 |
| v1.0.0 | Public leaderboard website, community submissions | Week 10+ |

---

## Sprint 1 Timeline (8 weeks)

```
Week 1-2:  lexparse v0.1 + legal-clause-library v0.1
           ├── Set up repos, CI, packaging
           ├── Implement Docling backend + clause detector
           ├── Curate first 50 clauses
           └── Define ContractJSON schema

Week 3-4:  lexparse v0.2 + legal-clause-library v0.2 + lexbench v0.1
           ├── DOCX support, exhibit/signature detection
           ├── Expand to 130 clauses
           └── First 2 benchmark tasks

Week 5-6:  lexparse v0.3 + lexbench v0.2
           ├── Pluggable backends, party extraction
           ├── All 5 benchmark tasks
           └── Docling/Marker adapters for lexbench

Week 7-8:  lexparse v0.4 + lexbench v0.3
           ├── OCR pipeline, batch processing
           ├── CLI runner, HTML reports
           └── First public benchmark results published
```

## Tech Stack Summary

| Tool | Purpose |
|------|---------|
| Python 3.10+ | All 3 repos |
| Docling | Primary parsing backend |
| Marker | Alternative parsing backend |
| Pydantic | Data models & validation |
| spaCy | NER for party/entity extraction |
| pytest | Testing |
| PyPI | Package distribution |
| GitHub Actions | CI/CD |
| HuggingFace Hub | Dataset hosting (clause library) |

## Repos Worth Studying Before Building

### Must study (directly relevant)
| Repo | What to learn |
|------|---------------|
| [Docling](https://github.com/docling-project/docling) | DoclingDocument format, pipeline architecture, how to extend |
| [Marker](https://github.com/VikParuchuri/marker) | Block-based parsing, JSON tree output, heuristic accuracy |
| [OpenParse](https://github.com/Filimoa/open-parse) | Semantic chunking approach, visual layout analysis |
| [CUAD](https://github.com/TheAtticusProject/cuad) | Contract annotation schema, clause categories |

### Should study (architecture inspiration)
| Repo | What to learn |
|------|---------------|
| [MinerU](https://github.com/opendatalab/MinerU) | VLM+OCR dual engine, multi-backend architecture |
| [Unstructured](https://github.com/Unstructured-IO/unstructured) | Element types, partitioning pattern, enterprise patterns |
| [ColPali](https://github.com/illuin-tech/colpali) | Vision embeddings for future lexsearch integration |
| [LegalBench](https://github.com/HazyResearch/legalbench) | Legal task design, evaluation methodology |

## Success Criteria (End of Sprint 1)

- [ ] `pip install lexparse` works, parses a real contract PDF into ContractJSON
- [ ] legal-clause-library has 130+ annotated clauses on GitHub + HuggingFace
- [ ] lexbench can compare lexparse vs Docling vs Marker on clause extraction
- [ ] All 3 repos have clean READMEs, CI, and Apache-2.0 / CC-BY-4.0 licenses
- [ ] At least 1 blog post / Twitter thread announcing the project
- [ ] Combined GitHub stars target: 100+ in first month
