"""
tests/unit/test_batch_zip_workflow.py
Comprehensive unit test suite for Dual Upload Page (Single + Batch/Zip Folders),
Zip Slip Security, Resilient Batch Workflow Engine, Department Assignment,
Database Persistence, Analytics, History, and Export Integration.
"""

import zipfile
import pytest
from pathlib import Path
import fitz  # PyMuPDF
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop, QTimer

from src.services.file_service import FileService
from src.services.pdf_service import PDFService
from src.services.workflow_engine import ProcessingWorkflowEngine
from src.services.analytics_service import AnalyticsService
from src.services.export_service import ExportService
from src.infrastructure.pdf.pymupdf_adapter import PyMuPDFAdapter
from src.infrastructure.storage.repository import (
    DatabaseEngine,
    DrawingRepository,
    CommentRepository,
    ProjectRepository,
    EngineeringDepartmentRepository
)
from app.controllers.app_controller import AppController
from app.screens.upload_screen import UploadPage
from src.core.dtos.workflow_dtos import BatchWorkflowResultDTO, BatchWorkflowProgressDTO
from src.core.dtos.export_dtos import ExportConfigDTO, ExportFormat


@pytest.fixture
def sample_pdf_1(tmp_path: Path) -> Path:
    pdf_file = tmp_path / "drawing_A.pdf"
    doc = fitz.open()
    page = doc.new_page(width=841.89, height=595.28)
    page.insert_text((50, 50), "DRAWING NO: UCC-DWG-101", fontsize=14)
    doc.save(pdf_file)
    doc.close()
    return pdf_file


@pytest.fixture
def sample_pdf_2(tmp_path: Path) -> Path:
    pdf_file = tmp_path / "drawing_B.pdf"
    doc = fitz.open()
    page = doc.new_page(width=841.89, height=595.28)
    page.insert_text((50, 50), "DRAWING NO: UCC-DWG-102", fontsize=14)
    doc.save(pdf_file)
    doc.close()
    return pdf_file


@pytest.fixture
def sample_zip_archive(tmp_path: Path, sample_pdf_1: Path, sample_pdf_2: Path) -> Path:
    zip_path = tmp_path / "project_drawings.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(sample_pdf_1, arcname="drawings/drawing_A.pdf")
        zf.write(sample_pdf_2, arcname="drawings/drawing_B.pdf")
    return zip_path


# ── 1. Single PDF Selection & Validation ──────────────────────────────────────

def test_1_single_pdf_selection_validation(sample_pdf_1: Path):
    file_service = FileService()
    res = file_service.validate_pdf_file(sample_pdf_1)

    assert res.is_valid is True
    assert res.file_name == "drawing_A.pdf"
    assert res.file_size_mb >= 0.0
    assert len(res.file_hash_sha256) == 64


# ── 2. Multiple PDF Selection & Expansion ─────────────────────────────────────

def test_2_multiple_pdf_selection(sample_pdf_1: Path, sample_pdf_2: Path):
    file_service = FileService()
    resolved = file_service.expand_file_sources([sample_pdf_1, sample_pdf_2])

    assert len(resolved) == 2
    names = {p.name for p in resolved}
    assert "drawing_A.pdf" in names
    assert "drawing_B.pdf" in names


# ── 3. Single ZIP Extraction ──────────────────────────────────────────────────

def test_3_single_zip_extraction(sample_zip_archive: Path):
    file_service = FileService()
    extracted_pdfs = file_service.extract_zip_archive(sample_zip_archive)

    assert len(extracted_pdfs) == 2
    names = {p.name for p in extracted_pdfs}
    assert "drawing_A.pdf" in names
    assert "drawing_B.pdf" in names


# ── 4. Multiple ZIP Files Extraction ──────────────────────────────────────────

def test_4_multiple_zip_files_extraction(tmp_path: Path, sample_pdf_1: Path, sample_pdf_2: Path):
    zip1 = tmp_path / "zip1.zip"
    with zipfile.ZipFile(zip1, "w") as zf:
        zf.write(sample_pdf_1, arcname="part1/drawing_A.pdf")

    zip2 = tmp_path / "zip2.zip"
    with zipfile.ZipFile(zip2, "w") as zf:
        zf.write(sample_pdf_2, arcname="part2/drawing_B.pdf")

    file_service = FileService()
    expanded = file_service.expand_file_sources([zip1, zip2])

    assert len(expanded) == 2
    names = {p.name for p in expanded}
    assert "drawing_A.pdf" in names
    assert "drawing_B.pdf" in names


