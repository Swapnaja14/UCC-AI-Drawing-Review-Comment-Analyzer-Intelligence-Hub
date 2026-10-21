"""
tests/unit/test_drawing_department_fk.py
Regression test for drawing and comment department foreign key resolution.
Verifies that passing 'Unassigned', department names, or invalid IDs does not trigger
SQLite FOREIGN KEY constraint failures when PRAGMA foreign_keys=ON is active.
"""
from pathlib import Path
import pytest
from src.core.dtos.pdf_dtos import PDFDocumentDTO, PageMetadataDTO
from src.infrastructure.storage.models import Base, EngineeringDepartmentModel, DrawingModel
from src.infrastructure.storage.repository import (
    DatabaseEngine,
    DrawingRepository,
    CommentRepository,
    EngineeringDepartmentRepository,
)


def _make_dummy_dto(file_hash: str) -> PDFDocumentDTO:
    return PDFDocumentDTO(
        file_path="dummy.pdf",
        file_name="dummy.pdf",
        file_size_bytes=1000,
        file_hash_sha256=file_hash,
        total_pages=1,
        is_encrypted=False,
        is_scanned=False,
        pages=[
            PageMetadataDTO(
                page_number=1,
                width_pt=612.0,
                height_pt=792.0,
                aspect_ratio=0.7727,
                has_native_text=True,
                text_character_count=100,
                orientation_deg=0,
            )
        ],
    )


def test_save_drawing_with_unassigned_department(tmp_path):
    """Passing department_id='Unassigned' must resolve to None without FK error."""
    db_file = tmp_path / "test_fk.db"
    engine = DatabaseEngine(db_path=db_file)
    drawing_repo = DrawingRepository(engine)

    dto = _make_dummy_dto("hash_unassigned_test_01")
    # This must NOT raise sqlite3.IntegrityError: FOREIGN KEY constraint failed
    record = drawing_repo.save_drawing_from_dto(dto, department_id="Unassigned")
    assert record["id"] is not None
    assert record["department_id"] is None


def test_save_drawing_resolves_department_name(tmp_path):
    """Passing a department name (e.g. 'Piping Engineering') must resolve to its ID."""
    db_file = tmp_path / "test_fk_name.db"
    engine = DatabaseEngine(db_path=db_file)
    drawing_repo = DrawingRepository(engine)

    # Seed departments
    dept_repo = EngineeringDepartmentRepository(engine)
    dept_repo.seed_default_departments()

    dto = _make_dummy_dto("hash_name_resolve_01")
    record = drawing_repo.save_drawing_from_dto(dto, department_id="Piping Engineering")
    assert record["department_id"] is not None
    assert record["department_id"].startswith("DEPT-")


def test_save_drawing_with_invalid_department_id(tmp_path):
    """Passing a non-existent department ID must fallback to None instead of crashing."""
    db_file = tmp_path / "test_fk_invalid.db"
    engine = DatabaseEngine(db_path=db_file)
    drawing_repo = DrawingRepository(engine)

    dto = _make_dummy_dto("hash_invalid_dept_01")
    record = drawing_repo.save_drawing_from_dto(dto, department_id="DEPT-DOES-NOT-EXIST")
    assert record["id"] is not None
    assert record["department_id"] is None


def test_create_comment_with_unassigned_department(tmp_path):
    """Passing department_id='Unassigned' to save_comment must resolve to None."""
    db_file = tmp_path / "test_cmt_fk.db"
    engine = DatabaseEngine(db_path=db_file)
    drawing_repo = DrawingRepository(engine)
    comment_repo = CommentRepository(engine)

    dto = _make_dummy_dto("hash_cmt_test_01")
    dwg = drawing_repo.save_drawing_from_dto(dto)

    # This must NOT raise sqlite3.IntegrityError: FOREIGN KEY constraint failed
    cmt = comment_repo.save_comment(
        drawing_id=dwg["id"],
        page_number=1,
        raw_text="Test comment",
        bbox=(0.0, 0.0, 10.0, 10.0),
        department_id="Unassigned",
    )
    assert cmt["id"] is not None
    with engine.get_session() as sess:
        from src.infrastructure.storage.models import CommentModel
        saved = sess.get(CommentModel, cmt["id"])
        assert saved.department_id is None
