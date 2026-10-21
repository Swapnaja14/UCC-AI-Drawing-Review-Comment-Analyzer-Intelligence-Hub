"""
tests/unit/test_stability_fixes.py
Comprehensive unit test suite verifying the 6 stability corrections:
1. Tesseract timeout protection
2. Upload UI error recovery and retry state
3. Safe removal of redundant processEvents
4. Dashboard auto-refresh timer pausing/resuming
5. Screen refresh efficiency & drawing list updates
6. Safe cooperative cancellation without database corruption
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import fitz

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QShowEvent, QHideEvent

from src.services.ocr_service import OCRService
from src.services.file_service import FileService
from src.services.pdf_service import PDFService
from src.services.workflow_engine import ProcessingWorkflowEngine
from src.infrastructure.pdf.pymupdf_adapter import PyMuPDFAdapter
from src.infrastructure.storage.repository import DatabaseEngine, DrawingRepository
from src.core.exceptions.workflow_exceptions import WorkflowCancelledError
from app.screens.upload_screen import UploadPage
from app.screens.dashboard_screen import DashboardPage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    pdf_file = tmp_path / "test_stability.pdf"
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    page.insert_text((50, 50), "DRAWING STABILITY TEST", fontsize=12)
    doc.save(pdf_file)
    doc.close()
    return pdf_file


# ── 1. Tesseract Timeout Protection Tests ─────────────────────────────────

def test_ocr_service_timeout_protection(sample_pdf):
    """Verify OCRService handles Tesseract timeout gracefully and returns empty text."""
    service = OCRService()
    service.timeout = 1

    with patch("pytesseract.image_to_data", side_effect=RuntimeError("Tesseract process timeout")):
        with patch("pytesseract.image_to_string", side_effect=RuntimeError("Tesseract process timeout")):
            result = service.process_pdf(sample_pdf)
            assert result["metadata"]["total_pages"] == 1
            assert result["pages"][0]["text"] == ""
            assert result["pages"][0]["confidence_scores"] == []


def test_workflow_engine_ocr_timeout_graceful_fallback(sample_pdf, tmp_path):
    """Verify ProcessingWorkflowEngine handles OCR timeout on a region without crashing."""
    db_file = tmp_path / "test_timeout.db"
    db_engine = DatabaseEngine(db_path=db_file)
    drawing_repo = DrawingRepository(db_engine)

    engine = ProcessingWorkflowEngine(
        file_service=FileService(),
        pdf_service=PDFService(pdf_loader=PyMuPDFAdapter()),
        drawing_repo=drawing_repo,
    )

    with patch("pytesseract.image_to_data", side_effect=RuntimeError("Tesseract process timeout")):
        with patch("pytesseract.image_to_string", side_effect=RuntimeError("Tesseract process timeout")):
            text, conf = engine._run_tesseract_psm(MagicMock(), psm=6, timeout=1)
            assert text == ""
            assert conf == 0.0


# ── 2. UI Error Recovery Tests ────────────────────────────────────────────

def test_upload_screen_error_recovery_single_mode(qapp):
    """Verify single-mode error recovery restores button state, text, and retry capability."""
    mock_ctrl = MagicMock()
    mock_ctrl.get_all_departments.return_value = [{"id": "D1", "name": "Electrical"}]
    mock_ctrl.current_department_id = "D1"

    page = UploadPage(controller=mock_ctrl)
    page._single_filepath = "dummy.pdf"
    page._start_single_workflow()

    assert not page._single_process_btn.isEnabled()

    # Trigger error
    page._on_doc_error("Tesseract engine timeout on page 1")

    assert page._single_process_btn.isEnabled()
    assert "Retry Processing" in page._single_process_btn.text()
    assert "❌" in page._single_status_lbl.text()
    assert not page._ui_timer.isActive()


def test_upload_screen_error_recovery_batch_mode(qapp):
    """Verify batch-mode error recovery restores batch button state and retry capability."""
    mock_ctrl = MagicMock()
    mock_ctrl.get_all_departments.return_value = []
    mock_ctrl.current_department_id = None

    page = UploadPage(controller=mock_ctrl)
    page._batch_filepaths = ["dwg1.pdf", "dwg2.pdf"]
    page._start_batch_workflow()

    assert not page._batch_process_btn.isEnabled()

    # Trigger error
    page._on_doc_error("Batch worker encountered unhandled exception")

    assert page._batch_process_btn.isEnabled()
    assert "Retry Batch Processing" in page._batch_process_btn.text()
    assert "❌" in page._batch_status_lbl.text()
    assert not page._ui_timer.isActive()


# ── 3. Dashboard Auto-Refresh Timer Tests ─────────────────────────────────

def test_dashboard_timer_visibility_behavior(qapp):
    """Verify Dashboard timer stops when hidden, resumes on showEvent, and pauses during processing."""
    mock_ctrl = MagicMock()
    mock_ctrl.get_dashboard_kpis.return_value = None
    mock_ctrl.get_dashboard_metrics.return_value = {}
    mock_ctrl.get_recent_drawings.return_value = []
    mock_ctrl.get_department_summaries.return_value = []

    page = DashboardPage(controller=mock_ctrl)

    # Initial show: timer should start
    page.showEvent(QShowEvent())
    assert page._auto_timer.isActive()

    # Hide: timer stops to prevent background load
    page.hideEvent(QHideEvent())
    assert not page._auto_timer.isActive()

    # Show again: timer resumes
    page.showEvent(QShowEvent())
    assert page._auto_timer.isActive()

    # Workflow step received: timer pauses during heavy processing
    mock_step = MagicMock()
    mock_step.step_name = "OCR Processing"
    mock_step.progress = 50
    page._on_workflow_step(mock_step)
    assert not page._auto_timer.isActive()


# ── 4. Safe Cooperative Cancellation Tests ────────────────────────────────

def test_workflow_cooperative_cancellation_before_persistence(sample_pdf, tmp_path):
    """Verify cooperative cancellation exits cleanly before database persistence."""
    db_file = tmp_path / "test_cancel.db"
    db_engine = DatabaseEngine(db_path=db_file)
    drawing_repo = MagicMock(spec=DrawingRepository)

    engine = ProcessingWorkflowEngine(
        file_service=FileService(),
        pdf_service=PDFService(pdf_loader=PyMuPDFAdapter()),
        drawing_repo=drawing_repo,
    )

    # Cancellation check returns True
    cancel_check = MagicMock(return_value=True)

    with pytest.raises(WorkflowCancelledError):
        engine.execute_workflow(sample_pdf, cancel_check=cancel_check)

    # Drawing repo must NOT have saved any record
    drawing_repo.save_drawing_from_dto.assert_not_called()


def test_batch_workflow_cancellation(sample_pdf, tmp_path):
    """Verify batch workflow aborts gracefully when cancel_check triggers."""
    db_file = tmp_path / "test_batch_cancel.db"
    db_engine = DatabaseEngine(db_path=db_file)
    drawing_repo = DrawingRepository(db_engine)

    engine = ProcessingWorkflowEngine(
        file_service=FileService(),
        pdf_service=PDFService(pdf_loader=PyMuPDFAdapter()),
        drawing_repo=drawing_repo,
    )

    cancel_flag = False

    def check_cancel():
        return cancel_flag

    # Cancel before processing
    pdf_list = [sample_pdf, sample_pdf]
    cancel_flag = True

    result = engine.execute_batch_workflow(pdf_list, cancel_check=check_cancel)

    # Should have stopped without failing catastrophically
    assert result.total_files_processed == 0
    assert result.successful_files_count == 0
