"""
tests/unit/test_precision_annotation_detection.py
Unit tests verifying strict Red, Blue, Green comment markup detection
and 0% false positives from black CAD drawing lines, title blocks, and AutoCAD grid tags.
"""

import pytest
import pymupdf as fitz
from pathlib import Path

from src.services.annotation_service_enhanced import AnnotationDetectionServiceEnhanced
from src.core.dtos.annotation_dtos import DocumentAnnotationDTO


@pytest.fixture
def service():
    return AnnotationDetectionServiceEnhanced()


@pytest.fixture
def multi_color_markup_pdf(tmp_path: Path) -> Path:
    """Creates a synthetic drawing with Red, Blue, and Green comments + Black CAD text + AutoCAD grid marks."""
    pdf_path = tmp_path / "engineering_review_markup.pdf"
    doc = fitz.open()
    page = doc.new_page(width=1000, height=800)
    
    # 1. Normal Black CAD Drawing Text & Lines (MUST NOT BE DETECTED AS COMMENTS)
    page.insert_text((50, 50), "DRAWING NO: UCC-PIPE-8001 REV C", fontsize=12, color=(0, 0, 0))
    page.insert_text((50, 75), "PUMP DISCHARGE LINE 10-HC-4001", fontsize=10, color=(0.1, 0.1, 0.1))
    page.draw_line((40, 40), (950, 40), color=(0, 0, 0), width=1)
    page.draw_rect(fitz.Rect(700, 700, 980, 780), color=(0, 0, 0), width=1)
    
    # 2. AutoCAD Grid Box Annotations (A, B, C, 1, 2) (MUST NOT BE DETECTED AS COMMENTS)
    for idx, letter in enumerate(["A", "B", "C", "D"]):
        annot = page.add_rect_annot(fitz.Rect(20 + idx * 30, 10, 40 + idx * 30, 25))
        annot.set_info(content=letter, title="AutoCAD")
        annot.update()
        
    for idx, num in enumerate(["1", "2", "3"]):
        annot = page.add_rect_annot(fitz.Rect(10, 100 + idx * 40, 25, 120 + idx * 40))
        annot.set_info(content=num, title="AutoCAD")
        annot.update()

    # 3. RED Reviewer Comment (Digital text + Cloud)
    page.insert_text((200, 200), "Relocate pipe hanger 2 feet North to avoid clash with cable tray.", fontsize=11, color=(0.95, 0.05, 0.05))
    red_cloud = page.add_rect_annot(fitz.Rect(190, 190, 550, 230))
    red_cloud.set_colors(stroke=(1.0, 0.0, 0.0))
    red_cloud.set_info(content="Relocate pipe hanger 2 feet North to avoid clash with cable tray.", subject="Cloud")
    red_cloud.update()

    # 4. BLUE Reviewer Comment (Digital text + FreeText Callout)
    page.insert_text((200, 350), "Change flange rating from 150# to 300# ANSI spec.", fontsize=11, color=(0.05, 0.20, 0.95))
    blue_callout = page.add_freetext_annot(
        fitz.Rect(190, 340, 520, 380),
        "Change flange rating from 150# to 300# ANSI spec.",
        fontsize=10,
        text_color=(0.0, 0.2, 0.9)
    )
    blue_callout.update()

    # 5. GREEN Reviewer Comment (Digital text)
    page.insert_text((200, 500), "Approved as noted for structural gusset plate addition.", fontsize=11, color=(0.05, 0.80, 0.15))
    green_annot = page.add_rect_annot(fitz.Rect(190, 490, 560, 530))
    green_annot.set_colors(stroke=(0.0, 0.8, 0.1))
    green_annot.set_info(content="Approved as noted for structural gusset plate addition.", subject="Review")
    green_annot.update()

    doc.save(pdf_path)
    doc.close()
    return pdf_path


def test_strict_color_rgb_methods(service):
    """Test unit color predicates for red, blue, green with strict chromatic thresholds."""
    # Red checks
    assert service._is_red_rgb(255, 0, 0) is True
    assert service._is_red_rgb(200, 30, 30) is True
    assert service._is_red_rgb(50, 50, 50) is False      # Black/dark gray
    assert service._is_red_rgb(200, 200, 200) is False  # Light gray
    assert service._is_red_rgb(180, 160, 140) is False  # Beige/neutral

    # Blue checks
    assert service._is_blue_rgb(0, 50, 255) is True
    assert service._is_blue_rgb(20, 40, 200) is True
    assert service._is_blue_rgb(0, 0, 0) is False

    # Green checks
    assert service._is_green_rgb(0, 200, 0) is True
    assert service._is_green_rgb(30, 180, 40) is True
    assert service._is_green_rgb(120, 120, 120) is False


