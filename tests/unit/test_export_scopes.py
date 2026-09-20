"""
tests/unit/test_export_scopes.py — Test suite for Export Scopes, distinct Excel templates, and persistent Export History.
"""

import pytest
from pathlib import Path
import openpyxl

from src.core.dtos.export_dtos import ExportConfigDTO, ExportFormat
from src.infrastructure.storage.repository import (
    DatabaseEngine,
    DrawingRepository,
    ProjectRepository,
    CommentRepository,
    EngineeringDepartmentRepository,
    ExportHistoryRepository,
)
from src.services.export_service import ExportService


@pytest.fixture
def db_engine(tmp_path):
    db_file = tmp_path / "test_export_scopes.db"
    engine = DatabaseEngine(db_path=db_file)
    return engine


@pytest.fixture
def test_setup(db_engine):
    """
    Setup database with:
    Project A:
        Drawing A1 -> 2 comments (Piping Engineering & Electrical Engineering)
        Drawing A2 -> 3 comments (Piping Engineering & Standards/Technical)
    Project B:
        Drawing B1 -> 4 comments (GPD & System Engineering)

    Total = 9 comments across 3 drawings and 2 projects.
    """
    proj_repo = ProjectRepository(db_engine)
    dwg_repo = DrawingRepository(db_engine)
    cmt_repo = CommentRepository(db_engine)
    dept_repo = EngineeringDepartmentRepository(db_engine)
    hist_repo = ExportHistoryRepository(db_engine)

    # 1. Projects
    proj_a = proj_repo.create_project(name="Project A", description="First test project")
    proj_b = proj_repo.create_project(name="Project B", description="Second test project")
    proj_empty = proj_repo.create_project(name="Project Empty", description="Project with no drawings")

    piping_dept = dept_repo.get_or_create_department("Piping Engineering")
    elec_dept = dept_repo.get_or_create_department("Electrical Engineering")
    gpd_dept = dept_repo.get_or_create_department("GPD")

    # 2. Drawings
    with db_engine.get_session() as session:
        from src.infrastructure.storage.models import DrawingModel
        dwg_a1_model = DrawingModel(
            id="DWG-A1",
            project_id=proj_a["id"],
            department_id=piping_dept["id"],
            file_path="C:/drawings/A1.pdf",
            file_name="Drawing_A1.pdf",
            file_size_bytes=1000,
            file_hash_sha256="hash_a1",
            total_pages=1,
            title="Piping Layout A1",
        )
        dwg_a2_model = DrawingModel(
            id="DWG-A2",
            project_id=proj_a["id"],
            department_id=piping_dept["id"],
            file_path="C:/drawings/A2.pdf",
            file_name="Drawing_A2.pdf",
            file_size_bytes=1000,
            file_hash_sha256="hash_a2",
            total_pages=1,
            title="Piping Isometric A2",
        )
        dwg_b1_model = DrawingModel(
            id="DWG-B1",
            project_id=proj_b["id"],
            department_id=elec_dept["id"],
            file_path="C:/drawings/B1.pdf",
            file_name="Drawing_B1.pdf",
            file_size_bytes=1000,
            file_hash_sha256="hash_b1",
            total_pages=1,
            title="Substation Layout B1",
        )
        session.add_all([dwg_a1_model, dwg_a2_model, dwg_b1_model])
        session.commit()

    # 3. Comments
    # Drawing A1: 2 comments
    cmt_repo.save_comment(
        drawing_id="DWG-A1",
        page_number=1,
        raw_text="A1 Comment 1 - Pipe clearance error",
        bbox=(10, 10, 50, 50),
        department_id=piping_dept["id"],
        category_name="Technical",
        status="Approved",
    )
    cmt_repo.save_comment(
        drawing_id="DWG-A1",
        page_number=1,
        raw_text="A1 Comment 2 - Cable tray clash",
        bbox=(60, 60, 100, 100),
        department_id=elec_dept["id"],
        category_name="Coordination",
        status="Pending",
    )

    # Drawing A2: 3 comments
    cmt_repo.save_comment(
        drawing_id="DWG-A2",
        page_number=1,
        raw_text="A2 Comment 1 - Missing flange dimension",
        bbox=(10, 10, 50, 50),
        department_id=piping_dept["id"],
        category_name="Dimension",
        status="Approved",
    )
    cmt_repo.save_comment(
        drawing_id="DWG-A2",
        page_number=1,
        raw_text="A2 Comment 2 - Weld symbol spec issue",
        bbox=(60, 60, 100, 100),
        department_id=piping_dept["id"],
        category_name="Standards",
        status="Pending",
    )
    cmt_repo.save_comment(
        drawing_id="DWG-A2",
        page_number=1,
        raw_text="A2 Comment 3 - Valve tag mismatch",
        bbox=(110, 110, 150, 150),
        department_id=piping_dept["id"],
        category_name="Technical",
        status="Approved",
    )

    # Drawing B1: 4 comments
    for i in range(1, 5):
        cmt_repo.save_comment(
            drawing_id="DWG-B1",
            page_number=1,
            raw_text=f"B1 Comment {i} - Equipment footprint issue",
            bbox=(i * 10, i * 10, i * 10 + 20, i * 10 + 20),
            department_id=gpd_dept["id"],
            category_name="Feasibility",
            status="Approved",
        )

    return {
        "db_engine": db_engine,
        "proj_a": proj_a,
        "proj_b": proj_b,
        "proj_empty": proj_empty,
        "proj_repo": proj_repo,
        "dwg_repo": dwg_repo,
        "cmt_repo": cmt_repo,
        "dept_repo": dept_repo,
        "hist_repo": hist_repo,
    }


