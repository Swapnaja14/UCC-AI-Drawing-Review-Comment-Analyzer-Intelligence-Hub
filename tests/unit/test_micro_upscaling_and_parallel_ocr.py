"""
tests/unit/test_micro_upscaling_and_parallel_ocr.py

Unit test suite verifying:
1. Micro-Upscaling for Small Engineering Notes (< 35px height/width).
2. Parallel Region OCR on Multi-Comment Pages.
3. Advanced OCR Configuration resolution from AppConfig.
"""
import pytest
import cv2
import numpy as np
import pytesseract
from PIL import Image
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.config.app_config import AppConfig, OCRConfig
from src.services.workflow_engine import ProcessingWorkflowEngine
from src.core.dtos.annotation_dtos import DocumentAnnotationDTO, AnnotationResultDTO, BoundingBoxDTO


@pytest.fixture(scope="module", autouse=True)
def check_tesseract_installed():
    """Verify tesseract binary is available before running tests."""
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        pytest.skip("Tesseract OCR is not installed or not in PATH.")


def create_small_text_image(text: str, width: int = 140, height: int = 22) -> np.ndarray:
    """Helper to create tiny engineering note / dimension flag image."""
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.putText(
        canvas,
        text,
        (4, int(height * 0.75)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (0, 0, 0),
        1,
        cv2.LINE_AA,
    )
    return canvas


def test_micro_upscale_dimension_scaling():
    """Verify that images smaller than min_dim are upscaled to target dimensions."""
    # Small crop: 100 x 20
    small_pil = Image.new("RGB", (100, 20), color="white")
    upscaled = ProcessingWorkflowEngine._micro_upscale_crop(small_pil, min_dim=35, target_dim=80)
    
    assert upscaled.height >= 70, f"Expected height >= 70, got {upscaled.height}"
    assert upscaled.width >= 200, f"Expected width >= 200, got {upscaled.width}"

    # Standard large crop: 300 x 100 (should not be altered)
    large_pil = Image.new("RGB", (300, 100), color="white")
    same_img = ProcessingWorkflowEngine._micro_upscale_crop(large_pil, min_dim=35, target_dim=80)
    assert same_img.size == (300, 100)


def test_micro_upscale_small_note_ocr_extraction():
    """Verify small note (< 35px) is transcribed accurately via micro-upscaling."""
    small_cv = create_small_text_image("NOTE 4B", width=140, height=22)
    small_pil = Image.fromarray(cv2.cvtColor(small_cv, cv2.COLOR_BGR2RGB))

    text, conf, engine_name = ProcessingWorkflowEngine._ocr_crop_with_fallback(
        small_pil,
        primary_psm=6,
        fallback_psm=11,
        conf_threshold=0.50,
        engine_name="tesseract",
        enable_micro_upscale=True,
        min_upscale_dim=35,
        target_upscale_dim=80,
    )

    assert text != ""
    assert any(w in text.upper() for w in ["NOTE", "4B", "NOTE 4B"])
    assert conf >= 0.50


def test_resolve_advanced_ocr_config_defaults_and_custom():
    """Verify default and custom resolution of micro-upscaling and parallel OCR settings."""
    # 1. Defaults
    engine = ProcessingWorkflowEngine(
        file_service=MagicMock(),
        pdf_service=MagicMock(),
        drawing_repo=MagicMock(),
        config=None,
    )
    defaults = engine._resolve_advanced_ocr_config()
    assert defaults["primary_psm"] == 6
    assert defaults["fallback_psm"] == 11
    assert defaults["enable_micro_upscale"] is True
    assert defaults["min_upscale_dim"] == 35
    assert defaults["target_upscale_dim"] == 80
    assert defaults["parallel_region_ocr"] is True
    assert defaults["max_region_workers"] == 4

    # 2. Custom AppConfig
    custom_cfg = AppConfig()
    custom_cfg.ocr = OCRConfig(
        tesseract_psm=4,
        fallback_psm=12,
        confidence_threshold=0.60,
        enable_micro_upscaling=False,
        micro_upscaling_min_px=40,
        micro_upscaling_target_px=100,
        parallel_region_ocr=False,
        max_region_workers=8,
    )
    engine_custom = ProcessingWorkflowEngine(
        file_service=MagicMock(),
        pdf_service=MagicMock(),
        drawing_repo=MagicMock(),
        config=custom_cfg,
    )
    custom_res = engine_custom._resolve_advanced_ocr_config()
    assert custom_res["primary_psm"] == 4
    assert custom_res["fallback_psm"] == 12
    assert custom_res["conf_threshold"] == 0.60
    assert custom_res["enable_micro_upscale"] is False
    assert custom_res["min_upscale_dim"] == 40
    assert custom_res["target_upscale_dim"] == 100
    assert custom_res["parallel_region_ocr"] is False
    assert custom_res["max_region_workers"] == 8


def test_parallel_region_ocr_multi_comment_execution():
    """Verify multi-comment pages execute OCR across parallel workers and maintain sequence."""
    file_service_mock = MagicMock()
    file_service_mock.validate_pdf_file.return_value = MagicMock(is_valid=True, error_message=None)
    file_service_mock.copy_to_managed_storage.side_effect = lambda p: p

    pdf_service_mock = MagicMock()
    pdf_service_mock.process_pdf_document.return_value = MagicMock(
        page_count=1,
        title="MULTI COMMENT TEST",
        drawing_number="DWG-PARALLEL-001",
        revision="A",
    )

    # 4 distinct reviewer markups on Page 1
    regions = [
        BoundingBoxDTO(x0=50, y0=50, x1=200, y1=100, page_number=0, confidence=0.95, label="red_box"),
        BoundingBoxDTO(x0=250, y0=50, x1=400, y1=100, page_number=0, confidence=0.92, label="blue_box"),
        BoundingBoxDTO(x0=50, y0=150, x1=200, y1=200, page_number=0, confidence=0.90, label="green_box"),
        BoundingBoxDTO(x0=250, y0=150, x1=400, y1=200, page_number=0, confidence=0.98, label="native_annotation"),
    ]

    annotation_service_mock = MagicMock()
    annotation_service_mock.detect_all_pages.return_value = DocumentAnnotationDTO(
        file_name="test_parallel.pdf",
        total_pages=1,
        total_regions=4,
        page_results=[AnnotationResultDTO(drawing_id="1", page_number=0, regions=regions, detection_method="hybrid", processing_time_ms=50.0)],
    )

    drawing_repo_mock = MagicMock()
    drawing_repo_mock.get_by_hash.return_value = None
    drawing_repo_mock.save_drawing_from_dto.return_value = {"id": "DWG-PARALLEL-001", "department_id": None, "project_id": None}

    comment_repo_mock = MagicMock()
    comment_repo_mock.save_comment.side_effect = lambda **kwargs: MagicMock(id=1, **kwargs)

    classification_service_mock = MagicMock()
    classification_service_mock.classify_comment.return_value = MagicMock(
        category_name="General",
        confidence=0.90,
        classification_method="rule_based",
    )

    text_cleaning_mock = MagicMock()
    text_cleaning_mock.clean_text.side_effect = lambda t: MagicMock(cleaned_text=t)

    engine = ProcessingWorkflowEngine(
        file_service=file_service_mock,
        pdf_service=pdf_service_mock,
        drawing_repo=drawing_repo_mock,
        comment_repo=comment_repo_mock,
        annotation_service=annotation_service_mock,
        classification_service=classification_service_mock,
        text_cleaning_service=text_cleaning_mock,
    )

    # Mock _process_single_region_ocr to return simulated comment dict
    def mock_process_region(p_obj, reg, p_idx, page_envs, **kwargs):
        return {
            "page_number": p_idx + 1,
            "raw_text": f"COMMENT FOR {reg.label}",
            "cleaned_text": f"COMMENT FOR {reg.label}",
            "bbox": (reg.x0, reg.y0, reg.x1, reg.y1),
            "detection_confidence": reg.confidence,
            "ocr_confidence": 0.90,
            "classification_confidence": 0.0,
            "confidence": 0.90,
            "ocr_engine": "tesseract",
            "label": reg.label,
            "is_ocr_failed": False,
        }

    with patch.object(engine, "_process_single_region_ocr", side_effect=mock_process_region) as mock_ocr:
        with patch("src.services.workflow_engine.fitz.open") as mock_fitz_open:
            mock_doc = MagicMock()
            mock_doc.__len__.return_value = 1
            mock_doc.__getitem__.return_value = MagicMock()
            mock_fitz_open.return_value = mock_doc
            mock_doc.__enter__.return_value = mock_doc

            result = engine.execute_workflow(Path("test_parallel.pdf"))

            assert result.status == "Completed"
            assert result.total_comments_found == 4
            assert mock_ocr.call_count == 4
            assert comment_repo_mock.save_comment.call_count == 4
            saved_calls = comment_repo_mock.save_comment.call_args_list
            assert len(saved_calls) == 4
            # Verify ordering is preserved
            assert saved_calls[0].kwargs["raw_text"] == "COMMENT FOR red_box"
            assert saved_calls[1].kwargs["raw_text"] == "COMMENT FOR blue_box"
            assert saved_calls[2].kwargs["raw_text"] == "COMMENT FOR green_box"
            assert saved_calls[3].kwargs["raw_text"] == "COMMENT FOR native_annotation"

