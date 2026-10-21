"""
OCR-Based Comment Extraction Service

Extracts typed and handwritten comments from engineering drawings using OCR,
filtering out normal drawing text based on heuristics:
- Location (margins, title block, isolated areas)
- Text characteristics (small blocks, colored text)
- Drawing context (not part of main schematic)
"""

import re
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass

import cv2
import numpy as np
import pymupdf as fitz
import pytesseract
from PIL import Image

from src.core.dtos.annotation_dtos import BoundingBoxDTO
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OCRResult:
    """Single OCR text detection result."""
    text: str
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1) in PDF points
    confidence: float
    is_likely_comment: bool
    comment_score: float  # 0-1 score indicating likelihood this is a comment


class OCRCommentExtractor:
    """
    Extract comments from engineering drawings using OCR.
    
    Strategy:
    1. Run OCR on entire page (Tesseract for printed, TrOCR for handwritten)
    2. Get all text regions with bounding boxes
    3. Filter for likely comments based on:
       - Location (margins, isolated from main drawing)
       - Size (small text blocks)
       - Color (red, colored text)
       - Content (keywords, revision marks)
    4. Return comment regions with OCR text
    """
    
    def __init__(self, tesseract_path: Optional[str] = None):
        """
        Initialize OCR extractor.
        
        Args:
            tesseract_path: Optional path to tesseract executable.
                           If None, assumes tesseract is in PATH.
        """
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        
        # Try to verify tesseract is available
        try:
            pytesseract.get_tesseract_version()
            logger.info(f"Tesseract OCR available: {pytesseract.get_tesseract_version()}")
        except Exception as e:
            logger.warning(f"Tesseract OCR not available: {e}")
    
    def extract_comments_from_pdf(
        self,
        pdf_path: Path,
        page_number: int,
        dpi: int = 300
    ) -> List[OCRResult]:
        """
        Extract comment text from a PDF page using OCR.
        
        Args:
            pdf_path: Path to PDF file
            page_number: Page number (0-based)
            dpi: Resolution for OCR (higher = better accuracy but slower)
            
        Returns:
            List of OCRResult objects for detected comments
        """
        logger.info(f"Extracting comments from {pdf_path.name}, page {page_number + 1}")
        
        # Render PDF page to image
        doc = fitz.open(pdf_path)
        page = doc[page_number]
        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to PIL Image
        img_bytes = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))
        
        # Convert to OpenCV format for preprocessing
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        
        # Get page dimensions for coordinate conversion
        page_width_pt = page.rect.width
        page_height_pt = page.rect.height
        scale_x = page_width_pt / pix.width
        scale_y = page_height_pt / pix.height
        
        doc.close()
        
        # Run OCR with detailed data (bounding boxes, confidence) and safe timeout
        try:
            ocr_data = pytesseract.image_to_data(
                img,
                output_type=pytesseract.Output.DICT,
                config='--psm 11',  # Sparse text with no OSD
                timeout=30,
            )
        except Exception as e:
            logger.warning(f"Comment extraction OCR timed out or failed: {e}")
            ocr_data = {'text': [], 'conf': [], 'left': [], 'top': [], 'width': [], 'height': []}
        
        # Extract text regions and filter for comments
        results = []
        n_boxes = len(ocr_data['text'])
        
        for i in range(n_boxes):
            text = ocr_data['text'][i].strip()
            conf = float(ocr_data['conf'][i])
            
            # Skip empty text or low confidence
            if not text or conf < 30:
                continue
            
            # Get bounding box (in pixels)
            x_px = ocr_data['left'][i]
            y_px = ocr_data['top'][i]
            w_px = ocr_data['width'][i]
            h_px = ocr_data['height'][i]
            
            # Convert to PDF points
            x0_pt = x_px * scale_x
            y0_pt = y_px * scale_y
            x1_pt = (x_px + w_px) * scale_x
            y1_pt = (y_px + h_px) * scale_y
            
            # Calculate comment score
            comment_score = self._calculate_comment_score(
                text=text,
                bbox_pt=(x0_pt, y0_pt, x1_pt, y1_pt),
                page_width_pt=page_width_pt,
                page_height_pt=page_height_pt,
                img_cv=img_cv,
                bbox_px=(x_px, y_px, w_px, h_px)
            )
            
            is_comment = comment_score > 0.5
            
            results.append(OCRResult(
                text=text,
                bbox=(x0_pt, y0_pt, x1_pt, y1_pt),
                confidence=conf / 100.0,
                is_likely_comment=is_comment,
                comment_score=comment_score
            ))
        
        # Group nearby text into comment blocks
        comment_blocks = self._group_into_comment_blocks(
            [r for r in results if r.is_likely_comment]
        )
        
        logger.info(f"Found {len(comment_blocks)} comment blocks from {len(results)} text regions")
        
        return comment_blocks
    
    def _calculate_comment_score(
        self,
        text: str,
        bbox_pt: Tuple[float, float, float, float],
        page_width_pt: float,
        page_height_pt: float,
        img_cv: np.ndarray,
        bbox_px: Tuple[int, int, int, int]
    ) -> float:
        """
        Calculate likelihood score (0-1) that this text is a comment.
        
        Heuristics:
        1. Location: Margins, title block, isolated areas
        2. Color: Red, colored text
        3. Size: Small text blocks
        4. Content: Keywords (REV, NOTE, CHECK, etc.)
        5. Context: Not part of component labels
        """
        score = 0.0
        x0, y0, x1, y1 = bbox_pt
        
        # 1. LOCATION SCORE (0-0.3)
        # Comments are often in margins or title block
        margin_threshold_pt = 100  # 100 points from edges
        in_right_margin = x0 > (page_width_pt - margin_threshold_pt * 2)
        in_bottom_margin = y0 > (page_height_pt - margin_threshold_pt * 1.5)
        in_title_block = in_right_margin and in_bottom_margin
        
        if in_title_block:
            score += 0.2
        elif in_right_margin or in_bottom_margin:
            score += 0.1
        
        # 2. COLOR SCORE (0-0.3)
        # Red/colored text is likely a comment
        x_px, y_px, w_px, h_px = bbox_px
        if w_px > 0 and h_px > 0:
            try:
                # Extract region
                region = img_cv[y_px:y_px+h_px, x_px:x_px+w_px]
                if region.size > 0:
                    # Calculate average color
                    avg_color = cv2.mean(region)[:3]  # BGR
                    b, g, r = avg_color
                    
                    # Check if red-ish
                    if r > g * 1.2 and r > b * 1.2 and r > 100:
                        score += 0.3
                    # Check if colored (not grayscale)
                    elif max(abs(r - g), abs(g - b), abs(b - r)) > 30:
                        score += 0.15
            except Exception:
                pass
        
        # 3. SIZE SCORE (0-0.2)
        # Comments are typically small blocks
        text_length = len(text)
        if text_length < 20:
            score += 0.2
        elif text_length < 50:
            score += 0.1
        
        # 4. CONTENT SCORE (0-0.3)
        # Keywords that appear in comments
        comment_keywords = [
            'rev', 'revision', 'note', 'check', 'verify', 'see', 
            'refer', 'typical', 'dwg', 'drawing', 'sheet',
            'remarks', 'comments', 'issue', 'by', 'date',
            'approved', 'reviewed', 'checked'
        ]
        
        text_lower = text.lower()
        if any(keyword in text_lower for keyword in comment_keywords):
            score += 0.3
        
        # Revision marks (A, B, C, etc. in circles)
        if re.match(r'^[A-Z]$', text):
            score += 0.2
        
        # Dates
        if re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', text):
            score += 0.2
        
        # 5. CONTEXT SCORE (negative)
        # Reduce score for text that looks like component labels
        if re.match(r'^[A-Z0-9]+(-[A-Z0-9]+)*$', text):  # E.g., "T-101", "PV-205"
            score -= 0.2
        
        # Common drawing text (not comments)
        drawing_text = ['elevation', 'plan', 'section', 'scale', 'view']
        if text_lower in drawing_text:
            score -= 0.3
        
        return max(0.0, min(1.0, score))  # Clamp to 0-1
    
    def _group_into_comment_blocks(
        self,
        ocr_results: List[OCRResult],
        proximity_threshold_pt: float = 20.0
    ) -> List[OCRResult]:
        """
        Group nearby text regions into comment blocks.
        
        Args:
            ocr_results: List of OCR results
            proximity_threshold_pt: Maximum distance (in points) to group text
            
        Returns:
            List of grouped OCRResult objects (merged text)
        """
        if not ocr_results:
            return []
        
        # Simple grouping: merge text that is close together
        groups = []
        used = set()
        
        for i, result in enumerate(ocr_results):
            if i in used:
                continue
            
            group_texts = [result.text]
            group_boxes = [result.bbox]
            group_confs = [result.confidence]
            used.add(i)
            
            x0, y0, x1, y1 = result.bbox
            
            # Find nearby text
            for j, other in enumerate(ocr_results):
                if j in used or j == i:
                    continue
                
                ox0, oy0, ox1, oy1 = other.bbox
                
                # Check proximity (vertically or horizontally aligned)
                vert_overlap = max(0, min(y1, oy1) - max(y0, oy0))
                horiz_overlap = max(0, min(x1, ox1) - max(x0, ox0))
                
                vert_dist = abs((y0 + y1) / 2 - (oy0 + oy1) / 2)
                horiz_dist = abs((x0 + x1) / 2 - (ox0 + ox1) / 2)
                
                if (vert_overlap > 0 and horiz_dist < proximity_threshold_pt) or \
                   (horiz_overlap > 0 and vert_dist < proximity_threshold_pt):
                    group_texts.append(other.text)
                    group_boxes.append(other.bbox)
                    group_confs.append(other.confidence)
                    used.add(j)
            
            # Merge into single comment block
            all_x0 = [b[0] for b in group_boxes]
            all_y0 = [b[1] for b in group_boxes]
            all_x1 = [b[2] for b in group_boxes]
            all_y1 = [b[3] for b in group_boxes]
            
            merged_bbox = (
                min(all_x0),
                min(all_y0),
                max(all_x1),
                max(all_y1)
            )
            
            merged_text = ' '.join(group_texts)
            merged_conf = sum(group_confs) / len(group_confs)
            
            groups.append(OCRResult(
                text=merged_text,
                bbox=merged_bbox,
                confidence=merged_conf,
                is_likely_comment=True,
                comment_score=result.comment_score
            ))
        
        return groups


# Import for BytesIO
import io