def test_1_current_loaded_drawing_scope_a1(test_setup, tmp_path):
    """TEST 1: Current Loaded Drawing = A1 -> Expected: 2 comments."""
    service = ExportService(test_setup["cmt_repo"], test_setup["proj_repo"], test_setup["dwg_repo"])
    out_file = tmp_path / "a1_export.csv"
    config = ExportConfigDTO(
        output_path=out_file,
        format=ExportFormat.CSV,
        drawing_id="DWG-A1",
        scope="drawing",
    )
    res = service.export_drawing_comments(config)
    assert res.success is True
    assert res.total_rows == 2


def test_2_current_loaded_drawing_scope_a2(test_setup, tmp_path):
    """TEST 2: Current Loaded Drawing = A2 -> Expected: 3 comments (must NOT contain A1 comments)."""
    service = ExportService(test_setup["cmt_repo"], test_setup["proj_repo"], test_setup["dwg_repo"])
    out_file = tmp_path / "a2_export.csv"
    config = ExportConfigDTO(
        output_path=out_file,
        format=ExportFormat.CSV,
        drawing_id="DWG-A2",
        scope="drawing",
    )
    res = service.export_drawing_comments(config)
    assert res.success is True
    assert res.total_rows == 3


def test_3_current_project_scope(test_setup, tmp_path):
    """TEST 3: Current Project = Project A -> Expected: 5 comments (A1 + A2, must NOT contain B1)."""
    service = ExportService(test_setup["cmt_repo"], test_setup["proj_repo"], test_setup["dwg_repo"])
    out_file = tmp_path / "project_a_export.csv"
    config = ExportConfigDTO(
        output_path=out_file,
        format=ExportFormat.CSV,
        project_id=test_setup["proj_a"]["id"],
        scope="project",
    )
    res = service.export_drawing_comments(config)
    assert res.success is True
    assert res.total_rows == 5


def test_4_all_historical_comments_scope(test_setup, tmp_path):
    """TEST 4: All Historical Comments -> Expected: 9 comments (A1 + A2 + B1)."""
    service = ExportService(test_setup["cmt_repo"], test_setup["proj_repo"], test_setup["dwg_repo"])
    out_file = tmp_path / "historical_export.csv"
    config = ExportConfigDTO(
        output_path=out_file,
        format=ExportFormat.CSV,
        scope="all",
    )
    res = service.export_drawing_comments(config)
    assert res.success is True
    assert res.total_rows == 9


