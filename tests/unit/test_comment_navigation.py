"""
test_comment_navigation.py — Unit tests for:
1. Sequential human-readable comment ID generation (CMT-P1-01, CMT-P1-02, etc.)
2. HumanReviewPage direct comment selection by ID (select_comment_by_id)
3. Filter auto-reset when selecting filtered-out comments
4. Comment ID search bar lookup (exact, partial, numeric, keyword)
5. Cross-screen comment redirection signals and MainWindow navigation
"""
from pathlib import Path
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.infrastructure.storage.repository import (
    DatabaseEngine,
    CommentRepository,
    DrawingRepository,
)
from src.infrastructure.storage.models import DrawingModel, CommentModel
from app.screens.review_screen import HumanReviewPage
from app.screens.ocr_results_screen import OcrResultsPage
from app.screens.classification_screen import ClassificationPage
from app.main_window import MainWindow


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseEngine:
    db_file = tmp_path / "test_nav.db"
    return DatabaseEngine(f"sqlite:///{db_file.as_posix()}")


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_sequential_page_indexed_comment_ids(test_db: DatabaseEngine):
    comment_repo = CommentRepository(test_db)
    drawing_id = "DWG-NAV-001"

    with test_db.get_session() as session:
        session.add(
            DrawingModel(
                id=drawing_id,
                file_path="sample.pdf",
                file_name="sample.pdf",
                file_size_bytes=1024,
                file_hash_sha256="dummyhash123",
                total_pages=2,
            )
        )
        session.commit()

    # Save 3 comments on Page 1
    c1 = comment_repo.save_comment(drawing_id, 1, "Page 1 note 1", (0.1, 0.1, 0.2, 0.2))
    c2 = comment_repo.save_comment(drawing_id, 1, "Page 1 note 2", (0.2, 0.2, 0.3, 0.3))
    c3 = comment_repo.save_comment(drawing_id, 1, "Page 1 note 3", (0.3, 0.3, 0.4, 0.4))

    # Save 2 comments on Page 2
    c4 = comment_repo.save_comment(drawing_id, 2, "Page 2 note 1", (0.1, 0.1, 0.2, 0.2))
    c5 = comment_repo.save_comment(drawing_id, 2, "Page 2 note 2", (0.2, 0.2, 0.3, 0.3))

    assert c1["id"] == "CMT-P1-01"
    assert c2["id"] == "CMT-P1-02"
    assert c3["id"] == "CMT-P1-03"
    assert c4["id"] == "CMT-P2-01"
    assert c5["id"] == "CMT-P2-02"


def test_select_comment_by_id_and_filter_reset(qapp):
    page = HumanReviewPage(controller=None)

    test_comments = [
        {"id": "CMT-P1-01", "ocr_text": "Verify pipe diameter", "status": "Pending", "confidence": 0.90, "page": 1, "bbox": (0, 0, 0.1, 0.1)},
        {"id": "CMT-P1-02", "ocr_text": "Approved weld inspection", "status": "Approved", "confidence": 0.95, "page": 1, "bbox": (0.1, 0.1, 0.2, 0.2)},
        {"id": "CMT-P2-01", "ocr_text": "Flagged valve clearance", "status": "Flagged", "confidence": 0.80, "page": 2, "bbox": (0.2, 0.2, 0.3, 0.3)},
    ]
    page._all_comments = list(test_comments)
    page._statuses = {c["id"]: c["status"] for c in test_comments}
    page._current_filter = "Pending"
    page._apply_filter()

    assert len(page._comments) == 1
    assert page._comments[0]["id"] == "CMT-P1-01"

    found = page.select_comment_by_id("CMT-P1-02")
    assert found is True
    assert page._current_filter == "All Comments"
    assert page._comments[page._idx]["id"] == "CMT-P1-02"
    assert "Approved weld inspection" in page._ocr_edit.toPlainText()


def test_human_review_search_id(qapp):
    page = HumanReviewPage(controller=None)

    test_comments = [
        {"id": "CMT-P1-01", "ocr_text": "Check flange bolts", "status": "Pending", "confidence": 0.90, "page": 1, "bbox": (0, 0, 0.1, 0.1)},
        {"id": "CMT-P1-02", "ocr_text": "Check gasket material", "status": "Pending", "confidence": 0.92, "page": 1, "bbox": (0.1, 0.1, 0.2, 0.2)},
        {"id": "CMT-P2-01", "ocr_text": "Review seismic bracing", "status": "Pending", "confidence": 0.88, "page": 2, "bbox": (0.2, 0.2, 0.3, 0.3)},
    ]
    page._all_comments = list(test_comments)
    page._statuses = {c["id"]: c["status"] for c in test_comments}
    page._current_filter = "All Comments"
    page._apply_filter()

    page._id_search_input.setText("CMT-P2-01")
    page._on_search_id_submitted()
    assert page._comments[page._idx]["id"] == "CMT-P2-01"

    page._id_search_input.setText("P1-02")
    page._on_search_id_submitted()
    assert page._comments[page._idx]["id"] == "CMT-P1-02"

    page._id_search_input.setText("1")
    page._on_search_id_submitted()
    assert "01" in page._comments[page._idx]["id"]

    page._id_search_input.setText("gasket")
    page._on_search_id_submitted()
    assert page._comments[page._idx]["id"] == "CMT-P1-02"


def test_cross_screen_signals_and_main_window_jump(qapp):
    window = MainWindow()

    test_comments = [
        {"id": "CMT-P1-01", "ocr_text": "Anchor bolt spacing", "confidence": 0.91, "status": "Pending", "page": 1, "bbox": (0, 0, 0.1, 0.1)},
        {"id": "CMT-P1-02", "ocr_text": "Support pad thickness", "confidence": 0.94, "status": "Approved", "page": 1, "bbox": (0.1, 0.1, 0.2, 0.2)},
    ]
    window.human_review_page._all_comments = list(test_comments)
    window.human_review_page._statuses = {c["id"]: c["status"] for c in test_comments}
    window.human_review_page._apply_filter()

    window._on_jump_to_human_review("CMT-P1-02")

    assert window._stack.currentIndex() == 6
    assert window.human_review_page._comments[window.human_review_page._idx]["id"] == "CMT-P1-02"
    assert "Support pad thickness" in window.human_review_page._ocr_edit.toPlainText()

    received_ocr = []
    window.ocr_results_page.comment_selected.connect(lambda cid: received_ocr.append(cid))
    window.ocr_results_page.comment_selected.emit("CMT-P1-01")
    assert received_ocr == ["CMT-P1-01"]

    received_cls = []
    window.classification_page.comment_selected.connect(lambda cid: received_cls.append(cid))
    window.classification_page.comment_selected.emit("CMT-P1-02")
    assert received_cls == ["CMT-P1-02"]
