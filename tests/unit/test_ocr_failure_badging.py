import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QModelIndex, QRect
from PySide6.QtGui import QPainter, QImage, QColor

from app.components.comment_table import EngineDelegate, StatusDelegate, ConfidenceDelegate
from app.screens.ocr_results_screen import OcrResultsPage
from src.core.dtos.annotation_dtos import BoundingBoxDTO, AnnotationResultDTO, DocumentAnnotationDTO


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def test_engine_delegate_renders_ocr_failed_badge(qapp):
    """EngineDelegate must render a distinct '⚠️ OCR Failed' warning badge for failed OCR engines."""
    delegate = EngineDelegate()
    image = QImage(200, 50, QImage.Format.Format_ARGB32)
    image.fill(QColor("#000000"))
    painter = QPainter(image)

    from PySide6.QtWidgets import QStyleOptionViewItem
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 200, 50)

    # Test "OCR Failed" attribution
    mock_index = MagicMock(spec=QModelIndex)
    mock_index.data.return_value = "OCR Failed"
    delegate.paint(painter, option, mock_index)

    # Test lowercase "tesseract_failed"
    mock_index.data.return_value = "tesseract_failed"
    delegate.paint(painter, option, mock_index)

    # Test "Unreadable"
    mock_index.data.return_value = "unreadable_region"
    delegate.paint(painter, option, mock_index)

    painter.end()


def test_ocr_results_screen_failure_badging_and_text_styling(qapp):
    """OcrResultsPage must display OCR Failed placeholder with warning color, 0% confidence, and failure badge."""
    mock_controller = MagicMock()
    mock_controller.get_all_drawings.return_value = [
        {"id": "DWG-TEST-01", "file_name": "Sheet_A1.pdf", "comments_count": 2}
    ]
    mock_controller.current_drawing_id = "DWG-TEST-01"

    comments = [
        {
            "id": "CMT-TEST-01",
            "page_number": 1,
            "raw_text": "OCR Failed (Needs Manual Transcription)",
            "cleaned_text": "OCR Failed (Needs Manual Transcription)",
            "bbox": (100.0, 150.0, 250.0, 200.0),
            "detection_confidence": 0.92,
            "ocr_confidence": 0.0,
            "classification_confidence": 0.0,
            "confidence": 0.0,
            "ocr_engine": "OCR Failed",
            "category_name": "Uncategorized",
            "status": "Flagged",
        },
        {
            "id": "CMT-TEST-02",
            "page_number": 1,
            "raw_text": "CHECK CLEARANCE 500MM",
            "cleaned_text": "CHECK CLEARANCE 500MM",
            "bbox": (300.0, 400.0, 450.0, 430.0),
            "detection_confidence": 0.95,
            "ocr_confidence": 0.94,
            "classification_confidence": 0.91,
            "confidence": 0.93,
            "ocr_engine": "Tesseract OCR",
            "category_name": "Dimensional",
            "status": "Approved",
        }
    ]
    mock_controller.get_comments_for_drawing.return_value = comments

    page = OcrResultsPage(controller=mock_controller)
    model = page._model

    assert model.rowCount() == 2

    # Verify Row 0 (Failed OCR)
    row0_id = model.item(0, 0).text()
    row0_page = model.item(0, 1).text()
    row0_text_item = model.item(0, 2)
    row0_bbox = model.item(0, 3).text()
    row0_conf = model.item(0, 4).data(Qt.ItemDataRole.UserRole)
    row0_engine = model.item(0, 5).text()
    row0_status = model.item(0, 6).text()

    assert row0_id == "CMT-TEST-01"
    assert row0_page == "1"
    assert "OCR Failed (Needs Manual Transcription)" in row0_text_item.text()
    assert row0_text_item.foreground().color().name().upper() == "#F87171"
    assert "Double-click to manually transcribe" in row0_text_item.toolTip()
    assert row0_bbox == "[100, 150, 150, 50]"
    assert float(row0_conf) == 0.0
    assert row0_engine == "OCR Failed"
    assert row0_status == "Flagged"

    # Verify Row 1 (Normal valid comment)
    row1_text_item = model.item(1, 2)
    assert row1_text_item.text() == "CHECK CLEARANCE 500MM"
    assert row1_text_item.foreground().color().name().upper() != "#F87171"
    assert model.item(1, 5).text() == "Tesseract OCR"
    assert model.item(1, 6).text() == "Approved"