def test_5_no_current_drawing_graceful(test_setup, tmp_path):
    """TEST 5: No current drawing -> Current Loaded Drawing export rejects missing drawing_id."""
    service = ExportService(test_setup["cmt_repo"], test_setup["proj_repo"], test_setup["dwg_repo"])
    out_file = tmp_path / "no_dwg_export.csv"
    config = ExportConfigDTO(
        output_path=out_file,
        format=ExportFormat.CSV,
        drawing_id=None,
        scope="drawing",
    )
    res = service.export_drawing_comments(config)
    assert res.success is False
    assert "No drawing is currently loaded" in res.error_message


def test_6_no_current_project_validation(test_setup, tmp_path):
    """TEST 6: No current project -> Current Project export fails validation with error message."""
    service = ExportService(test_setup["cmt_repo"], test_setup["proj_repo"], test_setup["dwg_repo"])
    out_file = tmp_path / "no_proj_export.csv"
    config = ExportConfigDTO(
        output_path=out_file,
        format=ExportFormat.CSV,
        project_id=None,
        scope="project",
    )
    res = service.export_drawing_comments(config)
    assert res.success is False
    assert "No project is currently selected" in res.error_message


def test_7_empty_project_validation(test_setup, tmp_path):
    """TEST 7: Empty project -> returns 0 comments."""
    service = ExportService(test_setup["cmt_repo"], test_setup["proj_repo"], test_setup["dwg_repo"])
    out_file = tmp_path / "empty_proj_export.csv"
    config = ExportConfigDTO(
        output_path=out_file,
        format=ExportFormat.CSV,
        project_id=test_setup["proj_empty"]["id"],
        scope="project",
    )
    res = service.export_drawing_comments(config)
    assert res.success is True
    assert res.total_rows == 0


def test_8_department_separation(test_setup):
    """TEST 8: Verify comments retain their real engineering department."""
    comments = test_setup["cmt_repo"].get_comments_for_drawing("DWG-A1")
    depts = [c["department_name"] for c in comments]
    assert "Piping Engineering" in depts
    assert "Electrical Engineering" in depts


def test_9_classification_independence(test_setup):
    """TEST 9: Engineering Department and Error Classification are separate concepts."""
    comments = test_setup["cmt_repo"].get_comments_for_drawing("DWG-A1")
    for c in comments:
        assert "department_name" in c
        assert "category_name" in c
        assert c["department_name"] != c["category_name"]


def test_10_persistent_export_history(test_setup, tmp_path):
    """TEST 10: Successful export creates persistent export history record."""
    service = ExportService(
        test_setup["cmt_repo"],
        test_setup["proj_repo"],
        test_setup["dwg_repo"],
        test_setup["dept_repo"],
        test_setup["hist_repo"],
    )
    out_file = tmp_path / "history_test.csv"
    config = ExportConfigDTO(
        output_path=out_file,
        format=ExportFormat.CSV,
        scope="all",
    )
    res = service.export_drawing_comments(config)
    assert res.success is True

    recent = test_setup["hist_repo"].get_recent_exports()
    assert len(recent) >= 1
    latest = recent[0]
    assert latest["file_name"] == "history_test.csv"
    assert latest["total_rows"] == 9
    assert latest["status"] == "Success"


