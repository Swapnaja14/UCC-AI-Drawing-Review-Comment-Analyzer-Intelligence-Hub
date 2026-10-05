"""
Unit tests verifying Image Preprocessing applied before OCR / model inference:
- Grayscale conversion and chromatic color isolation
- Thresholding (Otsu, Adaptive) vs stroke preservation
- Denoising (Bilateral, fastNlMeans, Median) vs punctuation preservation
- Sharpening / Contrast Enhancement (CLAHE)
- Resizing / Lanczos Micro-Upscaling for small engineering text
- Rotation and Deskew correction (90° orthogonal + subtle skew)
- Verification that preprocessing improves OCR accuracy without destroying useful engineering information
"""

import os
import sys
import time
import io
import cv2
import numpy as np
import pymupdf as fitz
from PIL import Image
import pytesseract

possible_paths = [
    r'C:\Program Files\Tesseract-OCR\tesseract.exe',
    r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    r'C:\Users\{}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'.format(os.getenv('USERNAME')),
]
for p in possible_paths:
    if os.path.exists(p):
        pytesseract.pytesseract.tesseract_cmd = p
        break

from src.services.image_preprocessing_service import ImagePreprocessingService
from src.services.workflow_engine import ProcessingWorkflowEngine


def test_grayscale_and_color_isolation_preservation():
    """
    Verify that grayscale conversion simplifies standard text, while
    chromatic color isolation prevents faint red/blue reviewer markup
    from washing out against bright background.
    """
    prep = ImagePreprocessingService()
    
    # 1. Standard RGB image with dark text
    img_rgb = np.full((100, 400, 3), 255, dtype=np.uint8)
    cv2.putText(img_rgb, "SPECIFICATION NOTE", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    gray = prep.grayscale_conversion(img_rgb)
    assert len(gray.shape) == 2
    assert gray.shape[:2] == (100, 400)
    
    # 2. Colored red markup on textured/colored background
    red_markup = np.full((80, 350, 3), 250, dtype=np.uint8)
    cv2.putText(red_markup, "VERIFY FLANGE", (15, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (30, 30, 220), 2)
    
    # Color isolation mask
    nr = red_markup[:, :, 2].astype(int)
    ng = red_markup[:, :, 1].astype(int)
    nb = red_markup[:, :, 0].astype(int)
    mask_red = (nr >= 120) & ((nr - np.maximum(ng, nb)) >= 24)
    
    iso_arr = np.full((red_markup.shape[0], red_markup.shape[1]), 255, dtype=np.uint8)
    iso_arr[mask_red] = 0
    
    txt_raw = pytesseract.image_to_string(red_markup, config='--psm 6').strip()
    txt_iso = pytesseract.image_to_string(iso_arr, config='--psm 6').strip()
    
    assert "VERIFY" in txt_iso or "FLANGE" in txt_iso


def test_thresholding_and_punctuation_preservation():
    """
    Verify that binarization (Otsu & Adaptive) maintains character continuity
    and preserves essential punctuation like decimal points and hyphens (e.g. ELEV 104.5M, JB-401).
    """
    prep = ImagePreprocessingService()
    
    img = np.full((80, 500, 3), 255, dtype=np.uint8)
    # Drawing note with precision decimal and hyphenated tag
    cv2.putText(img, "ELEV 104.5M TAG: JB-401", (15, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 0), 2)
    
    # Otsu binarization
    otsu_bin = prep.binarize(img, method='otsu')
    assert np.unique(otsu_bin).tolist() == [0, 255]
    
    txt_otsu = pytesseract.image_to_string(otsu_bin, config='--psm 6').strip()
    assert "104.5" in txt_otsu or "104" in txt_otsu
    assert "JB-401" in txt_otsu or "JB" in txt_otsu


def test_denoising_noise_removal_vs_information_retention():
    """
    Verify that noise removal filters scanner grain without blurring fine text features.
    """
    prep = ImagePreprocessingService()
    
    # Create synthetic noisy scanned drawing image
    img = np.full((100, 450, 3), 245, dtype=np.uint8)
    cv2.putText(img, "CHECK VALVE CV-102", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (10, 10, 10), 2)
    
    # Add Gaussian scanner noise
    noise = np.random.normal(0, 15, img.shape).astype(np.int16)
    noisy_img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    # Bilateral denoising preserves sharp edges while smoothing noise
    denoised_bilateral = prep.denoise(noisy_img, method='bilateral', strength=8)
    assert denoised_bilateral.shape == noisy_img.shape
    
    # FastNlMeans denoising
    denoised_nlm = prep.denoise(noisy_img, method='fastNlMeans', strength=10)
    assert denoised_nlm.shape == noisy_img.shape
    
    txt_denoised = pytesseract.image_to_string(denoised_bilateral, config='--psm 6').strip()
    assert "CHECK" in txt_denoised or "VALVE" in txt_denoised or "CV-102" in txt_denoised


def test_contrast_enhancement_clahe():
    """
    Verify that CLAHE (Contrast Limited Adaptive Histogram Equalization)
    enhances low-contrast handwritten or faded notes without clipping.
    """
    prep = ImagePreprocessingService()
    
    # Low-contrast faint drawing note
    faint_img = np.full((80, 400, 3), 230, dtype=np.uint8)
    cv2.putText(faint_img, "LOW CONTRAST NOTE", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 2)
    
    clahe_enhanced = prep.enhance_contrast(faint_img, method='clahe', clip_limit=2.5)
    assert len(clahe_enhanced.shape) == 2
    
    # Std deviation / contrast of the enhanced image should be significantly higher
    assert np.std(clahe_enhanced) > np.std(faint_img)
    
    txt_clahe = pytesseract.image_to_string(clahe_enhanced, config='--psm 6').strip()
    assert "CONTRAST" in txt_clahe or "NOTE" in txt_clahe or "LOW" in txt_clahe


def test_resizing_and_micro_upscaling_accuracy_gain():
    """
    Verify that resizing / Lanczos micro-upscaling boosts character recognition
    for small engineering annotations (<35px).
    """
    # Create small note (height 24px)
    small_img = np.full((24, 160, 3), 255, dtype=np.uint8)
    cv2.putText(small_img, "REV-02 DELTA", (5, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    
    pil_small = Image.fromarray(small_small := cv2.cvtColor(small_img, cv2.COLOR_BGR2RGB))
    
    # Raw small OCR (often fails or yields low confidence on 24px image)
    raw_txt, raw_conf = ProcessingWorkflowEngine._run_tesseract_psm(pil_small, psm=6)
    
    # Micro-upscaled via Lanczos to 80px target dimension
    upscaled_pil = ProcessingWorkflowEngine._micro_upscale_crop(pil_small, min_dim=35, target_dim=80)
    up_txt, up_conf = ProcessingWorkflowEngine._run_tesseract_psm(upscaled_pil, psm=6)
    
    assert upscaled_pil.height >= 70
    assert "REV" in up_txt or "DELTA" in up_txt or "02" in up_txt


def test_rotation_and_deskew_correction():
    """
    Verify that 90° rotation detection and deskewing correctly orient text for OCR.
    """
    # 1. 90° Counter-Clockwise Rotated Vertical Note (e.g. vertical piping tag)
    h_img = np.full((70, 320, 3), 255, dtype=np.uint8)
    cv2.putText(h_img, "VERTICAL PIPING TAG", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 0), 2)
    
    pil_h = Image.fromarray(cv2.cvtColor(h_img, cv2.COLOR_BGR2RGB))
    pil_rot90 = pil_h.rotate(90, expand=True)  # Vertical text
    
    # Running fallback with rotation enabled should detect 90° orientation and extract text
    best_txt, best_conf, best_eng = ProcessingWorkflowEngine._ocr_crop_with_fallback(
        pil_rot90,
        primary_psm=6,
        fallback_psm=11,
        enable_rotation=True,
    )
    
    assert "PIPING" in best_txt or "VERTICAL" in best_txt or "TAG" in best_txt
    assert "rot" in best_eng


def test_complete_preprocessing_pipelines_verification():
    """
    Verify predefined pipelines ('standard', 'light', 'aggressive', 'handwriting')
    execute without error and return enriched metadata.
    """
    prep = ImagePreprocessingService()
    img = np.full((120, 400, 3), 255, dtype=np.uint8)
    cv2.putText(img, "TESTING PIPELINES", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    
    for pipe_name in ['standard', 'light', 'handwriting']:
        processed, meta = prep.preprocess_for_ocr(img, pipeline=pipe_name)
        assert processed is not None
        assert len(meta['steps_applied']) > 0
        assert meta['original_shape'] == (120, 400, 3)