def test_detects_only_colored_markup(service, multi_color_markup_pdf):
    """Verify that only the 3 red, blue, and green comments are extracted and 0 AutoCAD grid tags or black text."""
    res = service.detect_annotations_on_page(multi_color_markup_pdf, 0, method='hybrid')
    
    assert len(res.regions) >= 3
    
    # Verify labels include red, blue, green
    labels = [r.label for r in res.regions]
    assert any("red" in l for l in labels)
    assert any("blue" in l for l in labels)
    assert any("green" in l for l in labels)
    
    # Check that no AutoCAD grid tags ('A', 'B', '1', '2' at top/left) are included
    for r in res.regions:
        # None of the detected boxes should be near the top grid bar (y < 40)
        assert not (r.y0 < 35 and (r.x1 - r.x0) < 30)


def test_rejects_empty_and_monochrome_drawings(service, tmp_path):
    """Verify that a drawing with only standard black CAD text produces 0 comment regions."""
    pdf_path = tmp_path / "monochrome_cad.pdf"
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    page.insert_text((100, 100), "STANDARD BLACK PIPING DRAWING", color=(0, 0, 0))
    page.insert_text((100, 130), "VALVE V-101 4 INCH GATE VALVE", color=(0, 0, 0))
    page.draw_rect(fitz.Rect(50, 50, 750, 550), color=(0, 0, 0), width=2)
    doc.save(pdf_path)
    doc.close()

    res = service.detect_annotations_on_page(pdf_path, 0, method='hybrid')
    assert len(res.regions) == 0


def test_deduplicate_consolidates_cohesive_regions(service):
    """Verify deduplication properly merges overlapping cloud + text boxes without dropping separate colors."""
    from src.core.dtos.annotation_dtos import BoundingBoxDTO
    
    r1 = BoundingBoxDTO(x0=100, y0=100, x1=200, y1=150, page_number=0, confidence=0.98, label="comment_red")
    r2 = BoundingBoxDTO(x0=90,  y0=90,  x1=210, y1=160, page_number=0, confidence=0.90, label="native_redline")
    # Separate blue comment
    r3 = BoundingBoxDTO(x0=300, y0=100, x1=400, y1=150, page_number=0, confidence=0.98, label="comment_blue")
    
    deduped = service._deduplicate_regions([r1, r2, r3])
    assert len(deduped) == 2
    
    # The red region should be expanded to encompass both r1 and r2
    red_box = next(b for b in deduped if "red" in b.label)
    assert red_box.x0 <= 90
    assert red_box.y0 <= 90
    assert red_box.x1 >= 210
    assert red_box.y1 >= 160
    
    # Blue box preserved intact
    blue_box = next(b for b in deduped if "blue" in b.label)
    assert blue_box.x0 == 300


def test_revision_cloud_enclosed_text_extraction(tmp_path: Path):
    """Verify that a red revision cloud drawn around drawing text extracts the enclosed text as review subject."""
    from src.services.workflow_engine import ProcessingWorkflowEngine
    from src.services.file_service import FileService
    from src.services.pdf_service import PDFService
    from src.infrastructure.pdf.pymupdf_adapter import PyMuPDFAdapter
    from src.services.text_cleaning_service import TextCleaningService
    from src.services.classification_service import ClassificationService
    from src.infrastructure.storage.repository import DrawingRepository, CommentRepository
    from unittest.mock import MagicMock

    pdf_path = tmp_path / "revision_cloud_sample.pdf"
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    
    # Drawing text (black)
    page.insert_text((300, 300), "SET GAP @ 1/4 INCH", fontsize=12, color=(0, 0, 0))
    # Red revision cloud polygon/rect around this text
    cloud = page.add_rect_annot(fitz.Rect(280, 280, 480, 330))
    cloud.set_colors(stroke=(1.0, 0.0, 0.0))
    cloud.set_info(subject="Cloud")
    cloud.update()
    
    doc.save(pdf_path)
    doc.close()

    mock_drawing_repo = MagicMock(spec=DrawingRepository)
    mock_drawing_repo.save_drawing_from_dto.return_value = {"id": "DWG-TEST-CLOUD"}
    mock_comment_repo = MagicMock(spec=CommentRepository)
    
    mock_classification = MagicMock()
    mock_classification.classify_comment.return_value = MagicMock(
        primary_category=MagicMock(category_name="Dimension", confidence=0.95)
    )

    engine = ProcessingWorkflowEngine(
        file_service=FileService(),
        pdf_service=PDFService(pdf_loader=PyMuPDFAdapter()),
        drawing_repo=mock_drawing_repo,
        annotation_service=AnnotationDetectionServiceEnhanced(),
        comment_repo=mock_comment_repo,
        text_cleaning_service=TextCleaningService(),
        classification_service=mock_classification,
    )

    res = engine.execute_workflow(pdf_path)
    assert res.status == "Completed"
    
    # Verify that comment_repo.save_comment was called with the enclosed text 'SET GAP @ 1/4 INCH'
    assert mock_comment_repo.save_comment.called
    saved_calls = mock_comment_repo.save_comment.call_args_list
    saved_texts = [call.kwargs.get("cleaned_text", "") for call in saved_calls]
    assert any("SET GAP @ 1/4 INCH" in t for t in saved_texts)


