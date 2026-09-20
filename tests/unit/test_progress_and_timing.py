"""
test_progress_and_timing.py — Unit tests for real workflow progress and timing UI integration.
"""

import sys
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication
from app.screens.upload_screen import UploadPage
from src.services.workflow_engine import WorkflowStepDTO, BatchWorkflowProgressDTO


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def create_mock_controller():
    controller = MagicMock()
    controller.get_all_departments.return_value = [
        {"id": "DEPT-01", "name": "Electrical Engineering"},
        {"id": "DEPT-02", "name": "Piping Engineering"},
    ]
    return controller


@patch("os.path.exists", return_value=True)
def test_single_workflow_progress_and_timer(mock_exists, qapp):
    mock_controller = create_mock_controller()
    page = UploadPage(controller=mock_controller)
    page._single_filepath = "dummy.pdf"
    page._single_dept_combo.setCurrentIndex(1)
    
    # 1. Start single workflow — initial range should be (0,0) indeterminate
    page._start_single_workflow()
    assert page._single_prog.minimum() == 0
    assert page._single_prog.maximum() == 0
    assert page._active_workflow_mode == UploadPage.MODE_SINGLE
    assert page._ui_timer.isActive()

    # 2. Receive 0% step — stays indeterminate
    step0 = WorkflowStepDTO("PDF Extraction", "RUNNING", 0, "Extracting pages...")
    page._on_workflow_step(step0)
    assert page._single_prog.maximum() == 0
    assert "PDF Extraction" in page._single_status_lbl.text()

    # 3. Receive 50% step — switches to determinate (0, 100)
    step50 = WorkflowStepDTO("OCR Processing", "RUNNING", 50, "Running Tesseract...")
    page._on_workflow_step(step50)
    assert page._single_prog.minimum() == 0
    assert page._single_prog.maximum() == 100
    assert page._single_prog.value() == 50
    assert "OCR Processing" in page._single_status_lbl.text()

    # 4. Timer tick test — ETA calculation
    page._workflow_start_time = page._workflow_start_time - 10  # 10s elapsed at 50% => ETA ~10s
    page._on_timer_tick()
    assert "Elapsed: 00:10" in page._single_timer_lbl.text()
    assert "ETA: ~00:10" in page._single_timer_lbl.text()

    # 5. Complete workflow — progress 100%, timer stopped
    class DummyResult:
        processing_duration_seconds = 12.5

    page._on_workflow_completed(DummyResult())
    assert page._single_prog.value() == 100
    assert not page._ui_timer.isActive()
    assert "✓ Complete in 12.5s!" in page._single_status_lbl.text()


@patch("os.path.exists", return_value=True)
def test_batch_workflow_progress_and_timer(mock_exists, qapp):
    mock_controller = create_mock_controller()
    page = UploadPage(controller=mock_controller)
    page._batch_filepaths = ["doc1.pdf", "doc2.pdf"]
    page._batch_dept_combo.setCurrentIndex(1)
    
    # 1. Start batch workflow
    page._start_batch_workflow()
    assert page._batch_prog.minimum() == 0
    assert page._batch_prog.maximum() == 0
    assert page._active_workflow_mode == UploadPage.MODE_BATCH
    assert page._ui_timer.isActive()

    # 2. Receive batch step signal
    step_inner = WorkflowStepDTO("Comment Detection", "RUNNING", 60, "Scanning...")
    batch_step = BatchWorkflowProgressDTO(
        current_file_index=1,
        total_files=2,
        current_file_name="doc1.pdf",
        overall_progress_percentage=30,
        step_snapshot=step_inner
    )
    page._on_batch_workflow_step(batch_step)
    assert page._batch_prog.maximum() == 100
    assert page._batch_prog.value() == 30
    assert "[1/2] doc1.pdf — Comment Detection (30%)" in page._batch_status_lbl.text()

    # 3. Complete batch workflow
    class DummyBatchResult:
        successful_files_count = 2
        total_files_processed = 2
        total_duration_seconds = 24.0
        total_comments_found = 15

    page._on_batch_workflow_completed(DummyBatchResult())
    assert page._batch_prog.value() == 100
    assert not page._ui_timer.isActive()
    assert "✓ Batch Complete!" in page._batch_status_lbl.text()


@patch("os.path.exists", return_value=True)
def test_workflow_error_stops_timer(mock_exists, qapp):
    mock_controller = create_mock_controller()
    page = UploadPage(controller=mock_controller)
    page._single_filepath = "dummy.pdf"
    page._single_dept_combo.setCurrentIndex(1)
    page._start_single_workflow()
    assert page._ui_timer.isActive()

    page._on_doc_error("Corrupted PDF file header")
    assert not page._ui_timer.isActive()
    assert "❌ Corrupted PDF file header" in page._single_status_lbl.text()
