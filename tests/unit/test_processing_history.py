"""
tests/unit/test_processing_history.py — Unit test suite for persistent Processing Run history and timestamps.
"""

import pytest
import pymupdf as fitz
from pathlib import Path
from datetime import datetime, timezone, timedelta

from src.infrastructure.storage.repository import (
    DatabaseEngine,
    DrawingRepository,
    ProjectRepository,
    ProcessingRunRepository,
)
from src.infrastructure.pdf.pymupdf_adapter import PyMuPDFAdapter
from src.services.pdf_service import PDFService
from src.services.file_service import FileService
from src.services.workflow_engine import ProcessingWorkflowEngine
from app.controllers.app_controller import AppController


@pytest.fixture
def test_db_engine(tmp_path):
    db_file = tmp_path / "test_processing_history.db"
    return DatabaseEngine(db_path=db_file)


@pytest.fixture
def sample_pdf_drawing(tmp_path):
    """Generates a simple 1-page sample PDF file in a temporary folder."""
    temp_dir = tmp_path / "temp_user_downloads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = temp_dir / "processing_run_sample.pdf"

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((50, 50), "UCC Processing Run Test Content", fontsize=14)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_1_processing_run_creation(test_db_engine):
    """TEST 1: Create initial processing run record in database."""
    run_repo = ProcessingRunRepository(test_db_engine)
    start_dt = datetime.now(timezone.utc)

    run = run_repo.create_processing_run(
        file_name="structural_plan.pdf",
        status="PROCESSING",
        started_at=start_dt,
    )

    assert run["id"].startswith("RUN-")
    assert run["original_filename"] == "structural_plan.pdf"
    assert run["status"] == "PROCESSING"
    assert run["started_at"] != ""
    assert run["completed_at"] == ""
    assert run["duration_seconds"] == 0.0


def test_2_completed_processing_run(test_db_engine, sample_pdf_drawing):
    """TEST 2: Update processing run to COMPLETED with duration and timestamps."""
    file_service = FileService()
    pdf_service = PDFService(pdf_loader=PyMuPDFAdapter())
    dwg_repo = DrawingRepository(test_db_engine)
    proj_repo = ProjectRepository(test_db_engine)
    run_repo = ProcessingRunRepository(test_db_engine)

    proj = proj_repo.create_project(name="Project Alpha", description="Test")
    persistent_path = file_service.copy_to_managed_storage(sample_pdf_drawing)
    doc_dto = pdf_service.process_pdf_document(persistent_path)
    res_dwg = dwg_repo.save_drawing_from_dto(doc_dto, project_id=proj["id"])

    start_dt = datetime.now(timezone.utc)
    comp_dt = start_dt + timedelta(seconds=4, microseconds=500000)

    initial = run_repo.create_processing_run(
        file_name="piping_diagram.pdf",
        status="PROCESSING",
        started_at=start_dt,
    )
    run_id = initial["id"]

    updated = run_repo.update_processing_run(
        run_id=run_id,
        status="COMPLETED",
        drawing_id=res_dwg["id"],
        project_id=proj["id"],
        completed_at=comp_dt,
        duration_seconds=4.5,
    )

    assert updated is not None
    assert updated["status"] == "COMPLETED"
    assert updated["drawing_id"] == res_dwg["id"]
    assert updated["project_id"] == proj["id"]
    assert updated["duration_seconds"] == 4.5
    assert updated["completed_at"] != ""
    assert updated["updated_at"] != ""


def test_3_failed_processing_run(test_db_engine):
    """TEST 3: Update processing run to FAILED with error message."""
    run_repo = ProcessingRunRepository(test_db_engine)

    initial = run_repo.create_processing_run(file_name="corrupted.pdf", status="PROCESSING")
    run_id = initial["id"]

    updated = run_repo.update_processing_run(
        run_id=run_id,
        status="FAILED",
        completed_at=datetime.now(timezone.utc),
        duration_seconds=0.8,
        error_message="Corrupted PDF bytes encounter: EOF invalid",
    )

    assert updated is not None
    assert updated["status"] == "FAILED"
    assert updated["error_message"] == "Corrupted PDF bytes encounter: EOF invalid"
    assert updated["duration_seconds"] == 0.8