def test_title_block_and_status_stamp_suppression(tmp_path: Path):
    """Verify that title blocks and review status approval stamps are completely excluded from detection."""
    from src.services.workflow_engine import ProcessingWorkflowEngine
    from src.services.file_service import FileService
    from src.services.pdf_service import PDFService
    from src.infrastructure.pdf.pymupdf_adapter import PyMuPDFAdapter
    from src.services.text_cleaning_service import TextCleaningService
    from src.infrastructure.storage.repository import DrawingRepository, CommentRepository
    from unittest.mock import MagicMock

    pdf_path = tmp_path / "title_block_drawing.pdf"
    doc = fitz.open()
    page = doc.new_page(width=1000, height=800)

    # 1. Corner Title Block in bottom-right corner (grid & metadata)
    page.draw_rect(fitz.Rect(700, 600, 980, 780), color=(0, 0, 0), width=1.0)
    page.insert_text((710, 620), "SCALE: 1/4\" = 1'-0\"", fontsize=10, color=(0, 0, 0))
    page.insert_text((710, 640), "DRAWING NUMBER: DWG-55767-01", fontsize=10, color=(0, 0, 0))
    page.insert_text((710, 660), "CONTRACT NUMBER: C-99182", fontsize=10, color=(0, 0, 0))
    page.insert_text((710, 680), "DESIGNED BY: ENG   DRAWN BY: CAD", fontsize=10, color=(0, 0, 0))
    page.insert_text((710, 700), "CHECKED BY: CHK    APPROVED BY: APVD", fontsize=10, color=(0, 0, 0))
    page.insert_text((710, 720), "DO NOT SCALE DRAWING", fontsize=10, color=(0, 0, 0))

    # 2. Document Return Review Status Stamp in top-left corner (red box + checkboxes)
    page.draw_rect(fitz.Rect(40, 40, 300, 240), color=(1.0, 0.0, 0.0), width=2.0)
    page.insert_text((50, 60), "DOCUMENT RETURN REVIEW STATUS", fontsize=11, color=(0.9, 0.0, 0.0))
    page.insert_text((50, 80), "1. NO EXCEPTIONS NOTED. PROCEED WITH ENGINEERING", fontsize=9, color=(0.9, 0.0, 0.0))
    page.insert_text((50, 100), "2. ENGINEERING/PROCUREMENT/FABRICATION MAY PROCEED", fontsize=9, color=(0.9, 0.0, 0.0))
    page.insert_text((50, 120), "3. NOT APPROVED. CORRECT AS NOTED AND RESUBMIT", fontsize=9, color=(0.9, 0.0, 0.0))
    page.insert_text((50, 140), "4. NO APPROVAL REQUIRED", fontsize=9, color=(0.9, 0.0, 0.0))
    page.insert_text((50, 170), "BY BreKol          DATE 2/5/2026", fontsize=10, color=(0.9, 0.0, 0.0))
    page.insert_text((50, 190), "EXP: 06/30/2026", fontsize=9, color=(0.9, 0.0, 0.0))

    # 3. Genuine Reviewer Redline in drawing center
    page.insert_text((400, 400), "VERIFY CLEARANCE AT STRUCTURAL FLANGE", fontsize=11, color=(0.9, 0.0, 0.0))
    red_callout = page.add_rect_annot(fitz.Rect(390, 385, 680, 420))
    red_callout.set_colors(stroke=(1.0, 0.0, 0.0))
    red_callout.set_info(content="VERIFY CLEARANCE AT STRUCTURAL FLANGE", subject="Callout")
    red_callout.update()

    doc.save(pdf_path)
    doc.close()

    mock_drawing_repo = MagicMock(spec=DrawingRepository)
    mock_drawing_repo.save_drawing_from_dto.return_value = {"id": "DWG-TB-TEST"}
    mock_comment_repo = MagicMock(spec=CommentRepository)
    mock_classification = MagicMock()
    mock_classification.classify_comment.return_value = MagicMock(
        primary_category=MagicMock(category_name="Clearance", confidence=0.95)
    )

    engine = ProcessingWorkflowEngine(
        file_service=FileService(),
        pdf_service=PDFService(pdf_loader=PyMuPDFAdapter()),
        drawing_repo=mock_drawing_repo,
        annotation_service=AnnotationDetectionServiceEnhanced(),
        comment_repo=mock_comment_repo,
        text_cleaning_service=TextCleaningService(),
        classification_service=mock_classification,
    )

    res = engine.execute_workflow(pdf_path)
    assert res.status == "Completed"

    saved_calls = mock_comment_repo.save_comment.call_args_list
    saved_texts = [call.kwargs.get("cleaned_text", "") for call in saved_calls]

    # Verify that ONLY the genuine reviewer comment was saved
    assert len(saved_texts) == 1
    assert "VERIFY CLEARANCE AT STRUCTURAL FLANGE" in saved_texts[0]

    # Verify that title block and stamp text were completely suppressed
    for t in saved_texts:
        assert "DOCUMENT RETURN" not in t
        assert "NO EXCEPTIONS" not in t
        assert "ENGINEERING/PROCUREMENT" not in t
        assert "SCALE:" not in t
        assert "DRAWING NUMBER:" not in t
        assert "DESIGNED BY:" not in t
        assert "BreKol" not in t


