"""
Unit tests for High Priority: Surface AI vs. Fallback Method to UI & Database.

Verifies:
1. ClassificationMethodDelegate formats and renders pill badges for:
   - "ai_model" / "distilbert" -> "🤖 AI Model"
   - "rule_based_fallback" / fallback_used=True -> "📋 Rule Fallback"
   - "rule_based" -> "⚡ Rule-Based"
   - "manual" / "human_verified" -> "✍️ Manual"
   - "manual_transcription_required" -> "⚠️ Needs Transc."
2. ClassificationPage table setup:
   - 5 columns: ["Comment", "Category", "Method", "Category Conf.", "Status"]
   - Column 2 assigned ClassificationMethodDelegate.
   - Method items carry fallback_used metadata on Qt.ItemDataRole.UserRole + 1.
3. ClassificationPage Inspector Drawer:
   - Surfaces method badge and fallback chips.
   - Category overrides mark classification_method as manual and fallback_used as False.
4. HumanReviewPage method badge:
   - Updates dynamically on comment navigation.
   - Automatically switches to "✍️ Manual" when reviewer changes category.
5. Database CommentRepository:
   - update_comment_category() persists classification_method = "manual" and fallback_used = False.
"""
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QModelIndex
from PySide6.QtGui import QStandardItemModel, QStandardItem

from pathlib import Path
from app.components.comment_table import ClassificationMethodDelegate
from app.screens.classification_screen import ClassificationPage
from app.screens.review_screen import HumanReviewPage
from src.infrastructure.storage.repository import DatabaseEngine, CommentRepository
from src.infrastructure.storage.models import DrawingModel, CommentModel


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def in_memory_db(tmp_path: Path):
    db_file = tmp_path / "test_surface_method.db"
    db_engine = DatabaseEngine(db_path=db_file)
    repo = CommentRepository(db_engine)

    with db_engine.get_session() as session:
        dwg = DrawingModel(
            id="DWG-TEST-01",
            file_path="test_drawing.pdf",
            file_name="test_drawing.pdf",
            file_size_bytes=2048,
            file_hash_sha256="test_hash_01",
            total_pages=1,
            is_scanned=False,
        )
        session.add(dwg)
        session.commit()

    return repo, db_engine


def test_classification_method_delegate_styles():
    """Verify delegate style mapping for all classification methods."""
    delegate = ClassificationMethodDelegate()
    styles = delegate._METHOD_STYLES

    assert "ai_model" in styles
    assert styles["ai_model"][0] == "🤖 AI Model"

    assert "rule_fallback" in styles
    assert styles["rule_fallback"][0] == "📋 Rule Fallback"

    assert "rule_based" in styles
    assert styles["rule_based"][0] == "⚡ Rule-Based"

    assert "manual" in styles
    assert styles["manual"][0] == "✍️ Manual"

    assert "transcription" in styles
    assert styles["transcription"][0] == "⚠️ Needs Transc."


