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
    controller.current_department_id = None
    controller.current_department_name = None
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


@patch("os.path.exists", return_value=True)
def test_single_upload_refreshes_on_new_file_selection(mock_exists, qapp):
    """Verify that when a second file is uploaded, the Single File Upload UI completely refreshes."""
    mock_controller = create_mock_controller()
    mock_val = MagicMock()
    mock_val.is_valid = True
    mock_val.file_size_mb = 1.5
    mock_controller.validate_file.return_value = mock_val

    page = UploadPage(controller=mock_controller)
    page._single_dept_combo.setCurrentIndex(1)

    # 1. First file upload & processing completion
    page._on_single_file_selected("first_drawing.pdf")
    page._start_single_workflow()

    class DummyResult:
        processing_duration_seconds = 8.2

    page._on_workflow_completed(DummyResult())

    # Verify completed state (green viewer button)
    assert "View PDF Drawing" in page._single_process_btn.text()
    assert "#059669" in page._single_process_btn.styleSheet()

    # Verify open_viewer signal emission on click when in completed state
    viewer_emitted = []
    page.open_viewer_requested.connect(lambda: viewer_emitted.append(True))
    page._single_process_btn.click()
    assert len(viewer_emitted) == 1

    # 2. User selects a SECOND file
    page._on_single_file_selected("second_drawing.pdf")

    # Verify UI is completely refreshed
    assert page._single_filepath == "second_drawing.pdf"
    assert "Process Single Drawing" in page._single_process_btn.text()
    assert page._single_process_btn.styleSheet() == ""
    assert page._single_process_btn.isEnabled() is True
    assert page._single_prog.isHidden() is True
    assert page._single_prog.value() == 0
    assert page._single_timer_lbl.isHidden() is True
    assert "Ready: 'second_drawing.pdf'" in page._single_status_lbl.text()

    # 3. Clicking "Process Single Drawing" must now trigger the workflow, NOT open the viewer!
    page._single_process_btn.click()
    # It must have called start_processing_workflow on the controller with second_drawing.pdf
    mock_controller.start_processing_workflow.assert_called_with(
        "second_drawing.pdf", department_id="DEPT-01"
    )
    # The viewer signal must NOT have been emitted again
    assert len(viewer_emitted) == 1


@patch("os.path.exists", return_value=True)
def test_single_upload_clear_refreshes_ui(mock_exists, qapp):
    """Verify that clearing the single file resets button connections and hides cards."""
    mock_controller = create_mock_controller()
    page = UploadPage(controller=mock_controller)
    page._single_dept_combo.setCurrentIndex(1)

    # Simulate completed file
    page._single_filepath = "drawing_done.pdf"
    class DummyResult:
        processing_duration_seconds = 5.0
    page._on_workflow_completed(DummyResult())

    # User clicks remove (✕)
    page._clear_single_file()

    assert page._single_filepath is None
    assert page._single_file_card.isHidden() is True
    assert page._single_process_btn.isEnabled() is False
    assert "Process Single Drawing" in page._single_process_btn.text()
    assert page._single_process_btn.styleSheet() == ""
    assert page._single_prog.isHidden() is True
    assert page._single_timer_lbl.isHidden() is True

