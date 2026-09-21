"""
test_context_aware_drawings_visibility.py — Unit tests for context-aware drawings sidebar.

Tests:
1. AppController active_upload_mode, current_batch_drawing_ids, and get_batch_drawings().
2. PdfToolbar toggle_sidebar_requested signal and set_sidebar_button_checked().
3. PdfViewerPage sidebar visibility defaults, context-aware toggle, and batch drawings scoping.
"""

import pytest
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.infrastructure.storage.repository import (
    DatabaseEngine,
    DrawingRepository,
    ProjectRepository,
)
from src.core.dtos.pdf_dtos import PDFDocumentDTO, PageMetadataDTO
from src.core.dtos.workflow_dtos import WorkflowResultDTO, BatchWorkflowResultDTO
from app.controllers.app_controller import AppController
from app.components.pdf_toolbar import PdfToolbar
from app.screens.pdf_viewer_screen import PdfViewerPage


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    engine = DatabaseEngine(db_path)
    yield engine
    try:
        engine.engine.dispose()
    except Exception:
        pass
    try:
        db_path.unlink(missing_ok=True)
    except Exception:
        pass


def test_app_controller_batch_and_single_mode_tracking(temp_db):
    """Verify AppController tracks upload mode and scopes batch drawings correctly."""
    controller = AppController(db_engine=temp_db)
    assert controller.active_upload_mode == "SINGLE"
    assert controller.current_batch_drawing_ids == []

    # Create dummy drawings in DB
    dwg_repo = DrawingRepository(temp_db)
    proj_repo = ProjectRepository(temp_db)
    proj = proj_repo.create_project("Project Alpha", "CTR-01", "Austin")
    proj_id = proj["id"]

    dto1 = PDFDocumentDTO(
        file_path=Path("/path/to/D1.pdf"),
        file_name="D1.pdf",
        file_size_bytes=1000,
        file_hash_sha256="hash1",
        total_pages=1,
        is_encrypted=False,
        is_scanned=False,
        pages=[PageMetadataDTO(1, 600, 800, 0.75, True, 50, 0)],
    )
    dto2 = PDFDocumentDTO(
        file_path=Path("/path/to/D2.pdf"),
        file_name="D2.pdf",
        file_size_bytes=2000,
        file_hash_sha256="hash2",
        total_pages=2,
        is_encrypted=False,
        is_scanned=False,
        pages=[PageMetadataDTO(1, 600, 800, 0.75, True, 50, 0)],
    )
    dto3 = PDFDocumentDTO(
        file_path=Path("/path/to/D3.pdf"),
        file_name="D3.pdf",
        file_size_bytes=3000,
        file_hash_sha256="hash3",
        total_pages=3,
        is_encrypted=False,
        is_scanned=False,
        pages=[PageMetadataDTO(1, 600, 800, 0.75, True, 50, 0)],
    )

    d1 = dwg_repo.save_drawing_from_dto(dto1, project_id=proj_id)
    d2 = dwg_repo.save_drawing_from_dto(dto2, project_id=proj_id)
    d3 = dwg_repo.save_drawing_from_dto(dto3, project_id=proj_id)

    # Test Single Workflow completed
    single_res = WorkflowResultDTO(
        drawing_id=d1["id"],
        file_name="D1.pdf",
        total_pages=1,
        is_scanned=False,
        status="SUCCESS",
    )
    controller._on_workflow_completed(single_res)
    assert controller.active_upload_mode == "SINGLE"
    assert controller.current_batch_drawing_ids == [d1["id"]]

    # Test Batch Workflow completed with d2 and d3 only
    batch_res = BatchWorkflowResultDTO(
        total_files_processed=2,
        successful_files_count=2,
        failed_files_count=0,
        total_comments_found=0,
        total_duration_seconds=1.2,
        results=[
            WorkflowResultDTO(drawing_id=d2["id"], file_name="D2.pdf", total_pages=2, is_scanned=False, status="SUCCESS"),
            WorkflowResultDTO(drawing_id=d3["id"], file_name="D3.pdf", total_pages=3, is_scanned=False, status="SUCCESS"),
        ],
    )
    controller._on_batch_workflow_completed(batch_res)
    assert controller.active_upload_mode == "BATCH"
    assert controller.current_batch_drawing_ids == [d2["id"], d3["id"]]

    # get_batch_drawings should ONLY return d2 and d3, not d1
    batch_dwgs = controller.get_batch_drawings()
    assert len(batch_dwgs) == 2
    batch_dwg_ids = [d["id"] for d in batch_dwgs]
    assert d2["id"] in batch_dwg_ids
    assert d3["id"] in batch_dwg_ids
    assert d1["id"] not in batch_dwg_ids


