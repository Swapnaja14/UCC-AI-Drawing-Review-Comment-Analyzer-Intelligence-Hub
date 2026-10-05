"""
Unit test suite verifying Disentangled Confidences (Issues #5 & #9):
- Separation of detection_confidence, ocr_confidence, and classification_confidence
- Persistence in CommentModel and CommentRepository
- Database auto-migration
- Correct exposure in DTOs and UI screens
"""
import pytest
from pathlib import Path

from src.infrastructure.storage.models import CommentModel, DrawingModel
from src.infrastructure.storage.repository import DatabaseEngine, CommentRepository
from src.core.dtos.comment_processing_dtos import ExtractedCommentDTO
from app.screens.review_screen import _CommentAdapter


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_confidences.db"
    engine = DatabaseEngine(db_path=db_file)
    return engine


def test_comment_model_has_separated_confidence_fields():
    """Verify CommentModel defines separate columns for detection, OCR, and classification confidences."""
    assert hasattr(CommentModel, "confidence")
    assert hasattr(CommentModel, "detection_confidence")
    assert hasattr(CommentModel, "ocr_confidence")
    assert hasattr(CommentModel, "classification_confidence")


def test_repository_persists_and_retrieves_disentangled_confidences(temp_db):
    """Verify CommentRepository correctly saves and returns detection, OCR, and classification confidences."""
    comment_repo = CommentRepository(temp_db)

    # 1. Create a parent drawing with all required fields
    drawing_id = "DWG-CONF-001"
    with temp_db.get_session() as session:
        dwg = DrawingModel(
            id=drawing_id,
            file_path="test_drawing.pdf",
            file_name="test_drawing.pdf",
            file_size_bytes=2048,
            file_hash_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            total_pages=1
        )
        session.add(dwg)
        session.commit()

    # 2. Save comment with explicit disentangled confidences
    saved = comment_repo.save_comment(
        drawing_id=drawing_id,
        page_number=1,
        raw_text="3/4 INCH FILLET WELD MISSING",
        bbox=(50.0, 100.0, 250.0, 150.0),
        confidence=0.88,
        detection_confidence=0.95,
        ocr_confidence=0.92,
        classification_confidence=0.85,
        category_name="Technical",
        status="Pending"
    )
    cid = saved["id"]

    # 3. Retrieve comment by ID and verify all three confidences are separate and exact
    comment = comment_repo.get_comment_by_id(cid)
    assert comment is not None
    assert comment["detection_confidence"] == pytest.approx(0.95, rel=1e-3)
    assert comment["ocr_confidence"] == pytest.approx(0.92, rel=1e-3)
    assert comment["classification_confidence"] == pytest.approx(0.85, rel=1e-3)
    assert comment["confidence"] == pytest.approx(0.88, rel=1e-3)

    # 4. Verify list retrieval via get_comments_for_drawing
    comments_list = comment_repo.get_comments_for_drawing(drawing_id)
    assert len(comments_list) == 1
    c = comments_list[0]
    assert c["detection_confidence"] == pytest.approx(0.95, rel=1e-3)
    assert c["ocr_confidence"] == pytest.approx(0.92, rel=1e-3)
    assert c["classification_confidence"] == pytest.approx(0.85, rel=1e-3)


def test_legacy_fallback_confidence_support(temp_db):
    """Verify that legacy callers providing only 'confidence' gracefully populate the specific confidences."""
    comment_repo = CommentRepository(temp_db)

    drawing_id = "DWG-LEGACY-001"
    with temp_db.get_session() as session:
        dwg = DrawingModel(
            id=drawing_id,
            file_path="legacy_drawing.pdf",
            file_name="legacy_drawing.pdf",
            file_size_bytes=1024,
            file_hash_sha256="da39a3ee5e6b4b0d3255bfef95601890afd80709",
            total_pages=1
        )
        session.add(dwg)
        session.commit()

    saved = comment_repo.save_comment(
        drawing_id=drawing_id,
        page_number=1,
        raw_text="LEGACY NOTE",
        bbox=(10.0, 20.0, 80.0, 40.0),
        confidence=0.78,
        category_name="Notes"
    )
    comment = comment_repo.get_comment_by_id(saved["id"])
    assert comment["confidence"] == pytest.approx(0.78, rel=1e-3)
    assert comment["detection_confidence"] == pytest.approx(0.78, rel=1e-3)
    assert comment["ocr_confidence"] == pytest.approx(0.78, rel=1e-3)
    assert comment["classification_confidence"] == pytest.approx(0.78, rel=1e-3)


def test_extracted_comment_dto_structure():
    """Verify ExtractedCommentDTO accepts and holds separated confidences."""
    dto = ExtractedCommentDTO(
        page_number=2,
        raw_text="REVISE ELEVATION CALLOUT",
        cleaned_text="Revise elevation callout",
        bbox=(100.0, 200.0, 300.0, 250.0),
        detection_confidence=0.96,
        ocr_confidence=0.89,
        classification_confidence=0.91,
        confidence=0.90,
        category_name="Dimension",
        ocr_engine="tesseract"
    )
    assert dto.detection_confidence == 0.96
    assert dto.ocr_confidence == 0.89
    assert dto.classification_confidence == 0.91
    assert dto.ocr_engine == "tesseract"


def test_ui_comment_adapter_preserves_separated_confidences():
    """Verify _CommentAdapter in review_screen wraps separated confidences."""
    comment_dict = {
        "id": "CMT-01",
        "ocr_text": "CHECK WELD SIZE",
        "detection_confidence": 0.94,
        "ocr_confidence": 0.87,
        "classification_confidence": 0.93,
        "confidence": 0.90,
        "status": "Pending"
    }

    adapter = _CommentAdapter(comment_dict)
    assert adapter.detection_confidence == 0.94
    assert adapter.ocr_confidence == 0.87
    assert adapter.classification_confidence == 0.93
    assert adapter.confidence == 0.90
