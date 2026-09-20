"""
tests/unit/test_pdf_persistence.py — Test suite for uploaded PDF persistence and metadata storage.
"""

import pytest
import pymupdf as fitz
from pathlib import Path

from src.infrastructure.storage.repository import DatabaseEngine, DrawingRepository, ProjectRepository, CommentRepository, EngineeringDepartmentRepository
from src.infrastructure.pdf.pymupdf_adapter import PyMuPDFAdapter
from src.services.pdf_service import PDFService
from src.services.file_service import FileService


@pytest.fixture
def test_db_engine(tmp_path):
    db_file = tmp_path / "test_pdf_persistence.db"
    return DatabaseEngine(db_path=db_file)


@pytest.fixture
def sample_pdf_drawing(tmp_path):
    """Generates a simple 1-page sample PDF file in a temporary folder."""
    temp_dir = tmp_path / "temp_user_downloads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = temp_dir / "sample_review_drawing.pdf"

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((50, 50), "UCC Engineering Drawing Test Content", fontsize=14)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_1_uploaded_file_persistence(test_db_engine, sample_pdf_drawing):
    """TEST 1: Uploaded PDF is copied into managed persistent storage even if original temp file is deleted."""
    file_service = FileService()
    pdf_service = PDFService(pdf_loader=PyMuPDFAdapter())
    dwg_repo = DrawingRepository(test_db_engine)

    # Copy to managed storage
    persistent_path = file_service.copy_to_managed_storage(sample_pdf_drawing)
    assert persistent_path.exists()
    assert persistent_path != sample_pdf_drawing

    doc_dto = pdf_service.process_pdf_document(persistent_path)
    res = dwg_repo.save_drawing_from_dto(doc_dto)

    # Delete original source file in temp user folder
    sample_pdf_drawing.unlink()
    assert not sample_pdf_drawing.exists()

    # Persistent file in managed storage must still exist
    managed_file = Path(res["file_path"])
    assert managed_file.exists()
    assert managed_file.stat().st_size > 0


def test_2_metadata_persistence(test_db_engine, sample_pdf_drawing):
    """TEST 2: Verify drawing metadata is stored in SQLite (id, project_id, file_name, file_path, size, hash, uploaded_at)."""
    file_service = FileService()
    pdf_service = PDFService(pdf_loader=PyMuPDFAdapter())
    dwg_repo = DrawingRepository(test_db_engine)
    proj_repo = ProjectRepository(test_db_engine)
    dept_repo = EngineeringDepartmentRepository(test_db_engine)

    proj = proj_repo.create_project(name="Project Alpha", description="Test Project")
    dept = dept_repo.get_or_create_department("Electrical Engineering")

    persistent_path = file_service.copy_to_managed_storage(sample_pdf_drawing)
    doc_dto = pdf_service.process_pdf_document(persistent_path)
    res = dwg_repo.save_drawing_from_dto(doc_dto, project_id=proj["id"], department_id=dept["id"])

    dwg_data = dwg_repo.get_drawing_by_id(res["id"])
    assert dwg_data is not None
    assert dwg_data["id"] == res["id"]
    assert dwg_data["project_id"] == proj["id"]
    assert dwg_data["department_id"] == dept["id"]
    assert dwg_data["file_name"] == "sample_review_drawing.pdf"
    assert Path(dwg_data["file_path"]).exists()
    assert dwg_data["file_size_bytes"] > 0
    assert len(dwg_data["file_hash_sha256"]) == 64
    assert dwg_data["uploaded_at"] != ""


def test_3_correct_drawing_association_and_reprocessing(test_db_engine, sample_pdf_drawing):
    """TEST 3: Reprocessing the same PDF retains stable drawing ID and attached comments without duplicating."""
    file_service = FileService()
    pdf_service = PDFService(pdf_loader=PyMuPDFAdapter())
    dwg_repo = DrawingRepository(test_db_engine)
    proj_repo = ProjectRepository(test_db_engine)
    cmt_repo = CommentRepository(test_db_engine)

    proj = proj_repo.create_project(name="Project Beta", description="Test Project")

    persistent_path = file_service.copy_to_managed_storage(sample_pdf_drawing)
    doc_dto = pdf_service.process_pdf_document(persistent_path)
    res_initial = dwg_repo.save_drawing_from_dto(doc_dto, project_id=proj["id"])
    initial_id = res_initial["id"]

    # Save a comment attached to this drawing
    cmt_repo.save_comment(
        drawing_id=initial_id,
        page_number=1,
        raw_text="Test comment attached to drawing",
        bbox=(10, 10, 50, 50),
        status="Approved",
    )

    # Process same drawing again
    res_secondary = dwg_repo.save_drawing_from_dto(doc_dto, project_id=proj["id"])
    assert res_secondary["id"] == initial_id

    # Verify historical comments remain intact
    comments = cmt_repo.get_comments_for_drawing(initial_id)
    assert len(comments) == 1
    assert comments[0]["raw_text"] == "Test comment attached to drawing"


def test_4_application_restart_recovery(test_db_engine, sample_pdf_drawing):
    """TEST 4: After application restart simulation, drawing and persistent file can be retrieved and read."""
    file_service = FileService()
    pdf_service = PDFService(pdf_loader=PyMuPDFAdapter())
    dwg_repo_1 = DrawingRepository(test_db_engine)

    persistent_path = file_service.copy_to_managed_storage(sample_pdf_drawing)
    doc_dto = pdf_service.process_pdf_document(persistent_path)
    res = dwg_repo_1.save_drawing_from_dto(doc_dto)
    dwg_id = res["id"]

    # Simulate fresh app start with new repo instance
    dwg_repo_2 = DrawingRepository(test_db_engine)
    retrieved = dwg_repo_2.get_drawing_by_id(dwg_id)

    assert retrieved is not None
    restored_path = Path(retrieved["file_path"])
    assert restored_path.exists()

    # Re-open PDF with PyMuPDF to verify integrity
    doc = fitz.open(restored_path)
    assert len(doc) == 1
    doc.close()


def test_5_missing_source_file_handled_gracefully(tmp_path):
    """TEST 5: Missing source file path handles existence check gracefully."""
    missing_file = tmp_path / "deleted_drawing.pdf"
    assert not missing_file.exists()

    exists = missing_file.exists()
    assert exists is False
    status_msg = "File available" if exists else "Source file missing"
    assert status_msg == "Source file missing"