def test_workflow_engine_creates_placeholder_for_unreadable_high_conf_region(tmp_path):
    """ProcessingWorkflowEngine must create a placeholder comment record when OCR produces no words on a high-confidence markup region."""
    from src.services.workflow_engine import ProcessingWorkflowEngine
    from src.services.file_service import FileService
    from src.services.pdf_service import PDFService
    from src.infrastructure.pdf.pymupdf_adapter import PyMuPDFAdapter
    from src.infrastructure.storage.repository import DatabaseEngine, CommentRepository, DrawingRepository

    db_path = tmp_path / "test_ocr_fail.db"
    db_engine = DatabaseEngine(db_path)

    comment_repo = CommentRepository(db_engine)
    drawing_repo = DrawingRepository(db_engine)

    mock_annotation_service = MagicMock()
    mock_classification_service = MagicMock()
    mock_text_cleaning_service = MagicMock()
    mock_text_cleaning_service.clean_text.side_effect = lambda t: MagicMock(cleaned_text=t)

    # Mock high-confidence region and low-confidence region
    high_conf_reg = BoundingBoxDTO(
        x0=50.0, y0=50.0, x1=120.0, y1=80.0,
        page_number=0, confidence=0.88, label="comment_red"
    )
    low_conf_reg = BoundingBoxDTO(
        x0=200.0, y0=200.0, x1=230.0, y1=220.0,
        page_number=0, confidence=0.55, label="comment_red"
    )

    doc_annot = DocumentAnnotationDTO(
        file_name="sample.pdf",
        total_pages=1,
        page_results=[
            AnnotationResultDTO(
                drawing_id="DWG-001",
                page_number=0,
                regions=[high_conf_reg, low_conf_reg],
                detection_method="hybrid",
                processing_time_ms=10.0,
            )
        ],
        total_regions=2,
    )
    mock_annotation_service.detect_all_pages.return_value = doc_annot

    file_service = FileService()
    pdf_adapter = PyMuPDFAdapter()
    pdf_service = PDFService(pdf_loader=pdf_adapter)

    workflow = ProcessingWorkflowEngine(
        file_service=file_service,
        pdf_service=pdf_service,
        drawing_repo=drawing_repo,
        comment_repo=comment_repo,
        annotation_service=mock_annotation_service,
        classification_service=mock_classification_service,
        text_cleaning_service=mock_text_cleaning_service,
    )

    # Create dummy single-page PDF with empty text
    import pymupdf as fitz
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    pdf_file = tmp_path / "sample.pdf"
    doc.save(str(pdf_file))
    doc.close()

    # Run workflow
    res = workflow.execute_workflow(pdf_file)
    assert res.status == "Completed"

    # Inspect persisted comments in database
    all_drawings = drawing_repo.get_all_drawings()
    assert len(all_drawings) >= 1
    drawing_id = all_drawings[0]["id"]
    comments = comment_repo.get_comments_for_drawing(drawing_id)

    # Exactly 1 comment should be saved (high-confidence region placeholder), low-confidence ignored
    assert len(comments) == 1
    cmt = comments[0]
    assert cmt["raw_text"] == "OCR Failed (Needs Manual Transcription)"
    assert cmt["cleaned_text"] == "OCR Failed (Needs Manual Transcription)"
    assert cmt["status"] == "Flagged"
    assert cmt["ocr_engine"] == "OCR Failed"
    assert float(cmt["ocr_confidence"]) == 0.0
    assert float(cmt["classification_confidence"]) == 0.0
    assert float(cmt["detection_confidence"]) >= 0.70
    assert cmt["category_name"] == "Uncategorized"

    # AI classifier should NOT have been called with the placeholder text
    mock_classification_service.classify_batch.assert_not_called()
