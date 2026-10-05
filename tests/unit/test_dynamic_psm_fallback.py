"""
tests/unit/test_dynamic_psm_fallback.py
Unit tests verifying Dynamic PSM Fallback (PSM 6 -> PSM 11) for sparse text
in engineering drawings and markup clouds.
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from PIL import Image

from src.config.app_config import AppConfig, OCRConfig
from src.services.workflow_engine import ProcessingWorkflowEngine
from src.services.file_service import FileService
from src.services.pdf_service import PDFService
from src.infrastructure.pdf.pymupdf_adapter import PyMuPDFAdapter
from src.infrastructure.storage.repository import DatabaseEngine, DrawingRepository, CommentRepository
from src.core.dtos.annotation_dtos import BoundingBoxDTO, AnnotationResultDTO, DocumentAnnotationDTO


def test_resolve_ocr_config_defaults():
    """When no config is provided, defaults to PSM 6 -> PSM 11 with 0.50 threshold."""
    engine = ProcessingWorkflowEngine(
        file_service=MagicMock(),
        pdf_service=MagicMock(),
        drawing_repo=MagicMock(),
        config=None,
    )
    primary, fallback, threshold = engine._resolve_ocr_config()
    assert primary == 6
    assert fallback == 11
    assert threshold == 0.50


def test_resolve_ocr_config_from_app_config():
    """Reads custom tesseract_psm, fallback_psm, and confidence_threshold directly from AppConfig."""
    custom_cfg = AppConfig()
    custom_cfg.ocr = OCRConfig(
        tesseract_psm=4,
        fallback_psm=12,
        confidence_threshold=0.65,
    )

    engine = ProcessingWorkflowEngine(
        file_service=MagicMock(),
        pdf_service=MagicMock(),
        drawing_repo=MagicMock(),
        config=custom_cfg,
    )
    primary, fallback, threshold = engine._resolve_ocr_config()
    assert primary == 4
    assert fallback == 12
    assert threshold == 0.65


def test_psm_fallback_primary_high_confidence():
    """When primary PSM yields good text and confidence >= threshold, fallback is not called."""
    dummy_img = Image.new("RGB", (100, 50), color="white")

    with patch.object(
        ProcessingWorkflowEngine,
        "_run_tesseract_psm",
        return_value=("VERIFY PIPE CLEARANCE", 0.92)
    ) as mock_run:
        text, conf, engine_name = ProcessingWorkflowEngine._ocr_crop_with_fallback(
            dummy_img,
            primary_psm=6,
            fallback_psm=11,
            conf_threshold=0.50,
            engine_name="tesseract",
        )

        assert text == "VERIFY PIPE CLEARANCE"
        assert conf == 0.92
        assert engine_name == "tesseract"
        # Only primary PSM 6 should be called
        mock_run.assert_called_once_with(dummy_img, psm=6)


def test_psm_fallback_primary_empty_rescued_by_fallback():
    """When primary PSM 6 returns empty text (e.g. sparse cloud text), PSM 11 is executed and adopted."""
    dummy_img = Image.new("RGB", (100, 50), color="white")

    def mock_run(img, psm):
        if psm == 6:
            return ("", 0.0)
        elif psm == 11:
            return ("REVISE FLANGE SPECS", 0.88)
        return ("", 0.0)

    with patch.object(ProcessingWorkflowEngine, "_run_tesseract_psm", side_effect=mock_run) as mock_run_fn:
        text, conf, engine_name = ProcessingWorkflowEngine._ocr_crop_with_fallback(
            dummy_img,
            primary_psm=6,
            fallback_psm=11,
            conf_threshold=0.50,
            engine_name="tesseract",
        )

        assert text == "REVISE FLANGE SPECS"
        assert conf == 0.88
        assert engine_name == "tesseract_psm11"
        assert mock_run_fn.call_count == 2
        mock_run_fn.assert_any_call(dummy_img, psm=6)
        mock_run_fn.assert_any_call(dummy_img, psm=11)


def test_psm_fallback_primary_low_confidence_improved_by_fallback():
    """When primary PSM 6 returns low confidence (< threshold), PSM 11 is called and adopted if better."""
    dummy_img = Image.new("RGB", (100, 50), color="white")

    def mock_run(img, psm):
        if psm == 6:
            # Low confidence noisy fragment
            return ("REV", 0.25)
        elif psm == 11:
            # Clean sparse transcription
            return ("REVISE PER SPEC 402", 0.84)
        return ("", 0.0)

    with patch.object(ProcessingWorkflowEngine, "_run_tesseract_psm", side_effect=mock_run) as mock_run_fn:
        text, conf, engine_name = ProcessingWorkflowEngine._ocr_crop_with_fallback(
            dummy_img,
            primary_psm=6,
            fallback_psm=11,
            conf_threshold=0.50,
            engine_name="tesseract",
        )

        assert text == "REVISE PER SPEC 402"
        assert conf == 0.84
        assert engine_name == "tesseract_psm11"
        assert mock_run_fn.call_count == 2


def test_psm_fallback_primary_low_confidence_retained_if_fallback_worse():
    """When primary PSM has low confidence but fallback yields empty, retain primary to prevent data loss."""
    dummy_img = Image.new("RGB", (100, 50), color="white")

    def mock_run(img, psm):
        if psm == 6:
            return ("UNCERTAIN TEXT", 0.40)
        elif psm == 11:
            return ("", 0.0)
        return ("", 0.0)

    with patch.object(ProcessingWorkflowEngine, "_run_tesseract_psm", side_effect=mock_run):
        text, conf, engine_name = ProcessingWorkflowEngine._ocr_crop_with_fallback(
            dummy_img,
            primary_psm=6,
            fallback_psm=11,
            conf_threshold=0.50,
            engine_name="tesseract",
        )

        # Primary retained
        assert text == "UNCERTAIN TEXT"
        assert conf == 0.40
        assert engine_name == "tesseract"


def test_workflow_execution_dynamic_psm_end_to_end(tmp_path: Path):
    """End-to-end workflow execution where sparse markup text is recovered via PSM 11 fallback."""
    db_file = tmp_path / "test_psm_workflow.db"
    db_engine = DatabaseEngine(db_path=db_file)
    drawing_repo = DrawingRepository(db_engine)
    comment_repo = CommentRepository(db_engine)

    mock_annotation_service = MagicMock()
    cloud_reg = BoundingBoxDTO(
        x0=100.0, y0=100.0, x1=250.0, y1=160.0,
        page_number=0,
        confidence=0.92,
        label="redline_cloud",
    )
    doc_annot = DocumentAnnotationDTO(
        file_name="drawing_psm.pdf",
        total_pages=1,
        page_results=[
            AnnotationResultDTO(
                drawing_id="DWG-PSM-01",
                page_number=0,
                regions=[cloud_reg],
                detection_method="hybrid",
                processing_time_ms=10.0,
            )
        ],
        total_regions=1,
    )
    mock_annotation_service.detect_all_pages.return_value = doc_annot

    cat_mock = MagicMock()
    cat_mock.category_name = "Structural"
    cat_mock.confidence = 0.89

    res_mock = MagicMock()
    res_mock.primary_category = cat_mock
    res_mock.fallback_used = False
    res_mock.classification_method = "ai_model"

    batch_mock = MagicMock()
    batch_mock.results = [res_mock]

    mock_classification_service = MagicMock()
    mock_classification_service.classify_batch.return_value = batch_mock

    mock_text_cleaning_service = MagicMock()
    mock_text_cleaning_service.clean_text.side_effect = lambda t: MagicMock(cleaned_text=t, corrections=[])

    cfg = AppConfig()
    cfg.ocr.tesseract_psm = 6
    cfg.ocr.fallback_psm = 11
    cfg.ocr.confidence_threshold = 0.50

    file_service = FileService()
    pdf_adapter = PyMuPDFAdapter()
    pdf_service = PDFService(pdf_loader=pdf_adapter)

    workflow = ProcessingWorkflowEngine(
        file_service=file_service,
        pdf_service=pdf_service,
        drawing_repo=drawing_repo,
        comment_repo=comment_repo,
        annotation_service=mock_annotation_service,
        classification_service=mock_classification_service,
        text_cleaning_service=mock_text_cleaning_service,
        config=cfg,
    )

    # Create dummy PDF
    import pymupdf as fitz
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # Add high contrast drawing in the region so std >= 6.0
    page.draw_rect(fitz.Rect(100, 100, 250, 160), color=(1, 0, 0), fill=(0, 0, 0))
    pdf_file = tmp_path / "drawing_psm.pdf"
    doc.save(str(pdf_file))
    doc.close()

    def mock_run_psm(img, psm):
        if psm == 6:
            # PSM 6 fails to read sparse text in markup cloud
            return ("", 0.0)
        elif psm == 11:
            # PSM 11 successfully extracts sparse text
            return ("VERIFY BEAM EMBEDMENT DEPTH", 0.91)
        return ("", 0.0)

    with patch.object(ProcessingWorkflowEngine, "_run_tesseract_psm", side_effect=mock_run_psm):
        res = workflow.execute_workflow(pdf_file)
        assert res.status == "Completed"

    all_drawings = drawing_repo.get_all_drawings()
    assert len(all_drawings) == 1
    comments = comment_repo.get_comments_for_drawing(all_drawings[0]["id"])
    assert len(comments) == 1

    cmt = comments[0]
    assert cmt["raw_text"] == "VERIFY BEAM EMBEDMENT DEPTH"
    assert cmt["ocr_confidence"] == 0.91
    assert cmt["ocr_engine"] == "tesseract_psm11"
    assert cmt["category_name"] == "Structural"
