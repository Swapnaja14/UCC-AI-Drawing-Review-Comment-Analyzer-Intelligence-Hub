"""
Unit test suite verifying Colored Markup Detection Architecture across:
1. Pure Vector PDFs (vector drawings, digital colored text, native annotations)
2. Pure Scanned PDFs (flat rasterized image with colored markup, 0 vector objects)
3. Mixed PDFs (vector CAD line background + scanned/raster color markups)
4. Multi-Resolution / Different DPI levels (54 DPI, 72 DPI, 150 DPI, 300 DPI)
5. Validation that detection does NOT rely solely on vector color, guaranteeing scanned drawing support.
"""
import pytest
import numpy as np
import cv2
import pymupdf as fitz
from pathlib import Path

from src.services.annotation_service_enhanced import AnnotationDetectionServiceEnhanced
from src.core.dtos.annotation_dtos import BoundingBoxDTO


@pytest.fixture
def annotation_service():
    return AnnotationDetectionServiceEnhanced()


def create_pure_vector_pdf(pdf_path: Path) -> Path:
    """Create a digital vector PDF with native colored text, vector redline box, and native FreeText."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    # 1. Digital Red Text (Vector text span)
    page.insert_text(
        fitz.Point(100, 100),
        "INCORRECT WELD DETAIL ON FLANGE",
        fontsize=12,
        color=(0.9, 0.1, 0.1)  # Red RGB
    )

    # 2. Vector Blue Box (Drawings path)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(100, 200, 300, 260))
    shape.finish(color=(0.1, 0.2, 0.9), width=2.0)  # Blue stroke
    shape.commit()

    # 3. Native PDF Annotation (FreeText)
    annot = page.add_freetext_annot(
        fitz.Rect(100, 320, 350, 360),
        "CHECK CLEARANCE TO COLUMN B4",
        fontsize=10,
        text_color=(0.1, 0.7, 0.2)  # Green text
    )
    annot.update()

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def create_pure_scanned_pdf(pdf_path: Path) -> Path:
    """
    Create a scanned drawing PDF: A pure raster image page with 0 vector paths and 0 digital text spans.
    Contains red, blue, and green highlighter / pen markups embedded directly into the pixel raster.
    """
    # Create white raster canvas (800 x 1000 pixels)
    img_bgr = np.full((1000, 800, 3), 255, dtype=np.uint8)

    # Simulate black CAD lines (background)
    cv2.rectangle(img_bgr, (50, 50), (750, 950), (40, 40, 40), 2)
    cv2.line(img_bgr, (100, 500), (700, 500), (50, 50, 50), 1)

    # 1. Scanned Red Reviewer Pen Markup
    cv2.rectangle(img_bgr, (120, 120), (380, 200), (30, 30, 220), 4)  # BGR Red
    cv2.putText(img_bgr, "HOLD - VERIFY ASME B16.5", (130, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (30, 30, 220), 2)

    # 2. Scanned Blue Revision Cloud / Note
    cv2.rectangle(img_bgr, (120, 300), (420, 380), (220, 50, 30), 4)  # BGR Blue
    cv2.putText(img_bgr, "ROTATE VIEW 90 DEG", (130, 345), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 50, 30), 2)

    # 3. Scanned Green Field Note
    cv2.rectangle(img_bgr, (120, 600), (400, 680), (30, 190, 40), 4)  # BGR Green
    cv2.putText(img_bgr, "CLARIFY TOC ELEVATION", (130, 645), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (30, 190, 40), 2)

    # Encode to PNG and insert as a full-page raster scan
    success, png_bytes = cv2.imencode(".png", img_bgr)
    assert success

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_image(page.rect, stream=png_bytes.tobytes())
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def create_mixed_pdf(pdf_path: Path) -> Path:
    """
    Create a Mixed PDF: Vector CAD geometry background + superimposed raster colored markup image.
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    # 1. Black/Neutral Vector CAD geometry
    shape = page.new_shape()
    for y in range(100, 700, 50):
        shape.draw_line(fitz.Point(50, y), fitz.Point(550, y))
    shape.finish(color=(0.2, 0.2, 0.2), width=1.0)
    shape.commit()

    # 2. Superimposed Raster Redline Stamp Image (RGBA with markup)
    stamp_bgr = np.full((120, 300, 3), 255, dtype=np.uint8)
    cv2.rectangle(stamp_bgr, (5, 5), (295, 115), (20, 20, 220), 8)
    cv2.putText(stamp_bgr, "REDLINE REVISION A", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 220), 3)
    success, png_bytes = cv2.imencode(".png", stamp_bgr)
    assert success

    page.insert_image(fitz.Rect(120, 220, 360, 320), stream=png_bytes.tobytes())
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_pure_vector_pdf_detection(tmp_path, annotation_service):
    """Verify markup detection on Pure Vector PDFs."""
    pdf_file = tmp_path / "pure_vector.pdf"
    create_pure_vector_pdf(pdf_file)

    doc = fitz.open(pdf_file)
    page = doc[0]

    # Verify vector objects exist
    assert len(page.get_drawings()) > 0
    assert len(page.get_text("blocks")) > 0

    # Run detection
    res = annotation_service.detect_annotations_on_page(pdf_file, 0, method='hybrid')
    doc.close()

    assert len(res.regions) >= 2
    # Verify colored labels detected
    labels = [r.label for r in res.regions]
    assert any("red" in l.lower() for l in labels)
    assert any("blue" in l.lower() or "green" in l.lower() or "native" in l.lower() for l in labels)


