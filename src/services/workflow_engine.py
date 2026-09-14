"""
src/services/workflow_engine.py
Processing Workflow Engine orchestrating end-to-end processing steps as a Finite State Machine.
"""

from pathlib import Path
from typing import Callable, Optional, List
import time
import io
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
from src.infrastructure.storage.repository import DrawingRepository, CommentRepository
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
    ) -> None:
        self.file_service = file_service
        self.pdf_service = pdf_service
        self.drawing_repo = drawing_repo
        self.annotation_service = annotation_service or AnnotationDetectionServiceEnhanced()
        self.comment_repo = comment_repo
        self.text_cleaning_service = text_cleaning_service or TextCleaningService()
        self.classification_service = classification_service or ClassificationService()
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
                        
                        for reg in page_res.regions:
                            # Prioritize reviewer comments and colored markups
                            is_comment_markup = (
                                "red" in reg.label.lower() or
                                "blue" in reg.label.lower() or
                                "yellow" in reg.label.lower() or
                                "green" in reg.label.lower() or
                                reg.label in ("native_annotation", "native_text_block", "native_freetext", "native_ink", "native_redline") or
                                reg.confidence >= 0.80
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
                            
                            raw_ocr_text = ""
                            # 1. Check for targeted colored spans (e.g. red or blue reviewer markup text)
                            try:
                                colored_spans_text = []
                                annot_text_dict = p_obj.get_text("dict", clip=crop_rect)
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
                                                is_red = (sr > 130 and sr > max(sg, sb) * 1.25) or (sr > 150 and (sr - max(sg, sb)) > 25)
                                                is_blue = (sb > 120 and sb > max(sr, sg) * 1.20) or (sb > 140 and (sb - max(sr, sg)) > 25)
                                                
                                                if ("red" in reg.label.lower() and is_red) or ("blue" in reg.label.lower() and is_blue):
                                                    colored_spans_text.append(txt)
                                
                                if colored_spans_text:
                                    raw_ocr_text = " ".join(colored_spans_text)
                            except Exception:
                                raw_ocr_text = ""

                            # 2. Fall back to direct digital text in crop if no colored spans matched
                            if not raw_ocr_text:
                                try:
                                    direct_text = p_obj.get_text("text", clip=crop_rect).strip()
                                    if direct_text:
                                        raw_ocr_text = direct_text
                                except Exception:
                                    raw_ocr_text = ""

                            # 3. Fall back to high-resolution OCR (for scanned drawings / handwriting / raster text)
                            if not raw_ocr_text and crop_rect.width > 2 and crop_rect.height > 2:
                                try:
                                    zoom = 300.0 / 72.0
                                    mat = fitz.Matrix(zoom, zoom)
                                    pix = p_obj.get_pixmap(matrix=mat, clip=crop_rect)
                                    if pix.width > 0 and pix.height > 0:
                                        img_bytes = pix.tobytes("png")
                                        img = Image.open(io.BytesIO(img_bytes))
                                        
                                        raw_ocr_text = pytesseract.image_to_string(img, config='--psm 6').strip()
                                        if not raw_ocr_text:
                                            raw_ocr_text = pytesseract.image_to_string(img, config='--psm 11').strip()
                                except Exception as ocr_err:
                                    logger.debug(f"OCR failed for region {reg}: {ocr_err}")
                                    raw_ocr_text = ""
                            
                            # Filter out single/small letter fragments and noise
                            clean_text_check = raw_ocr_text.strip()
                            words = [w for w in clean_text_check.split() if any(c.isalnum() for c in w)]
                            if len(words) == 0:
                                continue
                            if len(clean_text_check) <= 2 and not any(k in clean_text_check.upper() for k in ["NO", "OK", "RE"]):
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

            # ── Step 5: AI Category Classification ────────────────
            notify("AI Classification", WorkflowState.AI_CLASSIFYING, 90, f"Classifying review comments.")
            
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
                        self.comment_repo.save_comment(
                            drawing_id=drawing_id,
                            page_number=c_item["page_number"],
                            raw_text=c_item["raw_text"],
                            cleaned_text=c_item.get("cleaned_text", ""),
                            bbox=c_item["bbox"],
                            confidence=c_item.get("confidence", 0.0),
                            category_name=c_item.get("category_name", "Uncategorized"),
                            department_id=effective_dept_id,
                            label=c_item.get("label", "comment_red"),
                        )
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
                processing_duration_seconds=duration
            )

        except Exception as e:
            self._current_state = WorkflowState.FAILED
            err_msg = f"Workflow failed for '{path.name}': {e}"
            logger.error(err_msg)
            notify("Workflow Failure", WorkflowState.FAILED, 0, err_msg)
            raise WorkflowProcessingError(err_msg) from e
