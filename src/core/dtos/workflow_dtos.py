"""
src/core/dtos/workflow_dtos.py
Data Transfer Objects (DTOs) for Processing Workflow & File Validation.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path


class WorkflowState(Enum):
    IDLE = auto()
    FILE_VALIDATING = auto()
    METADATA_EXTRACTING = auto()
    ANNOTATION_DETECTING = auto()
    OCR_PROCESSING = auto()
    AI_CLASSIFYING = auto()
    PERSISTING = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass(frozen=True)
class FileValidationResultDTO:
    """Result container for file validation checks."""
    file_path: Path
    is_valid: bool
    file_name: str
    file_size_mb: float
    file_hash_sha256: str
    error_message: Optional[str] = None


@dataclass(frozen=True)
class WorkflowStepDTO:
    """Progress snapshot for a single step in the processing workflow."""
    step_name: str
    state: WorkflowState
    progress_percentage: int     # 0-100%
    message: str
    started_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class WorkflowResultDTO:
    """Final output container of the processing workflow pipeline."""
    drawing_id: str
    file_name: str
    total_pages: int
    is_scanned: bool
    status: str
    total_comments_found: int = 0
    processing_duration_seconds: float = 0.0
    annotation_result: Optional[Any] = None
