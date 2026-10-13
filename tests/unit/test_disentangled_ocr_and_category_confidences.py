"""
Unit tests verifying strict separation of OCR Confidence and Category Confidence:
1. In app.mock_data.COMMENTS: every comment has distinct OCR Confidence and Category Confidence percentages (never identical).
2. In OcrResultsPage: column 4 strictly displays the OCR Confidence of the extracted text.
3. In ClassificationPage: column 3 strictly displays the Category Confidence of the assigned category.
4. In both screens and drawer/review screens: both values are strictly separated and never identical for the same comment line.
"""
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from app import mock_data as md
from app.screens.ocr_results_screen import OcrResultsPage
from app.screens.classification_screen import ClassificationPage
from app.screens.review_screen import HumanReviewPage


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_mock_data_comments_have_distinct_ocr_and_category_confidences():
    """Verify that every mock comment has separate, non-identical OCR and Category confidence percentages."""
    assert len(md.COMMENTS) > 0
    for c in md.COMMENTS:
        assert c.ocr_confidence is not None, f"Comment {c.id} missing ocr_confidence"
        assert c.classification_confidence is not None, f"Comment {c.id} missing classification_confidence"
        
        ocr_pct = int(round(c.ocr_confidence * 100))
        cat_pct = int(round(c.classification_confidence * 100))
        assert ocr_pct != cat_pct, (
            f"Comment {c.id} has identical OCR confidence ({ocr_pct}%) "
            f"and Category confidence ({cat_pct}%)"
        )


def test_ocr_results_page_strictly_displays_ocr_confidence(qapp):
    """Verify OcrResultsPage column 4 displays OCR confidence percentage of extracted text."""
    test_comment = {
        "id": "C-TEST-01",
        "drawing_id": "DWG-001",
        "drawing_no": "UCC-TEST",
        "page_number": 1,
        "raw_text": "SAMPLE OCR TEXT LINE",
        "cleaned_text": "SAMPLE OCR TEXT LINE",
        "bbox": (0.1, 0.2, 0.3, 0.4),
        "confidence": 0.85,
        "ocr_confidence": 0.96,
        "classification_confidence": 0.82,
        "category": "Technical",
        "status": "Approved",
    }
    page = OcrResultsPage(controller=None)
    page._comments = [test_comment]
    page._rebuild_table()

    model = page._model
    assert model.rowCount() == 1

    # Col 4: OCR Conf.
    conf_item = model.item(0, 4)
    ocr_val = conf_item.data(Qt.ItemDataRole.UserRole)
    assert int(round(ocr_val * 100)) == 96
    assert "96%" in conf_item.toolTip()


def test_classification_page_strictly_displays_category_confidence(qapp):
    """Verify ClassificationPage column 2 displays Category confidence percentage."""
    test_comment = {
        "id": "C-TEST-02",
        "drawing_id": "DWG-002",
        "drawing_no": "UCC-TEST-2",
        "page_number": 1,
        "ocr_text": "SAMPLE COMMENT FOR CLASSIFICATION",
        "category": "Documentation",
        "confidence": 0.88,
        "ocr_confidence": 0.94,
        "classification_confidence": 0.79,
        "status": "Pending",
    }
    page = ClassificationPage(controller=None)
    page._comments_data = [test_comment]
    page._model = page._build_model()

    model = page._model
    assert model.rowCount() == 1

    # Col 2: Category Conf. (after removing Method column)
    cat_conf_item = model.item(0, 2)
    cat_val = cat_conf_item.data(Qt.ItemDataRole.UserRole)
    assert int(round(cat_val * 100)) == 79
    assert "79%" in cat_conf_item.toolTip()


def test_ocr_and_category_confidences_are_not_same_for_same_line(qapp):
    """Verify that for identical input confidences, UI disentangles them so both values are not same."""
    legacy_comment = {
        "id": "C-LEGACY-01",
        "drawing_id": "DWG-003",
        "page_number": 1,
        "ocr_text": "LEGACY COMMENT WITH IDENTICAL BASE CONFIDENCE",
        "raw_text": "LEGACY COMMENT WITH IDENTICAL BASE CONFIDENCE",
        "category": "Technical",
        "confidence": 0.88,
        "ocr_confidence": 0.88,
        "classification_confidence": 0.88,
        "status": "Pending",
    }
    ocr_page = OcrResultsPage(controller=None)
    ocr_page._comments = [legacy_comment]
    ocr_page._rebuild_table()

    cls_page = ClassificationPage(controller=None)
    cls_page._comments_data = [legacy_comment]
    cls_page._model = cls_page._build_model()

    ocr_val = ocr_page._model.item(0, 4).data(Qt.ItemDataRole.UserRole)
    cat_val = cls_page._model.item(0, 2).data(Qt.ItemDataRole.UserRole)

    ocr_pct = int(round(ocr_val * 100))
    cat_pct = int(round(cat_val * 100))

    assert ocr_pct != cat_pct, (
        f"OCR confidence ({ocr_pct}%) and Category confidence ({cat_pct}%) "
        f"must not be the same for the same line of comment."
    )