def test_11_persistent_excel_artifact_creation_and_metadata(test_setup, tmp_path):
    """TEST 11: Successful Excel export creates persistent artifact and stores full metadata in SQLite."""
    service = ExportService(
        test_setup["cmt_repo"],
        test_setup["proj_repo"],
        test_setup["dwg_repo"],
        test_setup["dept_repo"],
        test_setup["hist_repo"],
    )
    out_file = tmp_path / "persistent_excel_test.xlsx"
    config = ExportConfigDTO(
        output_path=out_file,
        format=ExportFormat.EXCEL,
        drawing_id="DWG-A1",
        scope="drawing",
        department_name="Piping Engineering",
    )
    res = service.export_drawing_comments(config)
    assert res.success is True

    recent = test_setup["hist_repo"].get_recent_exports()
    latest = recent[0]
    artifact_path = Path(latest["file_path"])
    assert artifact_path.exists()
    assert artifact_path.stat().st_size > 0

    assert latest["file_name"] == "persistent_excel_test.xlsx"
    assert latest["format"] == "Excel"
    assert latest["scope"] == "drawing"
    assert latest["drawing_id"] == "DWG-A1"
    assert latest["department_name"] == "Piping Engineering"
    assert latest["total_rows"] == 2
    assert latest["file_size_bytes"] > 0
    assert latest["status"] == "Success"
    assert "created_at" in latest and latest["created_at"] != ""


def test_12_excel_drawing_scope_template_structure(test_setup, tmp_path):
    """TEST 12: Inspect openpyxl structure for Current Loaded Drawing Excel Template."""
    service = ExportService(
        test_setup["cmt_repo"],
        test_setup["proj_repo"],
        test_setup["dwg_repo"],
        test_setup["dept_repo"],
    )
    out_file = tmp_path / "Drawing_A1_Error_Tracker.xlsx"
    config = ExportConfigDTO(
        output_path=out_file,
        format=ExportFormat.EXCEL,
        drawing_id="DWG-A1",
        scope="drawing",
        drawing_no="Drawing_A1",
    )
    res = service.export_drawing_comments(config)
    assert res.success is True

    wb = openpyxl.load_workbook(out_file)
    sheet_names = wb.sheetnames

    # Primary sheet must be "Drawing Error Tracker"
    assert "Drawing Error Tracker" in sheet_names
    ws = wb["Drawing Error Tracker"]

    # Top header title banner check
    banner_val = ws.cell(row=1, column=1).value
    assert "CURRENT LOADED DRAWING" in banner_val

    # Metadata block check (Drawing ID)
    dwg_id_val = ws.cell(row=4, column=5).value
    assert dwg_id_val == "DWG-A1"

    # Comment table header check
    table_hdr = ws.cell(row=8, column=1).value
    assert table_hdr == "Comment ID"

    # Comment data rows count (A1 has 2 comments)
    row9_cmt_id = ws.cell(row=9, column=1).value
    row10_cmt_id = ws.cell(row=10, column=1).value
    assert row9_cmt_id is not None
    assert row10_cmt_id is not None
    assert ws.cell(row=11, column=1).value is None  # Exactly 2 data rows


def test_13_excel_project_scope_template_structure(test_setup, tmp_path):
    """TEST 13: Inspect openpyxl structure for Current Project Excel Template."""
    service = ExportService(
        test_setup["cmt_repo"],
        test_setup["proj_repo"],
        test_setup["dwg_repo"],
        test_setup["dept_repo"],
    )
    out_file = tmp_path / "Project_A_Project_Error_Tracker.xlsx"
    config = ExportConfigDTO(
        output_path=out_file,
        format=ExportFormat.EXCEL,
        project_id=test_setup["proj_a"]["id"],
        scope="project",
    )
    res = service.export_drawing_comments(config)
    assert res.success is True

    wb = openpyxl.load_workbook(out_file)
    sheet_names = wb.sheetnames

    # Must contain Project Summary and All Drawing Comments
    assert "Project Summary" in sheet_names
    assert "All Drawing Comments" in sheet_names

    ws_sum = wb["Project Summary"]
    banner_val = ws_sum.cell(row=1, column=1).value
    assert "PROJECT ERROR TRACKER SUMMARY" in banner_val

    ws_cmts = wb["All Drawing Comments"]
    hdr1 = ws_cmts.cell(row=1, column=1).value
    assert hdr1 == "Drawing ID"

    # Project A comments total = 5 (A1:2 + A2:3). Row 1 is header, so rows 2-6 must be data
    data_rows = 0
    for r in range(2, 20):
        if ws_cmts.cell(row=r, column=1).value is not None:
            data_rows += 1
    assert data_rows == 5


