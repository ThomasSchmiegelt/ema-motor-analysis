from .detection.config import DetectionConfig
from .model import ConnectionCandidate, ConnectionGraph, Part
from .pipeline import detect_connections, detect_connections_in_document

__all__ = [
    "detect_connections", "detect_connections_in_document", "DetectionConfig",
    "Part", "ConnectionCandidate", "ConnectionGraph",
]
