"""Base ingestor interface and shared data types."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    level: int = 0
    page: int = 0
    bbox: Optional[BBox] = None
    children: list[Block] = field(default_factory=list)
    raw_label: str = ""


class BaseIngestor:
    """Base class for all parsing backends.

    Subclasses must implement `ingest()` which takes a file path
    and returns a flat list of Block objects in reading order.
    """

    def ingest(self, file_path: str) -> list[Block]:
        raise NotImplementedError

    def supports(self, file_path: str) -> bool:
        """Check if this ingestor can handle the given file type."""
        raise NotImplementedError
