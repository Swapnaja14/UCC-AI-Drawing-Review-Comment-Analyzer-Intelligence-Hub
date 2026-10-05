"""
Unit tests for Issues #7 & #8: Expose Telemetry & Attribution in OcrResultsPage.

Verifies:
1. Table structure: 7 columns (Comment ID, Page, OCR Text, BBox (X, Y, W, H), OCR Conf., Engine, Status).
2. Proper spatial telemetry extraction and formatting for BBox [X, Y, W, H] with detailed tooltips.
3. Engine attribution extraction and badge display (Tesseract OCR / Native).
4. Page column representation and badge delegation.
5. Delegates assigned correctly: PageDelegate on col 1, ConfidenceDelegate on col 4, EngineDelegate on col 5, StatusDelegate on col 6.
6. Inline text editing on column 2 and status filter proxy correctly tracking column 6.
"""
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from app.screens.ocr_results_screen import OcrResultsPage
from app.components.comment_table import (
    ConfidenceDelegate,
    StatusDelegate,
    EngineDelegate,
    PageDelegate,
)


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_ocr_results_table_columns_and_headers(qapp):
    """Verify table has 7 columns with exact required telemetry and attribution headers."""
    page = OcrResultsPage(controller=None)
    model = page._model

    expected_headers = [
        "Comment ID",
        "Page",
        "OCR Text",
        "BBox (X, Y, W, H)",
        "OCR Conf.",
        "Engine",
        "Status",
    ]
    assert model.columnCount() == 7
    for col_idx, expected_title in enumerate(expected_headers):
        header_text = model.headerData(col_idx, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        assert header_text == expected_title, f"Column {col_idx} header mismatch: expected '{expected_title}', got '{header_text}'"


def test_ocr_results_delegates_assigned(qapp):
    """Verify delegates are assigned to the respective columns."""
    page = OcrResultsPage(controller=None)
    table = page._table

    assert isinstance(table.itemDelegateForColumn(1), PageDelegate)
    assert isinstance(table.itemDelegateForColumn(4), ConfidenceDelegate)
    assert isinstance(table.itemDelegateForColumn(5), EngineDelegate)
    assert isinstance(table.itemDelegateForColumn(6), StatusDelegate)


def test_ocr_results_status_proxy_column(qapp):
    """Verify status proxy filters on column 6 (Status)."""
    page = OcrResultsPage(controller=None)
    assert page._status_proxy.filterKeyColumn() == 6


def test_ocr_results_telemetry_and_attribution_display(qapp):
    """Verify telemetry BBox formatting and engine attribution in table rows."""
    test_comment = {
        "id": "CMT-P2-01",
        "drawing_id": "DWG-TEST",
        "drawing_no": "DWG-TEST-001",
        "page_number": 2,
        "raw_text": "CHECK CLEARANCE AT GRID B-4",
        "cleaned_text": "CHECK CLEARANCE AT GRID B-4",
        "bbox": (100.0, 150.0, 350.0, 220.0), # x0, y0, x1, y1 -> w=250, h=70
        "confidence": 0.94,
        "ocr_confidence": 0.94,
        "ocr_engine": "Tesseract OCR",
        "status": "Approved",
    }

    page = OcrResultsPage(controller=None)
    page._comments = [test_comment]
    page._rebuild_table()

    model = page._model
    assert model.rowCount() == 1

    # Col 0: Comment ID
    item_id = model.item(0, 0)
    assert item_id.text() == "CMT-P2-01"

    # Col 1: Page
    item_page = model.item(0, 1)
    assert item_page.text() == "2"
    assert "Drawing Page 2" in item_page.toolTip()

    # Col 2: Text
    item_text = model.item(0, 2)
    assert item_text.text() == "CHECK CLEARANCE AT GRID B-4"
    assert item_text.isEditable() is True

    # Col 3: BBox (X, Y, W, H)
    item_bbox = model.item(0, 3)
    # [100, 150, 250, 70]
    assert "[100, 150, 250, 70]" in item_bbox.text()
    assert "Spatial Telemetry (Bounding Box)" in item_bbox.toolTip()
    assert "Width: 250.00" in item_bbox.toolTip()
    assert "Height: 70.00" in item_bbox.toolTip()

    # Col 4: Confidence
    item_conf = model.item(0, 4)
    assert float(item_conf.data(Qt.ItemDataRole.UserRole)) == 0.94
    assert "94%" in item_conf.toolTip()

    # Col 5: Engine
    item_engine = model.item(0, 5)
    assert item_engine.text() == "Tesseract OCR"
    assert "Tesseract OCR" in item_engine.toolTip()

    # Col 6: Status
    item_status = model.item(0, 6)
    assert item_status.text() == "Approved"


def test_ocr_results_native_engine_and_normalized_bbox(qapp):
    """Verify handling of Native OCR engine and normalized float bboxes."""
    test_comment = {
        "id": "CMT-P1-05",
        "page_number": 1,
        "raw_text": "NATIVE TEXT STREAM COMMENT",
        "bbox": (0.10, 0.20, 0.40, 0.25), # x0, y0, x1, y1 -> x=0.10, y=0.20, w=0.30, h=0.05
        "ocr_confidence": 0.99,
        "ocr_engine": "Native",
        "status": "Pending",
    }

    page = OcrResultsPage(controller=None)
    page._comments = [test_comment]
    page._rebuild_table()

    model = page._model
    item_bbox = model.item(0, 3)
    assert "[0.10, 0.20, 0.30, 0.05]" == item_bbox.text()

    item_engine = model.item(0, 5)
    assert item_engine.text() == "Native"
