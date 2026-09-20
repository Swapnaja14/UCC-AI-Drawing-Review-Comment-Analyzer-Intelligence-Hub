from dataclasses import dataclass
from typing import Optional
from pathlib import Path

class ExportFormat:
    EXCEL = 'xlsx'
    JSON = 'json'
    CSV = 'csv'

@dataclass
class ExportConfigDTO:
    output_path: Path
    format: str = 'xlsx'
    include_summary_sheet: bool = True
    include_confidence_scores: bool = True
    filter_status: Optional[str] = None
    drawing_id: Optional[str] = None
    project_id: Optional[str] = None
    scope: str = 'drawing'
    template_style: str = "error_tracker"  # "error_tracker" | "standard"
    date_str: Optional[str] = None
    contract_no: Optional[str] = None
    plant_name: Optional[str] = None
    epod_wo_no: Optional[str] = None
    designer_name: Optional[str] = None
    drawing_no: Optional[str] = None
    drawing_title: Optional[str] = None
    department_name: Optional[str] = None

@dataclass
class ExportResultDTO:
    output_path: Path
    format: str
    total_rows: int
    total_sheets: int
    file_size_bytes: int
    success: bool
    error_message: str = ''
