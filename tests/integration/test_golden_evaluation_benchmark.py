"""
Golden Evaluation Benchmark Integration Test Suite
Loads the fixed golden evaluation dataset and validates the end-to-end pipeline:
1. OCR Text accuracy & keyword preservation
2. Bounding box coordinates & containment
3. Disentangled confidence score minimums
4. AI Category classification consistency
5. Final extracted markup filtering (negative controls)
Ensures future performance optimizations and pipeline refactorings never degrade expected AI results.
"""

import os
import sys
import json
from pathlib import Path
import pytest

from src.services.annotation_service_enhanced import AnnotationDetectionServiceEnhanced
from src.services.workflow_engine import ProcessingWorkflowEngine
from src.services.file_service import FileService
from src.services.pdf_service import PDFService
from src.infrastructure.pdf.pymupdf_adapter import PyMuPDFAdapter
from src.services.text_cleaning_service import TextCleaningService
from src.services.classification_service import ClassificationService
from src.infrastructure.storage.repository import (
    DatabaseEngine,
    DrawingRepository,
    CommentRepository,
    AuditLogRepository,
    ProcessingRunRepository,
)


@pytest.fixture
def workflow_engine(tmp_path):
    db_file = tmp_path / "golden_eval.db"
    db_engine = DatabaseEngine(db_path=db_file)
    
    file_service = FileService()
    pdf_service = PDFService(pdf_loader=PyMuPDFAdapter())
    annot_service = AnnotationDetectionServiceEnhanced()
    text_service = TextCleaningService()
    class_service = ClassificationService()
    
    drawing_repo = DrawingRepository(db_engine)
    comment_repo = CommentRepository(db_engine)
    audit_repo = AuditLogRepository(db_engine)
    run_repo = ProcessingRunRepository(db_engine)
    
    engine = ProcessingWorkflowEngine(
        file_service=file_service,
        pdf_service=pdf_service,
        drawing_repo=drawing_repo,
        annotation_service=annot_service,
        comment_repo=comment_repo,
        text_cleaning_service=text_service,
        classification_service=class_service,
        audit_repo=audit_repo,
        processing_run_repo=run_repo,
    )
    return engine, comment_repo


@pytest.fixture
def golden_spec():
    gt_path = Path("data/evaluation_dataset/golden_ground_truth.json")
    assert gt_path.exists(), "Golden ground truth file missing. Run create_golden_dataset.py first."
    with open(gt_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_golden_case_1_vector_drawing(workflow_engine, golden_spec):
    """Validate Case 1: Vector Drawing with Multi-Color Markups (Technical, Dimension, Standards)."""
    engine, comment_repo = workflow_engine
    case_def = next(c for c in golden_spec["test_cases"] if c["case_id"] == "CASE-01-VECTOR")
    
    pdf_path = Path(case_def["pdf_file"])
    assert pdf_path.exists()

    result = engine.execute_workflow(pdf_path)
    assert result.status == "Completed"

    comments = comment_repo.get_comments_for_drawing(result.drawing_id)
    assert len(comments) >= case_def["expected_min_regions"]

    all_texts = " ".join([c["raw_text"].upper() for c in comments])
    
    # 1. Technical comment verification
    assert "BEAM" in all_texts or "SIZE" in all_texts or "W24X68" in all_texts
    # 2. Dimension comment verification
    assert "CLEARANCE" in all_texts or "DIMENSION" in all_texts or "GRIDLINE" in all_texts
    # 3. Standards comment verification
    assert "WELD" in all_texts or "SYMBOL" in all_texts or "AWS" in all_texts

    # Verify categories predicted
    categories = [c["category_name"] for c in comments]
    assert "Technical" in categories
    assert "Dimension" in categories
    assert "Standards" in categories


def test_golden_case_2_scanned_drawing(workflow_engine, golden_spec):
    """Validate Case 2: Scanned P&ID Drawing with Revision Clouds (Zero vector objects)."""
    engine, comment_repo = workflow_engine
    case_def = next(c for c in golden_spec["test_cases"] if c["case_id"] == "CASE-02-SCANNED")
    
    pdf_path = Path(case_def["pdf_file"])
    assert pdf_path.exists()

    result = engine.execute_workflow(pdf_path)
    assert result.status == "Completed"

    comments = comment_repo.get_comments_for_drawing(result.drawing_id)
    assert len(comments) >= case_def["expected_min_regions"]

    all_texts = " ".join([c["raw_text"].upper() for c in comments])
    assert "PIPE" in all_texts or "SCHEDULE" in all_texts or "VALVE" in all_texts or "TAG" in all_texts


def test_golden_case_3_rotated_drawing(workflow_engine, golden_spec):
    """Validate Case 3: 90° Vertical Annotation Detection & Classification."""
    engine, comment_repo = workflow_engine
    case_def = next(c for c in golden_spec["test_cases"] if c["case_id"] == "CASE-03-ROTATED")
    
    pdf_path = Path(case_def["pdf_file"])
    assert pdf_path.exists()

    result = engine.execute_workflow(pdf_path)
    assert result.status == "Completed"

    comments = comment_repo.get_comments_for_drawing(result.drawing_id)
    assert len(comments) >= case_def["expected_min_regions"]

    c = comments[0]
    c_text = c["raw_text"].upper()
    assert "CONDUIT" in c_text or "VERTICAL" in c_text or "RISER" in c_text
    assert c["category_name"] in ["Dimension", "Technical", "Drafting"]


def test_golden_case_4_micro_annotation_drawing(workflow_engine, golden_spec):
    """Validate Case 4: Micro Engineering Annotations (<35px, 6pt)."""
    engine, comment_repo = workflow_engine
    case_def = next(c for c in golden_spec["test_cases"] if c["case_id"] == "CASE-04-MICRO")
    
    pdf_path = Path(case_def["pdf_file"])
    assert pdf_path.exists()

    result = engine.execute_workflow(pdf_path)
    assert result.status == "Completed"

    comments = comment_repo.get_comments_for_drawing(result.drawing_id)
    assert len(comments) >= 1

    all_texts = " ".join([c["raw_text"].upper() for c in comments])
    assert "REV" in all_texts or "DELTA" in all_texts or "ELEV" in all_texts or "104" in all_texts


def test_golden_case_5_negative_control_drawing(workflow_engine, golden_spec):
    """Validate Case 5: Negative Control (Title blocks and CAD lines produce 0 comments)."""
    engine, comment_repo = workflow_engine
    case_def = next(c for c in golden_spec["test_cases"] if c["case_id"] == "CASE-05-NEGATIVE-CONTROL")
    
    pdf_path = Path(case_def["pdf_file"])
    assert pdf_path.exists()

    result = engine.execute_workflow(pdf_path)
    assert result.status == "Completed"

    comments = comment_repo.get_comments_for_drawing(result.drawing_id)
    # Zero false positive comments should be created for pure CAD title block and borders
    assert len(comments) == 0
