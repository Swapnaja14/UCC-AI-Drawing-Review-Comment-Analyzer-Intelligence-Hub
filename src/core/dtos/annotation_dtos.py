from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class BoundingBoxDTO:
    x0: float
    y0: float
    x1: float
    y1: float
    page_number: int
    confidence: float
    label: str
    source_id: Optional[str] = None
    region_role: str = "primary"  # "primary", "supporting", "markup_without_text", "marker", "highlight"
    parent_id: Optional[str] = None
    source_text: Optional[str] = None
    drop_reason: Optional[str] = None


@dataclass
class PageDetectionStatusDTO:
    page_number: int
    status: str = "ok"  # "ok", "no_markup_found", "error", "warning"
    message: str = ""
    candidates_found: int = 0
    kept: int = 0
    dropped: int = 0
    drop_reasons: Dict[str, int] = field(default_factory=dict)
    has_colored_pixels: bool = False
    warning: Optional[str] = None


@dataclass
class AnnotationResultDTO:
    drawing_id: str
    page_number: int
    regions: List[BoundingBoxDTO]
    detection_method: str
    processing_time_ms: float
    page_status: Optional[PageDetectionStatusDTO] = None


@dataclass
class DocumentAnnotationDTO:
    file_name: str
    total_pages: int
    page_results: List[AnnotationResultDTO]
    total_regions: int
    page_statuses: List[PageDetectionStatusDTO] = field(default_factory=list)
