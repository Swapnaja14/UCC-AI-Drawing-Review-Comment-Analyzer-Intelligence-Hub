import json
import csv
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, date

from src.core.dtos.export_dtos import ExportConfigDTO, ExportResultDTO, ExportFormat
from src.infrastructure.storage.repository import (
    CommentRepository,
    ProjectRepository,
    DrawingRepository,
)
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
    logger.warning("openpyxl is not installed. Excel export will not work.")


class ExportService:
    """
    Export Service generating structured reports including the specialized
    4-Tier Multi-Header Error Tracker Sheet matching standard engineering review formats.
    """

    def __init__(
        self,
        comment_repo: CommentRepository,
        project_repo: Optional[ProjectRepository] = None,
        drawing_repo: Optional[DrawingRepository] = None,
    ):
        self.comment_repo = comment_repo
        self.project_repo = project_repo
        self.drawing_repo = drawing_repo

    def export_drawing_comments(self, config: ExportConfigDTO) -> ExportResultDTO:
        """Export review comments to the requested format (Excel, JSON, or CSV)."""
        try:
            if config.drawing_id:
                comments = self.comment_repo.get_comments_for_drawing(config.drawing_id)
            else:
                comments = []

            if config.filter_status:
                comments = [c for c in comments if c.get('status') == config.filter_status]

            # Resolve drawing/project metadata fallbacks if not explicitly provided
            self._enrich_config_metadata(config)

            if config.format == ExportFormat.EXCEL:
                return self._export_to_excel(comments, config)
            elif config.format == ExportFormat.JSON:
                return self._export_to_json(comments, config)
            elif config.format == ExportFormat.CSV:
                return self._export_to_csv(comments, config)
            else:
                return ExportResultDTO(
                    output_path=config.output_path,
                    format=config.format,
                    total_rows=0,
                    total_sheets=0,
                    file_size_bytes=0,
                    success=False,
                    error_message=f"Unsupported format: {config.format}"
                )
        except Exception as e:
            logger.error(f"Export failed: {str(e)}")
            return ExportResultDTO(
                output_path=config.output_path,
                format=config.format,
                total_rows=0,
                total_sheets=0,
                file_size_bytes=0,
                success=False,
                error_message=str(e)
            )

    def _enrich_config_metadata(self, config: ExportConfigDTO) -> None:
        """Enrich config with drawing and project metadata if available."""
        if not config.date_str:
            config.date_str = date.today().strftime("%Y-%m-%d")

        if config.drawing_id and self.drawing_repo:
            try:
                dwg = self.drawing_repo.get_drawing_by_id(config.drawing_id)
                if dwg:
                    if not config.drawing_no:
                        # Use file_name without extension or drawing id
                        fname = dwg.get("file_name", "")
                        config.drawing_no = fname.rsplit(".", 1)[0] if "." in fname else (fname or config.drawing_id)
                    if not config.drawing_title:
                        config.drawing_title = dwg.get("title") or "Engineering Review Drawing"
                    if not config.designer_name and dwg.get("author"):
                        config.designer_name = dwg.get("author")
            except Exception as ex:
                logger.debug(f"Could not fetch drawing metadata: {ex}")

    def _export_to_excel(self, comments: List[Dict[str, Any]], config: ExportConfigDTO) -> ExportResultDTO:
        """
        Generate Excel spreadsheet formatted according to the 4-tier
        Error Tracker Sheet specification:
        - Row 1: Group Banners ('Standard Input Field', 'Auto Read by Program')
        - Row 2: Column Numbers (1, 2, 3, 4, 6, 7, 8, 9, 10)
        - Row 3: Data Source / Role ('User Input', 'Drawing # from Title Block', etc.)
        - Row 4: Column Header Names ('Date', 'Contract #', 'Plant Name', etc.)
        - Rows 5+: Formatted Data Rows
        """
        if not OPENPYXL_AVAILABLE:
            raise ImportError("openpyxl is required for Excel export")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Error Tracker"
        ws.views.sheetView[0].showGridLines = True

        # Styles & Color Palette
        ORANGE_FILL = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
        GREEN_FILL  = PatternFill(start_color="92D050", end_color="92D050", fill_type="solid")
        
        FONT_GROUP   = Font(name="Segoe UI", size=11, bold=True, color="000000")
        FONT_NUM     = Font(name="Segoe UI", size=11, bold=True, color="000000")
        FONT_ROLE    = Font(name="Segoe UI", size=10, bold=True, color="000000")
        FONT_HEADER  = Font(name="Segoe UI", size=11, bold=True, color="000000")
        FONT_DATA    = Font(name="Segoe UI", size=10, color="000000")
        
        THIN_SIDE    = Side(border_style="thin", color="000000")
        THIN_BORDER  = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)

        ALIGN_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ALIGN_LEFT   = Alignment(horizontal="left", vertical="center", wrap_text=True)

        # -------------------------------------------------------------------
        # ROW 1: Grouping Banners (Standard Input Field vs Auto Read by Program)
        # -------------------------------------------------------------------
        ws.row_dimensions[1].height = 28
        
        row1_cells = [
            (1, "Standard Input Field", ORANGE_FILL),
            (2, "",                     ORANGE_FILL),
            (3, "Auto Read by Program", GREEN_FILL),
            (4, "Standard Input Field", ORANGE_FILL),
            (5, "",                     ORANGE_FILL),
            (6, "Auto Read by Program", GREEN_FILL),
            (7, "",                     GREEN_FILL),
            (8, "",                     GREEN_FILL),
            (9, "",                     GREEN_FILL),
            (10, "",                    GREEN_FILL),
        ]
        for col_idx, val, fill in row1_cells:
            c = ws.cell(row=1, column=col_idx, value=val)
            c.fill = fill
            c.font = FONT_GROUP
            c.alignment = ALIGN_CENTER
            c.border = THIN_BORDER

        # Merge header bands
        ws.merge_cells("A1:B1")
        ws.merge_cells("D1:E1")
        ws.merge_cells("F1:J1")

        # -------------------------------------------------------------------
        # ROW 2: Column Index Numbering
        # -------------------------------------------------------------------
        ws.row_dimensions[2].height = 22
        col_numbers = [
            (1, 1, ORANGE_FILL),
            (2, 2, ORANGE_FILL),
            (3, 3, GREEN_FILL),
            (4, 4, ORANGE_FILL),
            (5, 6, ORANGE_FILL),   # Column 6 in template numbering
            (6, 7, GREEN_FILL),
            (7, 8, GREEN_FILL),
            (8, 9, GREEN_FILL),
            (9, 10, GREEN_FILL),
            (10, 11, GREEN_FILL),
        ]
        for col_idx, num_val, fill in col_numbers:
            c = ws.cell(row=2, column=col_idx, value=num_val)
            c.fill = fill
            c.font = FONT_NUM
            c.alignment = ALIGN_CENTER
            c.border = THIN_BORDER

        # -------------------------------------------------------------------
        # ROW 3: Data Source / Role Description
        # -------------------------------------------------------------------
        ws.row_dimensions[3].height = 55
        col_roles = [
            (1, "User Input", ORANGE_FILL),
            (2, "User Input", ORANGE_FILL),
            (3, "User Input", GREEN_FILL),
            (4, "User Input", ORANGE_FILL),
            (5, "User Input", ORANGE_FILL),
            (6, "Drawing # from\nTitle Block", GREEN_FILL),
            (7, "Drawing # from\nTitle Block", GREEN_FILL),
            (8, "Drawing\nCommentary", GREEN_FILL),
            (9, "Classify Error\nbased on Error\nDescription", GREEN_FILL),
            (10, "Engineering\nDepartment", GREEN_FILL),
        ]
        for col_idx, role_text, fill in col_roles:
            c = ws.cell(row=3, column=col_idx, value=role_text)
            c.fill = fill
            c.font = FONT_ROLE
            c.alignment = ALIGN_CENTER
            c.border = THIN_BORDER

        # -------------------------------------------------------------------
        # ROW 4: Primary Column Header Names
        # -------------------------------------------------------------------
        ws.row_dimensions[4].height = 28
        headers = [
            (1, "Date", ORANGE_FILL),
            (2, "Contract #", ORANGE_FILL),
            (3, "Plant Name", GREEN_FILL),
            (4, "E-Pod WO #", ORANGE_FILL),
            (5, "UCC-I Designer", ORANGE_FILL),
            (6, "Drawing #", GREEN_FILL),
            (7, "Drawing Title", GREEN_FILL),
            (8, "Errors Description", GREEN_FILL),
            (9, "Category of Error", GREEN_FILL),
            (10, "Engineering Department", GREEN_FILL),
        ]
        for col_idx, hdr_text, fill in headers:
            c = ws.cell(row=4, column=col_idx, value=hdr_text)
            c.fill = fill
            c.font = FONT_HEADER
            c.alignment = ALIGN_CENTER
            c.border = THIN_BORDER

        # -------------------------------------------------------------------
        # ROWS 5+: Data Rows
        # -------------------------------------------------------------------
        date_val     = config.date_str or date.today().strftime("%Y-%m-%d")
        contract_val = config.contract_no or ""
        plant_val    = config.plant_name or ""
        epod_val     = config.epod_wo_no or ""
        designer_val = config.designer_name or ""
        drawing_no   = config.drawing_no or (config.drawing_id or "")
        drawing_ttl  = config.drawing_title or ""

        start_row = 5
        if not comments:
            # If no comments, insert 5 empty placeholder rows with grid borders
            for r in range(start_row, start_row + 5):
                ws.row_dimensions[r].height = 24
                for col_idx in range(1, 11):
                    c = ws.cell(row=r, column=col_idx, value="")
                    c.font = FONT_DATA
                    c.border = THIN_BORDER
        else:
            for idx, comment in enumerate(comments, start_row):
                desc = comment.get('raw_text') or comment.get('cleaned_text') or ""
                cat  = comment.get('category_name') or comment.get('category') or "Uncategorized"
                dept = comment.get('department_name') or comment.get('department') or config.department_name or "Unassigned"
                reviewer = comment.get('reviewer_id') or designer_val

                row_data = [
                    (1, date_val, ALIGN_CENTER),
                    (2, contract_val, ALIGN_CENTER),
                    (3, plant_val, ALIGN_LEFT),
                    (4, epod_val, ALIGN_CENTER),
                    (5, reviewer, ALIGN_LEFT),
                    (6, drawing_no, ALIGN_CENTER),
                    (7, drawing_ttl, ALIGN_LEFT),
                    (8, desc, ALIGN_LEFT),
                    (9, cat, ALIGN_LEFT),
                    (10, dept, ALIGN_LEFT),
                ]

                # Dynamically set row height based on text length
                text_len = len(desc)
                if text_len > 120:
                    ws.row_dimensions[idx].height = 65
                elif text_len > 60:
                    ws.row_dimensions[idx].height = 45
                else:
                    ws.row_dimensions[idx].height = 28

                for col_idx, cell_value, alignment in row_data:
                    c = ws.cell(row=idx, column=col_idx, value=cell_value)
                    c.font = FONT_DATA
                    c.alignment = alignment
                    c.border = THIN_BORDER

        # -------------------------------------------------------------------
        # Set Explicit Column Widths for readability
        # -------------------------------------------------------------------
        col_widths = {
            "A": 15,  # Date
            "B": 18,  # Contract #
            "C": 22,  # Plant Name
            "D": 18,  # E-Pod WO #
            "E": 20,  # UCC-I Designer
            "F": 22,  # Drawing #
            "G": 28,  # Drawing Title
            "H": 55,  # Errors Description
            "I": 30,  # Category of Error
            "J": 25,  # Engineering Department
        }
        for col_letter, width in col_widths.items():
            ws.column_dimensions[col_letter].width = width

        # Optional Summary Sheet
        total_sheets = 1
        if config.include_summary_sheet and comments:
            summary_ws = wb.create_sheet(title="Executive Summary")
            summary_ws.views.sheetView[0].showGridLines = True
            
            # Header
            summary_ws.cell(row=1, column=1, value="Review Metrics Summary").font = FONT_GROUP
            summary_ws.cell(row=3, column=1, value="Metric").font = FONT_HEADER
            summary_ws.cell(row=3, column=2, value="Count").font = FONT_HEADER
            summary_ws.cell(row=3, column=1).fill = ORANGE_FILL
            summary_ws.cell(row=3, column=2).fill = ORANGE_FILL
            summary_ws.cell(row=3, column=1).border = THIN_BORDER
            summary_ws.cell(row=3, column=2).border = THIN_BORDER

            summary_ws.cell(row=4, column=1, value="Total Comments Extracted").border = THIN_BORDER
            summary_ws.cell(row=4, column=2, value=len(comments)).border = THIN_BORDER

            statuses = [c.get('status', 'Pending') for c in comments]
            for idx, stat in enumerate(['Approved', 'Rejected', 'Pending', 'Flagged'], start=5):
                summary_ws.cell(row=idx, column=1, value=f"{stat} Status").border = THIN_BORDER
                summary_ws.cell(row=idx, column=2, value=statuses.count(stat)).border = THIN_BORDER

            summary_ws.column_dimensions["A"].width = 30
            summary_ws.column_dimensions["B"].width = 15
            total_sheets += 1

        os.makedirs(os.path.dirname(os.path.abspath(config.output_path)), exist_ok=True)
        wb.save(config.output_path)
        file_size = os.path.getsize(config.output_path)

        return ExportResultDTO(
            output_path=config.output_path,
            format=config.format,
            total_rows=len(comments),
            total_sheets=total_sheets,
            file_size_bytes=file_size,
            success=True
        )

    def _export_to_json(self, comments: List[Dict[str, Any]], config: ExportConfigDTO) -> ExportResultDTO:
        data = {
            "metadata": {
                "export_date": datetime.now().isoformat(),
                "total_records": len(comments),
                "drawing_id": config.drawing_id,
                "contract_no": config.contract_no or "",
                "plant_name": config.plant_name or "",
                "epod_wo_no": config.epod_wo_no or "",
                "designer_name": config.designer_name or "",
                "drawing_no": config.drawing_no or "",
                "drawing_title": config.drawing_title or "",
                "department_name": config.department_name or "",
            },
            "comments": comments
        }
        
        os.makedirs(os.path.dirname(os.path.abspath(config.output_path)), exist_ok=True)
        with open(config.output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
            
        file_size = os.path.getsize(config.output_path)

        return ExportResultDTO(
            output_path=config.output_path,
            format=config.format,
            total_rows=len(comments),
            total_sheets=1,
            file_size_bytes=file_size,
            success=True
        )

    def _export_to_csv(self, comments: List[Dict[str, Any]], config: ExportConfigDTO) -> ExportResultDTO:
        os.makedirs(os.path.dirname(os.path.abspath(config.output_path)), exist_ok=True)
        
        # Produce the Error Tracker CSV format matching the 10 columns
        headers = [
            "Date",
            "Contract #",
            "Plant Name",
            "E-Pod WO #",
            "UCC-I Designer",
            "Drawing #",
            "Drawing Title",
            "Errors Description",
            "Category of Error",
            "Engineering Department"
        ]

        date_val     = config.date_str or date.today().strftime("%Y-%m-%d")
        contract_val = config.contract_no or ""
        plant_val    = config.plant_name or ""
        epod_val     = config.epod_wo_no or ""
        designer_val = config.designer_name or ""
        drawing_no   = config.drawing_no or (config.drawing_id or "")
        drawing_ttl  = config.drawing_title or ""

        with open(config.output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Write header
            writer.writerow(headers)
            for comment in comments:
                desc = comment.get('raw_text') or comment.get('cleaned_text') or ""
                cat  = comment.get('category_name') or comment.get('category') or "Uncategorized"
                dept = comment.get('department_name') or comment.get('department') or config.department_name or "Unassigned"
                reviewer = comment.get('reviewer_id') or designer_val
                writer.writerow([
                    date_val,
                    contract_val,
                    plant_val,
                    epod_val,
                    reviewer,
                    drawing_no,
                    drawing_ttl,
                    desc,
                    cat,
                    dept,
                ])
            
        file_size = os.path.getsize(config.output_path)

        return ExportResultDTO(
            output_path=config.output_path,
            format=config.format,
            total_rows=len(comments),
            total_sheets=1,
            file_size_bytes=file_size,
            success=True
        )
