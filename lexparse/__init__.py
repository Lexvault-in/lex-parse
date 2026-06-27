"""lexparse — Contract-aware document parser for Legal AI."""

__version__ = "0.1.0"

from lexparse.models import (
    UNKNOWN_CLAUSE_TYPE,
    Clause,
    Contract,
    ContractMetadata,
    CrossRef,
    Definition,
    DocumentType,
    Exhibit,
    ExtractionMethod,
    Party,
    RiskLevel,
    Section,
    Signature,
    get_clause_types,
    is_valid_clause_type,
    register_clause_type,
)

__all__ = [
    "Clause",
    "Contract",
    "ContractMetadata",
    "CrossRef",
    "Definition",
    "DocumentType",
    "Exhibit",
    "ExtractionMethod",
    "Party",
    "RiskLevel",
    "Section",
    "Signature",
    "UNKNOWN_CLAUSE_TYPE",
    "get_clause_types",
    "is_valid_clause_type",
    "register_clause_type",
]
