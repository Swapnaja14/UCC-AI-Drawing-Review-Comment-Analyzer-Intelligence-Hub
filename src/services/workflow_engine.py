"""
src/services/workflow_engine.py
Processing Workflow Engine orchestrating end-to-end processing steps as a Finite State Machine.
"""

from pathlib import Path
from typing import Callable, Optional, List
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
    FileValidationResultDTO
)
from src.core.exceptions.workflow_exceptions import WorkflowProcessingError
from src.services.file_service import FileService
from src.services.pdf_service import PDFService
from src.services.annotation_service_enhanced import AnnotationDetectionServiceEnhanced
from src.services.text_cleaning_service import TextCleaningService
from src.services.classification_service import ClassificationService
from src.infrastructure.storage.repository import DrawingRepository, CommentRepository, AuditLogRepository
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
    ) -> None:
        self.file_service = file_service
        self.pdf_service = pdf_service
        self.drawing_repo = drawing_repo
        self.annotation_service = annotation_service or AnnotationDetectionServiceEnhanced()
        self.comment_repo = comment_repo
        self.text_cleaning_service = text_cleaning_service or TextCleaningService()
        self.classification_service = classification_service or ClassificationService()
        self.audit_repo = audit_repo
        self._current_state = WorkflowState.IDLE

    @property
    def current_state(self) -> WorkflowState:
        return self._current_state

    def execute_workflow(
        self,
        file_path: Path,
        progress_callback: Optional[Callable[[WorkflowStepDTO], None]] = None,
        department_id: Optional[str] = None,
    ) -> WorkflowResultDTO:
        """
        Executes complete multi-step processing workflow for an engineering drawing PDF.

        Args:
            file_path: Path to drawing PDF file.
            progress_callback: Optional callback function receiving WorkflowStepDTO snapshots.
            department_id: Optional engineering department ID selected during upload.

        Returns:
            WorkflowResultDTO: Summary result of completed processing pipeline.

        Raises:
            WorkflowProcessingError: If any pipeline step fails.
        """
        start_time = time.time()
        path = Path(file_path).resolve()
        logger.info(f"Starting processing workflow execution for: {path.name} (department_id={department_id})")

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
            notify("File Validation", WorkflowState.FILE_VALIDATING, 10, f"Validating '{path.name}' size and extension.")
            val_result: FileValidationResultDTO = self.file_service.validate_pdf_file(path)
            if not val_result.is_valid:
                raise WorkflowProcessingError(val_result.error_message or "File validation failed.")

            # ── Step 2: Metadata Extraction ──────────────────────
            notify("Metadata Extraction", WorkflowState.METADATA_EXTRACTING, 30, f"Extracting page metrics and PDF structure.")
            doc_dto = self.pdf_service.process_pdf_document(path)

            # ── Step 3: Annotation Region Detection ─────────────
            notify("Annotation Detection", WorkflowState.ANNOTATION_DETECTING, 50, 
                   f"Detecting drawing callout boxes and redline regions.")
            
            annotation_result = None
            total_regions = 0
            try:
                annotation_result = self.annotation_service.detect_all_pages(path, method='hybrid')
                total_regions = annotation_result.total_regions
                
                logger.info(f"Annotation detection complete: {total_regions} regions detected across {annotation_result.total_pages} pages")
                
            except Exception as e:
                logger.error(f"Annotation detection failed: {e}. Continuing without annotations.")
                total_regions = 0

            # ── Step 4: OCR & Text Extraction on Detected Regions ─
            notify("OCR Engine", WorkflowState.OCR_PROCESSING, 70, f"Extracting whole comment text from detected markup regions.")
            
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
                        
                        for reg in page_res.regions:
                            # Prioritize reviewer comments and colored markups (red, blue, green)
                            is_comment_markup = (
                                "red" in reg.label.lower() or
                                "blue" in reg.label.lower() or
                                "green" in reg.label.lower() or
                                "yellow" in reg.label.lower() or
                                reg.label in ("native_annotation", "native_text_block", "native_freetext", "native_ink", "native_redline")
                            )
                            if not is_comment_markup:
                                continue
                                
                            pad = 4.0
                            crop_rect = fitz.Rect(
                                max(0.0, reg.x0 - pad),
                                max(0.0, reg.y0 - pad),
                                min(p_obj.rect.width, reg.x1 + pad),
                                min(p_obj.rect.height, reg.y1 + pad)
                            )
                            
                            # Convert visual crop_rect to unrotated clip for PyMuPDF text & annot APIs
                            if p_obj.rotation != 0:
                                crop_unrot = crop_rect * p_obj.derotation_matrix
                                unrot_clip = fitz.Rect(
                                    min(crop_unrot.x0, crop_unrot.x1),
                                    min(crop_unrot.y0, crop_unrot.y1),
                                    max(crop_unrot.x0, crop_unrot.x1),
                                    max(crop_unrot.y0, crop_unrot.y1)
                                )
                            else:
                                unrot_clip = crop_rect

                            # Strictly filter out Title Blocks and Review Status Stamps
                            if AnnotationDetectionServiceEnhanced._is_title_block_or_status_stamp(p_obj, crop_rect, envelopes=page_envs):
                                continue
                                
                            raw_ocr_text = ""
                            
                            # 1. Check for native annotation content (FreeText callouts, Stamps, Notes)
                            try:
                                for annot in p_obj.annots():
                                    if annot.rect.intersects(unrot_clip):
                                        c_text = (annot.info.get('content') or '').strip()
                                        if len(c_text) >= 3 and not (len(c_text) <= 2 and c_text.upper() in ['A','B','C','D','E','F','G','H','1','2','3','4','5','6','7','8']):
                                            raw_ocr_text = c_text
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
                                except Exception:
                                    raw_ocr_text = ""

                            # 3. Check for enclosed digital text inside revision clouds and redline markups
                            if not raw_ocr_text:
                                try:
                                    enclosed_digital_text = p_obj.get_text("text", clip=unrot_clip).strip()
                                    if enclosed_digital_text:
                                        # Normalize multiple spaces and line breaks
                                        clean_candidate = " ".join(enclosed_digital_text.split())
                                        cand_words = [w for w in clean_candidate.split() if any(c.isalnum() for c in w)]
                                        if len(cand_words) > 0 and not (len(clean_candidate) <= 2 and clean_candidate.upper() in [
                                            'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', '1', '2', '3', '4', '5', '6', '7', '8', '.', '-'
                                        ]):
                                            raw_ocr_text = clean_candidate
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
                                        
                                        # Single fast OCR pass with PSM 6
                                        ocr_full = pytesseract.image_to_string(pil_img, config='--psm 6').strip()
                                        if ocr_full and len([w for w in ocr_full.split() if any(c.isalnum() for c in w)]) > 0:
                                            raw_ocr_text = ocr_full
                                        else:
                                            # Optional color-isolated OCR if colored pixels exist
                                            np_img = np.array(pil_img)
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
                                                
                                                raw_ocr_text = pytesseract.image_to_string(ocr_input_pil, config='--psm 6').strip()
                                except Exception as ocr_err:
                                    logger.debug(f"OCR failed for region {reg}: {ocr_err}")
                                    raw_ocr_text = ""
                            
                            # Filter out single/small letter fragments, noise, and title block boilerplate
                            clean_text_check = raw_ocr_text.strip().upper()
                            words = [w for w in clean_text_check.split() if any(c.isalnum() for c in w)]
                            if len(words) == 0:
                                continue
                            if any(phrase in clean_text_check for phrase in AnnotationDetectionServiceEnhanced.TITLE_BLOCK_PHRASES):
                                continue
                            # Reject review stamp sign-off sub-lines like "BY BreKol", "DATE 2/5/2026", "EXP. 06/30/2026"
                            if re.match(r'^(BY\s+[A-Z0-9_]+|DATE\s+[0-9\/\-]+|EXP[\.\:\s]+[0-9\/\-]+)$', clean_text_check):
                                continue
                            # Reject title block label clusters
                            tb_label_hits = sum(1 for label in AnnotationDetectionServiceEnhanced.TITLE_BLOCK_FIELD_LABELS if re.search(r'\b' + re.escape(label) + r'\b', clean_text_check))
                            if tb_label_hits >= 2:
                                continue
                            if len(clean_text_check) <= 2 and clean_text_check in [
                                'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', '1', '2', '3', '4', '5', '6', '7', '8', '.', '-'
                            ]:
                                continue

                            cleaned_dto = self.text_cleaning_service.clean_text(raw_ocr_text)
                            final_text = cleaned_dto.cleaned_text or raw_ocr_text
                            
                            extracted_comments_data.append({
                                "page_number": p_idx + 1,
                                "raw_text": raw_ocr_text,
                                "cleaned_text": final_text,
                                "bbox": (reg.x0, reg.y0, reg.x1, reg.y1),
                                "confidence": reg.confidence,
                                "label": reg.label,
                            })
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
                        if len(item.get("cleaned_text", "")) > len(kept.get("cleaned_text", "")):
                            kept["raw_text"] = item["raw_text"]
                            kept["cleaned_text"] = item["cleaned_text"]
                        kept["confidence"] = max(kept["confidence"], item["confidence"])
                        merged = True
                        break
                        
                if not merged:
                    deduped_comments.append(item)
            extracted_comments_data = deduped_comments

            # ── Step 5: Batched AI Category Classification ─────────
            notify("AI Classification", WorkflowState.AI_CLASSIFYING, 90, f"Classifying review comments with AI.")
            
            if extracted_comments_data:
                texts_to_classify = [
                    item.get("cleaned_text") or item.get("raw_text", "")
                    for item in extracted_comments_data
                ]
                try:
                    batch_dto = self.classification_service.classify_batch(texts_to_classify)
                    class_results = batch_dto.results
                    for item, class_res in zip(extracted_comments_data, class_results):
                        item["category_name"] = class_res.primary_category.category_name
                        if class_res.primary_category.confidence > 0:
                            item["confidence"] = round((item["confidence"] + class_res.primary_category.confidence) / 2.0, 2)
                except Exception as batch_err:
                    logger.warning(f"Batched classification failed, falling back to item-by-item: {batch_err}")
                    for item in extracted_comments_data:
                        try:
                            text_to_classify = item.get("cleaned_text") or item.get("raw_text", "")
                            class_res = self.classification_service.classify_comment(text_to_classify)
                            item["category_name"] = class_res.primary_category.category_name
                            if class_res.primary_category.confidence > 0:
                                item["confidence"] = round((item["confidence"] + class_res.primary_category.confidence) / 2.0, 2)
                        except Exception as class_err:
                            logger.debug(f"Classification failed for '{item.get('raw_text')}': {class_err}")
                            item["category_name"] = "Uncategorized"

            # ── Step 6: Database Persistence ─────────────────────
            notify("Data Persistence", WorkflowState.PERSISTING, 95, f"Saving drawing records to SQLite database.")
            db_record = self.drawing_repo.save_drawing_from_dto(doc_dto, department_id=department_id)
            drawing_id = db_record.get("id", "DWG-000")
            effective_dept_id = db_record.get("department_id") or department_id

            if self.comment_repo and extracted_comments_data:
                try:
                    self.comment_repo.delete_comments_for_drawing(drawing_id)
                except Exception as del_err:
                    logger.debug(f"Error clearing previous comments: {del_err}")
                for c_item in extracted_comments_data:
                    try:
                        conf = c_item.get("confidence", 0.0)
                        auto_approve = True
                        auto_threshold = 0.85
                        try:
                            from src.config import get_config
                            cfg = get_config()
                            auto_approve = getattr(cfg.ai, "auto_approve_high_confidence", True)
                            auto_threshold = getattr(cfg.ai, "auto_approve_threshold", 0.85)
                        except Exception:
                            pass

                        initial_status = "Approved" if (auto_approve and conf >= auto_threshold) else "Pending"

                        saved_c = self.comment_repo.save_comment(
                            drawing_id=drawing_id,
                            page_number=c_item["page_number"],
                            raw_text=c_item["raw_text"],
                            cleaned_text=c_item.get("cleaned_text", ""),
                            bbox=c_item["bbox"],
                            confidence=conf,
                            category_name=c_item.get("category_name", "Uncategorized"),
                            department_id=effective_dept_id,
                            label=c_item.get("label", "comment_red"),
                            status=initial_status,
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
                                    notes=f"Auto-approved by AI (Confidence: {int(conf * 100)}%)",
                                )
                            except Exception as audit_err:
                                logger.debug(f"Auto-approve audit log error: {audit_err}")
                    except Exception as save_err:
                        logger.error(f"Error persisting comment {c_item}: {save_err}")

            # ── Workflow Complete ──────────────────────────────────
            duration = round(time.time() - start_time, 2)
            total_saved = len(extracted_comments_data)
            notify("Workflow Complete", WorkflowState.COMPLETED, 100, f"Successfully processed '{path.name}' in {duration}s.")

            return WorkflowResultDTO(
                drawing_id=drawing_id,
                file_name=doc_dto.file_name,
                total_pages=doc_dto.total_pages,
                is_scanned=doc_dto.is_scanned,
                status="Completed",
                total_comments_found=total_saved if total_saved > 0 else total_regions,
                processing_duration_seconds=duration,
                annotation_result=annotation_result,
            )

        except Exception as e:
            self._current_state = WorkflowState.FAILED
            err_msg = f"Workflow failed for '{path.name}': {e}"
            logger.error(err_msg)
            notify("Workflow Failure", WorkflowState.FAILED, 0, err_msg)
            raise WorkflowProcessingError(err_msg) from e