# ── 5. Mixed PDF + ZIP Selection ──────────────────────────────────────────────

def test_5_mixed_pdf_plus_zip_selection(sample_pdf_1: Path, sample_zip_archive: Path):
    file_service = FileService()
    expanded = file_service.expand_file_sources([sample_pdf_1, sample_zip_archive])

    assert len(expanded) == 2
    names = {p.name for p in expanded}
    assert "drawing_A.pdf" in names
    assert "drawing_B.pdf" in names


# ── 6. ZIP Containing Non-PDF Files (Skipping Non-PDFs) ───────────────────────

def test_6_zip_containing_non_pdf_files(tmp_path: Path, sample_pdf_1: Path):
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("Specification notes")

    img_file = tmp_path / "photo.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00")

    zip_mixed = tmp_path / "mixed.zip"
    with zipfile.ZipFile(zip_mixed, "w") as zf:
        zf.write(sample_pdf_1, arcname="drawing_A.pdf")
        zf.write(txt_file, arcname="notes.txt")
        zf.write(img_file, arcname="photo.png")

    file_service = FileService()
    extracted = file_service.extract_zip_archive(zip_mixed)

    assert len(extracted) == 1
    assert extracted[0].name == "drawing_A.pdf"


# ── 7. Corrupted ZIP Handling ──────────────────────────────────────────────────

def test_7_corrupted_zip_handling(tmp_path: Path):
    bad_zip = tmp_path / "corrupted.zip"
    bad_zip.write_bytes(b"PK\x03\x04corrupted_header_data_xyz")

    file_service = FileService()
    extracted = file_service.extract_zip_archive(bad_zip)

    assert extracted == []


# ── 8. ZIP Slip Path Traversal Protection ─────────────────────────────────────

def test_8_zip_slip_path_traversal_protection(tmp_path: Path):
    malicious_zip = tmp_path / "malicious.zip"
    with zipfile.ZipFile(malicious_zip, "w") as zf:
        zf.writestr("../../etc/malicious.pdf", "fake pdf content")

    file_service = FileService()
    extracted = file_service.extract_zip_archive(malicious_zip)

    # Should block Zip Slip attempt and return empty list
    assert extracted == []


# ── 9. Empty ZIP Handling ─────────────────────────────────────────────────────

def test_9_empty_zip_handling(tmp_path: Path):
    empty_zip = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty_zip, "w") as zf:
        pass

    file_service = FileService()
    extracted = file_service.extract_zip_archive(empty_zip)

    assert extracted == []


# ── 10. Invalid PDF File Validation ────────────────────────────────────────────

def test_10_invalid_pdf_validation(tmp_path: Path):
    file_service = FileService()

    # Non-existent
    res1 = file_service.validate_pdf_file(tmp_path / "non_existent.pdf")
    assert res1.is_valid is False

    # Non-pdf extension
    txt_file = tmp_path / "doc.txt"
    txt_file.write_text("Hello")
    res2 = file_service.validate_pdf_file(txt_file)
    assert res2.is_valid is False

    # 0 bytes empty pdf
    empty_pdf = tmp_path / "empty.pdf"
    empty_pdf.write_bytes(b"")
    res3 = file_service.validate_pdf_file(empty_pdf)
    assert res3.is_valid is False


# ── 11. Department Assignment in Batch ────────────────────────────────────────

def test_11_department_assignment_in_batch(
    tmp_path: Path, sample_zip_archive: Path
):
    db_file = tmp_path / "test_dept_assign.db"
    db_engine = DatabaseEngine(db_path=db_file)
    drawing_repo = DrawingRepository(db_engine)
    dept_repo = EngineeringDepartmentRepository(db_engine)

    dept_info = dept_repo.get_or_create_department("Electrical Engineering", "ELE-01")
    dept_id = dept_info["id"]

    file_service = FileService()
    pdf_service = PDFService(pdf_loader=PyMuPDFAdapter())

    engine = ProcessingWorkflowEngine(
        file_service=file_service,
        pdf_service=pdf_service,
        drawing_repo=drawing_repo
    )

    batch_res = engine.execute_batch_workflow([sample_zip_archive], department_id=dept_id)

    assert batch_res.successful_files_count == 2
    drawings = drawing_repo.get_recent_drawings(limit=10)
    for d in drawings:
        assert d["department_id"] == dept_id
        assert d["department_name"] == "Electrical Engineering"


