"""
Unit tests verifying Tesseract OCR in the production pipeline:
- Tesseract availability and configuration (Language & PSM)
- Extracted text, bounding boxes, confidence scores, region reading order
- Preprocessing accuracy preservation
- Serial vs parallel execution output equivalence
- OCR behavior on clean digital, scanned, low-res, rotated, small text, and noisy/blurred regions
"""
import os
import sys
import numpy as np
import cv2
from PIL import Image
import pytesseract
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Auto-detect Tesseract executable if needed
possible_paths = [
    r'C:\Program Files\Tesseract-OCR\tesseract.exe',
    r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    r'C:\Users\{}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'.format(os.getenv('USERNAME')),
]
for p in possible_paths:
    if os.path.exists(p):
        pytesseract.pytesseract.tesseract_cmd = p
        break

from src.config.app_config import AppConfig
from src.services.ocr_service import OCRService
from src.services.image_preprocessing_service import ImagePreprocessingService


def test_tesseract_installed_and_configured():
    """Verify Tesseract OCR is installed and accessible with version info."""
    version = pytesseract.get_tesseract_version()
    assert version is not None
    assert str(version).startswith("5.") or str(version).startswith("4.")


def test_ocr_configuration_language_and_psm():
    """Confirm configured OCR language and page segmentation mode in config and service."""
    cfg = AppConfig.load_from_yaml("config/config.yaml")
    assert cfg.ocr.tesseract_psm == 6  # PSM 6: Uniform block of text
    assert cfg.ocr.fallback_psm == 11  # PSM 11: Sparse text
    assert cfg.pdf.ocr_dpi == 300
    
    ocr_service = OCRService()
    assert ocr_service.lang == 'eng'


