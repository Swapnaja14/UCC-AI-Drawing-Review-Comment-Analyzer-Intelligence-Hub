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


@dataclass(frozen=True)
class BatchWorkflowProgressDTO:
    """Progress snapshot for a batch workflow run across multiple drawing files."""
    overall_progress_percentage: int   # 0-100%
    current_file_index: int            # 1-indexed (e.g. file 2 of 5)
    total_files: int
    current_file_name: str
    step_snapshot: WorkflowStepDTO


@dataclass(frozen=True)
class BatchWorkflowResultDTO:
    """Summary container of a completed multi-file/zip batch processing workflow."""
    total_files_processed: int
    successful_files_count: int
    failed_files_count: int
    total_comments_found: int
    total_duration_seconds: float
    results: List[WorkflowResultDTO] = field(default_factory=list)
    failed_files: List[Dict[str, str]] = field(default_factory=list)  # list of {"file_name": ..., "error": ...}