def test_14_excel_historical_scope_template_structure(test_setup, tmp_path):
    """TEST 14: Inspect openpyxl structure for All Historical Comments Excel Template."""
    service = ExportService(
        test_setup["cmt_repo"],
        test_setup["proj_repo"],
        test_setup["dwg_repo"],
        test_setup["dept_repo"],
    )
    out_file = tmp_path / "Historical_Error_Tracker.xlsx"
    config = ExportConfigDTO(
        output_path=out_file,
        format=ExportFormat.EXCEL,
        scope="all",
    )
    res = service.export_drawing_comments(config)
    assert res.success is True

    wb = openpyxl.load_workbook(out_file)
    sheet_names = wb.sheetnames

    # Must contain Historical Summary and Historical Comments
    assert "Historical Summary" in sheet_names
    assert "Historical Comments" in sheet_names

    ws_sum = wb["Historical Summary"]
    banner_val = ws_sum.cell(row=1, column=1).value
    assert "ALL HISTORICAL COMMENTS" in banner_val

    ws_cmts = wb["Historical Comments"]
    hdr1 = ws_cmts.cell(row=1, column=1).value
    assert hdr1 == "Project ID"

    # All historical comments total = 9 (A1:2 + A2:3 + B1:4).
    data_rows = 0
    for r in range(2, 20):
        if ws_cmts.cell(row=r, column=1).value is not None:
            data_rows += 1
    assert data_rows == 9


def test_15_distinct_templates_and_datasets_proof(test_setup, tmp_path):
    """TEST 15: Prove Current Drawing != Current Project != All Historical in dataset AND template structure."""
    service = ExportService(
        test_setup["cmt_repo"],
        test_setup["proj_repo"],
        test_setup["dwg_repo"],
        test_setup["dept_repo"],
    )

    # 1. Drawing Scope (A1)
    file_dwg = tmp_path / "drawing_scope.xlsx"
    res_dwg = service.export_drawing_comments(ExportConfigDTO(
        output_path=file_dwg, format=ExportFormat.EXCEL, drawing_id="DWG-A1", scope="drawing"
    ))
    assert res_dwg.total_rows == 2

    # 2. Project Scope (Proj A)
    file_proj = tmp_path / "project_scope.xlsx"
    res_proj = service.export_drawing_comments(ExportConfigDTO(
        output_path=file_proj, format=ExportFormat.EXCEL, project_id=test_setup["proj_a"]["id"], scope="project"
    ))
    assert res_proj.total_rows == 5

    # 3. All Historical Scope
    file_hist = tmp_path / "historical_scope.xlsx"
    res_hist = service.export_drawing_comments(ExportConfigDTO(
        output_path=file_hist, format=ExportFormat.EXCEL, scope="all"
    ))
    assert res_hist.total_rows == 9

    # Verify DATASET inequality
    assert res_dwg.total_rows != res_proj.total_rows
    assert res_proj.total_rows != res_hist.total_rows
    assert res_dwg.total_rows != res_hist.total_rows

    # Verify TEMPLATE STRUCTURE inequality
    wb_dwg = openpyxl.load_workbook(file_dwg)
    wb_proj = openpyxl.load_workbook(file_proj)
    wb_hist = openpyxl.load_workbook(file_hist)

    assert "Drawing Error Tracker" in wb_dwg.sheetnames
    assert "Project Summary" in wb_proj.sheetnames
    assert "Historical Summary" in wb_hist.sheetnames

    assert "Drawing Error Tracker" not in wb_proj.sheetnames
    assert "Project Summary" not in wb_hist.sheetnames
    assert "Historical Summary" not in wb_dwg.sheetnames
