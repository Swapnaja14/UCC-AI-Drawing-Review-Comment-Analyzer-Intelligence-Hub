"""
tests/unit/test_rotated_text_detection.py

Unit test suite verifying Rotated Text Detection (90° Vertical Annotations & Callouts)
in engineering drawings:
1. 90° Counter-Clockwise vertical text detection.
2. 90° Clockwise vertical stamp/callout text detection.
3. 180° Inverted text annotation rescue.
4. Horizontal 0° fast path (no unnecessary rotation passes when 0° OCR succeeds).
5. Proper engine attribution tagging (e.g. tesseract_rot90, tesseract_rot270, tesseract_rot180).
"""
import pytest
import cv2
import numpy as np
import pytesseract
from PIL import Image

from src.services.workflow_engine import ProcessingWorkflowEngine


@pytest.fixture(scope="module", autouse=True)
def check_tesseract_installed():
    """Verify tesseract binary is available before running tests."""
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        pytest.skip("Tesseract OCR is not installed or not in PATH.")


def create_text_image(text: str, width: int = 450, height: int = 80) -> np.ndarray:
    """Helper to create clean black text on white canvas."""
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.putText(
        canvas,
        text,
        (15, int(height * 0.65)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 0),
        2,
    )
    return canvas


def test_rotated_text_detection_90_counterclockwise():
    """Verify 90° CCW rotated vertical text annotation is successfully detected and extracted."""
    # Create horizontal text image: "VERTICAL CALLOUT 90DEG"
    h_img = create_text_image("VERTICAL CALLOUT 90DEG", width=450, height=80)

    # Rotate 90° Counter-Clockwise (results in vertical text)
    rot90_cv = cv2.rotate(h_img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    rot90_pil = Image.fromarray(cv2.cvtColor(rot90_cv, cv2.COLOR_BGR2RGB))

    # Run _ocr_crop_with_fallback with rotation enabled
    text, conf, engine = ProcessingWorkflowEngine._ocr_crop_with_fallback(
        rot90_pil,
        primary_psm=6,
        fallback_psm=11,
        conf_threshold=0.50,
        engine_name="tesseract",
        enable_rotation=True,
    )

    assert text != ""
    assert any(w in text.upper() for w in ["VERTICAL", "CALLOUT", "90DEG"])
    assert conf >= 0.50
    assert "rot" in engine, f"Expected rotation engine attribution, got '{engine}'"


def test_rotated_text_detection_90_clockwise():
    """Verify 90° CW rotated vertical stamp/margin text is successfully detected and extracted."""
    # Create horizontal text image: "MARGIN STAMP 270DEG"
    h_img = create_text_image("MARGIN STAMP 270DEG", width=450, height=80)

    # Rotate 90° Clockwise
    rot270_cv = cv2.rotate(h_img, cv2.ROTATE_90_CLOCKWISE)
    rot270_pil = Image.fromarray(cv2.cvtColor(rot270_cv, cv2.COLOR_BGR2RGB))

    text, conf, engine = ProcessingWorkflowEngine._ocr_crop_with_fallback(
        rot270_pil,
        primary_psm=6,
        fallback_psm=11,
        conf_threshold=0.50,
        engine_name="tesseract",
        enable_rotation=True,
    )

    assert text != ""
    assert any(w in text.upper() for w in ["MARGIN", "STAMP", "270DEG"])
    assert conf >= 0.50
    assert "rot" in engine, f"Expected rotation engine attribution, got '{engine}'"


def test_rotated_text_detection_180_inverted():
    """Verify 180° inverted text callout is rescued."""
    h_img = create_text_image("INVERTED NOTE 180", width=400, height=80)
    rot180_cv = cv2.rotate(h_img, cv2.ROTATE_180)
    rot180_pil = Image.fromarray(cv2.cvtColor(rot180_cv, cv2.COLOR_BGR2RGB))

    text, conf, engine = ProcessingWorkflowEngine._ocr_crop_with_fallback(
        rot180_pil,
        primary_psm=6,
        fallback_psm=11,
        conf_threshold=0.50,
        engine_name="tesseract",
        enable_rotation=True,
    )

    assert text != ""
    assert any(w in text.upper() for w in ["INVERTED", "NOTE", "180"])
    assert conf >= 0.50
    assert "rot180" in engine


def test_unrotated_fast_path():
    """Verify standard 0° horizontal crops bypass rotation passes when confidence is high."""
    h_img = create_text_image("STANDARD HORIZONTAL NOTE", width=450, height=80)
    pil_img = Image.fromarray(cv2.cvtColor(h_img, cv2.COLOR_BGR2RGB))

    text, conf, engine = ProcessingWorkflowEngine._ocr_crop_with_fallback(
        pil_img,
        primary_psm=6,
        fallback_psm=11,
        conf_threshold=0.50,
        engine_name="tesseract",
        enable_rotation=True,
    )

    assert "STANDARD" in text.upper() or "HORIZONTAL" in text.upper()
    assert conf >= 0.50
    assert "rot" not in engine, f"Unrotated image should not use rotation engine, got '{engine}'"
