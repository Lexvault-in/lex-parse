<div align="center">

# lexparse

**Contract-aware document parser for Legal AI.**

Converts PDFs and DOCX into structured, clause-level JSON — not just text, but clauses, definitions, exhibits, signatures, and cross-references.

[![PyPI](https://img.shields.io/pypi/v/lexparse.svg)](https://pypi.org/project/lexparse/)
[![Python](https://img.shields.io/pypi/pyversions/lexparse.svg)](https://pypi.org/project/lexparse/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Tests](https://github.com/Lexvault-in/lexparse/actions/workflows/tests.yml/badge.svg)](https://github.com/Lexvault-in/lexparse/actions)

[Installation](#installation) · [Quick Start](#quick-start) · [Output Format](#contractjson) · [Backends](#backends) · [Contributing](#contributing)

</div>

---

## Why lexparse?

Contracts aren't just documents — they're structured legal objects. lexparse understands that structure.

- **Clause boundaries** — splits contracts at clause level, not arbitrary token windows
- **Definition extraction** — pulls every defined term and its meaning
- **Section hierarchy** — reconstructs the full numbering tree (Articles → Sections → Subsections)
- **Clause classification** — labels clauses by type (confidentiality, indemnification, termination, etc.)
- **Cross-reference linking** — resolves "see Section 4.2" to the actual clause
- **Exhibit & schedule detection** — identifies attachments with page ranges
- **Signature block detection** — extracts signers, titles, and parties
- **Party extraction** — identifies contracting entities from the preamble
- **Clause-aware RAG chunks** — every chunk carries clause type, section, and page metadata

Built on top of [Docling](https://github.com/docling-project/docling) and [Marker](https://github.com/VikParuchuri/marker) for OCR and layout — lexparse adds the legal intelligence layer.

## Installation

```bash
# Core + Docling backend (recommended)
pip install "lexparse[docling]"

# Core + Marker backend
pip install "lexparse[marker]"

# Both backends
pip install "lexparse[all]"
```

**Requirements:** Python 3.10+

## Quick Start

```python
from lexparse import LexParser

parser = LexParser()
contract = parser.parse("service_agreement.pdf")

# Metadata
print(contract.metadata.title)         # "Master Services Agreement"
print(contract.metadata.governing_law) # "State of Delaware"
print(contract.metadata.page_count)    # 12

# Parties
for party in contract.parties:
    print(f"{party.name} (\"{party.alias}\")")
# Acme Corp ("Company")
# Widget Inc ("Client")

# Definitions
for defn in contract.definitions:
    print(f"{defn.term}: {defn.text[:60]}...")
# Confidential Information: means any information disclosed by...
# Services: means the consulting services described in Exhibit...

# Sections & Clauses
for section in contract.sections:
    print(f"{section.number}. {section.title}")
    for clause in section.clauses:
        print(f"  {clause.number} [{clause.clause_type}]")
# 1. DEFINITIONS
#   1.1 [definition]
#   1.2 [definition]
# 2. SERVICES
#   2.1 [unknown]
# 7. CONFIDENTIALITY
#   7.1 [confidentiality]
#   7.2 [confidentiality]

# Exhibits
for exhibit in contract.exhibits:
    print(f"{exhibit.label}: {exhibit.title} (pp. {exhibit.page_start}-{exhibit.page_end})")
# Exhibit A: Statement of Work (pp. 10-12)

# Signatures
for sig in contract.signatures:
    print(f"{sig.party}: {sig.signer_name}, {sig.title}")
# Acme Corp: John Smith, CEO
```

## ContractJSON

lexparse outputs a structured JSON format designed for legal AI workflows:

```json
{
  "metadata": {
    "title": "Master Services Agreement",
    "document_type": "MSA",
    "effective_date": "2024-01-15",
    "governing_law": "State of Delaware",
    "page_count": 12
  },
  "parties": [
    { "name": "Acme Corp", "alias": "Company", "entity_type": "corporation" },
    { "name": "Widget Inc", "alias": "Client", "entity_type": "corporation" }
  ],
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
      "number": "7",
      "title": "CONFIDENTIALITY",
      "level": 1,
      "clauses": [
        {
          "number": "7.1",
          "title": "Obligations",
          "text": "Each party agrees to hold in confidence...",
          "clause_type": "confidentiality",
          "page_start": 5,
          "page_end": 5,
          "cross_references": ["Section 1.3", "Section 7.2"]
        }
      ]
    }
  ],
  "exhibits": [
    { "label": "Exhibit A", "title": "Statement of Work", "page_start": 10, "page_end": 12 }
  ],
  "signatures": [
    { "party": "Acme Corp", "signer_name": "John Smith", "title": "CEO", "page": 9 }
  ]
}
```

## Clause-Aware Chunking for RAG

Standard chunkers split on token count. lexparse splits on **clause boundaries** — so your retrieval never returns half a clause.

```python
chunks = contract.to_chunks(max_tokens=512)

for chunk in chunks:
    print(chunk)
# {
#   "text": "Each party agrees to hold in confidence all Confidential Information...",
#   "clause_number": "7.1",
#   "clause_type": "confidentiality",
#   "section": "7. CONFIDENTIALITY",
#   "page": 5,
#   "definitions_referenced": ["Confidential Information"],
#   "cross_references": ["Section 1.3"]
# }
```

Each chunk carries metadata — clause type, section, page, referenced definitions — so your RAG pipeline can filter, boost, and cite accurately.

## Export Formats

```python
# Structured JSON
contract.to_json()

# Legal Markdown (preserves hierarchy)
contract.to_markdown()

# Clause-aware chunks (for RAG)
contract.to_chunks(max_tokens=512)

# Definition index
contract.definition_index()
# {"Confidential Information": "means any information...", ...}
```

## Backends

lexparse uses proven parsing libraries for OCR and layout detection, adding legal structure on top.

| Backend | Best for | Speed | Install |
|---------|----------|-------|---------|
| **Docling** (default) | General contracts, DOCX | Medium | `pip install "lexparse[docling]"` |
| **Marker** | Scanned PDFs, fast processing | Fast | `pip install "lexparse[marker]"` |

```python
# Use a specific backend
parser = LexParser(backend="marker")
contract = parser.parse("scanned_contract.pdf")
```

## Configuration

```python
parser = LexParser(
    backend="docling",            # "docling" | "marker"
)

contract = parser.parse(
    "agreement.pdf",
    extract_definitions=True,     # Extract defined terms
    extract_signatures=True,      # Detect signature blocks
    classify_clauses=True,        # Classify clause types
    resolve_cross_refs=True,      # Link cross-references
)
```

## What lexparse extracts

| Component | Method | Accuracy (v0.1) |
|-----------|--------|-----------------|
| **Section hierarchy** | Numbering pattern detection | ~95% |
| **Clause boundaries** | Section-aligned splitting | ~93% |
| **Definitions** | Pattern matching ("X" means...) | ~92% |
| **Exhibits & schedules** | Header detection | ~97% |
| **Signature blocks** | "IN WITNESS WHEREOF" + field patterns | ~95% |
| **Parties** | Preamble pattern matching | ~85% |
| **Clause classification** | Keyword matching (10 types) | ~80% |
| **Cross-references** | Regex + section tree resolution | ~88% |

Accuracy measured against annotated contracts from [legal-clause-library](https://github.com/Lexvault-in/legal-clause-library).

## Supported clause types

`confidentiality` · `indemnification` · `termination` · `limitation_of_liability` · `governing_law` · `force_majeure` · `ip_assignment` · `non_compete` · `representations_warranties` · `entire_agreement`

More types added based on community contributions and [CUAD](https://github.com/TheAtticusProject/cuad) categories.

## Architecture

```
PDF / DOCX / Image
       │
       ▼
┌─────────────────┐
│  Parsing Backend │  Docling or Marker
│  (OCR + Layout)  │  handles the hard stuff
└────────┬────────┘
         │  Structured blocks (headings, paragraphs, tables)
         ▼
┌─────────────────┐
│  Legal Engine    │  This is where lexparse adds value
│                  │
│  • Section tree  │  Numbering → hierarchy
│  • Clauses       │  Boundaries + classification
│  • Definitions   │  "X" means → extracted
│  • Exhibits      │  Schedules, appendices
│  • Signatures    │  Signing blocks
│  • Cross-refs    │  Section 4.2 → linked
│  • Parties       │  Entity extraction
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Output          │
│                  │
│  ContractJSON    │  Structured data
│  Legal Markdown  │  Human-readable
│  Clause chunks   │  RAG-ready
└─────────────────┘
```

## Part of LexVault Labs

lexparse is the foundational parser in the [LexVault Labs](https://github.com/Lexvault-in) ecosystem:

- **[lexparse](https://github.com/Lexvault-in/lexparse)** — Parse contracts (you are here)
- **[legal-clause-library](https://github.com/Lexvault-in/legal-clause-library)** — Open dataset of annotated legal clauses
- **[lexbench](https://github.com/Lexvault-in/lexbench)** — Benchmark suite for legal AI evaluation
- **[lexsearch](https://github.com/Lexvault-in/lexsearch)** — Legal search and retrieval (coming soon)

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Areas where we especially need help:
- **Contract fixtures** — share (non-confidential) contracts for testing
- **Numbering edge cases** — unusual section numbering schemes
- **Jurisdiction support** — non-US contract formats (UK, EU, India)
- **Clause types** — expand beyond the initial 10 types

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built by [LexVault Labs](https://github.com/Lexvault-in)** — open infrastructure for Legal AI.

</div>
