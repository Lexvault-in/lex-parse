"""Core data models for lexparse contract representation."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Clause Type Registry — extensible, not hardcoded
# ---------------------------------------------------------------------------

_CLAUSE_TYPE_REGISTRY: dict[str, dict] = {}


def register_clause_type(
    name: str,
    *,
    label: str = "",
    description: str = "",
    keywords: list[str] | None = None,
) -> None:
    """Register a new clause type at runtime."""
    _CLAUSE_TYPE_REGISTRY[name] = {
        "label": label or name.replace("_", " ").title(),
        "description": description,
        "keywords": keywords or [],
    }


def get_clause_types() -> dict[str, dict]:
    """Return all registered clause types."""
    return dict(_CLAUSE_TYPE_REGISTRY)


def is_valid_clause_type(name: str) -> bool:
    return name in _CLAUSE_TYPE_REGISTRY


# Built-in clause types — users can add more via register_clause_type()
_BUILTIN_CLAUSE_TYPES = {
    "confidentiality": {
        "label": "Confidentiality",
        "description": "Non-disclosure and confidential information obligations",
        "keywords": ["confidential information", "non-disclosure", "shall not disclose"],
    },
    "indemnification": {
        "label": "Indemnification",
        "description": "Hold harmless and indemnity obligations",
        "keywords": ["indemnif", "hold harmless", "defend and indemnify"],
    },
    "termination": {
        "label": "Termination",
        "description": "Contract termination rights and procedures",
        "keywords": ["terminat", "cancellation", "right to terminate"],
    },
    "limitation_of_liability": {
        "label": "Limitation of Liability",
        "description": "Caps and exclusions on liability",
        "keywords": ["limitation of liability", "aggregate liability", "consequential damages"],
    },
    "governing_law": {
        "label": "Governing Law",
        "description": "Choice of law and jurisdiction",
        "keywords": ["governing law", "governed by", "laws of the state", "jurisdiction"],
    },
    "force_majeure": {
        "label": "Force Majeure",
        "description": "Excused performance due to extraordinary events",
        "keywords": ["force majeure", "act of god", "beyond reasonable control"],
    },
    "ip_assignment": {
        "label": "IP Assignment",
        "description": "Intellectual property ownership and transfer",
        "keywords": ["intellectual property", "work for hire", "assigns all rights"],
    },
    "non_compete": {
        "label": "Non-Compete",
        "description": "Restrictions on competitive activities",
        "keywords": ["non-compete", "noncompetition", "shall not compete", "restrictive covenant"],
    },
    "non_solicitation": {
        "label": "Non-Solicitation",
        "description": "Restrictions on soliciting employees or customers",
        "keywords": ["non-solicitation", "shall not solicit", "no-solicit"],
    },
    "representations_warranties": {
        "label": "Representations & Warranties",
        "description": "Statements of fact and promises about contract subject matter",
        "keywords": ["represents and warrants", "representation", "warranty"],
    },
    "entire_agreement": {
        "label": "Entire Agreement",
        "description": "Integration clause superseding prior agreements",
        "keywords": ["entire agreement", "supersedes all prior", "constitutes the entire"],
    },
    "assignment": {
        "label": "Assignment",
        "description": "Rights and restrictions on assigning the contract",
        "keywords": ["shall not assign", "assignment", "without prior written consent"],
    },
    "notices": {
        "label": "Notices",
        "description": "How formal notices must be delivered",
        "keywords": ["notices shall be", "written notice", "notice to"],
    },
    "severability": {
        "label": "Severability",
        "description": "Survival of remaining provisions if one is invalid",
        "keywords": ["severability", "if any provision", "unenforceable"],
    },
    "waiver": {
        "label": "Waiver",
        "description": "Conditions under which rights may be waived",
        "keywords": ["waiver", "failure to enforce", "shall not constitute a waiver"],
    },
    "amendment": {
        "label": "Amendment",
        "description": "How the contract may be modified",
        "keywords": ["amendment", "modified only by", "written amendment"],
    },
    "payment": {
        "label": "Payment",
        "description": "Payment terms, schedules, and conditions",
        "keywords": ["payment", "invoice", "net 30", "due and payable"],
    },
    "insurance": {
        "label": "Insurance",
        "description": "Required insurance coverage",
        "keywords": ["insurance", "coverage", "policy", "certificate of insurance"],
    },
    "audit_rights": {
        "label": "Audit Rights",
        "description": "Right to inspect books, records, or compliance",
        "keywords": ["audit", "inspect", "right to examine", "books and records"],
    },
    "dispute_resolution": {
        "label": "Dispute Resolution",
        "description": "Arbitration, mediation, or litigation procedures",
        "keywords": ["arbitration", "mediation", "dispute resolution", "binding arbitration"],
    },
}

for _name, _info in _BUILTIN_CLAUSE_TYPES.items():
    register_clause_type(_name, **_info)

UNKNOWN_CLAUSE_TYPE = "unknown"


# ---------------------------------------------------------------------------
# Enums for non-extensible fields
# ---------------------------------------------------------------------------

class ExtractionMethod:
    RULE = "rule"
    ML = "ml"
    LLM = "llm"


class RiskLevel:
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DocumentType:
    NDA = "NDA"
    MSA = "MSA"
    EMPLOYMENT = "Employment"
    LICENSE = "License"
    SAAS = "SaaS"
    LEASE = "Lease"
    PARTNERSHIP = "Partnership"
    CONSULTING = "Consulting"
    PURCHASE = "Purchase"
    SETTLEMENT = "Settlement"
    UNKNOWN = "Unknown"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class Definition(BaseModel):
    term: str
    text: str
    section_ref: str = ""
    page: int = 0
    confidence: float = 1.0
    extraction_method: str = ExtractionMethod.RULE


class Party(BaseModel):
    name: str
    alias: str = ""
    entity_type: Optional[str] = None
    jurisdiction: Optional[str] = None
    confidence: float = 1.0
    extraction_method: str = ExtractionMethod.RULE


class CrossRef(BaseModel):
    source_clause: str
    target: str
    target_type: str = ""
    resolved: bool = False


class Clause(BaseModel):
    number: str
    title: Optional[str] = None
    text: str
    clause_type: str = UNKNOWN_CLAUSE_TYPE
    level: int = 0
    page_start: int = 0
    page_end: int = 0
    cross_references: list[CrossRef] = Field(default_factory=list)
    children: list[Clause] = Field(default_factory=list)
    confidence: float = 1.0
    extraction_method: str = ExtractionMethod.RULE
    risk_score: Optional[str] = None
    risk_reason: Optional[str] = None


class Section(BaseModel):
    number: str
    title: str = ""
    level: int = 0
    clauses: list[Clause] = Field(default_factory=list)
    children: list[Section] = Field(default_factory=list)

    def all_clauses(self) -> list[Clause]:
        result = list(self.clauses)
        for child in self.children:
            result.extend(child.all_clauses())
        return result


class Exhibit(BaseModel):
    label: str
    title: Optional[str] = None
    page_start: int = 0
    page_end: int = 0


class Signature(BaseModel):
    party: Optional[str] = None
    signer_name: Optional[str] = None
    title: Optional[str] = None
    date: Optional[str] = None
    page: int = 0


class ContractMetadata(BaseModel):
    title: Optional[str] = None
    document_type: str = DocumentType.UNKNOWN
    effective_date: Optional[str] = None
    expiration_date: Optional[str] = None
    governing_law: Optional[str] = None
    page_count: int = 0


class Contract(BaseModel):
    metadata: ContractMetadata = Field(default_factory=ContractMetadata)
    parties: list[Party] = Field(default_factory=list)
    definitions: list[Definition] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    exhibits: list[Exhibit] = Field(default_factory=list)
    signatures: list[Signature] = Field(default_factory=list)

    def all_clauses(self) -> list[Clause]:
        result: list[Clause] = []
        for section in self.sections:
            result.extend(section.all_clauses())
        return result

    def definition_index(self) -> dict[str, str]:
        return {d.term: d.text for d in self.definitions}

    def to_json(self, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent)

    def to_dict(self) -> dict:
        return self.model_dump()

    def to_markdown(self) -> str:
        lines: list[str] = []

        if self.metadata.title:
            lines.append(f"# {self.metadata.title}")
            lines.append("")

        if self.parties:
            parties_str = " and ".join(
                f"**{p.name}**" + (f' ("{p.alias}")' if p.alias else "") for p in self.parties
            )
            lines.append(f"Between {parties_str}")
            lines.append("")

        if self.definitions:
            lines.append("## Definitions")
            lines.append("")
            for defn in self.definitions:
                lines.append(f"**\"{defn.term}\"** — {defn.text}")
                lines.append("")

        for section in self.sections:
            lines.extend(self._section_to_markdown(section))

        if self.exhibits:
            lines.append("---")
            lines.append("")
            for exhibit in self.exhibits:
                title = f": {exhibit.title}" if exhibit.title else ""
                lines.append(
                    f"**{exhibit.label}**{title} (pp. {exhibit.page_start}-{exhibit.page_end})"
                )
                lines.append("")

        if self.signatures:
            lines.append("---")
            lines.append("")
            for sig in self.signatures:
                parts = [p for p in [sig.party, sig.signer_name, sig.title] if p]
                lines.append(f"**Signed:** {', '.join(parts)}")
                lines.append("")

        return "\n".join(lines)

    def _section_to_markdown(self, section: Section, depth: int = 2) -> list[str]:
        lines: list[str] = []
        prefix = "#" * min(depth, 6)
        title = f"{section.number}. {section.title}" if section.title else section.number
        lines.append(f"{prefix} {title}")
        lines.append("")

        for clause in section.clauses:
            if clause.title:
                lines.append(f"**{clause.number} {clause.title}**")
            lines.append(clause.text)
            lines.append("")

        for child in section.children:
            lines.extend(self._section_to_markdown(child, depth + 1))

        return lines

    def to_chunks(self, max_tokens: int = 512) -> list[dict]:
        chunks: list[dict] = []
        for section in self.sections:
            self._collect_chunks(section, chunks, max_tokens)
        return chunks

    def _collect_chunks(
        self, section: Section, chunks: list[dict], max_tokens: int
    ) -> None:
        for clause in section.clauses:
            text = clause.text
            if len(text.split()) <= max_tokens:
                chunks.append(self._clause_to_chunk(clause, section))
            else:
                words = text.split()
                for i in range(0, len(words), max_tokens):
                    chunk_text = " ".join(words[i : i + max_tokens])
                    chunk = self._clause_to_chunk(clause, section)
                    chunk["text"] = chunk_text
                    chunk["chunk_index"] = i // max_tokens
                    chunks.append(chunk)

        for child in section.children:
            self._collect_chunks(child, chunks, max_tokens)

    def _clause_to_chunk(self, clause: Clause, section: Section) -> dict:
        section_label = f"{section.number}. {section.title}" if section.title else section.number

        definitions_referenced = [
            d.term for d in self.definitions if d.term.lower() in clause.text.lower()
        ]

        return {
            "text": clause.text,
            "clause_number": clause.number,
            "clause_type": clause.clause_type,
            "section": section_label,
            "page_start": clause.page_start,
            "page_end": clause.page_end,
            "confidence": clause.confidence,
            "extraction_method": clause.extraction_method,
            "definitions_referenced": definitions_referenced,
            "cross_references": [cr.target for cr in clause.cross_references],
        }