# ── 12. Duplicate File Deduplication ──────────────────────────────────────────

def test_12_duplicate_file_deduplication(sample_pdf_1: Path):
    file_service = FileService()
    # Pass same file path twice
    expanded = file_service.expand_file_sources([sample_pdf_1, sample_pdf_1])

    # SHA-256 hash deduplication ensures only 1 resolved PDF
    assert len(expanded) == 1


# ── 13. Resilient Batch Processing (Partial Batch Failure) ────────────────────

def test_13_partial_batch_failure_resilience(
    tmp_path: Path, sample_pdf_1: Path
):
    db_file = tmp_path / "test_partial_fail.db"
    db_engine = DatabaseEngine(db_path=db_file)
    drawing_repo = DrawingRepository(db_engine)

    file_service = FileService()
    pdf_service = PDFService(pdf_loader=PyMuPDFAdapter())

    engine = ProcessingWorkflowEngine(
        file_service=file_service,
        pdf_service=pdf_service,
        drawing_repo=drawing_repo
    )

    # Pass 1 valid PDF and 1 non-existent path
    non_existent = tmp_path / "does_not_exist.pdf"
    
    # expand_file_sources filters non-existent paths cleanly
    expanded = file_service.expand_file_sources([sample_pdf_1, non_existent])
    assert len(expanded) == 1

    batch_res = engine.execute_batch_workflow(expanded)
    assert batch_res.successful_files_count == 1


# ── 14. History Visibility & Database Retrieval ───────────────────────────────

def test_14_history_visibility_from_database(
    tmp_path: Path, sample_zip_archive: Path
):
    db_file = tmp_path / "test_history.db"
    db_engine = DatabaseEngine(db_path=db_file)
    drawing_repo = DrawingRepository(db_engine)

    file_service = FileService()
    pdf_service = PDFService(pdf_loader=PyMuPDFAdapter())

    engine = ProcessingWorkflowEngine(
        file_service=file_service,
        pdf_service=pdf_service,
        drawing_repo=drawing_repo
    )

    engine.execute_batch_workflow([sample_zip_archive])

    recent_history = drawing_repo.get_recent_drawings(limit=10)
    assert len(recent_history) == 2
    names = {h["file_name"] for h in recent_history}
    assert "drawing_A.pdf" in names
    assert "drawing_B.pdf" in names


# ── 15. Analytics Inclusion ───────────────────────────────────────────────────

def test_15_analytics_inclusion(
    tmp_path: Path, sample_zip_archive: Path
):
    db_file = tmp_path / "test_analytics.db"
    db_engine = DatabaseEngine(db_path=db_file)
    drawing_repo = DrawingRepository(db_engine)
    comment_repo = CommentRepository(db_engine)
    analytics_service = AnalyticsService(db_engine)

    file_service = FileService()
    pdf_service = PDFService(pdf_loader=PyMuPDFAdapter())

    engine = ProcessingWorkflowEngine(
        file_service=file_service,
        pdf_service=pdf_service,
        drawing_repo=drawing_repo,
        comment_repo=comment_repo
    )

    engine.execute_batch_workflow([sample_zip_archive])

    kpis = analytics_service.get_global_kpis()
    total_dwgs = getattr(kpis, "total_drawings", 0) if not isinstance(kpis, dict) else kpis.get("total_drawings", 0)
    assert total_dwgs == 2


# ── 16. Error Tracker Export Compatibility ────────────────────────────────────

def test_16_error_tracker_export_compatibility(
    tmp_path: Path, sample_zip_archive: Path
):
    db_file = tmp_path / "test_export.db"
    db_engine = DatabaseEngine(db_path=db_file)
    drawing_repo = DrawingRepository(db_engine)
    comment_repo = CommentRepository(db_engine)
    project_repo = ProjectRepository(db_engine)
    dept_repo = EngineeringDepartmentRepository(db_engine)

    dept_info = dept_repo.get_or_create_department("Piping Engineering")
    export_service = ExportService(comment_repo, project_repo, drawing_repo, dept_repo)

    file_service = FileService()
    pdf_service = PDFService(pdf_loader=PyMuPDFAdapter())

    engine = ProcessingWorkflowEngine(
        file_service=file_service,
        pdf_service=pdf_service,
        drawing_repo=drawing_repo,
        comment_repo=comment_repo
    )

    engine.execute_batch_workflow([sample_zip_archive], department_id=dept_info["id"])

    export_cfg = ExportConfigDTO(
        scope="all",
        format=ExportFormat.EXCEL,
        output_path=tmp_path / "export_batch.xlsx"
    )

    res = export_service.export_drawing_comments(export_cfg)
    assert Path(res.output_path).exists()


