"""
tests/unit/test_reprocessing_integrity.py — Verification of human review preservation and reprocessing integrity.
"""

import pytest
import pymupdf as fitz
from pathlib import Path
from unittest.mock import MagicMock

from src.infrastructure.storage.repository import (
    DatabaseEngine,
    DrawingRepository,
    CommentRepository,
    AuditLogRepository,
    ProjectRepository,
)
from src.infrastructure.pdf.pymupdf_adapter import PyMuPDFAdapter
from src.services.pdf_service import PDFService
from src.services.file_service import FileService
from src.services.workflow_engine import ProcessingWorkflowEngine
from src.core.dtos.annotation_dtos import DocumentAnnotationDTO, AnnotationResultDTO, BoundingBoxDTO
from src.core.dtos.workflow_dtos import WorkflowState


@pytest.fixture
def test_db_engine(tmp_path):
    db_file = tmp_path / "test_reprocessing.db"
    return DatabaseEngine(db_path=db_file)


@pytest.fixture
def sample_pdf(tmp_path):
    pdf_path = tmp_path / "test_drawing_reprocess.pdf"
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    page.insert_text((100, 100), "TEST DRAWING FOR REPROCESSING", fontsize=14)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_reprocessing_preserves_human_verified_comments_and_audit(test_db_engine, sample_pdf, tmp_path):
    """
    Verify that when a drawing is re-ingested or re-processed:
    1. Human-verified comments are strictly retained with their status, edited text, and category.
    2. The original initial_category is preserved.
    3. The complete audit log history for verified comments is preserved.
    4. Re-extracted comments matching existing verified comments are not duplicated.
    5. Old unverified comments are safely cleaned up.
    """
    file_service = FileService()
    pdf_service = PDFService(pdf_loader=PyMuPDFAdapter())
    dwg_repo = DrawingRepository(test_db_engine)
    cmt_repo = CommentRepository(test_db_engine)
    audit_repo = AuditLogRepository(test_db_engine)

    # 1. Initial drawing registration
    persistent_path = file_service.copy_to_managed_storage(sample_pdf)
    doc_dto = pdf_service.process_pdf_document(persistent_path)
    dwg_record = dwg_repo.save_drawing_from_dto(doc_dto)
    dwg_id = dwg_record["id"]

    # 2. Save two comments: one that will be human verified, one that remains unverified
    c1 = cmt_repo.save_comment(
        drawing_id=dwg_id,
        page_number=1,
        raw_text="VERIFY BEAM CLEARANCE",
        bbox=(100.0, 100.0, 300.0, 150.0),
        confidence=0.80,
        ocr_confidence=0.85,
        classification_confidence=0.75,
        category_name="Dimensional",
        initial_category="Dimensional",
        status="Pending",
        comment_id="CMT-TEST-01",
    )

    c2 = cmt_repo.save_comment(
        drawing_id=dwg_id,
        page_number=1,
        raw_text="OLD UNVERIFIED COMMENT",
        bbox=(400.0, 200.0, 550.0, 240.0),
        confidence=0.50,
        status="Pending",
        comment_id="CMT-TEST-02",
    )

    # 3. Simulate Human Review: edit text, change category, approve status
    cmt_repo.update_comment_category("CMT-TEST-01", "Structural", changed_by_user_id="lead_eng")
    cmt_repo.update_comment_text("CMT-TEST-01", "VERIFY BEAM CLEARANCE - REVISED", changed_by_user_id="lead_eng")
    cmt_repo.update_comment_status("CMT-TEST-01", "Approved", verified_by_human=True, changed_by_user_id="lead_eng")

    # Verify state before reprocessing
    c1_loaded = cmt_repo.get_comment_by_id("CMT-TEST-01")
    assert c1_loaded["is_verified_by_human"] is True
    assert c1_loaded["category_name"] == "Structural"
    assert c1_loaded["initial_category"] == "Dimensional"
    assert c1_loaded["cleaned_text"] == "VERIFY BEAM CLEARANCE - REVISED"
    assert c1_loaded["raw_text"] == "VERIFY BEAM CLEARANCE"
    assert c1_loaded["status"] == "Approved"

    audit_trail = audit_repo.get_audit_logs_for_comment("CMT-TEST-01")
    assert len(audit_trail) >= 3  # edit_category, edit_text, approve

    # 4. Now simulate re-processing of the drawing through WorkflowEngine
    # Mock annotation detection returning:
    # - Region 1: identical physical location as c1 (IoU >= 0.70)
    # - Region 2: a NEW comment location
    mock_annot_service = MagicMock()
    mock_annot_service.detect_all_pages.return_value = DocumentAnnotationDTO(
        file_name=persistent_path.name,
        total_pages=1,
        total_regions=2,
        page_results=[
            AnnotationResultDTO(
                drawing_id=dwg_id,
                page_number=0,
                detection_method="hybrid",
                processing_time_ms=10.0,
                regions=[
                    BoundingBoxDTO(
                        x0=100.0, y0=100.0, x1=300.0, y1=150.0,
                        page_number=0, confidence=0.88, label="comment_red",
                        source_id="annot_1", source_text="VERIFY BEAM CLEARANCE",
                        region_role="primary",
                    ),
                    BoundingBoxDTO(
                        x0=50.0, y0=300.0, x1=250.0, y1=340.0,
                        page_number=0, confidence=0.91, label="comment_red",
                        source_id="annot_new", source_text="ADDITIONAL RECHECK NOTE",
                        region_role="primary",
                    ),
                ],
            )
        ],
    )

    engine = ProcessingWorkflowEngine(
        file_service=file_service,
        pdf_service=pdf_service,
        drawing_repo=dwg_repo,
        annotation_service=mock_annot_service,
        comment_repo=cmt_repo,
        audit_repo=audit_repo,
    )

    # Execute workflow reprocessing
    result = engine.execute_workflow(persistent_path)
    assert result.status == "Completed"
    assert engine.current_state == WorkflowState.COMPLETED

    # 5. Verify Database State after Reprocessing
    all_comments = cmt_repo.get_comments_for_drawing(dwg_id)

    # Should have exactly 2 comments:
    # 1) The human-verified CMT-TEST-01 (retained without duplicates)
    # 2) The newly extracted note (ADDITIONAL RECHECK NOTE)
    # The old unverified CMT-TEST-02 should be gone!
    assert len(all_comments) == 2

    # Check that CMT-TEST-01 is still intact
    verified_c = next((c for c in all_comments if c["id"] == "CMT-TEST-01"), None)
    assert verified_c is not None
    assert verified_c["is_verified_by_human"] is True
    assert verified_c["category_name"] == "Structural"
    assert verified_c["initial_category"] == "Dimensional"
    assert verified_c["cleaned_text"] == "VERIFY BEAM CLEARANCE - REVISED"
    assert verified_c["status"] == "Approved"

    # Check audit history for CMT-TEST-01 is preserved
    audit_after = audit_repo.get_audit_logs_for_comment("CMT-TEST-01")
    assert len(audit_after) == len(audit_trail)

    # Check old unverified comment is deleted
    assert cmt_repo.get_comment_by_id("CMT-TEST-02") is None

    # Check newly extracted comment is present
    new_c = next((c for c in all_comments if c["id"] != "CMT-TEST-01"), None)
    assert new_c is not None
    assert "ADDITIONAL RECHECK NOTE" in new_c["raw_text"]
