"""
tests/unit/test_export_scopes.py — Test suite for Export Scopes and persistent Export History.
"""

import pytest
from pathlib import Path

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
from app.controllers.app_controller import AppController


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
        Drawing A2 -> 3 comments (Piping Engineering & Structural)
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
    # Drawing A1
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
    """TEST 5: No current drawing -> Current Loaded Drawing export returns zero rows."""
    service = ExportService(test_setup["cmt_repo"], test_setup["proj_repo"], test_setup["dwg_repo"])
    out_file = tmp_path / "no_dwg_export.csv"
    config = ExportConfigDTO(
        output_path=out_file,
        format=ExportFormat.CSV,
        drawing_id=None,
        scope="drawing",
    )
    res = service.export_drawing_comments(config)
    assert res.success is True
    assert res.total_rows == 0


def test_6_no_current_project_graceful(test_setup, tmp_path):
    """TEST 6: No current project -> Current Project export handles empty project_id."""
    service = ExportService(test_setup["cmt_repo"], test_setup["proj_repo"], test_setup["dwg_repo"])
    out_file = tmp_path / "no_proj_export.csv"
    config = ExportConfigDTO(
        output_path=out_file,
        format=ExportFormat.CSV,
        project_id=None,
        scope="project",
    )
    res = service.export_drawing_comments(config)
    # When project_id is None, it defaults to historical fallback or zero
    assert res.success is True


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
        # Department and category names are distinct fields
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

    # Query persistent history
    recent = test_setup["hist_repo"].get_recent_exports()
    assert len(recent) == 1
    assert recent[0]["name"] == "history_test.csv"
    assert recent[0]["total_rows"] == 9