def test_red_revision_cloud_hollow_contour_detection(service, tmp_path: Path):
    """Verify that a hollow red revision cloud drawn with thin strokes is detected by color segmentation."""
    pdf_path = tmp_path / "hollow_cloud.pdf"
    doc = fitz.open()
    page = doc.new_page(width=1000, height=800)
    
    # Draw hollow red rectangle representing a cloud/box around drawing text
    page.draw_rect(fitz.Rect(150, 200, 350, 320), color=(0.95, 0.05, 0.05), width=2.0)
    page.insert_text((180, 260), "SET GAP @ X\"", fontsize=11, color=(0, 0, 0))
    
    doc.save(pdf_path)
    doc.close()
    
    res = service.detect_annotations_on_page(pdf_path, 0, method='color')
    assert len(res.regions) >= 1
    red_reg = next((r for r in res.regions if "red" in r.label), None)
    assert red_reg is not None
    assert red_reg.x0 <= 160
    assert red_reg.y0 <= 210
    assert red_reg.x1 >= 340
    assert red_reg.y1 >= 310


def test_detail_scale_does_not_suppress_reviewer_comments(service, tmp_path: Path):
    """Verify that a detail scale label (e.g. DETAIL 1 SCALE: 1/2"=1'-0") does not create a false title block exclusion."""
    pdf_path = tmp_path / "detail_scale_drawing.pdf"
    doc = fitz.open()
    page = doc.new_page(width=1000, height=800)
    
    # Detail header in bottom quadrant
    page.insert_text((400, 600), "DETAIL 1", fontsize=14, color=(0, 0, 0))
    page.insert_text((400, 620), "SCALE: 1/2\"=1'-0\"", fontsize=10, color=(0, 0, 0))
    page.insert_text((400, 640), "ITEMS TAGS ONLY (TYPICAL 20 PLACES)", fontsize=9, color=(0, 0, 0))
    
    # Red reviewer comment directly under the detail scale
    page.insert_text(
        (400, 680), 
        "CONSIDER HAVING A SECOND VIEW FOR THE OTHER NUVA FEEDER ARRANGEMENT. -JDM", 
        fontsize=11, 
        color=(0.95, 0.05, 0.05)
    )
    
    doc.save(pdf_path)
    doc.close()
    
    res = service.detect_annotations_on_page(pdf_path, 0, method='hybrid')
    assert len(res.regions) >= 1
    red_reg = next((r for r in res.regions if "red" in r.label), None)
    assert red_reg is not None
    assert red_reg.y0 >= 660


def test_small_reviewer_initials_and_arrows_detected(service, tmp_path: Path):
    """Verify that small reviewer callouts like BEK and arrows are detected as genuine markup."""
    pdf_path = tmp_path / "small_markup.pdf"
    doc = fitz.open()
    page = doc.new_page(width=1000, height=800)
    
    # Small red reviewer initials
    page.insert_text((850, 450), "BEK", fontsize=12, color=(0.95, 0.05, 0.05))
    
    # Red cross mark
    page.draw_line((800, 440), (820, 460), color=(0.95, 0.05, 0.05), width=2)
    page.draw_line((800, 460), (820, 440), color=(0.95, 0.05, 0.05), width=2)
    
    doc.save(pdf_path)
    doc.close()
    
    res = service.detect_annotations_on_page(pdf_path, 0, method='hybrid')
    assert len(res.regions) >= 1
    labels = [r.label for r in res.regions]
    assert any("red" in l for l in labels)




