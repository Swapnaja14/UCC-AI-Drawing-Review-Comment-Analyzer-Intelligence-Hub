"""
src/services/workflow_engine.py
Processing Workflow Engine orchestrating end-to-end processing steps as a Finite State Machine.
"""

import os
from pathlib import Path
from typing import Callable, Optional, List, Any, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import io
import re
import numpy as np
from datetime import datetime, timezone
import pymupdf as fitz
from PIL import Image
import pytesseract

from src.core.dtos.workflow_dtos import (
    WorkflowState,
    WorkflowStepDTO,
    WorkflowResultDTO,
    FileValidationResultDTO,
    BatchWorkflowProgressDTO,
    BatchWorkflowResultDTO
)
from src.core.exceptions.workflow_exceptions import WorkflowProcessingError
from src.services.file_service import FileService
from src.services.pdf_service import PDFService
from src.services.annotation_service_enhanced import AnnotationDetectionServiceEnhanced
from src.services.text_cleaning_service import TextCleaningService
from src.services.classification_service import ClassificationService
from src.infrastructure.storage.repository import (
    DrawingRepository,
    CommentRepository,
    AuditLogRepository,
    ProcessingRunRepository,
)
from src.infrastructure.logging.logger import get_logger

logger = get_logger("WorkflowEngine")


