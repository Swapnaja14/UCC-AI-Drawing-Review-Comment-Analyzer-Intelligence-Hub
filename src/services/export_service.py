import json
import csv
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from pathlib import Path

from src.core.dtos.export_dtos import ExportConfigDTO, ExportResultDTO, ExportFormat
from src.infrastructure.storage.repository import (
    CommentRepository,
    ProjectRepository,
    DrawingRepository,
    EngineeringDepartmentRepository,
    ExportHistoryRepository,
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
    Export Service generating structured reports with dedicated Excel templates per export scope:
    1. Current Loaded Drawing (Drawing Error Tracker / Executive Summary + Department sheets)
    2. Current Project (Project Summary & All Drawing Comments + Department sheets)
    3. All Historical Comments (Historical Summary & Historical Comments + Department sheets)
    """

    def __init__(
        self,
        comment_repo: CommentRepository,
        project_repo: Optional[ProjectRepository] = None,
        drawing_repo: Optional[DrawingRepository] = None,
        department_repo: Optional[EngineeringDepartmentRepository] = None,
        export_history_repo: Optional[ExportHistoryRepository] = None,
    ):
        self.comment_repo = comment_repo
        self.project_repo = project_repo
        self.drawing_repo = drawing_repo
        self.department_repo = department_repo
        self.export_history_repo = export_history_repo

    def export_drawing_comments(self, config: ExportConfigDTO) -> ExportResultDTO:
        """Export review comments to the requested format (Excel, JSON, or CSV)."""
        try:
            scope_val = getattr(config, 'scope', 'drawing')
            if scope_val == 'all':
                if hasattr(self.comment_repo, 'get_all_historical_comments'):
                    comments = self.comment_repo.get_all_historical_comments()
                else:
                    comments = self.comment_repo.get_all_comments()
            elif scope_val == 'project':
                if not getattr(config, 'project_id', None):
                    return ExportResultDTO(
                        output_path=config.output_path,
                        format=config.format,
                        total_rows=0,
                        total_sheets=0,
                        file_size_bytes=0,
                        success=False,
                        error_message="No project is currently selected for Current Project export."
                    )
                if hasattr(self.comment_repo, 'get_comments_for_project'):
                    comments = self.comment_repo.get_comments_for_project(config.project_id)
                else:
                    comments = []
            elif scope_val == 'drawing':
                if not getattr(config, 'drawing_id', None):
                    return ExportResultDTO(
                        output_path=config.output_path,
                        format=config.format,
                        total_rows=0,
                        total_sheets=0,
                        file_size_bytes=0,
                        success=False,
                        error_message="No drawing is currently loaded for Current Loaded Drawing export."
                    )
                comments = self.comment_repo.get_comments_for_drawing(config.drawing_id)
            else:
                comments = []

            if config.filter_status:
                comments = [c for c in comments if c.get('status') == config.filter_status]
            else:
                comments = [c for c in comments if c.get('status') != 'Rejected']

            # Resolve drawing/project metadata fallbacks if not explicitly provided
            self._enrich_config_metadata(config)

            if config.format == ExportFormat.EXCEL:
                result = self._export_to_excel(comments, config)
            elif config.format == ExportFormat.JSON:
                result = self._export_to_json(comments, config)
            elif config.format == ExportFormat.CSV:
                result = self._export_to_csv(comments, config)
            else:
                result = ExportResultDTO(
                    output_path=config.output_path,
                    format=config.format,
                    total_rows=0,
                    total_sheets=0,
                    file_size_bytes=0,
                    success=False,
                    error_message=f"Unsupported format: {config.format}"
                )

            if result and result.success:
                persistent_path = Path(result.output_path)
                try:
                    from src.config import get_config
                    managed_dir = get_config().export.get_resolved_export_dir()
                    managed_dir.mkdir(parents=True, exist_ok=True)
                    out_path = Path(result.output_path).resolve()

                    if out_path.exists():
                        target_managed_path = (managed_dir / out_path.name).resolve()
                        if out_path != target_managed_path:
                            import shutil
                            shutil.copy2(out_path, target_managed_path)
                            persistent_path = target_managed_path
                        else:
                            persistent_path = out_path
                except Exception as ex_store:
                    logger.warning(f"Could not copy export to managed storage: {ex_store}")

                if self.export_history_repo:
                    try:
                        format_label = "Excel" if config.format == ExportFormat.EXCEL else ("CSV" if config.format == ExportFormat.CSV else "JSON")
                        file_size = persistent_path.stat().st_size if persistent_path.exists() else result.file_size_bytes
                        self.export_history_repo.create_export_log(
                            file_name=persistent_path.name,
                            file_path=str(persistent_path),
                            format_name=format_label,
                            scope=scope_val,
                            drawing_id=config.drawing_id,
                            project_id=getattr(config, "project_id", None),
                            department_name=config.department_name,
                            total_rows=result.total_rows,
                            file_size_bytes=file_size,
                            status="Success",
                        )
                    except Exception as ex_hist:
                        logger.warning(f"Could not record export history event: {ex_hist}")

            return result
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
                        fname = dwg.get("file_name", "")
                        config.drawing_no = fname.rsplit(".", 1)[0] if "." in fname else (fname or config.drawing_id)
                    if not config.drawing_title:
                        config.drawing_title = dwg.get("title") or "Engineering Review Drawing"
                    if not config.designer_name and dwg.get("author"):
                        config.designer_name = dwg.get("author")
            except Exception as ex:
                logger.debug(f"Could not fetch drawing metadata: {ex}")

        if config.project_id and self.project_repo:
            try:
                proj = self.project_repo.get_project_by_id(config.project_id)
                if proj and not getattr(config, "project_name", None):
                    setattr(config, "project_name", proj.get("name", "Current Project"))
            except Exception as ex:
                logger.debug(f"Could not fetch project metadata: {ex}")

    def _enrich_comments_metadata(self, comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Enrich comment dictionary records with drawing number, original filename, and project metadata."""
        dwg_cache = {}
        proj_cache = {}

        enriched = []
        for c in comments:
            c_copy = dict(c)
            dwg_id = c_copy.get("drawing_id")
            dwg_info = None
            if dwg_id:
                if dwg_id not in dwg_cache:
                    if self.drawing_repo:
                        dwg_cache[dwg_id] = self.drawing_repo.get_drawing_by_id(dwg_id) or {}
                    else:
                        dwg_cache[dwg_id] = {}
                dwg_info = dwg_cache[dwg_id]

            fname = dwg_info.get("file_name", "") if dwg_info else ""
            dwg_no = fname.rsplit(".", 1)[0] if "." in fname else (fname or dwg_id or "")
            c_copy["drawing_number"] = c_copy.get("drawing_number") or dwg_no or c_copy.get("drawing_no") or dwg_id or ""
            c_copy["original_filename"] = c_copy.get("original_filename") or fname or ""

            proj_id = dwg_info.get("project_id") if dwg_info else c_copy.get("project_id")
            c_copy["project_id"] = proj_id or ""

            if proj_id:
                if proj_id not in proj_cache:
                    if self.project_repo:
                        proj_row = self.project_repo.get_project_by_id(proj_id)
                        proj_cache[proj_id] = proj_row.get("name", "") if proj_row else ""
                    else:
                        proj_cache[proj_id] = ""
                c_copy["project_name"] = proj_cache[proj_id]
            else:
                c_copy["project_name"] = c_copy.get("project_name") or ""

            enriched.append(c_copy)
        return enriched

    def _export_to_excel(self, comments: List[Dict[str, Any]], config: ExportConfigDTO) -> ExportResultDTO:
        """
        Delegate Excel generation to distinct template builders based on export scope.
        """
        if not OPENPYXL_AVAILABLE:
            raise ImportError("openpyxl is required for Excel export")

        enriched_comments = self._enrich_comments_metadata(comments)
        scope_val = getattr(config, 'scope', 'drawing')

        if scope_val == 'project':
            return self._export_project_scope_excel(enriched_comments, config)
        elif scope_val == 'all':
            return self._export_historical_scope_excel(enriched_comments, config)
        else:
            return self._export_drawing_scope_excel(enriched_comments, config)

    def _get_active_departments(self) -> List[str]:
        """Fetch list of active engineering department names."""
        if self.department_repo:
            try:
                depts = self.department_repo.get_all_departments()
                active = [d["name"] for d in depts if d.get("is_active", True)]
                if active:
                    return active
            except Exception as ex:
                logger.debug(f"Failed to fetch departments: {ex}")

        return [
            "Electrical Engineering",
            "GPD",
            "Pipe Support Engineering",
            "Piping Engineering",
            "Plakon",
            "Structural & Physical Design",
            "System Engineering",
        ]

    def _export_drawing_scope_excel(
        self, comments: List[Dict[str, Any]], config: ExportConfigDTO
    ) -> ExportResultDTO:
        """
        REQUIREMENT 1 — Current Loaded Drawing Template
        Workbook layout:
        Sheet 1: "Executive Summary" (if include_summary_sheet is True) OR "Drawing Error Tracker"
        Additional Sheets: Department-wise Error Tracker sheets + Unassigned sheet if needed
        """
        wb = openpyxl.Workbook()
        total_sheets = 0

        if config.include_summary_sheet:
            summary_ws = wb.active
            summary_ws.title = "Executive Summary"
            summary_ws.views.sheetView[0].showGridLines = True

            ORANGE_FILL = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")
            FONT_GROUP  = Font(name="Segoe UI", size=11, bold=True, color="000000")
            FONT_HEADER = Font(name="Segoe UI", size=11, bold=True, color="000000")
            THIN_SIDE   = Side(border_style="thin", color="000000")
            THIN_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)

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

            drawing_ws = wb.create_sheet(title="Drawing Error Tracker")
            self._create_drawing_summary_sheet(drawing_ws, comments, config)
            total_sheets += 1
        else:
            ws = wb.active
            ws.title = "Drawing Error Tracker"
            self._create_drawing_summary_sheet(ws, comments, config)
            total_sheets += 1

        active_departments = self._get_active_departments()
        comments_by_dept = {d: [] for d in active_departments}
        unassigned_comments = []

        for cmt in comments:
            dname = cmt.get("department_name") or cmt.get("department") or config.department_name
            if dname in comments_by_dept:
                comments_by_dept[dname].append(cmt)
            elif dname and dname != "Unassigned":
                comments_by_dept.setdefault(dname, []).append(cmt)
            else:
                unassigned_comments.append(cmt)

        for dname, dcomments in comments_by_dept.items():
            dept_ws = wb.create_sheet(title=dname[:31])
            self._create_department_sheet(dept_ws, dname, dcomments, config)
            total_sheets += 1

        if unassigned_comments:
            unassigned_ws = wb.create_sheet(title="Unassigned")
            self._create_department_sheet(unassigned_ws, "Unassigned", unassigned_comments, config)
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

    def _create_drawing_summary_sheet(
        self, ws: Any, comments: List[Dict[str, Any]], config: ExportConfigDTO
    ) -> None:
        """Populate Drawing Error Tracker worksheet with top metadata header block + comment table."""
        ws.views.sheetView[0].showGridLines = True

        HEADER_FILL = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        LABEL_FILL  = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
        TABLE_HDR_FILL = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")

        FONT_TITLE  = Font(name="Segoe UI", size=13, bold=True, color="FFFFFF")
        FONT_LABEL  = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        FONT_VAL    = Font(name="Segoe UI", size=10, bold=False, color="000000")
        FONT_THDR   = Font(name="Segoe UI", size=10, bold=True, color="000000")
        FONT_DATA   = Font(name="Segoe UI", size=10, color="000000")

        THIN_SIDE   = Side(border_style="thin", color="CBD5E1")
        THIN_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)

        ALIGN_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ALIGN_LEFT   = Alignment(horizontal="left", vertical="center", wrap_text=True)

        # 1. Header Banner
        ws.row_dimensions[1].height = 28
        ws.merge_cells("A1:L1")
        c1 = ws.cell(row=1, column=1, value="CURRENT LOADED DRAWING — DRAWING ERROR TRACKER REPORT")
        c1.fill = HEADER_FILL
        c1.font = FONT_TITLE
        c1.alignment = ALIGN_CENTER

        # 2. Metadata Block (Rows 3-6)
        proj_name = getattr(config, "project_name", "") or "N/A"
        dwg_no    = config.drawing_no or (config.drawing_id or "N/A")
        dwg_id    = config.drawing_id or "N/A"
        orig_filename = ""
        if comments:
            orig_filename = comments[0].get("original_filename") or ""
        if not orig_filename and self.drawing_repo and config.drawing_id:
            try:
                dwg = self.drawing_repo.get_drawing_by_id(config.drawing_id)
                if dwg:
                    orig_filename = dwg.get("file_name", "")
            except Exception:
                pass
        orig_filename = orig_filename or dwg_no
        dept_name = config.department_name or "Piping Engineering"
        export_date = config.date_str or date.today().strftime("%Y-%m-%d")
        designer_name = config.designer_name or "Lead Reviewer"

        meta_rows = [
            ("Project", proj_name, "Export Date", export_date),
            ("Drawing Number", dwg_no, "Drawing ID", dwg_id),
            ("Original Filename", orig_filename, "Engineering Department", dept_name),
            ("Total Comments", len(comments), "Reviewer", designer_name),
        ]

        for idx, (lbl1, val1, lbl2, val2) in enumerate(meta_rows, start=3):
            ws.row_dimensions[idx].height = 22

            c_lbl1 = ws.cell(row=idx, column=1, value=lbl1)
            c_lbl1.fill = LABEL_FILL
            c_lbl1.font = FONT_LABEL
            c_lbl1.alignment = ALIGN_LEFT
            c_lbl1.border = THIN_BORDER

            c_val1 = ws.cell(row=idx, column=2, value=val1)
            c_val1.font = FONT_VAL
            c_val1.alignment = ALIGN_LEFT
            c_val1.border = THIN_BORDER

            c_lbl2 = ws.cell(row=idx, column=4, value=lbl2)
            c_lbl2.fill = LABEL_FILL
            c_lbl2.font = FONT_LABEL
            c_lbl2.alignment = ALIGN_LEFT
            c_lbl2.border = THIN_BORDER

            c_val2 = ws.cell(row=idx, column=5, value=val2)
            c_val2.font = FONT_VAL
            c_val2.alignment = ALIGN_LEFT
            c_val2.border = THIN_BORDER

        # 3. Comment Table Header (Row 8)
        ws.row_dimensions[8].height = 28
        headers = [
            "Comment ID",
            "Page",
            "Comment Text",
            "Raw OCR Text",
            "Category",
            "Engineering Department",
            "Classification Confidence",
            "Detection Confidence",
            "Review Status",
            "Verified",
            "Reviewer",
            "Created/Updated Timestamp",
        ]
        for col_idx, text in enumerate(headers, start=1):
            c = ws.cell(row=8, column=col_idx, value=text)
            c.fill = TABLE_HDR_FILL
            c.font = FONT_THDR
            c.alignment = ALIGN_CENTER
            c.border = THIN_BORDER

        # 4. Data Rows (Rows 9+)
        start_row = 9
        if not comments:
            for r in range(start_row, start_row + 3):
                ws.row_dimensions[r].height = 22
                for col_idx in range(1, 13):
                    c = ws.cell(row=r, column=col_idx, value="")
                    c.font = FONT_DATA
                    c.border = THIN_BORDER
        else:
            for idx, cmt in enumerate(comments, start=start_row):
                desc = cmt.get("cleaned_text") or cmt.get("raw_text") or ""
                raw  = cmt.get("raw_text") or ""
                cat  = cmt.get("category_name") or cmt.get("category") or "Uncategorized"
                dept = cmt.get("department_name") or cmt.get("department") or dept_name
                conf = cmt.get("confidence", 0.0)
                conf_str = f"{conf:.2f}" if isinstance(conf, (int, float)) else str(conf)
                status = cmt.get("status", "Pending")
                verified = "Yes" if cmt.get("is_verified_by_human") or cmt.get("is_verified") else "No"
                reviewer = cmt.get("reviewer_id") or cmt.get("user_id") or cmt.get("reviewer") or designer_name
                ts = cmt.get("created_at") or cmt.get("timestamp") or export_date

                row_vals = [
                    (1, cmt.get("id", f"CMT-{idx}"), ALIGN_CENTER),
                    (2, cmt.get("page_number") or cmt.get("page", 1), ALIGN_CENTER),
                    (3, desc, ALIGN_LEFT),
                    (4, raw, ALIGN_LEFT),
                    (5, cat, ALIGN_LEFT),
                    (6, dept, ALIGN_LEFT),
                    (7, conf_str, ALIGN_CENTER),
                    (8, conf_str, ALIGN_CENTER),
                    (9, status, ALIGN_CENTER),
                    (10, verified, ALIGN_CENTER),
                    (11, reviewer, ALIGN_LEFT),
                    (12, str(ts), ALIGN_CENTER),
                ]

                ws.row_dimensions[idx].height = 45 if len(desc) > 80 else 24
                for col_idx, cell_value, alignment in row_vals:
                    cell = ws.cell(row=idx, column=col_idx, value=cell_value)
                    cell.font = FONT_DATA
                    cell.alignment = alignment
                    cell.border = THIN_BORDER

        col_widths = {
            "A": 16, "B": 10, "C": 45, "D": 35, "E": 25, "F": 25,
            "G": 18, "H": 18, "I": 15, "J": 12, "K": 20, "L": 22
        }
        for col_letter, width in col_widths.items():
            ws.column_dimensions[col_letter].width = width

    def _export_project_scope_excel(
        self, comments: List[Dict[str, Any]], config: ExportConfigDTO
    ) -> ExportResultDTO:
        """
        REQUIREMENT 2 — Current Project Template
        Workbook layout:
        Sheet 1: "Project Summary" (Project metadata & drawing breakdown)
        Sheet 2: "All Drawing Comments" (Multi-drawing comments dataset)
        Additional Sheets: Department-wise Error Tracker sheets
        """
        wb = openpyxl.Workbook()

        HEADER_FILL = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
        LABEL_FILL  = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
        THDR_FILL   = PatternFill(start_color="4ADE80", end_color="4ADE80", fill_type="solid")

        FONT_TITLE  = Font(name="Segoe UI", size=13, bold=True, color="FFFFFF")
        FONT_LABEL  = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        FONT_VAL    = Font(name="Segoe UI", size=10, color="000000")
        FONT_THDR   = Font(name="Segoe UI", size=10, bold=True, color="000000")
        FONT_DATA   = Font(name="Segoe UI", size=10, color="000000")

        THIN_SIDE   = Side(border_style="thin", color="CBD5E1")
        THIN_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)

        ALIGN_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ALIGN_LEFT   = Alignment(horizontal="left", vertical="center", wrap_text=True)

        proj_id = config.project_id or "N/A"
        proj_name = getattr(config, "project_name", "") or "Current Project"
        export_date = config.date_str or date.today().strftime("%Y-%m-%d")

        # Get unique drawings in project
        dwg_map = {}
        if self.drawing_repo and config.project_id:
            try:
                dwg_list = self.drawing_repo.get_all_drawings(project_id=config.project_id)
                for d in dwg_list:
                    dwg_map[d["id"]] = {
                        "drawing_id": d["id"],
                        "drawing_number": d.get("file_name", "").rsplit(".", 1)[0] or d["id"],
                        "original_filename": d.get("file_name", ""),
                        "department": d.get("department_name") or "Piping Engineering",
                        "comments_count": 0,
                    }
            except Exception:
                pass

        for cmt in comments:
            did = cmt.get("drawing_id", "DWG-UNKNOWN")
            if did not in dwg_map:
                dwg_map[did] = {
                    "drawing_id": did,
                    "drawing_number": cmt.get("drawing_number") or did,
                    "original_filename": cmt.get("original_filename") or "",
                    "department": cmt.get("department_name") or "Unassigned",
                    "comments_count": 0,
                }
            dwg_map[did]["comments_count"] += 1

        # ── Sheet 1: Project Summary ─────────────────────────────────
        ws_sum = wb.active
        ws_sum.title = "Project Summary"
        ws_sum.views.sheetView[0].showGridLines = True

        ws_sum.row_dimensions[1].height = 28
        ws_sum.merge_cells("A1:E1")
        c1 = ws_sum.cell(row=1, column=1, value="PROJECT ERROR TRACKER SUMMARY")
        c1.fill = HEADER_FILL
        c1.font = FONT_TITLE
        c1.alignment = ALIGN_CENTER

        meta_rows = [
            ("Project Name", proj_name, "Project ID", proj_id),
            ("Number of Drawings", len(dwg_map), "Total Comments", len(comments)),
            ("Export Date", export_date, "", ""),
        ]
        for idx, (lbl1, val1, lbl2, val2) in enumerate(meta_rows, start=3):
            ws_sum.row_dimensions[idx].height = 22

            c_lbl1 = ws_sum.cell(row=idx, column=1, value=lbl1)
            c_lbl1.fill = LABEL_FILL
            c_lbl1.font = FONT_LABEL
            c_lbl1.border = THIN_BORDER

            c_val1 = ws_sum.cell(row=idx, column=2, value=val1)
            c_val1.font = FONT_VAL
            c_val1.border = THIN_BORDER

            if lbl2:
                c_lbl2 = ws_sum.cell(row=idx, column=4, value=lbl2)
                c_lbl2.fill = LABEL_FILL
                c_lbl2.font = FONT_LABEL
                c_lbl2.border = THIN_BORDER

                c_val2 = ws_sum.cell(row=idx, column=5, value=val2)
                c_val2.font = FONT_VAL
                c_val2.border = THIN_BORDER

        # Drawing Breakdown Table Header (Row 7)
        ws_sum.cell(row=6, column=1, value="Project Drawing Breakdown").font = Font(name="Segoe UI", size=11, bold=True)
        ws_sum.row_dimensions[7].height = 25
        sum_headers = ["Drawing ID", "Drawing Number", "Original Filename", "Engineering Department", "Total Comments"]
        for col_idx, th in enumerate(sum_headers, start=1):
            c = ws_sum.cell(row=7, column=col_idx, value=th)
            c.fill = THDR_FILL
            c.font = FONT_THDR
            c.alignment = ALIGN_CENTER
            c.border = THIN_BORDER

        r = 8
        for did, dinfo in dwg_map.items():
            ws_sum.row_dimensions[r].height = 22
            ws_sum.cell(row=r, column=1, value=dinfo["drawing_id"]).border = THIN_BORDER
            ws_sum.cell(row=r, column=2, value=dinfo["drawing_number"]).border = THIN_BORDER
            ws_sum.cell(row=r, column=3, value=dinfo["original_filename"]).border = THIN_BORDER
            ws_sum.cell(row=r, column=4, value=dinfo["department"]).border = THIN_BORDER
            ws_sum.cell(row=r, column=5, value=dinfo["comments_count"]).border = THIN_BORDER
            r += 1

        for col_letter, w in [("A", 18), ("B", 25), ("C", 30), ("D", 25), ("E", 18)]:
            ws_sum.column_dimensions[col_letter].width = w

        # ── Sheet 2: All Drawing Comments ────────────────────────────
        ws_cmt = wb.create_sheet(title="All Drawing Comments")
        ws_cmt.views.sheetView[0].showGridLines = True

        ws_cmt.row_dimensions[1].height = 28
        cmt_headers = [
            "Drawing ID",
            "Drawing Number",
            "Original Filename",
            "Engineering Department",
            "Page",
            "Comment ID",
            "Comment Text",
            "Raw OCR Text",
            "Category",
            "Classification Confidence",
            "Detection Confidence",
            "Review Status",
            "Verified",
            "Reviewer",
            "Timestamp",
        ]
        for col_idx, th in enumerate(cmt_headers, start=1):
            c = ws_cmt.cell(row=1, column=col_idx, value=th)
            c.fill = THDR_FILL
            c.font = FONT_THDR
            c.alignment = ALIGN_CENTER
            c.border = THIN_BORDER

        for idx, cmt in enumerate(comments, start=2):
            desc = cmt.get("cleaned_text") or cmt.get("raw_text") or ""
            raw  = cmt.get("raw_text") or ""
            cat  = cmt.get("category_name") or cmt.get("category") or "Uncategorized"
            dept = cmt.get("department_name") or cmt.get("department") or "Unassigned"
            conf = cmt.get("confidence", 0.0)
            conf_str = f"{conf:.2f}" if isinstance(conf, (int, float)) else str(conf)
            status = cmt.get("status", "Pending")
            verified = "Yes" if cmt.get("is_verified_by_human") or cmt.get("is_verified") else "No"
            reviewer = cmt.get("reviewer_id") or cmt.get("user_id") or cmt.get("reviewer") or config.designer_name or ""
            ts = cmt.get("created_at") or cmt.get("timestamp") or export_date

            row_vals = [
                (1, cmt.get("drawing_id", ""), ALIGN_CENTER),
                (2, cmt.get("drawing_number", ""), ALIGN_CENTER),
                (3, cmt.get("original_filename", ""), ALIGN_LEFT),
                (4, dept, ALIGN_LEFT),
                (5, cmt.get("page_number") or cmt.get("page", 1), ALIGN_CENTER),
                (6, cmt.get("id", f"CMT-{idx}"), ALIGN_CENTER),
                (7, desc, ALIGN_LEFT),
                (8, raw, ALIGN_LEFT),
                (9, cat, ALIGN_LEFT),
                (10, conf_str, ALIGN_CENTER),
                (11, conf_str, ALIGN_CENTER),
                (12, status, ALIGN_CENTER),
                (13, verified, ALIGN_CENTER),
                (14, reviewer, ALIGN_LEFT),
                (15, str(ts), ALIGN_CENTER),
            ]
            ws_cmt.row_dimensions[idx].height = 40 if len(desc) > 80 else 22
            for col_idx, cell_value, alignment in row_vals:
                cell = ws_cmt.cell(row=idx, column=col_idx, value=cell_value)
                cell.font = FONT_DATA
                cell.alignment = alignment
                cell.border = THIN_BORDER

        for col_letter, w in [
            ("A", 18), ("B", 22), ("C", 28), ("D", 22), ("E", 8),
            ("F", 16), ("G", 40), ("H", 30), ("I", 22), ("J", 16),
            ("K", 16), ("L", 14), ("M", 10), ("N", 18), ("O", 20)
        ]:
            ws_cmt.column_dimensions[col_letter].width = w

        total_sheets = 2

        # Department sheets
        active_departments = self._get_active_departments()
        comments_by_dept = {d: [] for d in active_departments}
        unassigned_comments = []

        for cmt in comments:
            dname = cmt.get("department_name") or cmt.get("department") or config.department_name
            if dname in comments_by_dept:
                comments_by_dept[dname].append(cmt)
            elif dname and dname != "Unassigned":
                comments_by_dept.setdefault(dname, []).append(cmt)
            else:
                unassigned_comments.append(cmt)

        for dname, dcomments in comments_by_dept.items():
            dept_ws = wb.create_sheet(title=dname[:31])
            self._create_department_sheet(dept_ws, dname, dcomments, config)
            total_sheets += 1

        if unassigned_comments:
            unassigned_ws = wb.create_sheet(title="Unassigned")
            self._create_department_sheet(unassigned_ws, "Unassigned", unassigned_comments, config)
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

    def _export_historical_scope_excel(
        self, comments: List[Dict[str, Any]], config: ExportConfigDTO
    ) -> ExportResultDTO:
        """
        REQUIREMENT 3 — All Historical Comments Template
        Workbook layout:
        Sheet 1: "Historical Summary" (System-wide metrics & project breakdown)
        Sheet 2: "Historical Comments" (All persisted comments dataset across database)
        Additional Sheets: Department-wise Error Tracker sheets
        """
        wb = openpyxl.Workbook()

        HEADER_FILL = PatternFill(start_color="312E81", end_color="312E81", fill_type="solid")
        LABEL_FILL  = PatternFill(start_color="475569", end_color="475569", fill_type="solid")
        THDR_FILL   = PatternFill(start_color="818CF8", end_color="818CF8", fill_type="solid")

        FONT_TITLE  = Font(name="Segoe UI", size=13, bold=True, color="FFFFFF")
        FONT_LABEL  = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        FONT_VAL    = Font(name="Segoe UI", size=10, color="000000")
        FONT_THDR   = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        FONT_DATA   = Font(name="Segoe UI", size=10, color="000000")

        THIN_SIDE   = Side(border_style="thin", color="CBD5E1")
        THIN_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)

        ALIGN_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ALIGN_LEFT   = Alignment(horizontal="left", vertical="center", wrap_text=True)

        export_date = config.date_str or date.today().strftime("%Y-%m-%d")

        all_projects = self.project_repo.get_all_projects() if self.project_repo else []
        all_drawings = self.drawing_repo.get_all_drawings() if self.drawing_repo else []

        # ── Sheet 1: Historical Summary ─────────────────────────────
        ws_sum = wb.active
        ws_sum.title = "Historical Summary"
        ws_sum.views.sheetView[0].showGridLines = True

        ws_sum.row_dimensions[1].height = 28
        ws_sum.merge_cells("A1:D1")
        c1 = ws_sum.cell(row=1, column=1, value="ALL HISTORICAL COMMENTS — SYSTEM AUDIT REPORT")
        c1.fill = HEADER_FILL
        c1.font = FONT_TITLE
        c1.alignment = ALIGN_CENTER

        meta_rows = [
            ("Total Projects", len(all_projects), "Total Drawings", len(all_drawings)),
            ("Total Comments", len(comments), "Export Date", export_date),
        ]
        for idx, (lbl1, val1, lbl2, val2) in enumerate(meta_rows, start=3):
            ws_sum.row_dimensions[idx].height = 22

            c_lbl1 = ws_sum.cell(row=idx, column=1, value=lbl1)
            c_lbl1.fill = LABEL_FILL
            c_lbl1.font = FONT_LABEL
            c_lbl1.border = THIN_BORDER

            c_val1 = ws_sum.cell(row=idx, column=2, value=val1)
            c_val1.font = FONT_VAL
            c_val1.border = THIN_BORDER

            c_lbl2 = ws_sum.cell(row=idx, column=3, value=lbl2)
            c_lbl2.fill = LABEL_FILL
            c_lbl2.font = FONT_LABEL
            c_lbl2.border = THIN_BORDER

            c_val2 = ws_sum.cell(row=idx, column=4, value=val2)
            c_val2.font = FONT_VAL
            c_val2.border = THIN_BORDER

        # Project breakdown
        ws_sum.cell(row=5, column=1, value="Project Database Breakdown").font = Font(name="Segoe UI", size=11, bold=True)
        ws_sum.row_dimensions[6].height = 25
        sum_headers = ["Project ID", "Project Name", "Total Drawings", "Total Comments"]
        for col_idx, th in enumerate(sum_headers, start=1):
            c = ws_sum.cell(row=6, column=col_idx, value=th)
            c.fill = THDR_FILL
            c.font = FONT_THDR
            c.alignment = ALIGN_CENTER
            c.border = THIN_BORDER

        proj_comments_cnt = {}
        for cmt in comments:
            pid = cmt.get("project_id") or "PRJ-UNKNOWN"
            proj_comments_cnt[pid] = proj_comments_cnt.get(pid, 0) + 1

        r = 7
        if all_projects:
            for p in all_projects:
                pid = p["id"]
                ws_sum.row_dimensions[r].height = 22
                ws_sum.cell(row=r, column=1, value=pid).border = THIN_BORDER
                ws_sum.cell(row=r, column=2, value=p.get("name", "")).border = THIN_BORDER
                ws_sum.cell(row=r, column=3, value=p.get("total_drawings", 0)).border = THIN_BORDER
                ws_sum.cell(row=r, column=4, value=proj_comments_cnt.get(pid, 0)).border = THIN_BORDER
                r += 1
        else:
            for pid, count in proj_comments_cnt.items():
                ws_sum.row_dimensions[r].height = 22
                ws_sum.cell(row=r, column=1, value=pid).border = THIN_BORDER
                ws_sum.cell(row=r, column=2, value="Persisted Project").border = THIN_BORDER
                ws_sum.cell(row=r, column=3, value=1).border = THIN_BORDER
                ws_sum.cell(row=r, column=4, value=count).border = THIN_BORDER
                r += 1

        for col_letter, w in [("A", 20), ("B", 30), ("C", 18), ("D", 18)]:
            ws_sum.column_dimensions[col_letter].width = w

        # ── Sheet 2: Historical Comments ────────────────────────────
        ws_cmt = wb.create_sheet(title="Historical Comments")
        ws_cmt.views.sheetView[0].showGridLines = True

        ws_cmt.row_dimensions[1].height = 28
        cmt_headers = [
            "Project ID",
            "Project",
            "Drawing ID",
            "Drawing Number",
            "Original Filename",
            "Engineering Department",
            "Page",
            "Comment ID",
            "Comment Text",
            "Raw OCR Text",
            "Category",
            "Classification Confidence",
            "Detection Confidence",
            "Review Status",
            "Verified",
            "Reviewer",
            "Created Timestamp",
            "Updated Timestamp",
        ]
        for col_idx, th in enumerate(cmt_headers, start=1):
            c = ws_cmt.cell(row=1, column=col_idx, value=th)
            c.fill = THDR_FILL
            c.font = FONT_THDR
            c.alignment = ALIGN_CENTER
            c.border = THIN_BORDER

        for idx, cmt in enumerate(comments, start=2):
            desc = cmt.get("cleaned_text") or cmt.get("raw_text") or ""
            raw  = cmt.get("raw_text") or ""
            cat  = cmt.get("category_name") or cmt.get("category") or "Uncategorized"
            dept = cmt.get("department_name") or cmt.get("department") or "Unassigned"
            conf = cmt.get("confidence", 0.0)
            conf_str = f"{conf:.2f}" if isinstance(conf, (int, float)) else str(conf)
            status = cmt.get("status", "Pending")
            verified = "Yes" if cmt.get("is_verified_by_human") or cmt.get("is_verified") else "No"
            reviewer = cmt.get("reviewer_id") or cmt.get("user_id") or cmt.get("reviewer") or config.designer_name or ""
            created_ts = cmt.get("created_at") or cmt.get("timestamp") or export_date
            updated_ts = cmt.get("updated_at") or created_ts

            row_vals = [
                (1, cmt.get("project_id", ""), ALIGN_CENTER),
                (2, cmt.get("project_name", ""), ALIGN_LEFT),
                (3, cmt.get("drawing_id", ""), ALIGN_CENTER),
                (4, cmt.get("drawing_number", ""), ALIGN_CENTER),
                (5, cmt.get("original_filename", ""), ALIGN_LEFT),
                (6, dept, ALIGN_LEFT),
                (7, cmt.get("page_number") or cmt.get("page", 1), ALIGN_CENTER),
                (8, cmt.get("id", f"CMT-{idx}"), ALIGN_CENTER),
                (9, desc, ALIGN_LEFT),
                (10, raw, ALIGN_LEFT),
                (11, cat, ALIGN_LEFT),
                (12, conf_str, ALIGN_CENTER),
                (13, conf_str, ALIGN_CENTER),
                (14, status, ALIGN_CENTER),
                (15, verified, ALIGN_CENTER),
                (16, reviewer, ALIGN_LEFT),
                (17, str(created_ts), ALIGN_CENTER),
                (18, str(updated_ts), ALIGN_CENTER),
            ]
            ws_cmt.row_dimensions[idx].height = 40 if len(desc) > 80 else 22
            for col_idx, cell_value, alignment in row_vals:
                cell = ws_cmt.cell(row=idx, column=col_idx, value=cell_value)
                cell.font = FONT_DATA
                cell.alignment = alignment
                cell.border = THIN_BORDER

        for col_letter, w in [
            ("A", 16), ("B", 22), ("C", 16), ("D", 22), ("E", 25),
            ("F", 22), ("G", 8),  ("H", 16), ("I", 40), ("J", 30),
            ("K", 22), ("L", 16), ("M", 16), ("N", 14), ("O", 10),
            ("P", 18), ("Q", 20), ("R", 20)
        ]:
            ws_cmt.column_dimensions[col_letter].width = w

        total_sheets = 2

        # Department sheets
        active_departments = self._get_active_departments()
        comments_by_dept = {d: [] for d in active_departments}
        unassigned_comments = []

        for cmt in comments:
            dname = cmt.get("department_name") or cmt.get("department") or config.department_name
            if dname in comments_by_dept:
                comments_by_dept[dname].append(cmt)
            elif dname and dname != "Unassigned":
                comments_by_dept.setdefault(dname, []).append(cmt)
            else:
                unassigned_comments.append(cmt)

        for dname, dcomments in comments_by_dept.items():
            dept_ws = wb.create_sheet(title=dname[:31])
            self._create_department_sheet(dept_ws, dname, dcomments, config)
            total_sheets += 1

        if unassigned_comments:
            unassigned_ws = wb.create_sheet(title="Unassigned")
            self._create_department_sheet(unassigned_ws, "Unassigned", unassigned_comments, config)
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

    def _create_department_sheet(
        self,
        ws: Any,
        dept_name: str,
        comments: List[Dict[str, Any]],
        config: ExportConfigDTO,
    ) -> None:
        """
        Populate a single department worksheet formatted according to the 4-tier
        Error Tracker Sheet specification (9 Columns A-I).
        """
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

        # ROW 1: Grouping Banners
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
        ]
        for col_idx, val, fill in row1_cells:
            c = ws.cell(row=1, column=col_idx, value=val)
            c.fill = fill
            c.font = FONT_GROUP
            c.alignment = ALIGN_CENTER
            c.border = THIN_BORDER

        ws.merge_cells("A1:B1")
        ws.merge_cells("D1:E1")
        ws.merge_cells("F1:I1")

        # ROW 2: Column Index Numbering
        ws.row_dimensions[2].height = 22
        col_numbers = [
            (1, 1, ORANGE_FILL),
            (2, 2, ORANGE_FILL),
            (3, 3, GREEN_FILL),
            (4, 4, ORANGE_FILL),
            (5, 6, ORANGE_FILL),
            (6, 7, GREEN_FILL),
            (7, 8, GREEN_FILL),
            (8, 9, GREEN_FILL),
            (9, 10, GREEN_FILL),
        ]
        for col_idx, num_val, fill in col_numbers:
            c = ws.cell(row=2, column=col_idx, value=num_val)
            c.fill = fill
            c.font = FONT_NUM
            c.alignment = ALIGN_CENTER
            c.border = THIN_BORDER

        # ROW 3: Data Source / Role Description
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
        ]
        for col_idx, role_text, fill in col_roles:
            c = ws.cell(row=3, column=col_idx, value=role_text)
            c.fill = fill
            c.font = FONT_ROLE
            c.alignment = ALIGN_CENTER
            c.border = THIN_BORDER

        # ROW 4: Primary Column Header Names
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
        ]
        for col_idx, hdr_text, fill in headers:
            c = ws.cell(row=4, column=col_idx, value=hdr_text)
            c.fill = fill
            c.font = FONT_HEADER
            c.alignment = ALIGN_CENTER
            c.border = THIN_BORDER

        # ROWS 5+: Data Rows
        date_val     = config.date_str or date.today().strftime("%Y-%m-%d")
        contract_val = config.contract_no or ""
        plant_val    = config.plant_name or ""
        epod_val     = config.epod_wo_no or ""
        designer_val = config.designer_name or ""
        drawing_no   = config.drawing_no or (config.drawing_id or "")
        drawing_ttl  = config.drawing_title or ""

        start_row = 5
        if not comments:
            for r in range(start_row, start_row + 5):
                ws.row_dimensions[r].height = 24
                for col_idx in range(1, 10):
                    c = ws.cell(row=r, column=col_idx, value="")
                    c.font = FONT_DATA
                    c.border = THIN_BORDER
        else:
            for idx, comment in enumerate(comments, start_row):
                desc = comment.get('cleaned_text') or comment.get('raw_text') or ""
                cat  = comment.get('category_name') or comment.get('category') or "Uncategorized"
                reviewer = comment.get('reviewer_id') or designer_val
                cmt_dwg_no = comment.get('drawing_number') or comment.get('drawing_no') or drawing_no or (comment.get('drawing_id') or "")
                cmt_dwg_ttl = comment.get('drawing_title') or drawing_ttl

                row_data = [
                    (1, date_val, ALIGN_CENTER),
                    (2, contract_val, ALIGN_CENTER),
                    (3, plant_val, ALIGN_LEFT),
                    (4, epod_val, ALIGN_CENTER),
                    (5, reviewer, ALIGN_LEFT),
                    (6, cmt_dwg_no, ALIGN_CENTER),
                    (7, cmt_dwg_ttl, ALIGN_LEFT),
                    (8, desc, ALIGN_LEFT),
                    (9, cat, ALIGN_LEFT),
                ]

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

        col_widths = {
            "A": 15, "B": 18, "C": 22, "D": 18, "E": 20,
            "F": 22, "G": 28, "H": 55, "I": 30,
        }
        for col_letter, width in col_widths.items():
            ws.column_dimensions[col_letter].width = width

    def _export_to_json(self, comments: List[Dict[str, Any]], config: ExportConfigDTO) -> ExportResultDTO:
        data = {
            "metadata": {
                "export_date": datetime.now().isoformat(),
                "total_records": len(comments),
                "scope": config.scope,
                "drawing_id": config.drawing_id,
                "project_id": config.project_id,
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
            writer.writerow(headers)
            for comment in comments:
                desc = comment.get('raw_text') or comment.get('cleaned_text') or ""
                cat  = comment.get('category_name') or comment.get('category') or "Uncategorized"
                dept = comment.get('department_name') or comment.get('department') or config.department_name or "Unassigned"
                reviewer = comment.get('reviewer_id') or designer_val
                cmt_dwg_no = comment.get('drawing_number') or comment.get('drawing_no') or drawing_no or (comment.get('drawing_id') or "")
                cmt_dwg_ttl = comment.get('drawing_title') or drawing_ttl
                writer.writerow([
                    date_val,
                    contract_val,
                    plant_val,
                    epod_val,
                    reviewer,
                    cmt_dwg_no,
                    cmt_dwg_ttl,
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