# ── 17. UI Form Validation (Missing Dept or File) ─────────────────────────────

def test_17_ui_form_validation(sample_pdf_1: Path):
    app = QApplication.instance() or QApplication([])

    page = UploadPage()
    # Initially no file and no department -> invalid
    assert page._validate_forms() is False

    # Add single file
    page._on_single_file_selected(str(sample_pdf_1))
    assert page._process_btn.isEnabled() is False  # Department missing

    # Select department
    page._dept_combo.setCurrentIndex(1)
    assert page._validate_forms() is True
    assert page._process_btn.isEnabled() is True


# ── 18. AppController Batch Integration ───────────────────────────────────────

def test_18_app_controller_start_batch_workflow(
    tmp_path: Path, sample_zip_archive: Path, monkeypatch
):
    app = QApplication.instance() or QApplication([])

    db_file = tmp_path / "test_controller_batch_18.db"
    
    class DummyConfig:
        class DatabaseConfig:
            def get_resolved_db_path(self):
                return db_file
        database = DatabaseConfig()

    monkeypatch.setattr("app.controllers.app_controller.get_config", lambda: DummyConfig())

    controller = AppController()
    depts = controller.get_all_departments()
    dept_id = depts[0]["id"] if depts else "DEPT-DEF-01"

    completed_event = []
    event_loop = QEventLoop()

    def _on_completed(res):
        completed_event.append(res)
        event_loop.quit()

    controller.batch_workflow_completed_signal.connect(_on_completed)

    controller.start_batch_processing_workflow([sample_zip_archive], department_id=dept_id)

    QTimer.singleShot(10000, event_loop.quit)
    event_loop.exec()

    assert len(completed_event) == 1
    res = completed_event[0]
    assert res.total_files_processed == 2
    assert res.successful_files_count == 2


# ── 19. Separate Department Selection ─────────────────────────────────────────

def test_19_separate_department_selection(sample_pdf_1: Path, sample_zip_archive: Path):
    app = QApplication.instance() or QApplication([])
    page = UploadPage()

    page._single_dept_combo.setCurrentIndex(1)
    page._batch_dept_combo.setCurrentIndex(2)

    assert page._single_dept_combo.currentIndex() == 1
    assert page._batch_dept_combo.currentIndex() == 2
    assert page.get_single_department_name() != page.get_batch_department_name()


# ── 20. Non-Interfering Clear Actions ─────────────────────────────────────────

def test_20_non_interfering_clear_actions(sample_pdf_1: Path, sample_pdf_2: Path):
    app = QApplication.instance() or QApplication([])
    page = UploadPage()

    page._on_single_file_selected(str(sample_pdf_1))
    page._on_batch_files_selected([str(sample_pdf_2)])

    assert page._single_filepath == str(sample_pdf_1)
    assert len(page._batch_filepaths) == 1

    # Clear Batch should NOT clear Single
    page._clear_batch_files()
    assert len(page._batch_filepaths) == 0
    assert page._single_filepath == str(sample_pdf_1)

    # Clear Single should NOT clear Batch if re-added
    page._on_batch_files_selected([str(sample_pdf_2)])
    page._clear_single_file()
    assert page._single_filepath is None
    assert len(page._batch_filepaths) == 1


# ── 21. Independent Validation & Process Buttons ─────────────────────────────

def test_21_independent_validation_and_process_buttons(sample_pdf_1: Path, sample_pdf_2: Path):
    app = QApplication.instance() or QApplication([])
    page = UploadPage()

    # Initially both buttons disabled
    assert page._single_process_btn.isEnabled() is False
    assert page._batch_process_btn.isEnabled() is False

    # Valid Single setup
    page._on_single_file_selected(str(sample_pdf_1))
    page._single_dept_combo.setCurrentIndex(1)
    assert page._validate_single_form() is True
    assert page._single_process_btn.isEnabled() is True
    assert page._batch_process_btn.isEnabled() is False

    # Valid Batch setup
    page._on_batch_files_selected([str(sample_pdf_2)])
    page._batch_dept_combo.setCurrentIndex(2)
    assert page._validate_batch_form() is True
    assert page._single_process_btn.isEnabled() is True
    assert page._batch_process_btn.isEnabled() is True