class ProcessingWorkflowEngine:
    """
    Finite State Machine orchestrating end-to-end engineering drawing analysis:
    Validation -> Metadata Extraction -> Annotation Detection -> OCR -> AI Classification -> Persistence.
    """

    def __init__(
        self,
        file_service: FileService,
        pdf_service: PDFService,
        drawing_repo: DrawingRepository,
        annotation_service: Optional[AnnotationDetectionServiceEnhanced] = None,
        comment_repo: Optional[CommentRepository] = None,
        text_cleaning_service: Optional[TextCleaningService] = None,
        classification_service: Optional[ClassificationService] = None,
        audit_repo: Optional[AuditLogRepository] = None,
        processing_run_repo: Optional[ProcessingRunRepository] = None,
        config: Optional[Any] = None,
    ) -> None:
        self.file_service = file_service
        self.pdf_service = pdf_service
        self.drawing_repo = drawing_repo
        self.annotation_service = annotation_service or AnnotationDetectionServiceEnhanced()
        self.comment_repo = comment_repo
        self.text_cleaning_service = text_cleaning_service or TextCleaningService()
        self.classification_service = classification_service or ClassificationService()
        self.audit_repo = audit_repo
        self.processing_run_repo = processing_run_repo
        self.config = config
        self._current_state = WorkflowState.IDLE

    def _resolve_ocr_config(self) -> tuple[int, int, float]:
        """
        Resolves (tesseract_psm, fallback_psm, confidence_threshold) from
        self.config or global AppConfig.
        Defaults: primary_psm=6, fallback_psm=11, confidence_threshold=0.50.
        """
        active_cfg = self.config
        if active_cfg is None:
            try:
                from src.config import get_config
                active_cfg = get_config()
            except Exception:
                active_cfg = None

        primary_psm = 6
        fallback_psm = 11
        conf_threshold = 0.50

        if active_cfg:
            ocr_cfg = getattr(active_cfg, "ocr", None)
            if ocr_cfg is None and isinstance(active_cfg, dict):
                ocr_cfg = active_cfg.get("ocr")
            if ocr_cfg:
                if isinstance(ocr_cfg, dict):
                    primary_psm = int(ocr_cfg.get("tesseract_psm", 6))
                    fallback_psm = int(ocr_cfg.get("fallback_psm", 11))
                    conf_threshold = float(ocr_cfg.get("confidence_threshold", 0.50))
                else:
                    primary_psm = int(getattr(ocr_cfg, "tesseract_psm", 6))
                    fallback_psm = int(getattr(ocr_cfg, "fallback_psm", 11))
                    conf_threshold = float(getattr(ocr_cfg, "confidence_threshold", 0.50))

        return primary_psm, fallback_psm, conf_threshold

    def _resolve_advanced_ocr_config(self) -> dict:
        """
        Resolves full OCR configuration parameters including dynamic PSM,
        micro-upscaling settings, and parallel region OCR worker parameters.
        """
        primary_psm, fallback_psm, conf_threshold = self._resolve_ocr_config()

        active_cfg = self.config
        if active_cfg is None:
            try:
                from src.config import get_config
                active_cfg = get_config()
            except Exception:
                active_cfg = None

        enable_micro_upscale = True
        min_upscale_dim = 35
        target_upscale_dim = 80
        parallel_region_ocr = True
        max_region_workers = 4

        if active_cfg:
            ocr_cfg = getattr(active_cfg, "ocr", None)
            if ocr_cfg is None and isinstance(active_cfg, dict):
                ocr_cfg = active_cfg.get("ocr")
            if ocr_cfg:
                if isinstance(ocr_cfg, dict):
                    enable_micro_upscale = bool(ocr_cfg.get("enable_micro_upscaling", True))
                    min_upscale_dim = int(ocr_cfg.get("micro_upscaling_min_px", 35))
                    target_upscale_dim = int(ocr_cfg.get("micro_upscaling_target_px", 80))
                    parallel_region_ocr = bool(ocr_cfg.get("parallel_region_ocr", True))
                    max_region_workers = int(ocr_cfg.get("max_region_workers", 4))
                else:
                    enable_micro_upscale = bool(getattr(ocr_cfg, "enable_micro_upscaling", True))
                    min_upscale_dim = int(getattr(ocr_cfg, "micro_upscaling_min_px", 35))
                    target_upscale_dim = int(getattr(ocr_cfg, "micro_upscaling_target_px", 80))
                    parallel_region_ocr = bool(getattr(ocr_cfg, "parallel_region_ocr", True))
                    max_region_workers = int(getattr(ocr_cfg, "max_region_workers", 4))

        return {
            "primary_psm": primary_psm,
            "fallback_psm": fallback_psm,
            "conf_threshold": conf_threshold,
            "enable_micro_upscale": enable_micro_upscale,
            "min_upscale_dim": min_upscale_dim,
            "target_upscale_dim": target_upscale_dim,
            "parallel_region_ocr": parallel_region_ocr,
            "max_region_workers": max_region_workers,
        }

    @classmethod
    def _micro_upscale_crop(
        cls,
        img: Image.Image,
        min_dim: int = 35,
        target_dim: int = 80,
    ) -> Image.Image:
        """
        Applies high-fidelity micro-upscaling (Lanczos resampling) to small engineering
        notes, dimension labels, revision deltas, or superscript callouts (< 35px)
        to boost Tesseract OCR character recognition accuracy.
        """
        if img.height <= 0 or img.width <= 0:
            return img

        min_side = min(img.width, img.height)
        if min_side < min_dim or img.height < min_dim:
            scale = max(2.0, min(float(target_dim) / max(1, min_side), 4.0))

            new_w = max(1, int(round(img.width * scale)))
            new_h = max(1, int(round(img.height * scale)))

            resample_filter = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
            upscaled = img.resize((new_w, new_h), resample=resample_filter)
            return upscaled
        return img

    @classmethod
    def _run_tesseract_psm(cls, img: Image.Image, psm: int) -> tuple[str, float]:
        """
        Executes Tesseract OCR on a PIL Image with the specified PSM mode.
        Returns:
            tuple[str, float]: (extracted_text, average_word_confidence_0_to_1)
        """
        config_str = f"--psm {psm}"
        try:
            ocr_data = pytesseract.image_to_data(
                img,
                config=config_str,
                output_type=pytesseract.Output.DICT,
            )
            raw_confs = ocr_data.get("conf", [])
            raw_words = ocr_data.get("text", [])

            # Filter non-empty words and valid confidences (Tesseract returns -1 for non-text blocks)
            valid_word_confs = [
                float(c)
                for c, t in zip(raw_confs, raw_words)
                if t.strip() and float(c) >= 0
            ]
            valid_words = [t.strip() for t in raw_words if t.strip()]

            if valid_words and any(any(ch.isalnum() for ch in w) for w in valid_words):
                text = " ".join(valid_words).strip()
                avg_conf = (
                    round(sum(valid_word_confs) / (len(valid_word_confs) * 100.0), 4)
                    if valid_word_confs
                    else 0.85
                )
                return text, avg_conf
        except Exception as data_err:
            logger.debug(f"Tesseract image_to_data failed with PSM {psm}: {data_err}")

        # Fallback to image_to_string if image_to_data fails or returns no tokens
        try:
            ocr_full = pytesseract.image_to_string(img, config=config_str).strip()
            alnum_words = [w for w in ocr_full.split() if any(c.isalnum() for c in w)]
            if alnum_words:
                return ocr_full, 0.85
        except Exception as str_err:
            logger.debug(f"Tesseract image_to_string failed with PSM {psm}: {str_err}")

        return "", 0.0

    @classmethod
    def _ocr_crop_with_fallback(
        cls,
        img: Image.Image,
        primary_psm: int = 6,
        fallback_psm: int = 11,
        conf_threshold: float = 0.50,
        engine_name: str = "tesseract",
        enable_rotation: bool = True,
        enable_micro_upscale: bool = True,
        min_upscale_dim: int = 35,
        target_upscale_dim: int = 80,
    ) -> tuple[str, float, str]:
        """
        Executes OCR on an image crop using primary_psm. If primary_psm yields
        no text or low confidence (< conf_threshold), automatically falls back
        to fallback_psm (e.g. PSM 11 for sparse text in revision clouds).

        If 0° OCR yields no text or suboptimal confidence (< 0.90), automatically
        tests 90° vertical rotations (90° CCW, 270° CW, 180° inverted) to detect
        rotated callouts, vertical margin notes, and vertical stamp annotations.

        Applies micro-upscaling for small engineering notes (< 35px) to boost
        Tesseract OCR accuracy.

        Returns:
            tuple[str, float, str]: (extracted_text, confidence, engine_name)
        """
        # Apply micro-upscaling for small engineering notes (< 35px)
        if enable_micro_upscale:
            img = cls._micro_upscale_crop(img, min_dim=min_upscale_dim, target_dim=target_upscale_dim)

        # 1. Standard 0° unrotated pass
        text_primary, conf_primary = cls._run_tesseract_psm(img, psm=primary_psm)

        has_primary_text = bool(text_primary.strip()) and any(
            any(ch.isalnum() for ch in w) for w in text_primary.split()
        )

        best_text = text_primary
        best_conf = conf_primary
        best_eng = engine_name

        # Attempt fallback PSM at 0° if primary was empty/poor and fallback_psm differs
        if fallback_psm != primary_psm and (not has_primary_text or conf_primary < conf_threshold):
            text_fallback, conf_fallback = cls._run_tesseract_psm(img, psm=fallback_psm)
            has_fallback_text = bool(text_fallback.strip()) and any(
                any(ch.isalnum() for ch in w) for w in text_fallback.split()
            )

            if not has_primary_text and has_fallback_text:
                best_text = text_fallback
                best_conf = conf_fallback
                best_eng = f"{engine_name}_psm{fallback_psm}"
            elif has_primary_text and has_fallback_text:
                words_fallback = len([w for w in text_fallback.split() if any(c.isalnum() for c in w)])
                words_primary = len([w for w in text_primary.split() if any(c.isalnum() for c in w)])

                if conf_fallback > conf_primary or (conf_fallback >= conf_primary and words_fallback > words_primary):
                    best_text = text_fallback
                    best_conf = conf_fallback
                    best_eng = f"{engine_name}_psm{fallback_psm}"

        has_best_text = bool(best_text.strip()) and any(
            any(ch.isalnum() for ch in w) for w in best_text.split()
        )
        words_best_count = len([w for w in best_text.split() if any(c.isalnum() for c in w)])
        is_good_conf_0deg = has_best_text and (words_best_count > 0) and (best_conf >= max(0.80, conf_threshold))

        # Acceptable 0° OCR (has valid words and confidence >= max(0.80, conf_threshold)) -> Fast Path return
        if is_good_conf_0deg:
            return best_text, best_conf, best_eng

        # 2. Rotated Text Pass for 90° Vertical Annotations & Callouts
        if enable_rotation:
            for angle in (90, 270, 180):
                try:
                    rot_img = img.rotate(angle, expand=True)
                    if enable_micro_upscale:
                        rot_img = cls._micro_upscale_crop(rot_img, min_dim=min_upscale_dim, target_dim=target_upscale_dim)
                    rot_text_pri, rot_conf_pri = cls._run_tesseract_psm(rot_img, psm=primary_psm)
                    has_rot_pri = bool(rot_text_pri.strip()) and any(
                        any(ch.isalnum() for ch in w) for w in rot_text_pri.split()
                    )

                    rot_cand_text = rot_text_pri
                    rot_cand_conf = rot_conf_pri
                    rot_cand_eng = f"{engine_name}_rot{angle}"

                    if (not has_rot_pri or rot_conf_pri < conf_threshold) and fallback_psm != primary_psm:
                        rot_text_fb, rot_conf_fb = cls._run_tesseract_psm(rot_img, psm=fallback_psm)
                        has_rot_fb = bool(rot_text_fb.strip()) and any(
                            any(ch.isalnum() for ch in w) for w in rot_text_fb.split()
                        )
                        if not has_rot_pri and has_rot_fb:
                            rot_cand_text = rot_text_fb
                            rot_cand_conf = rot_conf_fb
                            rot_cand_eng = f"{engine_name}_rot{angle}_psm{fallback_psm}"
                        elif has_rot_pri and has_rot_fb and rot_conf_fb > rot_conf_pri:
                            rot_cand_text = rot_text_fb
                            rot_cand_conf = rot_conf_fb
                            rot_cand_eng = f"{engine_name}_rot{angle}_psm{fallback_psm}"

                    has_rot_cand = bool(rot_cand_text.strip()) and any(
                        any(ch.isalnum() for ch in w) for w in rot_cand_text.split()
                    )
                    if not has_rot_cand:
                        continue

                    words_rot = len([w for w in rot_cand_text.split() if any(c.isalnum() for c in w)])
                    words_best = len([w for w in best_text.split() if any(c.isalnum() for c in w)])

                    if not has_best_text and has_rot_cand:
                        best_text = rot_cand_text
                        best_conf = rot_cand_conf
                        best_eng = rot_cand_eng
                        has_best_text = True
                        logger.debug(f"Rotated text detection ({angle}°) rescued unreadable crop: '{best_text}' ({best_conf:.2f})")
                        if rot_cand_conf >= 0.85:
                            break
                    elif has_best_text and has_rot_cand:
                        # Prefer rotated if higher confidence, more valid words, or rescuing non-word noise
                        if rot_cand_conf > best_conf + 0.10 or (rot_cand_conf >= best_conf and words_rot > words_best) or (words_rot > 0 and words_best == 0 and rot_cand_conf >= 0.40):
                            best_text = rot_cand_text
                            best_conf = rot_cand_conf
                            best_eng = rot_cand_eng
                            logger.debug(f"Rotated text detection ({angle}°) improved crop text: '{best_text}' ({best_conf:.2f})")
                            if rot_cand_conf >= 0.85:
                                break
                except Exception as rot_err:
                    logger.debug(f"Rotated OCR pass ({angle}°) failed: {rot_err}")

        return best_text, best_conf, best_eng

    def _process_single_region_ocr(
        self,
        p_obj: fitz.Page,
        reg: Any,
        p_idx: int,
        page_envs: Any,
        primary_psm: int = 6,
        fallback_psm: int = 11,
        psm_conf_threshold: float = 0.50,
        enable_rotation: bool = True,
        enable_micro_upscale: bool = True,
        min_upscale_dim: int = 35,
        target_upscale_dim: int = 80,
    ) -> Optional[dict]:
        """
        Extracts, OCRs, filters, and cleans comment text for a single detected region.
        Returns extracted comment dictionary or None if filtered out.
        """
        pad = 4.0
        crop_rect = fitz.Rect(
            max(0.0, reg.x0 - pad),
            max(0.0, reg.y0 - pad),
            min(p_obj.rect.width, reg.x1 + pad),
            min(p_obj.rect.height, reg.y1 + pad),
        )

        # Convert visual crop_rect to unrotated clip for PyMuPDF text & annot APIs
        if p_obj.rotation != 0:
            crop_unrot = crop_rect * p_obj.derotation_matrix
            unrot_clip = fitz.Rect(
                min(crop_unrot.x0, crop_unrot.x1),
                min(crop_unrot.y0, crop_unrot.y1),
                max(crop_unrot.x0, crop_unrot.x1),
                max(crop_unrot.y0, crop_unrot.y1),
            )
        else:
            unrot_clip = crop_rect

        # Strictly filter out Title Blocks and Review Status Stamps
        if AnnotationDetectionServiceEnhanced._is_title_block_or_status_stamp(p_obj, crop_rect, envelopes=page_envs):
            return None

        raw_ocr_text = ""
        ocr_conf = 0.95
        ocr_engine = "native"

        # 1. Check for native annotation content (FreeText callouts, Stamps, Notes)
        try:
            for annot in p_obj.annots():
                if annot.rect.intersects(unrot_clip):
                    c_text = (annot.info.get("content") or "").strip()
                    if len(c_text) >= 3 and not (len(c_text) <= 2 and c_text.upper() in ["A", "B", "C", "D", "E", "F", "G", "H", "1", "2", "3", "4", "5", "6", "7", "8"]):
                        raw_ocr_text = c_text
                        ocr_conf = 0.99
                        ocr_engine = "native_annot"
                        break
        except Exception:
            raw_ocr_text = ""

        # 2. Check for targeted colored spans (Red, Blue, or Green reviewer markup text)
        if not raw_ocr_text:
            try:
                colored_spans_text = []
                annot_text_dict = p_obj.get_text("dict", clip=unrot_clip)
                for b in annot_text_dict.get("blocks", []):
                    if b.get("type") == 0:
                        for l in b.get("lines", []):
                            for s in l.get("spans", []):
                                txt = s.get("text", "").strip()
                                if not txt:
                                    continue
                                color = s.get("color", 0)
                                sr = (color >> 16) & 0xFF
                                sg = (color >> 8) & 0xFF
                                sb = color & 0xFF

                                is_red = AnnotationDetectionServiceEnhanced._is_red_rgb(sr, sg, sb)
                                is_blue = AnnotationDetectionServiceEnhanced._is_blue_rgb(sr, sg, sb)
                                is_green = AnnotationDetectionServiceEnhanced._is_green_rgb(sr, sg, sb)

                                if is_red or is_blue or is_green:
                                    colored_spans_text.append(txt)

                if colored_spans_text:
                    raw_ocr_text = " ".join(colored_spans_text)
                    ocr_conf = 0.98
                    ocr_engine = "pymupdf_native"
            except Exception:
                raw_ocr_text = ""

        # 3. Check for enclosed digital text inside revision clouds and redline markups
        if not raw_ocr_text:
            try:
                enclosed_digital_text = p_obj.get_text("text", clip=unrot_clip).strip()
                if enclosed_digital_text:
                    clean_candidate = " ".join(enclosed_digital_text.split())
                    cand_words = [w for w in clean_candidate.split() if any(c.isalnum() for c in w)]
                    if len(cand_words) > 0 and not (len(clean_candidate) <= 2 and clean_candidate.upper() in [
                        "A", "B", "C", "D", "E", "F", "G", "H", "1", "2", "3", "4", "5", "6", "7", "8", ".", "-"
                    ]):
                        raw_ocr_text = clean_candidate
                        ocr_conf = 0.95
                        ocr_engine = "pymupdf_digital"
            except Exception:
                raw_ocr_text = ""

        # 4. Fall back to high-resolution OCR (for scanned drawings, clouds & handwriting)
        if not raw_ocr_text and crop_rect.width > 2 and crop_rect.height > 2:
            try:
                zoom = 200.0 / 72.0
                mat = fitz.Matrix(zoom, zoom)
                pix = p_obj.get_pixmap(matrix=mat, clip=crop_rect)
                if pix.width > 0 and pix.height > 0:
                    img_bytes = pix.tobytes("png")
                    pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                    np_img = np.array(pil_img)

                    # Fast variance/contrast check: skip Tesseract if image lacks text contrast
                    gray_arr = np.mean(np_img, axis=2)
                    if float(np.std(gray_arr)) >= 6.0:
                        crop_text, crop_conf, crop_eng = self._ocr_crop_with_fallback(
                            pil_img,
                            primary_psm=primary_psm,
                            fallback_psm=fallback_psm,
                            conf_threshold=psm_conf_threshold,
                            engine_name="tesseract",
                            enable_rotation=enable_rotation,
                            enable_micro_upscale=enable_micro_upscale,
                            min_upscale_dim=min_upscale_dim,
                            target_upscale_dim=target_upscale_dim,
                        )
                        if crop_text:
                            raw_ocr_text = crop_text
                            ocr_conf = crop_conf
                            ocr_engine = crop_eng

                        # If still no text or low confidence, try color-isolated OCR if colored pixels exist
                        if not raw_ocr_text or ocr_conf < psm_conf_threshold:
                            nr = np_img[:, :, 0].astype(int)
                            ng = np_img[:, :, 1].astype(int)
                            nb = np_img[:, :, 2].astype(int)

                            mask_red = (nr >= 120) & ((nr - np.maximum(ng, nb)) >= 24)
                            mask_blue = (nb >= 110) & ((nb - np.maximum(nr, ng)) >= 24)
                            mask_green = (ng >= 100) & ((ng - np.maximum(nr, nb)) >= 24)
                            colored_mask = mask_red | mask_blue | mask_green

                            if np.count_nonzero(colored_mask) >= 15:
                                ocr_input_arr = np.full((np_img.shape[0], np_img.shape[1]), 255, dtype=np.uint8)
                                ocr_input_arr[colored_mask] = 0
                                ocr_input_pil = Image.fromarray(ocr_input_arr)

                                iso_text, iso_conf, iso_eng = self._ocr_crop_with_fallback(
                                    ocr_input_pil,
                                    primary_psm=primary_psm,
                                    fallback_psm=fallback_psm,
                                    conf_threshold=psm_conf_threshold,
                                    engine_name="tesseract_color_isolated",
                                    enable_rotation=enable_rotation,
                                    enable_micro_upscale=enable_micro_upscale,
                                    min_upscale_dim=min_upscale_dim,
                                    target_upscale_dim=target_upscale_dim,
                                )
                                if iso_text and (not raw_ocr_text or iso_conf > ocr_conf):
                                    raw_ocr_text = iso_text
                                    ocr_conf = iso_conf
                                    ocr_engine = iso_eng
            except Exception as ocr_err:
                logger.debug(f"OCR failed for region {reg}: {ocr_err}")
                raw_ocr_text = ""

        # Filter out single/small letter fragments, noise, and title block boilerplate
        clean_text_check = raw_ocr_text.strip().upper()
        words = [w for w in clean_text_check.split() if any(c.isalnum() for c in w)]
        det_conf = round(float(getattr(reg, "confidence", 0.90)), 4)
        if len(words) == 0:
            if det_conf >= 0.70:
                failed_placeholder = "OCR Failed (Needs Manual Transcription)"
                return {
                    "page_number": p_idx + 1,
                    "raw_text": failed_placeholder,
                    "cleaned_text": failed_placeholder,
                    "bbox": (reg.x0, reg.y0, reg.x1, reg.y1),
                    "detection_confidence": det_conf,
                    "ocr_confidence": 0.0,
                    "classification_confidence": 0.0,
                    "confidence": 0.0,
                    "ocr_engine": "OCR Failed",
                    "category_name": "Uncategorized",
                    "label": reg.label,
                    "status": "Flagged",
                    "is_ocr_failed": True,
                }
            return None

        if any(phrase in clean_text_check for phrase in AnnotationDetectionServiceEnhanced.TITLE_BLOCK_PHRASES):
            return None
        if re.match(r"^(BY\s+[A-Z0-9_]+|DATE\s+[0-9\/\-]+|EXP[\.\:\s]+[0-9\/\-]+)$", clean_text_check):
            return None
        tb_label_hits = sum(1 for label in AnnotationDetectionServiceEnhanced.TITLE_BLOCK_FIELD_LABELS if re.search(r"\b" + re.escape(label) + r"\b", clean_text_check))
        if tb_label_hits >= 2:
            return None
        if len(clean_text_check) <= 2 and clean_text_check in [
            "A", "B", "C", "D", "E", "F", "G", "H", "1", "2", "3", "4", "5", "6", "7", "8", ".", "-"
        ]:
            return None

        cleaned_dto = self.text_cleaning_service.clean_text(raw_ocr_text)
        final_text = cleaned_dto.cleaned_text or raw_ocr_text

        return {
            "page_number": p_idx + 1,
            "raw_text": raw_ocr_text,
            "cleaned_text": final_text,
            "bbox": (reg.x0, reg.y0, reg.x1, reg.y1),
            "detection_confidence": det_conf,
            "ocr_confidence": ocr_conf,
            "classification_confidence": 0.0,
            "confidence": ocr_conf,
            "ocr_engine": ocr_engine,
            "label": reg.label,
            "is_ocr_failed": False,
        }

    @property
    def current_state(self) -> WorkflowState:
        return self._current_state

    def execute_workflow(
        self,
        file_path: Path,
        progress_callback: Optional[Callable[[WorkflowStepDTO], None]] = None,
        department_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> WorkflowResultDTO:
        """
        Executes complete multi-step processing workflow for an engineering drawing PDF.

        Args:
            file_path: Path to drawing PDF file.
            progress_callback: Optional callback function receiving WorkflowStepDTO snapshots.
            department_id: Optional engineering department ID selected during upload.
            project_id: Optional project ID to associate drawing and run with.

        Returns:
            WorkflowResultDTO: Summary result of completed processing pipeline.

        Raises:
            WorkflowProcessingError: If any pipeline step fails.
        """
        start_time = time.time()
        path = Path(file_path).resolve()
        original_file_name = path.name
        logger.info(f"Starting processing workflow execution for: {original_file_name} (department_id={department_id}, project_id={project_id})")

        run_record = None
        if hasattr(self, "processing_run_repo") and self.processing_run_repo:
            try:
                run_record = self.processing_run_repo.create_processing_run(
                    file_name=original_file_name,
                    project_id=project_id,
                    status="PROCESSING",
                    started_at=datetime.now(timezone.utc),
                )
            except Exception as ex_run:
                logger.warning(f"Could not create processing run record: {ex_run}")

        def notify(step_name: str, state: WorkflowState, pct: int, msg: str):
            self._current_state = state
            snapshot = WorkflowStepDTO(
                step_name=step_name,
                state=state,
                progress_percentage=pct,
                message=msg,
                started_at=datetime.now(timezone.utc)
            )
            logger.info(f"Workflow [{pct}%] {step_name}: {msg}")
            if progress_callback:
                progress_callback(snapshot)

        try:
            # ── Step 1: File Validation ───────────────────────────
            notify("File Validation", WorkflowState.FILE_VALIDATING, 10, f"Validating '{original_file_name}' size and extension.")
            val_result: FileValidationResultDTO = self.file_service.validate_pdf_file(path)
            if not val_result.is_valid:
                raise WorkflowProcessingError(val_result.error_message or "File validation failed.")

            # Copy uploaded PDF to managed application storage for persistence
            path = self.file_service.copy_to_managed_storage(path)

            # ── Step 2: Metadata Extraction ──────────────────────
            notify("Metadata Extraction", WorkflowState.METADATA_EXTRACTING, 30, f"Extracting page metrics and PDF structure.")
            doc_dto = self.pdf_service.process_pdf_document(path)

            # ── Step 3: Annotation Region Detection ─────────────
            notify("Annotation Detection", WorkflowState.ANNOTATION_DETECTING, 50, 
                   f"Detecting drawing callout boxes and redline regions.")
            
            annotation_result = None
            total_regions = 0
            try:
                def on_page_progress(completed: int, total: int):
                    pct = 50 + int((completed / max(1, total)) * 18)
                    notify("Annotation Detection", WorkflowState.ANNOTATION_DETECTING, pct, 
                           f"Detecting drawing callout boxes and redline regions ({completed}/{total} pages).")

                annotation_result = self.annotation_service.detect_all_pages(path, method='hybrid', progress_callback=on_page_progress)
                total_regions = annotation_result.total_regions
                
                logger.info(f"Annotation detection complete: {total_regions} regions detected across {annotation_result.total_pages} pages")
                
            except Exception as e:
                logger.error(f"Annotation detection failed: {e}. Continuing without annotations.")
                total_regions = 0

            # ── Step 4: OCR & Text Extraction on Detected Regions ─
            notify("OCR Engine", WorkflowState.OCR_PROCESSING, 70, f"Extracting whole comment text from detected markup regions.")
            
            # Resolve OCR configuration parameters from AppConfig (Dynamic PSM, Micro-Upscaling, Parallel OCR)
            ocr_settings = self._resolve_advanced_ocr_config()
            primary_psm = ocr_settings["primary_psm"]
            fallback_psm = ocr_settings["fallback_psm"]
            psm_conf_threshold = ocr_settings["conf_threshold"]
            enable_micro_upscale = ocr_settings["enable_micro_upscale"]
            min_upscale_dim = ocr_settings["min_upscale_dim"]
            target_upscale_dim = ocr_settings["target_upscale_dim"]
            parallel_region_ocr = ocr_settings["parallel_region_ocr"]
            max_region_workers = ocr_settings["max_region_workers"]

            extracted_comments_data = []
            if annotation_result and annotation_result.page_results:
                try:
                    pdf_doc = fitz.open(path)
                    for page_res in annotation_result.page_results:
                        p_idx = page_res.page_number
                        if p_idx < 0 or p_idx >= len(pdf_doc):
                            continue
                        p_obj = pdf_doc[p_idx]
                        
                        # Cache title block and review status stamp envelopes ONCE per page
                        page_envs = AnnotationDetectionServiceEnhanced._get_title_block_and_stamp_envelopes(p_obj)
                        
                        candidate_regions = []
                        for reg in page_res.regions:
                            # Prioritize reviewer comments and colored markups (red, blue, green)
                            is_comment_markup = (
                                "red" in reg.label.lower() or
                                "blue" in reg.label.lower() or
                                "green" in reg.label.lower() or
                                "yellow" in reg.label.lower() or
                                reg.label in ("native_annotation", "native_text_block", "native_freetext", "native_ink", "native_redline")
                            )
                            if is_comment_markup:
                                candidate_regions.append(reg)

                        if not candidate_regions:
                            continue

                        if parallel_region_ocr and len(candidate_regions) > 1:
                            # Multi-Comment Page: Parallel Region OCR execution across worker pool
                            def _worker_task(item):
                                reg_idx, reg = item
                                try:
                                    with fitz.open(path) as local_doc:
                                        local_page = local_doc[p_idx]
                                        res = self._process_single_region_ocr(
                                            local_page,
                                            reg,
                                            p_idx,
                                            page_envs,
                                            primary_psm=primary_psm,
                                            fallback_psm=fallback_psm,
                                            psm_conf_threshold=psm_conf_threshold,
                                            enable_rotation=True,
                                            enable_micro_upscale=enable_micro_upscale,
                                            min_upscale_dim=min_upscale_dim,
                                            target_upscale_dim=target_upscale_dim,
                                        )
                                        return reg_idx, res
                                except Exception as reg_exc:
                                    logger.debug(f"Parallel OCR worker failed for region {reg}: {reg_exc}")
                                    return reg_idx, None

                            num_workers = min(max_region_workers, len(candidate_regions))
                            with ThreadPoolExecutor(max_workers=num_workers) as pool:
                                worker_results = list(pool.map(_worker_task, enumerate(candidate_regions)))

                            # Maintain original region sequence
                            for reg_idx, res_item in sorted(worker_results, key=lambda x: x[0]):
                                if res_item is not None:
                                    extracted_comments_data.append(res_item)
                        else:
                            # Sequential execution for single-comment or non-parallel mode
                            for reg in candidate_regions:
                                res_item = self._process_single_region_ocr(
                                    p_obj,
                                    reg,
                                    p_idx,
                                    page_envs,
                                    primary_psm=primary_psm,
                                    fallback_psm=fallback_psm,
                                    psm_conf_threshold=psm_conf_threshold,
                                    enable_rotation=True,
                                    enable_micro_upscale=enable_micro_upscale,
                                    min_upscale_dim=min_upscale_dim,
                                    target_upscale_dim=target_upscale_dim,
                                )
                                if res_item is not None:
                                    extracted_comments_data.append(res_item)

                    pdf_doc.close()
                except Exception as e:
                    logger.error(f"OCR processing failed: {e}")

            # Deduplicate extracted comments on the same page
            deduped_comments = []
            for item in extracted_comments_data:
                p_num = item["page_number"]
                b = item["bbox"]
                t = (item.get("cleaned_text") or item.get("raw_text") or "").strip().upper()
                
                merged = False
                for kept in deduped_comments:
                    if kept["page_number"] != p_num:
                        continue
                    kb = kept["bbox"]
                    kt = (kept.get("cleaned_text") or kept.get("raw_text") or "").strip().upper()
                    
                    # Calculate spatial overlap between b and kb
                    xi_min = max(b[0], kb[0])
                    yi_min = max(b[1], kb[1])
                    xi_max = min(b[2], kb[2])
                    yi_max = min(b[3], kb[3])
                    inter_w = max(0.0, xi_max - xi_min)
                    inter_h = max(0.0, yi_max - yi_min)
                    inter_area = inter_w * inter_h
                    
                    b_area = max(1.0, (b[2] - b[0]) * (b[3] - b[1]))
                    kb_area = max(1.0, (kb[2] - kb[0]) * (kb[3] - kb[1]))
                    iou = inter_area / (b_area + kb_area - inter_area) if (b_area + kb_area - inter_area) > 0 else 0.0
                    containment = inter_area / min(b_area, kb_area)
                    
                    # If same text nearby OR strong spatial overlap
                    same_text = (t == kt or t in kt or kt in t) and (abs(b[0] - kb[0]) < 60 and abs(b[1] - kb[1]) < 60)
                    if same_text or iou > 0.35 or containment > 0.60:
                        kept["bbox"] = (min(b[0], kb[0]), min(b[1], kb[1]), max(b[2], kb[2]), max(b[3], kb[3]))
                        item_is_failed = item.get("is_ocr_failed", False) or "OCR Failed" in str(item.get("raw_text", ""))
                        kept_is_failed = kept.get("is_ocr_failed", False) or "OCR Failed" in str(kept.get("raw_text", ""))

                        if kept_is_failed and not item_is_failed:
                            kept["raw_text"] = item["raw_text"]
                            kept["cleaned_text"] = item["cleaned_text"]
                            kept["is_ocr_failed"] = False
                            kept["ocr_engine"] = item.get("ocr_engine", "Tesseract OCR")
                            kept["ocr_confidence"] = item.get("ocr_confidence", 0.0)
                        elif not kept_is_failed and not item_is_failed:
                            if len(item.get("cleaned_text", "")) > len(kept.get("cleaned_text", "")):
                                kept["raw_text"] = item["raw_text"]
                                kept["cleaned_text"] = item["cleaned_text"]

                        kept["confidence"] = max(kept["confidence"], item["confidence"])
                        kept["detection_confidence"] = max(kept.get("detection_confidence", 0.0), item.get("detection_confidence", 0.0))
                        if not kept.get("is_ocr_failed", False):
                            kept["ocr_confidence"] = max(kept.get("ocr_confidence", 0.0), item.get("ocr_confidence", 0.0))
                        merged = True
                        break
                        
                if not merged:
                    deduped_comments.append(item)
            extracted_comments_data = deduped_comments

            # Establish drawing ID and effective department before classification
            db_record = self.drawing_repo.save_drawing_from_dto(doc_dto, project_id=project_id, department_id=department_id)
            drawing_id = db_record.get("id", "DWG-000")
            effective_dept_id = db_record.get("department_id") or department_id
            resolved_proj_id = db_record.get("project_id")

            if run_record and self.processing_run_repo:
                try:
                    self.processing_run_repo.update_processing_run(
                        run_id=run_record["id"],
                        drawing_id=drawing_id,
                        project_id=resolved_proj_id,
                    )
                except Exception as ex_upd:
                    logger.warning(f"Could not update processing run IDs: {ex_upd}")

            # ── Step 5: Batched AI Category Classification ─────────
            notify("AI Classification", WorkflowState.AI_CLASSIFYING, 90, f"Classifying review comments with AI.")
            
            if extracted_comments_data:
                valid_items = [
                    item for item in extracted_comments_data
                    if not item.get("is_ocr_failed") and "OCR Failed" not in str(item.get("raw_text", ""))
                ]
                failed_items = [
                    item for item in extracted_comments_data
                    if item.get("is_ocr_failed") or "OCR Failed" in str(item.get("raw_text", ""))
                ]
                for item in failed_items:
                    item["category_name"] = "Uncategorized"
                    item["classification_confidence"] = 0.0
                    item["fallback_used"] = False
                    item["classification_method"] = "manual_transcription_required"
                    item["confidence"] = 0.0
                    item["ocr_confidence"] = 0.0

                if valid_items:
                    texts_to_classify = [
                        item.get("cleaned_text") or item.get("raw_text", "")
                        for item in valid_items
                    ]
                    try:
                        batch_dto = self.classification_service.classify_batch(
                            texts_to_classify,
                            drawing_id=drawing_id,
                            department_name=effective_dept_id,
                        )
                        class_results = batch_dto.results
                        for item, class_res in zip(valid_items, class_results):
                            item["category_name"] = class_res.primary_category.category_name
                            cat_conf = round(float(class_res.primary_category.confidence), 4)
                            item["classification_confidence"] = cat_conf
                            item["fallback_used"] = getattr(class_res, "fallback_used", False)
                            item["classification_method"] = getattr(class_res, "classification_method", "ai_model")
                            det_c = float(item.get("detection_confidence", 0.90))
                            ocr_c = float(item.get("ocr_confidence", 0.90))
                            # Balanced composite confidence retaining true separation
                            item["confidence"] = round(min(0.99, det_c * 0.20 + ocr_c * 0.40 + cat_conf * 0.40), 2)
                    except Exception as batch_err:
                        logger.warning(f"Batched classification failed, falling back to item-by-item: {batch_err}")
                        for item in valid_items:
                            try:
                                text_to_classify = item.get("cleaned_text") or item.get("raw_text", "")
                                class_res = self.classification_service.classify_comment(
                                    text_to_classify,
                                    department_name=effective_dept_id,
                                )
                                item["category_name"] = class_res.primary_category.category_name
                                cat_conf = round(float(class_res.primary_category.confidence), 4)
                                item["classification_confidence"] = cat_conf
                                item["fallback_used"] = getattr(class_res, "fallback_used", False)
                                item["classification_method"] = getattr(class_res, "classification_method", "ai_model")
                                det_c = float(item.get("detection_confidence", 0.90))
                                ocr_c = float(item.get("ocr_confidence", 0.90))
                                item["confidence"] = round(min(0.99, det_c * 0.20 + ocr_c * 0.40 + cat_conf * 0.40), 2)
                            except Exception as class_err:
                                logger.debug(f"Classification failed for '{item.get('raw_text')}': {class_err}")
                                item["category_name"] = "Uncategorized"
                                item["classification_confidence"] = 0.0
                                item["fallback_used"] = True
                                item["classification_method"] = "error_fallback"

            # ── Step 6: Database Persistence ─────────────────────
            notify("Data Persistence", WorkflowState.PERSISTING, 95, f"Saving drawing records to SQLite database.")

            if self.comment_repo and extracted_comments_data:
                try:
                    self.comment_repo.delete_comments_for_drawing(drawing_id)
                except Exception as del_err:
                    logger.debug(f"Error clearing previous comments: {del_err}")
                page_counters: Dict[int, int] = {}
                for c_item in extracted_comments_data:
                    try:
                        p_num = c_item.get("page_number", 1)
                        page_counters[p_num] = page_counters.get(p_num, 0) + 1
                        seq = page_counters[p_num]
                        dwg_suffix = drawing_id.replace("DWG-", "")[:6] if drawing_id else uuid.uuid4().hex[:6].upper()
                        assigned_cid = f"CMT-{dwg_suffix}-P{p_num}-{seq:02d}"

                        conf = c_item.get("confidence", 0.0)
                        det_c = float(c_item.get("detection_confidence", conf))
                        ocr_c = float(c_item.get("ocr_confidence", conf))
                        cat_c = float(c_item.get("classification_confidence", conf))
                        fb_used = bool(c_item.get("fallback_used", False))
                        class_m = str(c_item.get("classification_method", "ai_model"))
                        c_text = c_item.get("cleaned_text") or c_item.get("raw_text", "")

                        auto_approve = True
                        auto_threshold = 0.85
                        try:
                            cfg = self.config
                            if cfg is None:
                                from src.config import get_config
                                cfg = get_config()
                            if cfg and hasattr(cfg, "ai"):
                                auto_approve = getattr(cfg.ai, "auto_approve_high_confidence", True)
                                auto_threshold = getattr(cfg.ai, "auto_approve_threshold", 0.85)
                        except Exception:
                            pass

                        from src.services.auto_approval_policy import evaluate_auto_approval
                        should_approve, approve_reason = evaluate_auto_approval(
                            ocr_confidence=ocr_c,
                            classification_confidence=cat_c,
                            text=c_text,
                            fallback_used=fb_used,
                            classification_method=class_m,
                            auto_approve_enabled=auto_approve,
                            threshold=auto_threshold,
                        )

                        is_failed_cmt = (
                            c_item.get("is_ocr_failed", False) or
                            "OCR Failed" in str(c_item.get("raw_text", ""))
                        )
                        if is_failed_cmt:
                            initial_status = "Flagged"
                        else:
                            initial_status = "Approved" if should_approve else "Pending"

                        saved_c = self.comment_repo.save_comment(
                            drawing_id=drawing_id,
                            page_number=p_num,
                            raw_text=c_item["raw_text"],
                            cleaned_text=c_item.get("cleaned_text", ""),
                            bbox=c_item["bbox"],
                            confidence=float(conf),
                            detection_confidence=det_c,
                            ocr_confidence=ocr_c,
                            classification_confidence=cat_c,
                            classification_method=class_m,
                            fallback_used=fb_used,
                            ocr_engine=c_item.get("ocr_engine", "OCR Failed" if is_failed_cmt else "Tesseract OCR"),
                            category_name=c_item.get("category_name", "Uncategorized"),
                            department_id=effective_dept_id,
                            label=c_item.get("label", "comment_red"),
                            status=initial_status,
                            comment_id=assigned_cid,
                        )

                        if initial_status == "Approved" and self.audit_repo and saved_c:
                            try:
                                self.audit_repo.create_audit_entry(
                                    comment_id=saved_c.get("id"),
                                    action="APPROVE",
                                    reviewer_id="system_ai",
                                    reviewer_name="AI Auto-Approval",
                                    old_value="Pending",
                                    new_value="Approved",
                                    notes=f"Auto-approved by AI ({approve_reason})",
                                )
                            except Exception as audit_err:
                                logger.debug(f"Auto-approve audit log error: {audit_err}")
                    except Exception as save_err:
                        logger.error(f"Error persisting comment {c_item}: {save_err}")

            # ── Workflow Complete ──────────────────────────────────
            duration = round(time.time() - start_time, 2)
            total_saved = len(extracted_comments_data)
            notify("Workflow Complete", WorkflowState.COMPLETED, 100, f"Successfully processed '{original_file_name}' in {duration}s.")

            if run_record and self.processing_run_repo:
                try:
                    self.processing_run_repo.update_processing_run(
                        run_id=run_record["id"],
                        status="COMPLETED",
                        completed_at=datetime.now(timezone.utc),
                        duration_seconds=duration,
                        drawing_id=drawing_id,
                        project_id=resolved_proj_id,
                    )
                except Exception as ex_comp:
                    logger.warning(f"Could not complete processing run: {ex_comp}")

            return WorkflowResultDTO(
                drawing_id=drawing_id,
                file_name=original_file_name,
                total_pages=doc_dto.total_pages,
                is_scanned=doc_dto.is_scanned,
                status="Completed",
                total_comments_found=total_saved if total_saved > 0 else total_regions,
                processing_duration_seconds=duration,
                annotation_result=annotation_result,
            )

        except Exception as e:
            self._current_state = WorkflowState.FAILED
            duration = round(time.time() - start_time, 2)
            if run_record and self.processing_run_repo:
                try:
                    self.processing_run_repo.update_processing_run(
                        run_id=run_record["id"],
                        status="FAILED",
                        completed_at=datetime.now(timezone.utc),
                        duration_seconds=duration,
                        error_message=str(e),
                    )
                except Exception as ex_fail:
                    logger.warning(f"Could not record failed processing run: {ex_fail}")
            err_msg = f"Workflow failed for '{original_file_name}': {e}"
            logger.error(err_msg)
            notify("Workflow Failure", WorkflowState.FAILED, 0, err_msg)
            raise WorkflowProcessingError(err_msg) from e

    def execute_batch_workflow(
        self,
        file_paths: List[str | Path],
        progress_callback: Optional[Callable[[BatchWorkflowProgressDTO], None]] = None,
        department_id: Optional[str] = None,
    ) -> BatchWorkflowResultDTO:
        """
        Executes complete processing workflow across a batch of PDF drawings or extracted zip files.

        Args:
            file_paths: List of file paths (PDF files or .zip folders).
            progress_callback: Optional callback receiving BatchWorkflowProgressDTO.
            department_id: Optional engineering department ID.

        Returns:
            BatchWorkflowResultDTO summary.
        """
        batch_start_time = time.time()
        
        # Expand zip files into PDF file paths
        resolved_pdfs = self.file_service.expand_file_sources(file_paths)
        total_files = len(resolved_pdfs)

        if total_files == 0:
            logger.warning("execute_batch_workflow called with no valid PDF files resolved.")
            return BatchWorkflowResultDTO(
                total_files_processed=0,
                successful_files_count=0,
                failed_files_count=0,
                total_comments_found=0,
                total_duration_seconds=0.0,
                results=[],
                failed_files=[]
            )

        logger.info(f"Starting batch workflow execution for {total_files} file(s) (department_id={department_id})")

        successful_results: List[WorkflowResultDTO] = []
        failed_records: List[Dict[str, str]] = []
        total_comments = 0

        num_workers = min(6, max(1, os.cpu_count() or 2))
        if total_files == 1 or num_workers == 1:
            for idx, pdf_path in enumerate(resolved_pdfs, start=1):
                file_name = pdf_path.name

                def _on_single_step(step_dto: WorkflowStepDTO):
                    single_pct = step_dto.progress_percentage
                    overall_pct = int(((idx - 1) / total_files * 100) + (single_pct / total_files))
                    overall_pct = max(0, min(100, overall_pct))

                    batch_snapshot = BatchWorkflowProgressDTO(
                        overall_progress_percentage=overall_pct,
                        current_file_index=idx,
                        total_files=total_files,
                        current_file_name=file_name,
                        step_snapshot=step_dto
                    )
                    if progress_callback:
                        progress_callback(batch_snapshot)

                try:
                    result = self.execute_workflow(
                        pdf_path,
                        progress_callback=_on_single_step,
                        department_id=department_id
                    )
                    successful_results.append(result)
                    total_comments += result.total_comments_found
                except Exception as exc:
                    logger.error(f"Batch item {idx}/{total_files} ('{file_name}') failed: {exc}")
                    failed_records.append({
                        "file_name": file_name,
                        "error": str(exc)
                    })
        else:
            # Parallel execution across CPU cores for maximum speed
            results_map = {}
            completed_count = 0
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                future_to_file = {
                    executor.submit(
                        self.execute_workflow,
                        pdf_p,
                        department_id=department_id
                    ): (i, pdf_p)
                    for i, pdf_p in enumerate(resolved_pdfs, start=1)
                }
                for future in as_completed(future_to_file):
                    i, pdf_p = future_to_file[future]
                    file_name = pdf_p.name
                    completed_count += 1
                    overall_pct = int((completed_count / total_files) * 100)

                    try:
                        res = future.result()
                        results_map[i] = res
                        total_comments += res.total_comments_found

                        if progress_callback:
                            step_snapshot = WorkflowStepDTO(
                                step_name="Complete",
                                state=WorkflowState.COMPLETED,
                                progress_percentage=100,
                                message=f"Processed '{file_name}' ({res.total_comments_found} comments)"
                            )
                            batch_snapshot = BatchWorkflowProgressDTO(
                                overall_progress_percentage=overall_pct,
                                current_file_index=completed_count,
                                total_files=total_files,
                                current_file_name=file_name,
                                step_snapshot=step_snapshot
                            )
                            progress_callback(batch_snapshot)
                    except Exception as exc:
                        logger.error(f"Batch item {i}/{total_files} ('{file_name}') failed: {exc}")
                        failed_records.append({
                            "file_name": file_name,
                            "error": str(exc)
                        })

            for i in sorted(results_map.keys()):
                successful_results.append(results_map[i])

        total_duration = round(time.time() - batch_start_time, 2)
        logger.info(
            f"Batch workflow complete: {len(successful_results)}/{total_files} succeeded, "
            f"{len(failed_records)} failed in {total_duration}s."
        )

        return BatchWorkflowResultDTO(
            total_files_processed=total_files,
            successful_files_count=len(successful_results),
            failed_files_count=len(failed_records),
            total_comments_found=total_comments,
            total_duration_seconds=total_duration,
            results=successful_results,
            failed_files=failed_records
        )