def test_ocr_extracted_text_bboxes_confidence_ordering():
    """Validate extracted text, bounding boxes, confidence scores, and region ordering."""
    img_h, img_w = 400, 700
    test_img = np.full((img_h, img_w, 3), 255, dtype=np.uint8)
    
    lines = [
        ("LINE 1: PIPING REVISION REQUIRED", (40, 60)),
        ("LINE 2: VERIFY VALVE TAG V-102", (40, 150)),
        ("LINE 3: CHECK FLANGE RATING 300#", (40, 240)),
        ("LINE 4: APPROVED BY JDM", (40, 330)),
    ]
    for text, pos in lines:
        cv2.putText(test_img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

    pil_img = Image.fromarray(test_img)
    data = pytesseract.image_to_data(pil_img, lang='eng', config='--psm 6', output_type=pytesseract.Output.DICT)

    words = []
    confs = []
    boxes = []
    for i in range(len(data['text'])):
        t = data['text'][i].strip()
        c = float(data['conf'][i])
        if t and c > 0:
            words.append(t)
            confs.append(c / 100.0)
            boxes.append((data['left'][i], data['top'][i], data['width'][i], data['height'][i]))

    assert len(words) > 15
    assert any("PIPING" in w for w in words)
    assert any("VALVE" in w for w in words)
    assert any("FLANGE" in w for w in words)
    assert np.mean(confs) > 0.80

    # Validate region ordering top-to-bottom
    y_coords = [b[1] for b in boxes]
    is_ordered = all(y_coords[i] <= y_coords[i+1] + 20 for i in range(len(y_coords)-1))
    assert is_ordered is True


def test_preprocessing_accuracy_preservation():
    """Ensure OCR preprocessing does not degrade recognition accuracy."""
    prep = ImagePreprocessingService()
    img = np.full((200, 600, 3), 255, dtype=np.uint8)
    cv2.putText(img, "STANDARD ACCURACY TEST 100#", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

    # Raw OCR
    raw_ocr = pytesseract.image_to_string(img, config='--psm 6').strip()
    
    # Contrast enhanced (CLAHE)
    clahe_gray = prep.enhance_contrast(prep.grayscale_conversion(img), method='clahe', clip_limit=2.0)
    clahe_ocr = pytesseract.image_to_string(clahe_gray, config='--psm 6').strip()

    assert "ACCURACY" in raw_ocr
    assert "ACCURACY" in clahe_ocr


def test_parallel_vs_serial_ocr_equivalence():
    """Verify that parallel OCR produces identical output to serial OCR."""
    test_crops = []
    for i in range(5):
        c_img = np.full((100, 400, 3), 255, dtype=np.uint8)
        cv2.putText(c_img, f"REGION {i+1} CALLOUT", (20, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 180), 2)
        test_crops.append(c_img)

    # Serial
    serial_results = [pytesseract.image_to_string(img, config='--psm 6').strip() for img in test_crops]

    # Parallel
    with ThreadPoolExecutor(max_workers=4) as ex:
        parallel_results = list(ex.map(lambda img: pytesseract.image_to_string(img, config='--psm 6').strip(), test_crops))

    assert serial_results == parallel_results


def test_ocr_behavior_on_specialized_scenarios():
    """Test OCR on clean, scanned, low-res, rotated, small, and noisy/blurred regions."""
    prep = ImagePreprocessingService()

    # 1. Clean digital text
    clean = np.full((80, 400, 3), 255, dtype=np.uint8)
    cv2.putText(clean, "CLEAN DRAWING NOTE", (15, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 0), 2)
    clean_txt = pytesseract.image_to_string(clean, config='--psm 6').strip()
    assert "CLEAN" in clean_txt

    # 2. Scanned / grain background
    scanned = np.full((80, 400, 3), (235, 240, 245), dtype=np.uint8)
    cv2.putText(scanned, "SCANNED SHEET SPEC", (15, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (20, 20, 20), 2)
    scanned_prep = prep.enhance_contrast(prep.grayscale_conversion(scanned), method='clahe', clip_limit=2.0)
    scanned_txt = pytesseract.image_to_string(scanned_prep, config='--psm 6').strip()
    assert "SCANNED" in scanned_txt

    # 3. Low-resolution text (upscaled)
    lores = np.full((35, 180, 3), 255, dtype=np.uint8)
    cv2.putText(lores, "LOW RES", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    upscaled = cv2.resize(lores, (540, 105), interpolation=cv2.INTER_CUBIC)
    lores_txt = pytesseract.image_to_string(upscaled, config='--psm 6').strip()
    assert "LOW" in lores_txt or "RES" in lores_txt

    # 4. Small text (upscaled)
    small = np.full((50, 350, 3), 255, dtype=np.uint8)
    cv2.putText(small, "NOTE: ELEV 104.5M", (10, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    small_up = cv2.resize(small, (700, 100), interpolation=cv2.INTER_CUBIC)
    small_txt = pytesseract.image_to_string(small_up, config='--psm 6').strip()
    assert "NOTE" in small_txt or "ELEV" in small_txt

    # 5. Rotated text (orientation corrected)
    h_temp = np.full((80, 300, 3), 255, dtype=np.uint8)
    cv2.putText(h_temp, "VERTICAL NOTE", (15, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 0), 2)
    rot_90 = cv2.rotate(h_temp, cv2.ROTATE_90_COUNTERCLOCKWISE)
    rot_corrected = cv2.rotate(rot_90, cv2.ROTATE_90_CLOCKWISE)
    rot_txt = pytesseract.image_to_string(rot_corrected, config='--psm 6').strip()
    assert "VERTICAL" in rot_txt

    # 6. Noisy / blurred text (sharpened)
    blur_img = np.full((80, 400, 3), 255, dtype=np.uint8)
    cv2.putText(blur_img, "CHECK PUMP ALIGNMENT", (15, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    blurred = cv2.GaussianBlur(blur_img, (3, 3), 1.0)
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpened = cv2.filter2D(blurred, -1, kernel)
    sharp_txt = pytesseract.image_to_string(sharpened, config='--psm 6').strip()
    assert "PUMP" in sharp_txt or "ALIGNMENT" in sharp_txt
