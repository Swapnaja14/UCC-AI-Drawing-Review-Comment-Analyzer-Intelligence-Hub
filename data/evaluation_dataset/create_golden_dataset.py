"""
Golden Evaluation Dataset Generator & Ground Truth Registry
Generates fixed representative engineering drawings and saves their expected ground-truth outputs:
- Case 1: Vector Drawing with Multi-Color Reviewer Markups
- Case 2: Scanned Drawing with Rasterized Revision Clouds & Annotations
- Case 3: Rotated / Vertical Margin & Schedule Callouts (90° / 270°)
- Case 4: Micro Engineering Annotations (<35px, 6pt deltas)
- Case 5: Negative Controls & Non-Markup CAD Elements (Title Blocks, Hatching, Calibration Bars)
"""

import os
import sys
import json
from pathlib import Path
import numpy as np
import cv2
import pymupdf as fitz
from PIL import Image

DATASET_DIR = Path("data/evaluation_dataset")
DATASET_DIR.mkdir(parents=True, exist_ok=True)


def generate_case_1_vector_drawing() -> Path:
    """Case 1: Pure Vector Drawing with Red, Blue, and Green Reviewer Markups."""
    pdf_path = DATASET_DIR / "case_1_vector_drawing.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # Standard Letter
    
    # Base CAD text
    page.insert_text((50, 50), "GENERAL STRUCTURAL PLAN - LEVEL 2", fontsize=14, color=(0, 0, 0))
    page.insert_text((50, 80), "ALL REBAR ASTM A615 GRADE 60", fontsize=10, color=(0, 0, 0))
    
    # Item 1: Red Technical Markup
    page.draw_rect(fitz.Rect(50, 130, 350, 170), color=(1, 0, 0), width=2)
    page.insert_text((55, 155), "REVISE BEAM SIZE TO W24X68 AT MOMENT CONNECTION", fontsize=10, color=(0.9, 0, 0))
    
    # Item 2: Blue Dimension Markup
    page.draw_rect(fitz.Rect(50, 200, 320, 235), color=(0, 0, 1), width=2)
    page.insert_text((55, 222), "VERIFY CLEARANCE DIMENSION TO GRIDLINE 4", fontsize=10, color=(0, 0, 0.9))
    
    # Item 3: Green Standards Markup
    page.draw_rect(fitz.Rect(50, 265, 300, 295), color=(0, 0.6, 0), width=2)
    page.insert_text((55, 285), "CHECK AWS A2.4 WELD SYMBOL SPECIFICATION", fontsize=9, color=(0, 0.5, 0))

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def generate_case_2_scanned_drawing() -> Path:
    """Case 2: 100% Scanned / Rasterized Drawing (0 vector objects) with Revision Clouds."""
    pdf_path = DATASET_DIR / "case_2_scanned_drawing.pdf"
    
    # Create high-res scanned image
    h, w = 1100, 850
    scanned_img = np.full((h, w, 3), (245, 248, 250), dtype=np.uint8)  # Paper texture
    
    # Draw CAD lines & text into raster pixels
    cv2.putText(scanned_img, "PIPING AND INSTRUMENTATION DIAGRAM P&ID-101", (60, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20, 20, 20), 2)
    cv2.line(scanned_img, (60, 100), (790, 100), (40, 40, 40), 2)
    
    # Red scanned revision cloud markup
    cv2.rectangle(scanned_img, (60, 180), (520, 240), (30, 30, 220), 3)
    cv2.putText(scanned_img, "REVISE PIPE SCHEDULE TO SCH 80", (75, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (30, 30, 220), 2)
    
    # Blue scanned valve tag markup
    cv2.rectangle(scanned_img, (60, 300), (460, 355), (200, 30, 30), 3)  # BGR Blue
    cv2.putText(scanned_img, "VERIFY VALVE TAG CV-102 RATING", (75, 338), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 30, 30), 2)
    
    # Add scanner noise/grain
    noise = np.random.normal(0, 4, scanned_img.shape).astype(np.int16)
    scanned_noisy = np.clip(scanned_img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    # Save as PDF via PyMuPDF image stream
    pil_img = Image.fromarray(cv2.cvtColor(scanned_noisy, cv2.COLOR_BGR2RGB))
    img_byte_arr = fitz.io.BytesIO()
    pil_img.save(img_byte_arr, format='PNG')
    
    doc = fitz.open()
    # 72 DPI page size for 850x1100 px image is ~612x792 pt
    page = doc.new_page(width=612, height=792)
    page.insert_image(page.rect, stream=img_byte_arr.getvalue())
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path



def generate_case_3_rotated_drawing() -> Path:
    """Case 3: Drawing with 90° Vertical Annotations and Callouts."""
    pdf_path = DATASET_DIR / "case_3_rotated_drawing.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    
    # Base CAD
    page.insert_text((50, 50), "ELECTRICAL CONDUIT ELEVATION SCHEDULE", fontsize=14, color=(0, 0, 0))
    
    # 90° Rotated Vertical Red Callout (Generated via raster/rotated pixmap insertion)
    rot_img = np.full((60, 300, 3), 255, dtype=np.uint8)
    cv2.putText(rot_img, "VERTICAL CONDUIT RISER", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (30, 30, 220), 2)
    rot_90 = cv2.rotate(rot_img, cv2.ROTATE_90_COUNTERCLOCKWISE)  # 300 high x 60 wide
    
    pil_rot = Image.fromarray(cv2.cvtColor(rot_90, cv2.COLOR_BGR2RGB))
    img_bytes = fitz.io.BytesIO()
    pil_rot.save(img_bytes, format='PNG')
    
    # Insert at position x=100..160, y=150..450
    page.insert_image(fitz.Rect(100, 150, 160, 450), stream=img_bytes.getvalue())
    page.draw_rect(fitz.Rect(95, 145, 165, 455), color=(1, 0, 0), width=2)
    
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def generate_case_4_micro_annotation_drawing() -> Path:
    """Case 4: Drawing with Small/Micro Engineering Annotations (<35px)."""
    pdf_path = DATASET_DIR / "case_4_micro_drawing.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    
    page.insert_text((50, 50), "FOUNDATION DETAIL SECTION D-D", fontsize=14, color=(0, 0, 0))
    
    # Micro annotation (6pt text, 14pt height box)
    page.draw_rect(fitz.Rect(50, 140, 180, 158), color=(1, 0, 0), width=1.2)
    page.insert_text((54, 153), "REV-02 DELTA REF", fontsize=6, color=(0.85, 0, 0))
    
    # Small elevation callout (8pt text)
    page.draw_rect(fitz.Rect(50, 200, 220, 222), color=(0, 0, 1), width=1.5)
    page.insert_text((54, 216), "ELEV 104.5M TOC", fontsize=8, color=(0, 0, 0.9))

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def generate_case_5_negative_control_drawing() -> Path:
    """Case 5: Drawing with Title Block, Border Lines, and CAD Hatching (Zero Reviewer Comments)."""
    pdf_path = DATASET_DIR / "case_5_negative_drawing.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    
    # Heavy CAD lines and border
    page.draw_rect(fitz.Rect(20, 20, 592, 772), color=(0, 0, 0), width=2)
    page.draw_line(fitz.Point(20, 700), fitz.Point(592, 700), color=(0, 0, 0), width=1)
    
    # Title block in corner
    tb_rect = fitz.Rect(350, 705, 585, 765)
    page.draw_rect(tb_rect, color=(0, 0, 0), width=1)
    page.insert_text((360, 725), "PROJECT: UCC DEMO PLANT", fontsize=8, color=(0, 0, 0))
    page.insert_text((360, 745), "APPROVED BY JDM DATE 2026-09-13", fontsize=8, color=(0, 0, 0))
    
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def build_and_save_golden_ground_truth():
    """Generates all PDFs and serializes golden evaluation ground truth specification."""
    p1 = generate_case_1_vector_drawing()
    p2 = generate_case_2_scanned_drawing()
    p3 = generate_case_3_rotated_drawing()
    p4 = generate_case_4_micro_annotation_drawing()
    p5 = generate_case_5_negative_control_drawing()

    ground_truth = {
        "metadata": {
            "version": "1.0.0",
            "description": "Fixed Golden Evaluation Benchmark for Drawing Review Intelligence",
            "created_date": "2026-10-06",
            "total_cases": 5,
        },
        "test_cases": [
            {
                "case_id": "CASE-01-VECTOR",
                "pdf_file": str(p1.relative_to(Path("."))),
                "description": "Vector drawing with standard red, blue, and green reviewer markups",
                "pdf_type": "vector",
                "expected_min_regions": 3,
                "expected_max_regions": 3,
                "expected_comments": [
                    {
                        "index": 0,
                        "required_keywords": ["BEAM", "SIZE", "W24X68", "MOMENT"],
                        "expected_category": "Technical",
                        "min_ocr_confidence": 0.85,
                        "min_classification_confidence": 0.70,
                    },
                    {
                        "index": 1,
                        "required_keywords": ["CLEARANCE", "DIMENSION", "GRIDLINE"],
                        "expected_category": "Dimension",
                        "min_ocr_confidence": 0.85,
                        "min_classification_confidence": 0.70,
                    },
                    {
                        "index": 2,
                        "required_keywords": ["WELD", "SYMBOL", "AWS"],
                        "expected_category": "Standards",
                        "min_ocr_confidence": 0.80,
                        "min_classification_confidence": 0.70,
                    },
                ]
            },
            {
                "case_id": "CASE-02-SCANNED",
                "pdf_file": str(p2.relative_to(Path("."))),
                "description": "Scanned rasterized P&ID drawing with revision cloud markups",
                "pdf_type": "scanned",
                "expected_min_regions": 2,
                "expected_max_regions": 2,
                "expected_comments": [
                    {
                        "index": 0,
                        "required_keywords": ["PIPE", "SCHEDULE", "SCH"],
                        "expected_category": "Technical",
                        "min_ocr_confidence": 0.70,
                    },
                    {
                        "index": 1,
                        "required_keywords": ["VALVE", "TAG", "CV-102"],
                        "expected_category": "Technical",
                        "min_ocr_confidence": 0.70,
                    },
                ]
            },
            {
                "case_id": "CASE-03-ROTATED",
                "pdf_file": str(p3.relative_to(Path("."))),
                "description": "Drawing with 90° vertical conduit callout requiring orientation correction",
                "pdf_type": "rotated",
                "expected_min_regions": 1,
                "expected_max_regions": 1,
                "expected_comments": [
                    {
                        "index": 0,
                        "required_keywords": ["CONDUIT", "VERTICAL", "RISER"],
                        "expected_category": "Technical",
                        "min_ocr_confidence": 0.75,
                    }
                ]
            },
            {
                "case_id": "CASE-04-MICRO",
                "pdf_file": str(p4.relative_to(Path("."))),
                "description": "Small/micro engineering notes requiring Lanczos micro-upscaling",
                "pdf_type": "micro",
                "expected_min_regions": 2,
                "expected_max_regions": 2,
                "expected_comments": [
                    {
                        "index": 0,
                        "required_keywords": ["REV", "DELTA"],
                        "expected_category": "Drafting",
                        "min_ocr_confidence": 0.60,
                    },
                    {
                        "index": 1,
                        "required_keywords": ["ELEV", "104.5M", "TOC"],
                        "expected_category": "Dimension",
                        "min_ocr_confidence": 0.70,
                    }
                ]
            },
            {
                "case_id": "CASE-05-NEGATIVE-CONTROL",
                "pdf_file": str(p5.relative_to(Path("."))),
                "description": "Negative control with CAD border lines and title block (0 comments expected)",
                "pdf_type": "negative_control",
                "expected_min_regions": 0,
                "expected_max_regions": 0,
                "expected_comments": []
            }
        ]
    }

    gt_path = DATASET_DIR / "golden_ground_truth.json"
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2)

    print(f"Golden dataset created with 5 test cases at: {DATASET_DIR}")
    print(f"Ground truth registered at: {gt_path}")


if __name__ == "__main__":
    build_and_save_golden_ground_truth()