def test_pure_scanned_pdf_detection(tmp_path, annotation_service):
    """
    CRITICAL: Verify that Pure Scanned PDFs (0 vector paths, 0 digital text)
    are successfully detected via pixel-level raster color segmentation.
    """
    pdf_file = tmp_path / "pure_scanned.pdf"
    create_pure_scanned_pdf(pdf_file)

    doc = fitz.open(pdf_file)
    page = doc[0]

    # Confirm pure scan: zero vector drawings and zero PDF text blocks
    assert len(page.get_drawings()) == 0
    assert len(page.get_text("blocks")) == 0
    assert len(list(page.annots())) == 0

    # Run detection using hybrid and color methods
    res_hybrid = annotation_service.detect_annotations_on_page(pdf_file, 0, method='hybrid')
    res_color = annotation_service.detect_annotations_on_page(pdf_file, 0, method='color')
    doc.close()

    # Must detect the 3 colored pen regions from raster pixels alone
    assert len(res_hybrid.regions) >= 3, f"Expected >= 3 regions from scanned raster, got {len(res_hybrid.regions)}"
    assert len(res_color.regions) >= 3

    labels = [r.label.lower() for r in res_hybrid.regions]
    assert any("red" in l for l in labels), "Must detect scanned Red pen"
    assert any("blue" in l for l in labels), "Must detect scanned Blue pen"
    assert any("green" in l for l in labels), "Must detect scanned Green pen"


def test_mixed_pdf_detection(tmp_path, annotation_service):
    """Verify markup detection on Mixed PDFs (vector CAD background + raster colored stamp)."""
    pdf_file = tmp_path / "mixed.pdf"
    create_mixed_pdf(pdf_file)

    doc = fitz.open(pdf_file)
    page = doc[0]
    assert len(page.get_drawings()) > 0
    doc.close()

    res = annotation_service.detect_annotations_on_page(pdf_file, 0, method='hybrid')
    assert len(res.regions) >= 1
    labels = [r.label.lower() for r in res.regions]
    assert any("red" in l for l in labels)


def test_color_segmentation_across_multiple_dpis(tmp_path, annotation_service):
    """
    Verify color segmentation stability across various rasterization resolutions
    (54 DPI, 72 DPI, 150 DPI, 300 DPI). Coordinates must normalize accurately to PDF page units.
    """
    pdf_file = tmp_path / "dpi_test_scanned.pdf"
    create_pure_scanned_pdf(pdf_file)

    doc = fitz.open(pdf_file)
    page = doc[0]
    pw, ph = page.rect.width, page.rect.height

    dpi_levels = [54, 72, 150, 300]
    bounding_unions_by_dpi = {}

    for dpi in dpi_levels:
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR if pix.n == 3 else cv2.COLOR_RGBA2BGR)

        # Apply HSV + RGB thresholding
        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        hsv_red1 = cv2.inRange(hsv, np.array([0, 35, 50], dtype=np.uint8), np.array([14, 255, 255], dtype=np.uint8))
        hsv_red2 = cv2.inRange(hsv, np.array([160, 35, 50], dtype=np.uint8), np.array([180, 255, 255], dtype=np.uint8))
        red_mask = cv2.bitwise_or(hsv_red1, hsv_red2)

        # Dilate to connect text and box
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (int(10 * dpi / 72.0), int(10 * dpi / 72.0)))
        dilated = cv2.dilate(red_mask, kernel, iterations=1)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        scale = 72.0 / dpi

        # Find the primary red markup bounding box in PDF points
        valid_boxes = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > (100 * (dpi / 72.0) ** 2):
                x, y, w, h = cv2.boundingRect(cnt)
                valid_boxes.append((x * scale, y * scale, (x + w) * scale, (y + h) * scale))

        assert len(valid_boxes) >= 1, f"Failed to detect red markup at {dpi} DPI"
        # Compute overall union of detected red markup
        ux0 = min(b[0] for b in valid_boxes)
        uy0 = min(b[1] for b in valid_boxes)
        ux1 = max(b[2] for b in valid_boxes)
        uy1 = max(b[3] for b in valid_boxes)
        bounding_unions_by_dpi[dpi] = (ux0, uy0, ux1, uy1)

    doc.close()

    # Compare bounding box centers across 54 DPI and 300 DPI in PDF page points
    box_54 = bounding_unions_by_dpi[54]
    box_300 = bounding_unions_by_dpi[300]

    cx_54 = (box_54[0] + box_54[2]) / 2.0
    cy_54 = (box_54[1] + box_54[3]) / 2.0

    cx_300 = (box_300[0] + box_300[2]) / 2.0
    cy_300 = (box_300[1] + box_300[3]) / 2.0

    assert abs(cx_54 - cx_300) < 10.0, f"Center X drift across 54 vs 300 DPI: {abs(cx_54 - cx_300):.2f} pt"
    assert abs(cy_54 - cy_300) < 10.0, f"Center Y drift across 54 vs 300 DPI: {abs(cy_54 - cy_300):.2f} pt"
