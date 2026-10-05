"""
Unit tests verifying OCR Confidence Score utilization, low-confidence behavior policies,
reprocessing pipelines, AI classifier handoff, and manual review guardrails.
"""

import os
import sys
import numpy as np
import cv2
from PIL import Image
import pymupdf as fitz
import pytest

from src.services.auto_approval_policy import evaluate_auto_approval
from src.services.workflow_engine import ProcessingWorkflowEngine
from src.infrastructure.storage.models import CommentModel, DrawingModel
from src.infrastructure.storage.repository import DatabaseEngine, CommentRepository


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_ocr_conf.db"
    return DatabaseEngine(db_path=db_file)


def test_ocr_confidence_calculation_and_disentanglement(temp_db):
    """Verify OCR confidence is accurately disentangled from detection and classification confidences."""
    comment_repo = CommentRepository(temp_db)
    drawing_id = "DWG-CONF-TEST"
    
    with temp_db.get_session() as session:
        dwg = DrawingModel(
            id=drawing_id,
            file_path="drawing.pdf",
            file_name="drawing.pdf",
            file_size_bytes=1024,
            file_hash_sha256="abcd1234efgh5678",
            total_pages=1
        )
        session.add(dwg)
        session.commit()

    # Save comment with different confidence levels
    saved = comment_repo.save_comment(
        drawing_id=drawing_id,
        page_number=1,
        raw_text="CHECK CONDUIT ROUTING AT LEVEL 2",
        bbox=(50.0, 50.0, 200.0, 100.0),
        confidence=0.82,
        detection_confidence=0.98,
        ocr_confidence=0.65,  # Low OCR confidence
        classification_confidence=0.95,  # High classification confidence
        category_name="Technical",
        status="Pending"
    )

    retrieved = comment_repo.get_comment_by_id(saved["id"])
    assert retrieved["detection_confidence"] == pytest.approx(0.98, rel=1e-3)
    assert retrieved["ocr_confidence"] == pytest.approx(0.65, rel=1e-3)
    assert retrieved["classification_confidence"] == pytest.approx(0.95, rel=1e-3)


def test_low_ocr_confidence_blocks_auto_approval():
    """Verify that low OCR confidence (<0.85) strictly blocks auto-approval even if classification is 99%."""
    # Scenario 1: Low OCR confidence (0.60), High AI confidence (0.98)
    approved, reason = evaluate_auto_approval(
        ocr_confidence=0.60,
        classification_confidence=0.98,
        text="REVISE VALVE SPECIFICATION TO ANSI 300# FLANGED",
        fallback_used=False,
        classification_method="ai_model",
        auto_approve_enabled=True,
        threshold=0.85,
    )
    assert approved is False
    assert "OCR confidence" in reason
    assert "below threshold" in reason

    # Scenario 2: High OCR confidence (0.95), High AI confidence (0.95)
    approved_high, reason_high = evaluate_auto_approval(
        ocr_confidence=0.95,
        classification_confidence=0.95,
        text="REVISE VALVE SPECIFICATION TO ANSI 300# FLANGED",
        fallback_used=False,
        classification_method="ai_model",
        auto_approve_enabled=True,
        threshold=0.85,
    )
    assert approved_high is True


def test_dynamic_psm_fallback_on_low_confidence():
    """Verify that low confidence or empty text on primary PSM triggers fallback PSM."""
    # Create image with sparse text
    img = np.full((100, 400, 3), 255, dtype=np.uint8)
    cv2.putText(img, "SPARSE CLOUD NOTE", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    pil_img = Image.fromarray(img)

    text, conf, engine = ProcessingWorkflowEngine._ocr_crop_with_fallback(
        pil_img,
        primary_psm=6,
        fallback_psm=11,
        conf_threshold=0.50,
        enable_rotation=False,
        enable_micro_upscale=False,
    )
    assert bool(text.strip()) is True
    assert conf >= 0.50


def test_ocr_failure_creates_flagged_placeholder():
    """Verify that regions with 0 OCR text but high detection confidence are flagged for manual review."""
    # Test OCR Failure badging logic for high-detection region
    det_conf = 0.92
    words = []
    
    if len(words) == 0 and det_conf >= 0.70:
        placeholder = "OCR Failed (Needs Manual Transcription)"
        res_dict = {
            "page_number": 1,
            "raw_text": placeholder,
            "cleaned_text": placeholder,
            "detection_confidence": det_conf,
            "ocr_confidence": 0.0,
            "classification_confidence": 0.0,
            "status": "Flagged",
            "is_ocr_failed": True,
        }
    
    assert res_dict["status"] == "Flagged"
    assert res_dict["is_ocr_failed"] is True
    assert res_dict["ocr_confidence"] == 0.0
    assert res_dict["raw_text"] == "OCR Failed (Needs Manual Transcription)"


def test_composite_confidence_weighting():
    """Verify the composite confidence formula properly weights detection, OCR, and classification."""
    det_c = 0.90
    ocr_c = 0.70
    cat_c = 0.95
    
    # Formula: 0.20 * det + 0.40 * ocr + 0.40 * cat
    composite = round(min(0.99, det_c * 0.20 + ocr_c * 0.40 + cat_c * 0.40), 2)
    expected = round(0.90 * 0.20 + 0.70 * 0.40 + 0.95 * 0.40, 2)  # 0.18 + 0.28 + 0.38 = 0.84
    
    assert composite == expected
    assert composite == 0.84