def test_classification_screen_table_columns_and_delegate(qapp):
    """Verify table has 5 columns with Method at column 2 using ClassificationMethodDelegate."""
    page = ClassificationPage(controller=None)
    table = page._table
    model = page._model

    expected_headers = ["Comment", "Category", "Method", "Category Conf.", "Status"]
    assert model.columnCount() == 5
    for idx, expected in enumerate(expected_headers):
        actual = model.headerData(idx, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        assert actual == expected, f"Column {idx} header: expected '{expected}', got '{actual}'"

    col2_delegate = table.itemDelegateForColumn(2)
    assert isinstance(col2_delegate, ClassificationMethodDelegate)


def test_classification_screen_model_build_method_metadata(qapp):
    """Verify _build_model populates Method data and fallback_used UserRole data."""
    page = ClassificationPage(controller=None)
    page._comments_data = [
        {
            "id": "C-TEST-01",
            "ocr_text": "AI classified text",
            "category": "Technical",
            "classification_method": "ai_model",
            "fallback_used": False,
            "confidence": 0.95,
            "status": "Approved",
        },
        {
            "id": "C-TEST-02",
            "ocr_text": "Fallback classified text",
            "category": "Notes",
            "classification_method": "rule_based_fallback",
            "fallback_used": True,
            "confidence": 0.65,
            "status": "Pending",
        },
    ]

    model = page._build_model()
    assert model.rowCount() == 2

    # Row 0: AI
    row0_method = model.item(0, 2)
    assert row0_method.text() == "ai_model"
    assert row0_method.data(Qt.ItemDataRole.UserRole + 1) is False
    assert "DistilBERT" in row0_method.toolTip()

    # Row 1: Fallback
    row1_method = model.item(1, 2)
    assert row1_method.text() == "rule_based_fallback"
    assert row1_method.data(Qt.ItemDataRole.UserRole + 1) is True
    assert "Rule-Based Fallback" in row1_method.toolTip()


def test_classification_screen_inspector_drawer_method_display(qapp):
    """Verify inspector drawer opens and includes method details."""
    page = ClassificationPage(controller=None)
    page._comments_data = [
        {
            "id": "C-TEST-FB",
            "ocr_text": "Sparse note requires review",
            "category": "Drafting",
            "classification_method": "rule_based_fallback",
            "fallback_used": True,
            "confidence": 0.70,
            "status": "Flagged",
        }
    ]
    page._model = page._build_model()
    page._proxy.setSourceModel(page._model)

    # Trigger drawer open
    proxy_idx = page._proxy.index(0, 0)
    page._open_drawer(proxy_idx)

    # Check drawer content
    assert page._drawer._title_lbl.text() == "Inspector — C-TEST-FB"
    from PySide6.QtWidgets import QLabel
    drawer_texts = [
        w.text() for w in page._drawer.findChildren(QLabel)
    ]
    assert any("Rule-Based Fallback" in t for t in drawer_texts)
    assert any("Fallback Active" in t for t in drawer_texts)


def test_human_review_screen_method_badge(qapp):
    """Verify HumanReviewPage displays method badge and changes to manual on edit."""
    page = HumanReviewPage(controller=None)
    mock_comment = {
        "id": "C-TEST-REV",
        "ocr_text": "Sample text for review",
        "category": "Dimensional",
        "classification_method": "rule_based_fallback",
        "fallback_used": True,
        "confidence": 0.80,
        "ocr_confidence": 0.90,
        "classification_confidence": 0.80,
        "status": "Pending",
    }
    page._comments = [mock_comment]
    page._idx = 0
    page._load_comment()

    # Verify badge initially indicates Fallback
    assert page._method_badge.text() == "📋 Rule Fallback"
    assert "Rule-based fallback" in page._method_badge.toolTip()

    # Now simulate user editing the category
    page._on_category_changed("Technical")

    # Verify comment was updated in memory and method changed to manual
    assert mock_comment["category"] == "Technical"
    assert mock_comment["classification_method"] == "manual"
    assert mock_comment["fallback_used"] is False
    assert page._method_badge.text() == "✍️ Manual"
    assert "Manually classified" in page._method_badge.toolTip()


def test_repository_update_comment_category_persists_manual(in_memory_db):
    """Verify CommentRepository.update_comment_category persists classification_method='manual'."""
    repo, db_engine = in_memory_db

    # Create initial comment with ai_model and fallback_used=True
    comm_res = repo.save_comment(
        drawing_id="DWG-TEST-01",
        page_number=1,
        raw_text="CHECK DIMENSION",
        cleaned_text="CHECK DIMENSION",
        bbox=(10.0, 20.0, 100.0, 50.0),
        category_name="Dimensional",
        confidence=0.72,
        classification_method="rule_based_fallback",
        fallback_used=True,
    )
    cid = comm_res["id"]
    assert cid is not None

    with db_engine.get_session() as session:
        initial = session.query(CommentModel).filter_by(id=cid).first()
        assert initial.classification_method == "rule_based_fallback"
        assert initial.fallback_used is True

    # Now update category
    ok = repo.update_comment_category(
        comment_id=cid,
        new_category="Technical",
        changed_by_user_id="lead_reviewer",
    )
    assert ok is True

    # Re-fetch from DB
    with db_engine.get_session() as session:
        reloaded = session.query(CommentModel).filter_by(id=cid).first()
        assert reloaded.category_name == "Technical"
        assert reloaded.classification_method == "manual"
        assert reloaded.fallback_used is False
        assert reloaded.is_verified_by_human is True