def test_pdf_toolbar_toggle_sidebar_button(qapp):
    """Verify PdfToolbar has Drawings toggle button and emits toggle_sidebar_requested."""
    toolbar = PdfToolbar(total_pages=5)
    assert hasattr(toolbar, "_toggle_sidebar_btn")
    assert hasattr(toolbar, "toggle_sidebar_requested")

    emitted = []
    toolbar.toggle_sidebar_requested.connect(lambda: emitted.append(True))

    toolbar._toggle_sidebar_btn.click()
    assert len(emitted) == 1

    toolbar.set_sidebar_button_checked(True)
    assert toolbar._toggle_sidebar_btn.isChecked() is True

    toolbar.set_sidebar_button_checked(False)
    assert toolbar._toggle_sidebar_btn.isChecked() is False


def test_pdf_viewer_page_context_visibility_and_batch_scoping(qapp, temp_db):
    """Verify PdfViewerPage auto-collapses in single mode, auto-expands in batch mode, and scopes items."""
    controller = AppController(db_engine=temp_db)
    dwg_repo = DrawingRepository(temp_db)
    proj_repo = ProjectRepository(temp_db)
    proj = proj_repo.create_project("Project Beta", "CTR-02", "Houston")

    dto1 = PDFDocumentDTO(
        file_path=Path("/path/to/Single.pdf"),
        file_name="Single.pdf",
        file_size_bytes=1000,
        file_hash_sha256="hash_single",
        total_pages=1,
        is_encrypted=False,
        is_scanned=False,
        pages=[PageMetadataDTO(1, 600, 800, 0.75, True, 50, 0)],
    )
    dto2 = PDFDocumentDTO(
        file_path=Path("/path/to/BatchA.pdf"),
        file_name="BatchA.pdf",
        file_size_bytes=2000,
        file_hash_sha256="hash_batch_a",
        total_pages=1,
        is_encrypted=False,
        is_scanned=False,
        pages=[PageMetadataDTO(1, 600, 800, 0.75, True, 50, 0)],
    )
    dto3 = PDFDocumentDTO(
        file_path=Path("/path/to/BatchB.pdf"),
        file_name="BatchB.pdf",
        file_size_bytes=3000,
        file_hash_sha256="hash_batch_b",
        total_pages=1,
        is_encrypted=False,
        is_scanned=False,
        pages=[PageMetadataDTO(1, 600, 800, 0.75, True, 50, 0)],
    )

    d1 = dwg_repo.save_drawing_from_dto(dto1, project_id=proj["id"])
    d2 = dwg_repo.save_drawing_from_dto(dto2, project_id=proj["id"])
    d3 = dwg_repo.save_drawing_from_dto(dto3, project_id=proj["id"])

    viewer = PdfViewerPage(controller=controller)

    # 1. Single Mode Test:
    controller.active_upload_mode = "SINGLE"
    controller.current_batch_drawing_ids = [d1["id"]]
    viewer.apply_context_visibility()
    viewer.reload_drawings()

    # Sidebar must be hidden by default in Single mode
    assert viewer._dwg_sidebar.isHidden() is True
    assert viewer._toolbar._toggle_sidebar_btn.isChecked() is False
    assert "PROJECT DRAWINGS" in viewer._sb_title.text()

    # User clicks toggle button to manually open sidebar
    viewer.toggle_sidebar()
    assert viewer._dwg_sidebar.isHidden() is False
    assert viewer._toolbar._toggle_sidebar_btn.isChecked() is True

    # User clicks toggle button again to close
    viewer.toggle_sidebar()
    assert viewer._dwg_sidebar.isHidden() is True
    assert viewer._toolbar._toggle_sidebar_btn.isChecked() is False

    # 2. Batch Mode Test:
    controller.active_upload_mode = "BATCH"
    controller.current_batch_drawing_ids = [d2["id"], d3["id"]]
    viewer.apply_context_visibility()
    viewer.reload_drawings()

    # Sidebar must automatically appear in Batch mode
    assert viewer._dwg_sidebar.isHidden() is False
    assert viewer._toolbar._toggle_sidebar_btn.isChecked() is True
    assert "BATCH DRAWINGS (2)" in viewer._sb_title.text()

    # List widget and combo must ONLY have the 2 batch drawings
    assert viewer._dwg_list_widget.count() == 2
    assert viewer._dwg_combo.count() == 2
    item0_id = viewer._dwg_list_widget.item(0).data(0x0100)  # UserRole
    item1_id = viewer._dwg_list_widget.item(1).data(0x0100)  # UserRole
    assert set([item0_id, item1_id]) == set([d2["id"], d3["id"]])
