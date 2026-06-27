"""Document ingestors — parsing backends for lexparse."""

from lexparse.ingestors.base import BaseIngestor, BBox, Block, BlockType


def get_ingestor(backend: str = "docling") -> BaseIngestor:
    """Factory to get an ingestor by backend name."""
    if backend == "docling":
        from lexparse.ingestors.docling_ingestor import DoclingIngestor
        return DoclingIngestor()
    elif backend == "marker":
        from lexparse.ingestors.marker_ingestor import MarkerIngestor
        return MarkerIngestor()
    else:
        raise ValueError(f"Unknown backend: {backend}. Use 'docling' or 'marker'.")


__all__ = [
    "BaseIngestor",
    "BBox",
    "Block",
    "BlockType",
    "get_ingestor",
]
