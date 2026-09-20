"""
tests/unit/test_workflow_engine.py
Unit test suite for FileService, ProcessingWorkflowEngine, and Workflow DTOs.
"""

import pytest
from pathlib import Path
import fitz  # PyMuPDF

from src.services.file_service import FileService
from src.services.pdf_service import PDFService
from src.services.workflow_engine import ProcessingWorkflowEngine
from src.infrastructure.pdf.pymupdf_adapter import PyMuPDFAdapter
from src.infrastructure.storage.repository import DatabaseEngine, DrawingRepository
from src.core.dtos.workflow_dtos import WorkflowState
from src.core.exceptions.workflow_exceptions import WorkflowProcessingError


@pytest.fixture
def sample_pdf_path(tmp_path: Path) -> Path:
    pdf_file = tmp_path / "drawing_test.pdf"
    doc = fitz.open()
    page = doc.new_page(width=841.89, height=595.28)
    page.insert_text((50, 50), "DRAWING NO: UCC-DWG-202", fontsize=14)
    doc.save(pdf_file)
    doc.close()
    return pdf_file


def test_file_service_validation_success(sample_pdf_path: Path):
    file_service = FileService(max_size_mb=500.0)
    res = file_service.validate_pdf_file(sample_pdf_path)

    assert res.is_valid is True
    assert res.file_name == "drawing_test.pdf"
    assert res.file_size_mb >= 0.0
    assert len(res.file_hash_sha256) == 64


def test_file_service_invalid_extension(tmp_path: Path):
    txt_file = tmp_path / "drawing.txt"
    txt_file.write_text("not a pdf")
    file_service = FileService()
    res = file_service.validate_pdf_file(txt_file)

    assert res.is_valid is False
    assert "Only .pdf drawings are supported" in res.error_message


def test_file_service_file_too_large(sample_pdf_path: Path):
    # Set max size to tiny limit (0.0001 MB)
    file_service = FileService(max_size_mb=0.0001)
    res = file_service.validate_pdf_file(sample_pdf_path)

    assert res.is_valid is False
    assert "exceeds maximum allowed limit" in res.error_message


def test_workflow_engine_execution_success(sample_pdf_path: Path, tmp_path: Path):
    db_file = tmp_path / "test_workflow.db"
    db_engine = DatabaseEngine(db_path=db_file)
    drawing_repo = DrawingRepository(db_engine)

    file_service = FileService()
    pdf_adapter = PyMuPDFAdapter()
    pdf_service = PDFService(pdf_loader=pdf_adapter)

    engine = ProcessingWorkflowEngine(
        file_service=file_service,
        pdf_service=pdf_service,
        drawing_repo=drawing_repo
    )

    steps_recorded = []

    def on_step(snapshot):
        steps_recorded.append(snapshot)

    result = engine.execute_workflow(sample_pdf_path, progress_callback=on_step)

    assert result.status == "Completed"
    assert result.file_name == "drawing_test.pdf"
    assert len(steps_recorded) >= 7
    assert steps_recorded[-1].state == WorkflowState.COMPLETED
    assert engine.current_state == WorkflowState.COMPLETED