def test_4_multiple_runs_for_same_drawing_not_deleted(test_db_engine, sample_pdf_drawing):
    """TEST 4: Reprocessing a drawing creates multiple distinct processing runs without overwriting or deleting historical runs."""
    file_service = FileService()
    pdf_service = PDFService(pdf_loader=PyMuPDFAdapter())
    dwg_repo = DrawingRepository(test_db_engine)
    proj_repo = ProjectRepository(test_db_engine)
    run_repo = ProcessingRunRepository(test_db_engine)

    proj = proj_repo.create_project(name="Project Multirun", description="Test")
    engine = ProcessingWorkflowEngine(
        file_service=file_service,
        pdf_service=pdf_service,
        drawing_repo=dwg_repo,
        processing_run_repo=run_repo,
    )

    # 1. Run 1 (20 Sep 2026 simulation)
    res1 = engine.execute_workflow(sample_pdf_drawing)
    dwg_id = res1.drawing_id

    # 2. Run 2 (25 Sep 2026 simulation)
    res2 = engine.execute_workflow(sample_pdf_drawing)
    assert res2.drawing_id == dwg_id

    # Query processing history for drawing
    runs = run_repo.get_processing_history_for_drawing(dwg_id)
    assert len(runs) == 2
    assert runs[0]["id"] != runs[1]["id"]
    assert runs[0]["status"] == "COMPLETED"
    assert runs[1]["status"] == "COMPLETED"


def test_5_repository_query_methods(test_db_engine, sample_pdf_drawing):
    """TEST 5: Test repository filtering for drawing history, project history, and latest run."""
    file_service = FileService()
    pdf_service = PDFService(pdf_loader=PyMuPDFAdapter())
    dwg_repo = DrawingRepository(test_db_engine)
    proj_repo = ProjectRepository(test_db_engine)
    run_repo = ProcessingRunRepository(test_db_engine)

    proj_a = proj_repo.create_project(name="Project A", description="Test A")
    proj_b = proj_repo.create_project(name="Project B", description="Test B")

    persistent_path = file_service.copy_to_managed_storage(sample_pdf_drawing)
    doc_dto = pdf_service.process_pdf_document(persistent_path)
    res_dwg1 = dwg_repo.save_drawing_from_dto(doc_dto, project_id=proj_a["id"])
    dwg1_id = res_dwg1["id"]

    # Run 1 & 2 for Drawing 1
    run_repo.create_processing_run(file_name="dwg1.pdf", drawing_id=dwg1_id, project_id=proj_a["id"], status="COMPLETED")
    run_repo.create_processing_run(file_name="dwg1.pdf", drawing_id=dwg1_id, project_id=proj_a["id"], status="COMPLETED")
    # Run for Project B
    run_repo.create_processing_run(file_name="dwg2.pdf", project_id=proj_b["id"], status="FAILED")

    dwg1_runs = run_repo.get_processing_history_for_drawing(dwg1_id)
    assert len(dwg1_runs) == 2

    prj_a_runs = run_repo.get_processing_history_for_project(proj_a["id"])
    assert len(prj_a_runs) == 2

    latest_dwg1 = run_repo.get_latest_processing_run(drawing_id=dwg1_id)
    assert latest_dwg1 is not None
    assert latest_dwg1["drawing_id"] == dwg1_id

    latest_global = run_repo.get_latest_processing_run()
    assert latest_global is not None


def test_6_app_controller_history_methods(test_db_engine, sample_pdf_drawing):
    """TEST 6: Test AppController methods for retrieving processing history without direct SQLite queries."""
    controller = AppController(db_engine=test_db_engine)

    proj = controller.project_repo.create_project(name="Ctrl Project", description="Test")
    persistent_path = controller.file_service.copy_to_managed_storage(sample_pdf_drawing)
    doc_dto = controller.pdf_service.process_pdf_document(persistent_path)
    res_dwg = controller.drawing_repo.save_drawing_from_dto(doc_dto, project_id=proj["id"])
    dwg_id = res_dwg["id"]

    # Create run via controller's repository
    controller.processing_run_repo.create_processing_run(
        file_name="ctrl_drawing.pdf",
        drawing_id=dwg_id,
        project_id=proj["id"],
        status="COMPLETED",
    )

    dwg_runs = controller.get_processing_history_for_drawing(dwg_id)
    assert len(dwg_runs) == 1
    assert dwg_runs[0]["drawing_id"] == dwg_id

    prj_runs = controller.get_processing_history_for_project(proj["id"])
    assert len(prj_runs) == 1
    assert prj_runs[0]["project_id"] == proj["id"]

    latest = controller.get_latest_processing_run(drawing_id=dwg_id)
    assert latest is not None
    assert latest["file_name"] == "ctrl_drawing.pdf"
