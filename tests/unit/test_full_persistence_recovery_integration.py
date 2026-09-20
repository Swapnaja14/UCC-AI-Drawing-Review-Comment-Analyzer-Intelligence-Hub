"""
test_full_persistence_recovery_integration.py — Integration test for Feature 7:
Complete persistence, audit history, app restart recovery, multi-run history,
and export scope integration flow.
"""

import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
import openpyxl
import pytest
import pymupdf as fitz

from src.config import get_config
from src.infrastructure.storage.repository import (
    DatabaseEngine,
    ProjectRepository,
    DrawingRepository,
    CommentRepository,
    AuditLogRepository,
    ExportHistoryRepository,
    ProcessingRunRepository,
    EngineeringDepartmentRepository,
    CategoryRepository,
)
from src.infrastructure.storage.models import Base
from src.services.file_service import FileService
from src.services.pdf_service import PDFService
from src.services.workflow_engine import ProcessingWorkflowEngine
from src.services.export_service import ExportService
from src.core.dtos.export_dtos import ExportConfigDTO, ExportFormat
from app.controllers.app_controller import AppController


def create_sample_pdf(file_path: Path, title: str, comments_text: list[str]):
    """Helper to create a simple valid PDF with text and annotations for testing."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((50, 30), f"TITLE: {title}", fontsize=12)
    page.insert_text((50, 50), "DRAWING NUMBER: DWG-TEST-100", fontsize=10)
    
    for idx, text in enumerate(comments_text):
        y = 400 + (idx * 60)
        page.insert_text((100, y), text, fontsize=11, color=(1, 0, 0))
        rect = fitz.Rect(95, y - 10, 500, y + 25)
        annot = page.add_freetext_annot(rect, text)
        annot.update()
        
    doc.save(file_path)
    doc.close()


@pytest.fixture
def integration_env(tmp_path: Path):
    db_file = tmp_path / "integration_test.db"
    storage_dir = tmp_path / "app_data"
    drawings_dir = storage_dir / "drawings"
    exports_dir = storage_dir / "exports"
    drawings_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    engine = DatabaseEngine(db_path=db_file)
    Base.metadata.create_all(engine.engine)

    file_service = FileService()
    
    yield {
        "db_file": db_file,
        "engine": engine,
        "storage_dir": storage_dir,
        "drawings_dir": drawings_dir,
        "exports_dir": exports_dir,
        "file_service": file_service,
        "tmp_path": tmp_path,
    }


def test_complete_persistence_recovery_integration_flow(integration_env):
    db_file = integration_env["db_file"]
    engine = integration_env["engine"]
    file_service = integration_env["file_service"]
    tmp_path = integration_env["tmp_path"]

    proj_repo = ProjectRepository(engine)
    dept_repo = EngineeringDepartmentRepository(engine)
    cat_repo = CategoryRepository(engine)
    dwg_repo = DrawingRepository(engine)
    cmt_repo = CommentRepository(engine)
    audit_repo = AuditLogRepository(engine)
    export_repo = ExportHistoryRepository(engine)
    run_repo = ProcessingRunRepository(engine)

    # 1. Create/select a project
    project = proj_repo.create_project(name="UCC AI Test Project")
    proj_id = project["id"]
    assert proj_id is not None

    # 2. Select engineering department
    departments = dept_repo.get_all_departments()
    dept_id = departments[0]["id"] if departments else "DEPT-ELEC"

    # 3. Upload Drawing A
    pdf_a_path = tmp_path / "Drawing_A.pdf"
    create_sample_pdf(pdf_a_path, "Drawing A - Electrical", [
        "Check cable tray support clearance 300mm",
        "Transformer earthing conductor size insufficient"
    ])
    assert pdf_a_path.exists()

    # 4. Process Drawing A
    from src.infrastructure.pdf.pymupdf_adapter import PyMuPDFAdapter
    workflow_engine = ProcessingWorkflowEngine(
        file_service=file_service,
        pdf_service=PDFService(pdf_loader=PyMuPDFAdapter()),
        drawing_repo=dwg_repo,
        comment_repo=cmt_repo,
        audit_repo=audit_repo,
        processing_run_repo=run_repo,
    )

    result_a = workflow_engine.execute_workflow(pdf_a_path, department_id=dept_id, project_id=proj_id)

    # 5. Verify real progress/timing
    assert result_a.status == "Completed"
    assert result_a.processing_duration_seconds >= 0.0
    dwg_a_id = result_a.drawing_id
    assert dwg_a_id is not None and dwg_a_id.startswith("DWG-")

    # 6. Verify processing run is stored
    runs_a_1 = run_repo.get_processing_history_for_drawing(dwg_a_id)
    assert len(runs_a_1) == 1
    assert runs_a_1[0]["status"] == "COMPLETED"
    run_1_id = runs_a_1[0]["id"]

    # 7. Verify comments are stored
    comments_a = cmt_repo.get_comments_for_drawing(dwg_a_id)
    assert len(comments_a) >= 1
    cmt_target = comments_a[0]
    cmt_target_id = cmt_target["id"]

    # 8. Verify OCR is stored
    assert cmt_target["raw_text"] != ""

    # 9. Verify classification is stored
    assert cmt_target["category_name"] != ""

    # 10. Verify source PDF is persistent
    dwg_a_rec = dwg_repo.get_drawing_by_id(dwg_a_id)
    managed_pdf_path = Path(dwg_a_rec["file_path"])
    assert managed_pdf_path.exists()

    # 11. Export Error Tracker
    export_service = ExportService(
        comment_repo=cmt_repo,
        project_repo=proj_repo,
        drawing_repo=dwg_repo,
        department_repo=dept_repo,
        export_history_repo=export_repo,
    )

    excel_output_path = tmp_path / "Error_Tracker_Drawing_A.xlsx"
    export_cfg = ExportConfigDTO(
        drawing_id=dwg_a_id,
        project_id=proj_id,
        format=ExportFormat.EXCEL,
        output_path=str(excel_output_path),
        scope="drawing",
    )
    exp_res = export_service.export_drawing_comments(export_cfg)
    assert exp_res.success is True

    # 12. Verify Excel file is persistent
    assert Path(exp_res.output_path).exists()
    first_excel_path = Path(exp_res.output_path)

    # 13. Verify export history is stored
    export_logs = export_repo.get_recent_exports()
    assert len(export_logs) >= 1
    latest_log = export_logs[0]
    assert latest_log["drawing_id"] == dwg_a_id

    # 14. Edit one historical comment
    initial_raw = cmt_target["raw_text"]
    cmt_repo.update_comment_category(
        cmt_target_id,
        new_category="Design Error",
        changed_by_user_id="reviewer_lead",
    )
    cmt_repo.update_comment_text(
        cmt_target_id,
        new_text="Check cable tray support clearance 300mm (Verified per NEC 392)",
        changed_by_user_id="reviewer_lead",
    )

    # 15. Save the change (implicitly committed in update methods)
    # 16. Verify audit history
    audits = audit_repo.get_audit_logs_for_comment(cmt_target_id)
    assert len(audits) >= 2

    # 17. CLOSE THE APPLICATION COMPLETELY
    del workflow_engine
    del export_service
    del engine

    # 18. REOPEN THE APPLICATION
    new_engine = DatabaseEngine(db_path=db_file)
    new_controller = AppController(db_engine=new_engine)

    # 19. Open the same project
    new_controller.current_project_id = proj_id
    assert new_controller.current_project_id == proj_id

    # 20. Open Drawing A
    switch_ok = new_controller.switch_current_drawing(dwg_a_id)
    assert switch_ok is True
    assert new_controller.current_drawing_id == dwg_a_id

    # 21. Verify comments
    reloaded_comments = new_controller.comment_repo.get_comments_for_drawing(dwg_a_id)
    assert len(reloaded_comments) == len(comments_a)

    # 22. Verify OCR
    reloaded_target = next(c for c in reloaded_comments if c["id"] == cmt_target_id)
    assert reloaded_target["raw_text"] == initial_raw

    # 23. Verify classification
    assert reloaded_target["category_name"] == "Design Error"

    # 24. Verify edited historical value
    assert reloaded_target["cleaned_text"] == "Check cable tray support clearance 300mm (Verified per NEC 392)"
    assert reloaded_target["is_verified_by_human"] is True

    # 25. Verify processing history
    reloaded_runs = new_controller.processing_run_repo.get_processing_history_for_drawing(dwg_a_id)
    assert len(reloaded_runs) == 1
    assert reloaded_runs[0]["id"] == run_1_id

    # 26. Verify export history
    reloaded_exports = new_controller.export_history_repo.get_recent_exports()
    assert len(reloaded_exports) >= 1

    # 27. Verify previous Excel artifact can still be opened
    wb = openpyxl.load_workbook(first_excel_path)
    assert len(wb.sheetnames) >= 1
    wb.close()

    # ── Then process Drawing A again ──────────────────────────────────────
    result_a_run2 = new_controller.workflow_engine.execute_workflow(
        managed_pdf_path, department_id=dept_id, project_id=proj_id
    )
    assert result_a_run2.status == "Completed"

    # Verify: Run 1 remains, Run 2 is created
    runs_a_2 = new_controller.processing_run_repo.get_processing_history_for_drawing(dwg_a_id)
    assert len(runs_a_2) == 2
    run_ids = [r["id"] for r in runs_a_2]
    assert run_1_id in run_ids

    # ── Then test Drawing B & Drawing C ───────────────────────────────────
    pdf_b_path = tmp_path / "Drawing_B.pdf"
    create_sample_pdf(pdf_b_path, "Drawing B - Piping", [
        "Piping valve schedule missing bypass isolation"
    ])
    result_b = new_controller.workflow_engine.execute_workflow(pdf_b_path, department_id=dept_id, project_id=proj_id)
    dwg_b_id = result_b.drawing_id
    assert result_b.total_comments_found >= 1

    pdf_c_path = tmp_path / "Drawing_C.pdf"
    create_sample_pdf(pdf_c_path, "Drawing C - Structural", [
        "Structural beam splice weld detail uncertified"
    ])
    result_c = new_controller.workflow_engine.execute_workflow(pdf_c_path, department_id=dept_id, project_id=proj_id)
    dwg_c_id = result_c.drawing_id
    assert result_c.total_comments_found >= 1

    cmts_a = new_controller.comment_repo.get_comments_for_drawing(dwg_a_id)
    cmts_b = new_controller.comment_repo.get_comments_for_drawing(dwg_b_id)
    cmts_c = new_controller.comment_repo.get_comments_for_drawing(dwg_c_id)
    assert len(cmts_a) >= 1
    assert len(cmts_b) >= 1
    assert len(cmts_c) >= 1

    # ── Verify project-level export includes all drawings ────────────────
    excel_project_path = tmp_path / "Project_Level_Export.xlsx"
    proj_export_cfg = ExportConfigDTO(
        project_id=proj_id,
        format=ExportFormat.EXCEL,
        output_path=str(excel_project_path),
        scope="project",
    )
    proj_exp_res = new_controller.export_service.export_drawing_comments(proj_export_cfg)
    assert proj_exp_res.success is True
    assert proj_exp_res.total_rows >= 4

    # ── Verify historical export includes all persisted comments ─────────
    excel_all_path = tmp_path / "Historical_Export_All.xlsx"
    all_export_cfg = ExportConfigDTO(
        format=ExportFormat.EXCEL,
        output_path=str(excel_all_path),
        scope="all",
    )
    all_exp_res = new_controller.export_service.export_drawing_comments(all_export_cfg)
    assert all_exp_res.success is True
    assert all_exp_res.total_rows >= 4