# ── 22. Independent Workflow Trigger & State Isolation ────────────────────────

def test_22_independent_workflow_trigger_and_state_isolation(sample_pdf_1: Path, sample_pdf_2: Path):
    app = QApplication.instance() or QApplication([])
    page = UploadPage()

    page._on_single_file_selected(str(sample_pdf_1))
    page._single_dept_combo.setCurrentIndex(1)
    page._on_batch_files_selected([str(sample_pdf_2)])
    page._batch_dept_combo.setCurrentIndex(2)

    page._start_single_workflow()
    assert "Processing Pipeline Active" in page._single_process_btn.text()
    assert page._batch_process_btn.text() == "  Process Batch Upload"


# ── 23. AppController Workflow Method Aliases ────────────────────────────────

def test_23_app_controller_start_single_and_batch_processing_aliases():
    controller = AppController()
    assert hasattr(controller, "start_single_processing")
    assert hasattr(controller, "start_batch_processing")


# ── 24. Database Department ID Persistence Both Workflows ────────────────────

def test_24_database_department_id_persistence_both_workflows(
    tmp_path: Path, sample_pdf_1: Path, sample_pdf_2: Path
):
    db_file = tmp_path / "test_dept_persistence_both.db"
    db_engine = DatabaseEngine(db_path=db_file)
    drawing_repo = DrawingRepository(db_engine)
    dept_repo = EngineeringDepartmentRepository(db_engine)

    elec_dept = dept_repo.get_or_create_department("Electrical Engineering")
    piping_dept = dept_repo.get_or_create_department("Piping Engineering")

    file_service = FileService()
    pdf_service = PDFService(pdf_loader=PyMuPDFAdapter())

    engine = ProcessingWorkflowEngine(
        file_service=file_service,
        pdf_service=pdf_service,
        drawing_repo=drawing_repo,
    )

    # 1. Single workflow for Electrical
    res1 = engine.execute_workflow(sample_pdf_1, department_id=elec_dept["id"])
    assert res1.status == "Completed"

    # 2. Batch workflow for Piping
    res2 = engine.execute_batch_workflow([sample_pdf_2], department_id=piping_dept["id"])
    assert res2.successful_files_count == 1

    # Verify DB persistence
    dwg1 = drawing_repo.get_drawing_by_id(res1.drawing_id)
    assert dwg1["department_id"] == elec_dept["id"]
    assert dwg1["department_name"] == "Electrical Engineering"

    dwg2_id = res2.results[0].drawing_id
    dwg2 = drawing_repo.get_drawing_by_id(dwg2_id)
    assert dwg2["department_id"] == piping_dept["id"]
    assert dwg2["department_name"] == "Piping Engineering"


# ── 25. History & Analytics Include Both Workflows ───────────────────────────

def test_25_history_and_analytics_include_both_workflows(
    tmp_path: Path, sample_pdf_1: Path, sample_pdf_2: Path
):
    db_file = tmp_path / "test_history_analytics_both.db"
    db_engine = DatabaseEngine(db_path=db_file)
    drawing_repo = DrawingRepository(db_engine)
    dept_repo = EngineeringDepartmentRepository(db_engine)
    analytics_service = AnalyticsService(db_engine)

    elec_dept = dept_repo.get_or_create_department("Electrical Engineering")
    piping_dept = dept_repo.get_or_create_department("Piping Engineering")

    file_service = FileService()
    pdf_service = PDFService(pdf_loader=PyMuPDFAdapter())

    engine = ProcessingWorkflowEngine(
        file_service=file_service,
        pdf_service=pdf_service,
        drawing_repo=drawing_repo,
    )

    engine.execute_workflow(sample_pdf_1, department_id=elec_dept["id"])
    engine.execute_batch_workflow([sample_pdf_2], department_id=piping_dept["id"])

    # Recent drawings history contains both
    recent = drawing_repo.get_recent_drawings(limit=10)
    assert len(recent) == 2

    # Global analytics KPIs aggregate both
    kpis = analytics_service.get_global_kpis()
    tot_dwgs = kpis.get("total_drawings") if isinstance(kpis, dict) else getattr(kpis, "total_drawings", 0)
    assert tot_dwgs == 2

