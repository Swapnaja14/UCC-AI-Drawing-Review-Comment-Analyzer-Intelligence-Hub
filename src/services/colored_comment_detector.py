"""
Colored Comment Detection Service
Specifically designed to extract colored comment boxes (red, yellow, blue, green, etc.)
from engineering drawings with improved filtering and OCR integration.

This service focuses on:
1. Detecting colored rectangular/box-shaped comments
2. Filtering out background highlights and template elements
3. Extracting text from detected comment regions
4. Distinguishing between comment types based on color
"""

import time
import cv2
import numpy as np
import pymupdf as fitz
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import pytesseract
from PIL import Image

from src.core.dtos.annotation_dtos import BoundingBoxDTO, AnnotationResultDTO, DocumentAnnotationDTO
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ColoredCommentDTO(BoundingBoxDTO):
    """Extended bounding box with comment-specific information"""
    color_category: str  # 'red', 'yellow', 'blue', 'green', etc.
    extracted_text: str = ""
    text_confidence: float = 0.0
    is_box_shaped: bool = False  # Whether it has box/rectangular borders
    
    
class ColoredCommentDetector:
    """
    Advanced detector for colored comment boxes in engineering drawings.
    
    Key features:
    - Multi-color detection (red, yellow, blue, green, cyan, magenta)
    - Shape-aware filtering (prefers rectangular boxes)
    - Background area filtering (excludes large highlight areas)
    - Border detection for framed comments
    - Integrated OCR for text extraction
    """
    
    def __init__(self, detection_dpi: int = 200, ocr_dpi: int = 300):
        """
        Initialize the colored comment detector.
        
        Args:
            detection_dpi: DPI for color detection (higher = more accurate, slower)
            ocr_dpi: DPI for OCR text extraction (higher = better text quality)
        """
        self.detection_dpi = detection_dpi
        self.ocr_dpi = ocr_dpi
        
        # Define color ranges in HSV space - STRICTER to avoid pastel backgrounds
        # Format: 'color_name': [(lower_hsv, upper_hsv), ...]
        self.color_ranges = {
            'red': [
                (np.array([0, 120, 100]), np.array([10, 255, 255])),    # Higher saturation/value
                (np.array([170, 120, 100]), np.array([180, 255, 255]))  # Red upper range (wraps)
            ],
            'yellow': [
                (np.array([20, 120, 150]), np.array([35, 255, 255]))    # Higher thresholds - avoid pale beige
            ],
            'blue': [
                (np.array([100, 120, 100]), np.array([130, 255, 255]))  # Vivid blue only
            ],
            'green': [
                (np.array([40, 120, 100]), np.array([85, 255, 255]))    # Vivid green - not pale backgrounds
            ],
            'cyan': [
                (np.array([85, 120, 100]), np.array([100, 255, 255]))
            ],
            'magenta': [
                (np.array([140, 120, 100]), np.array([170, 255, 255]))
            ],
            'orange': [
                (np.array([10, 120, 150]), np.array([20, 255, 255]))
            ]
        }
        
        # Area thresholds in pixels at detection_dpi
        self.min_comment_area_px = 300  # Lowered to catch smaller comments
        self.max_comment_area_px = 15000  # Exclude large backgrounds
        
        # Aspect ratio limits (width/height or height/width)
        self.min_aspect_ratio = 1.2  # Comments are typically wider than square
        self.max_aspect_ratio = 15   # Stricter limit (was 20)
        
        # Text validation settings
        self.require_text = True  # Only keep regions with actual text
        self.min_text_length = 2  # Minimum 2 characters
        self.min_text_confidence = 0.2  # More lenient (was 0.3)
        
        # Comment-specific patterns (NEW!)
        # Text that looks like measurements/labels, not comments
        self.measurement_patterns = [
            r'^\d+\.?\d*$',           # Pure numbers: "123", "12.5"
            r'^\d+\.?\d*\s*[mM]{1,2}$',  # Measurements: "100 mm", "12M"
            r'^\d+\.?\d*\s*[°]$',      # Angles: "45°", "90°"
            r'^[A-Z]\d*$',             # Labels: "A", "B1", "C2"
            r'^\d+-\d+$',              # Ranges: "1-10", "5-20"
            r'^[A-Z]{1,2}-\d+$',       # Drawing numbers: "E-123", "M-45"
        ]
        
        # Minimum word count for comments (measurements are usually 1-2 words)
        self.min_word_count = 1  # Allow single words if they're comment keywords
        
        logger.info(f"ColoredCommentDetector initialized (detection_dpi={detection_dpi}, ocr_dpi={ocr_dpi})")
    
    def detect_comments_on_page(
        self,
        pdf_path: Path,
        page_number: int,
        extract_text: bool = True,
        filter_by_shape: bool = True,
        require_text_validation: bool = True
    ) -> List[ColoredCommentDTO]:
        """
        Detect colored comment boxes on a single PDF page.
        
        Args:
            pdf_path: Path to PDF file
            page_number: Page index (0-based)
            extract_text: Whether to extract text from detected regions
            filter_by_shape: Whether to filter for box-shaped comments
            require_text_validation: Whether to require text presence (recommended to avoid false positives)
            
        Returns:
            List of ColoredCommentDTO objects with detected comments
        """
        logger.info(f"Detecting colored comments on {pdf_path.name}, page {page_number}")
        
        try:
            doc = fitz.open(pdf_path)
            
            if page_number < 0 or page_number >= len(doc):
                logger.error(f"Invalid page number: {page_number}")
                doc.close()
                return []
            
            page = doc[page_number]
            
            # Step 1: Detect colored regions
            colored_regions = self._detect_colored_regions(page, page_number)
            logger.info(f"  Found {len(colored_regions)} colored regions")
            
            # Step 2: Filter by shape if requested
            if filter_by_shape:
                colored_regions = self._filter_by_box_shape(page, colored_regions)
                logger.info(f"  After shape filtering: {len(colored_regions)} box-shaped comments")
            
            # Step 3: ALWAYS extract text for validation (even if not requested for output)
            colored_regions = self._extract_text_from_regions(page, colored_regions)
            
            # Step 4: NEW - Text validation to remove blank background regions
            if require_text_validation:
                colored_regions = self._validate_text_presence(colored_regions)
                logger.info(f"  After text validation: {len(colored_regions)} regions with actual text")
            else:
                logger.info(f"  Text extracted from {len(colored_regions)} regions (validation disabled)")
            
            doc.close()
            return colored_regions
            
        except Exception as e:
            logger.error(f"Error detecting colored comments: {e}")
            return []
    
    def detect_all_pages(
        self,
        pdf_path: Path,
        extract_text: bool = True,
        filter_by_shape: bool = True,
        require_text_validation: bool = True,
        progress_callback: Optional[callable] = None
    ) -> DocumentAnnotationDTO:
        """
        Detect colored comments across all pages.
        
        Args:
            pdf_path: Path to PDF file
            extract_text: Whether to extract text from detected regions
            filter_by_shape: Whether to filter for box-shaped comments
            require_text_validation: Whether to require text presence (removes blank backgrounds)
            progress_callback: Optional callback(page_num, total_pages)
            
        Returns:
            DocumentAnnotationDTO with all detected comments
        """
        logger.info(f"Detecting colored comments across all pages of {pdf_path.name}")
        
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            doc.close()
            
            page_results = []
            total_regions = 0
            
            for page_num in range(total_pages):
                start_time = time.time()
                
                comments = self.detect_comments_on_page(
                    pdf_path, page_num, extract_text, filter_by_shape, require_text_validation
                )
                
                processing_time_ms = (time.time() - start_time) * 1000
                
                result = AnnotationResultDTO(
                    drawing_id=pdf_path.name,
                    page_number=page_num,
                    regions=comments,
                    detection_method="colored_comment_detection",
                    processing_time_ms=processing_time_ms
                )
                
                page_results.append(result)
                total_regions += len(comments)
                
                if progress_callback:
                    progress_callback(page_num + 1, total_pages)
            
            return DocumentAnnotationDTO(
                file_name=pdf_path.name,
                total_pages=total_pages,
                page_results=page_results,
                total_regions=total_regions
            )
            
        except Exception as e:
            logger.error(f"Error processing document: {e}")
            return DocumentAnnotationDTO(
                file_name=pdf_path.name,
                total_pages=0,
                page_results=[],
                total_regions=0
            )
    
    # =========================================================================
    # CORE DETECTION METHODS
    # =========================================================================
    
    def _detect_colored_regions(
        self,
        page: fitz.Page,
        page_num: int
    ) -> List[ColoredCommentDTO]:
        """
        Detect colored regions using HSV color segmentation and RGB delta rules.
        Returns regions with their detected color category.
        """
        # Convert page to image
        pix = page.get_pixmap(dpi=self.detection_dpi)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        
        # Handle RGBA
        if pix.n == 4:
            img_rgb = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
        else:
            img_rgb = img.copy()
        
        # Convert to HSV for color detection
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        
        detected_regions = []
        scale_factor = 72.0 / self.detection_dpi  # Convert pixels to PDF points
        
        # ── 1. Dedicated Redline Detection (High-Precision Clustering) ──
        r = img_rgb[:, :, 0].astype(int)
        g = img_rgb[:, :, 1].astype(int)
        b = img_rgb[:, :, 2].astype(int)
        
        red_mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        red_cond = (r > 120) & ((r - np.maximum(g, b)) > 30)
        red_mask[red_cond] = 255
        
        # Cluster red text characters and arrows together
        kernel_red = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        red_clustered = cv2.dilate(red_mask, kernel_red, iterations=2)
        
        contours_red, _ = cv2.findContours(
            red_clustered, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        for contour in contours_red:
            x, y, w, h = cv2.boundingRect(contour)
            area_px = w * h
            if 80 <= area_px <= 500000:
                is_box_like = (w / max(h, 1)) >= self.min_aspect_ratio or abs(w - h) / max(w, h, 1) < 0.5
                x0_pt = float(max(0, x - 2) * scale_factor)
                y0_pt = float(max(0, y - 2) * scale_factor)
                x1_pt = float((x + w + 2) * scale_factor)
                y1_pt = float((y + h + 2) * scale_factor)
                confidence = self._calculate_confidence(w, h, area_px, is_box_like)
                
                detected_regions.append(
                    ColoredCommentDTO(
                        x0=x0_pt,
                        y0=y0_pt,
                        x1=x1_pt,
                        y1=y1_pt,
                        page_number=page_num,
                        confidence=max(confidence, 0.85),
                        label="comment_red",
                        color_category="red",
                        is_box_shaped=is_box_like
                    )
                )
        
        # ── 2. Dedicated Blue Comment Detection (High-Precision Clustering) ──
        blue_mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        blue_cond = (b > 100) & ((b - np.maximum(r, g)) > 25)
        blue_mask[blue_cond] = 255
        
        # Cluster blue text characters, revision clouds, and arrows together
        kernel_blue = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        blue_clustered = cv2.dilate(blue_mask, kernel_blue, iterations=2)
        
        contours_blue, _ = cv2.findContours(
            blue_clustered, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        for contour in contours_blue:
            x, y, w, h = cv2.boundingRect(contour)
            area_px = w * h
            if 80 <= area_px <= 500000:
                is_box_like = (w / max(h, 1)) >= self.min_aspect_ratio or abs(w - h) / max(w, h, 1) < 0.5
                x0_pt = float(max(0, x - 2) * scale_factor)
                y0_pt = float(max(0, y - 2) * scale_factor)
                x1_pt = float((x + w + 2) * scale_factor)
                y1_pt = float((y + h + 2) * scale_factor)
                confidence = self._calculate_confidence(w, h, area_px, is_box_like)
                
                detected_regions.append(
                    ColoredCommentDTO(
                        x0=x0_pt,
                        y0=y0_pt,
                        x1=x1_pt,
                        y1=y1_pt,
                        page_number=page_num,
                        confidence=max(confidence, 0.85),
                        label="comment_blue",
                        color_category="blue",
                        is_box_shaped=is_box_like
                    )
                )
        
        # ── 3. Other Color Annotations (Yellow, Green, Cyan, Magenta, Orange) ──
        for color_name, ranges in self.color_ranges.items():
            if color_name in ('red', 'blue'):
                continue  # Handled above with high-precision clustering
                
            color_mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
            for lower, upper in ranges:
                mask = cv2.inRange(hsv, lower, upper)
                color_mask = cv2.bitwise_or(color_mask, mask)
            
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
            color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_OPEN, kernel, iterations=1)
            
            contours, _ = cv2.findContours(
                color_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                area_px = w * h
                
                if not (self.min_comment_area_px <= area_px <= self.max_comment_area_px):
                    continue
                
                aspect_ratio = max(w, h) / max(min(w, h), 1)
                if aspect_ratio > self.max_aspect_ratio:
                    continue
                
                is_box_like = (w / max(h, 1)) >= self.min_aspect_ratio or abs(w - h) / max(w, h, 1) < 0.3
                
                x0_pt = float(x * scale_factor)
                y0_pt = float(y * scale_factor)
                x1_pt = float((x + w) * scale_factor)
                y1_pt = float((y + h) * scale_factor)
                
                confidence = self._calculate_confidence(w, h, area_px, is_box_like)
                
                detected_regions.append(
                    ColoredCommentDTO(
                        x0=x0_pt,
                        y0=y0_pt,
                        x1=x1_pt,
                        y1=y1_pt,
                        page_number=page_num,
                        confidence=confidence,
                        label=f"comment_{color_name}",
                        color_category=color_name,
                        is_box_shaped=is_box_like
                    )
                )
        
        return detected_regions
    
    def _filter_by_box_shape(
        self,
        page: fitz.Page,
        regions: List[ColoredCommentDTO]
    ) -> List[ColoredCommentDTO]:
        """
        Filter regions to identify box-shaped comments while preserving valid redline and blue comments.
        """
        # Red and Blue comments are often unboxed text + arrows, so preserve them
        filtered_regions = []
        for region in regions:
            if region.color_category in ('red', 'blue'):
                filtered_regions.append(region)
            elif region.is_box_shaped:
                filtered_regions.append(region)
            else:
                # Keep other regions if confidence is high
                if region.confidence >= 0.75:
                    filtered_regions.append(region)
                    
        return filtered_regions
    
    def _detect_rectangular_border(self, edge_image: np.ndarray) -> bool:
        """
        Detect if an edge image contains a rectangular border.
        """
        h, w = edge_image.shape
        
        # Check edges around perimeter
        top_edges = np.sum(edge_image[0:3, :]) / (w * 3)
        bottom_edges = np.sum(edge_image[-3:, :]) / (w * 3)
        left_edges = np.sum(edge_image[:, 0:3]) / (h * 3)
        right_edges = np.sum(edge_image[:, -3:]) / (h * 3)
        
        # Threshold for edge density (0-255 scale)
        edge_threshold = 30
        
        # Count how many sides have strong edges
        sides_with_edges = sum([
            top_edges > edge_threshold,
            bottom_edges > edge_threshold,
            left_edges > edge_threshold,
            right_edges > edge_threshold
        ])
        
        # Consider it a box if at least 3 sides have edges
        return sides_with_edges >= 3
    
    def _extract_text_from_regions(
        self,
        page: fitz.Page,
        regions: List[ColoredCommentDTO]
    ) -> List[ColoredCommentDTO]:
        """
        Extract text from each detected region using OCR with clip pixmaps.
        """
        pad = 5.0
        zoom = self.ocr_dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        
        for region in regions:
            try:
                crop_rect = fitz.Rect(
                    max(0.0, region.x0 - pad),
                    max(0.0, region.y0 - pad),
                    min(page.rect.width, region.x1 + pad),
                    min(page.rect.height, region.y1 + pad)
                )
                
                pix = page.get_pixmap(matrix=mat, clip=crop_rect)
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                
                if pix.n == 4:
                    region_img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
                elif pix.n == 3:
                    region_img = img.copy()
                else:
                    region_img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
                
                if region_img.size == 0:
                    continue
                
                # Preprocess for better OCR
                region_processed = self._preprocess_for_ocr(region_img)
                
                # Convert to PIL Image for pytesseract
                pil_img = Image.fromarray(region_processed)
                
                # Extract text with confidence
                ocr_data = pytesseract.image_to_data(
                    pil_img,
                    lang='eng',
                    output_type=pytesseract.Output.DICT,
                    timeout=25,
                )
                
                # Combine text and calculate average confidence
                text_parts = []
                confidences = []
                
                for i, conf in enumerate(ocr_data['conf']):
                    if int(conf) > 0:
                        text = ocr_data['text'][i].strip()
                        if text:  # Only include non-empty text
                            text_parts.append(text)
                            confidences.append(int(conf))
                
                region.extracted_text = ' '.join(text_parts).strip()
                region.text_confidence = sum(confidences) / len(confidences) / 100.0 if confidences else 0.0
                
            except Exception as e:
                logger.warning(f"Error extracting text from region: {e}")
                region.extracted_text = ""
                region.text_confidence = 0.0
        
        return regions
    
    def _validate_text_presence(
        self,
        regions: List[ColoredCommentDTO]
    ) -> List[ColoredCommentDTO]:
        """
        Filter regions to only keep those with actual COMMENT text.
        This removes:
        - Blank colored backgrounds
        - Regular drawing text (measurements, labels, dimensions)
        - Single-word technical annotations
        
        Only keeps actual reviewer comments (multi-word sentences/phrases)
        
        Args:
            regions: List of detected regions with text extracted
            
        Returns:
            Filtered list containing only regions with valid comment text
        """
        import re
        
        validated_regions = []
        
        for region in regions:
            # Check if region has meaningful text
            text = region.extracted_text.strip()
            
            # Filter 1: Must have text
            if not text:
                continue
            
            # Filter 2: Must be at least min_text_length characters
            if len(text) < self.min_text_length and region.text_confidence < 0.7:
                continue
            
            # Filter 3: Must have reasonable confidence
            if len(text) >= self.min_text_length and region.text_confidence < self.min_text_confidence:
                continue
            
            # Filter 4: Must contain actual alphanumeric content
            alphanumeric_chars = sum(c.isalnum() for c in text)
            if alphanumeric_chars < 2:  # At least 2 alphanumeric characters
                continue
            
            # Filter 4.5 (NEW): Check for OCR garbage/fragments
            # Reject if text is very short and looks like noise
            if len(text) <= 3:
                # Very short text - must be a known comment word or have punctuation
                short_comment_words = ['ok', 'yes', 'no', 'add', 'fix', 'see', 'new', 'old', 'is']
                if text.lower() not in short_comment_words and '.' not in text:
                    continue  # Reject 2-3 char fragments like "rly", "hen", "na"
            
            # Filter 5 (NEW): Reject measurement/label patterns
            is_measurement = False
            for pattern in self.measurement_patterns:
                if re.match(pattern, text.strip(), re.IGNORECASE):
                    is_measurement = True
                    break
            
            if is_measurement:
                continue  # Skip measurements/labels
            
            # Filter 6 (NEW): Word count check - more lenient now
            # Allow single words if they look like comments
            words = text.split()
            if len(words) < self.min_word_count:
                # Expanded list of comment keywords that can be single words
                comment_keywords = ['update', 'check', 'verify', 'review', 'change', 
                                   'fix', 'revise', 'note', 'see', 'confirm', 'approved',
                                   'modify', 'correct', 'attention', 'important', 'warning',
                                   'remove', 'add', 'move', 'replace', 'delete', 'insert',
                                   'ok', 'yes', 'no', 'done', 'pending', 'critical',
                                   'make', 'ensure', 'verify', 'validate']
                
                # Allow if:
                # 1. Contains comment keyword
                # 2. Has punctuation (like "OK!" or "Remove.")
                # 3. All caps (like "UPDATE" or "NOTE")
                has_keyword = any(keyword in text.lower() for keyword in comment_keywords)
                has_punctuation = any(c in text for c in '.!?,;:')
                is_all_caps = text.isupper() and len(text) > 2
                
                if not (has_keyword or has_punctuation or is_all_caps):
                    continue  # Skip if none of the above
            
            # Filter 7 (NEW): Check for common words - more lenient
            # Comments usually contain common words, but allow some flexibility
            common_words = ['the', 'this', 'that', 'with', 'from', 'for', 'to', 'as',
                           'is', 'are', 'was', 'be', 'on', 'at', 'in', 'of', 'and', 'or',
                           'a', 'an']
            has_common_word = any(word in text.lower().split() for word in common_words)
            
            # If text is very short and has no common words, check if it looks like a label
            if len(text) < 6 and not has_common_word:
                # Still reject pure technical labels
                if re.match(r'^[A-Z0-9\-]+$', text):  # Like "A-3" or "E125"
                    continue
            
            # Otherwise accept it (length >= 6 or has common word)
            
            # Passed all validation checks - this looks like an actual comment
            validated_regions.append(region)
        
        return validated_regions
    
    def _preprocess_for_ocr(self, img: np.ndarray) -> np.ndarray:
        """
        Preprocess image region for better OCR results.
        """
        # Convert to grayscale
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        else:
            gray = img.copy()
        
        # Increase contrast
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        # Denoise
        denoised = cv2.fastNlMeansDenoising(enhanced, None, h=10)
        
        # Thresholding
        _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        return binary
    
    def _calculate_confidence(
        self,
        width: int,
        height: int,
        area: int,
        is_box_shaped: bool
    ) -> float:
        """
        Calculate detection confidence based on geometric properties.
        """
        # Base confidence
        confidence = 0.6
        
        # Boost for box shape
        if is_box_shaped:
            confidence += 0.15
        
        # Boost for reasonable size (not too small, not too large)
        optimal_area_range = (500, 10000)  # pixels at detection_dpi
        if optimal_area_range[0] <= area <= optimal_area_range[1]:
            confidence += 0.15
        
        # Boost for reasonable aspect ratio (horizontal boxes are common)
        aspect_ratio = max(width, height) / min(width, height)
        if 1.5 <= aspect_ratio <= 5:  # Typical comment box ratios
            confidence += 0.1
        
        return min(1.0, confidence)
    
    # =========================================================================
    # VISUALIZATION & EXPORT
    # =========================================================================
    
    def visualize_detections(
        self,
        pdf_path: Path,
        page_number: int,
        comments: List[ColoredCommentDTO],
        output_path: Optional[Path] = None
    ) -> np.ndarray:
        """
        Create a visualization of detected comments overlaid on the original page.
        
        Args:
            pdf_path: Path to PDF
            page_number: Page number
            comments: Detected comments
            output_path: Optional path to save visualization
            
        Returns:
            Annotated image as numpy array
        """
        doc = fitz.open(pdf_path)
        page = doc[page_number]
        
        # Render page at high DPI for visualization
        pix = page.get_pixmap(dpi=200)
        img = np.frombuffer(pix.samples, dtype=np.uint8)
        img = img.reshape(pix.height, pix.width, pix.n)
        
        if pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        
        scale_factor = 200 / 72.0
        
        # Color map for visualization
        color_map = {
            'red': (0, 0, 255),
            'yellow': (0, 255, 255),
            'blue': (255, 0, 0),
            'green': (0, 255, 0),
            'cyan': (255, 255, 0),
            'magenta': (255, 0, 255),
            'orange': (0, 165, 255)
        }
        
        # Draw bounding boxes
        for comment in comments:
            x0 = int(comment.x0 * scale_factor)
            y0 = int(comment.y0 * scale_factor)
            x1 = int(comment.x1 * scale_factor)
            y1 = int(comment.y1 * scale_factor)
            
            color = color_map.get(comment.color_category, (128, 128, 128))
            
            # Draw rectangle
            thickness = 3 if comment.is_box_shaped else 2
            cv2.rectangle(img, (x0, y0), (x1, y1), color, thickness)
            
            # Add label
            label = f"{comment.color_category} ({comment.confidence:.2f})"
            cv2.putText(
                img, label, (x0, y0 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2
            )
            
            # Add text preview if available
            if comment.extracted_text:
                text_preview = comment.extracted_text[:30] + "..." if len(comment.extracted_text) > 30 else comment.extracted_text
                cv2.putText(
                    img, text_preview, (x0, y1 + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1
                )
        
        doc.close()
        
        if output_path:
            cv2.imwrite(str(output_path), img)
            logger.info(f"Visualization saved to {output_path}")
        
        return img
    
    def export_to_json(
        self,
        comments: List[ColoredCommentDTO],
        output_path: Path
    ):
        """
        Export detected comments to JSON format.
        """
        import json
        
        data = []
        for comment in comments:
            data.append({
                'bbox': {
                    'x0': comment.x0,
                    'y0': comment.y0,
                    'x1': comment.x1,
                    'y1': comment.y1
                },
                'page_number': comment.page_number,
                'color': comment.color_category,
                'text': comment.extracted_text,
                'text_confidence': comment.text_confidence,
                'detection_confidence': comment.confidence,
                'is_box_shaped': comment.is_box_shaped,
                'label': comment.label
            })
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Exported {len(comments)} comments to {output_path}")


def main():
    """Example usage"""
    from pathlib import Path
    
    # Initialize detector
    detector = ColoredCommentDetector(detection_dpi=200, ocr_dpi=300)
    
    # Test PDF
    pdf_path = Path("dataset/raw_drawings/Electrical Engineering/5-1307-137_F_RJY.pdf")
    
    if pdf_path.exists():
        print(f"\n{'='*80}")
        print(f"Detecting colored comments in: {pdf_path.name}")
        print(f"{'='*80}\n")
        
        # Detect comments on first page
        comments = detector.detect_comments_on_page(
            pdf_path,
            page_number=0,
            extract_text=True,
            filter_by_shape=True,
            require_text_validation=True  # Only show regions with actual text
        )
        
        print(f"Found {len(comments)} colored comments:\n")
        
        for i, comment in enumerate(comments, 1):
            print(f"Comment {i}:")
            print(f"  Color: {comment.color_category}")
            print(f"  Position: ({comment.x0:.1f}, {comment.y0:.1f}) - ({comment.x1:.1f}, {comment.y1:.1f})")
            print(f"  Box-shaped: {comment.is_box_shaped}")
            print(f"  Confidence: {comment.confidence:.2f}")
            if comment.extracted_text:
                print(f"  Text: '{comment.extracted_text}' (confidence: {comment.text_confidence:.2f})")
            print()
        
        # Create visualization
        output_dir = Path("dataset/preprocessed_images/comment_detection")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        vis_path = output_dir / f"{pdf_path.stem}_page0_comments.png"
        detector.visualize_detections(pdf_path, 0, comments, vis_path)
        
        print(f"Visualization saved to: {vis_path}")
        
    else:
        print(f"PDF not found: {pdf_path}")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    main()