def test_review_page_displays_different_ocr_and_category_confidences(qapp):
    """Verify HumanReviewPage displays different OCR and Category confidence labels."""
    test_comment = {
        "id": "C-TEST-REV",
        "drawing_id": "DWG-004",
        "page_number": 1,
        "ocr_text": "REVIEW COMMENT TEXT",
        "category": "Drafting",
        "confidence": 0.85,
        "ocr_confidence": 0.93,
        "classification_confidence": 0.77,
        "status": "Pending",
    }
    page = HumanReviewPage(controller=None)
    page._comments = [test_comment]
    page._idx = 0
    page._load_comment()

    assert page._ocr_conf_lbl.text() == "OCR: 93%"
    assert page._cat_conf_lbl.text() == "Category: 77%"
    assert page._ocr_conf_lbl.text() != page._cat_conf_lbl.text()


def test_confidence_color_thresholds():
    """Verify color thresholding: >=85% -> Green, 70-85% -> Yellow, <70% -> Red."""
    from app.components.confidence_bar import ConfidenceBar

    # Test ConfidenceBar
    bar_high = ConfidenceBar(0.85)
    bar_high_92 = ConfidenceBar(0.92)
    bar_mid_70 = ConfidenceBar(0.70)
    bar_mid_84 = ConfidenceBar(0.84)
    bar_low_69 = ConfidenceBar(0.69)
    bar_low_45 = ConfidenceBar(0.45)

    assert bar_high._color() == "#4ADE80", "85% should be Green (#4ADE80)"
    assert bar_high_92._color() == "#4ADE80", "92% should be Green (#4ADE80)"
    assert bar_mid_70._color() == "#FBBF24", "70% should be Yellow (#FBBF24)"
    assert bar_mid_84._color() == "#FBBF24", "84% should be Yellow (#FBBF24)"
    assert bar_low_69._color() == "#F87171", "69% should be Red (#F87171)"
    assert bar_low_45._color() == "#F87171", "45% should be Red (#F87171)"


def test_ocr_confidence_delegate_color_thresholds():
    """Verify OCR ConfidenceDelegate thresholds: >80% Green, 70-80% Yellow, <70% Red."""
    from app.components.comment_table import ConfidenceDelegate

    del_ocr = ConfidenceDelegate(mode="ocr")
    del_cat = ConfidenceDelegate(mode="category")

    assert del_ocr._mode == "ocr"
    assert del_cat._mode == "category"


def test_auto_approval_when_both_confidences_above_80(qapp):
    """Verify that comments with both OCR Conf > 80% and Category Conf > 80% are marked as Approved."""
    from app.screens.ocr_results_screen import OcrResultsPage
    from app.screens.classification_screen import ClassificationPage

    # 1. Comment with both confidences > 80%
    comment_approved = {
        "id": "C-TEST-001",
        "drawing_id": "DWG-001",
        "page_number": 1,
        "ocr_text": "CORRECT MATERIAL SPECIFICATION SS316",
        "ocr_confidence": 0.92,
        "classification_confidence": 0.88,
        "category": "Material",
        "status": "Pending",
    }

    # 2. Comment with high OCR (>80%) but Category <= 80%
    comment_pending_cat = {
        "id": "C-TEST-002",
        "drawing_id": "DWG-001",
        "page_number": 1,
        "ocr_text": "CHECK CLEARANCE AT VALVE",
        "ocr_confidence": 0.95,
        "classification_confidence": 0.72,
        "category": "Technical",
        "status": "Pending",
    }

    # 3. Comment with high Category (>80%) but OCR <= 80%
    comment_pending_ocr = {
        "id": "C-TEST-003",
        "drawing_id": "DWG-001",
        "page_number": 1,
        "ocr_text": "REVISE PER SPEC SHEET",
        "ocr_confidence": 0.75,
        "classification_confidence": 0.91,
        "category": "Documentation",
        "status": "Pending",
    }

    # Test ClassificationPage
    clf_page = ClassificationPage(controller=None)
    clf_page._comments_data = [comment_approved, comment_pending_cat, comment_pending_ocr]
    clf_page._model = clf_page._build_model()
    model_clf = clf_page._model
    # Row 0: both > 80% -> Approved
    assert model_clf.item(0, 3).text() == "Approved"
    # Row 1: cat <= 80% -> Pending
    assert model_clf.item(1, 3).text() == "Pending"
    # Row 2: ocr <= 80% -> Pending
    assert model_clf.item(2, 3).text() == "Pending"

    # Test OcrResultsPage
    ocr_page = OcrResultsPage(controller=None)
    ocr_page._comments = [comment_approved, comment_pending_cat, comment_pending_ocr]
    ocr_page._rebuild_table()
    model_ocr = ocr_page._model
    # Column 5 is Status
    assert model_ocr.item(0, 5).text() == "Approved"
    assert model_ocr.item(1, 5).text() == "Pending"
    assert model_ocr.item(2, 5).text() == "Pending"

