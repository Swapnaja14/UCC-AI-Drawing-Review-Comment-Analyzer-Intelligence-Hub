"""
Enhanced Annotation Detection Service with 4 Extraction Methods:
1. Native PDF Annotation Extraction
2. Color Segmentation
3. Connected Components Analysis
4. Advanced Region Detection (MSER, Edge, Blob)
"""

import os
import time
import re
import cv2
import numpy as np
import pymupdf as fitz
from pathlib import Path
from typing import List, Literal, Optional, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.core.dtos.annotation_dtos import BoundingBoxDTO, AnnotationResultDTO, DocumentAnnotationDTO
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

ExtractionMethod = Literal['native', 'color', 'connected', 'region', 'hybrid']


class AnnotationDetectionServiceEnhanced:
    """
    Enhanced annotation detection with multiple extraction strategies.
    
    Methods:
    - native: Fast, accurate PDF annotation extraction
    - color: HSV color segmentation for colored markup
    - connected: Connected component analysis for blob detection
    - region: Advanced region detection (MSER, edges, blobs)
    - hybrid: Combines all methods for best results
    """
    
    def __init__(self):
        self.default_dpi = 150  # Balance between quality and speed
        
    def detect_annotations_on_page(
        self, 
        pdf_path: Path, 
        page_number: int,
        method: ExtractionMethod = 'hybrid'
    ) -> AnnotationResultDTO:
        """
        Detect annotations on a single page using specified method.
        
        Args:
            pdf_path: Path to PDF file
            page_number: Page index (0-based)
            method: Detection method to use
            
        Returns:
            AnnotationResultDTO with detected regions
        """
        start_time = time.time()
        logger.info(f"Detecting annotations on {pdf_path.name}, page {page_number} using {method} method")
        
        regions = []
        try:
            doc = fitz.open(pdf_path)
            if 0 <= page_number < len(doc):
                page = doc[page_number]
                page_envelopes = self._get_title_block_and_stamp_envelopes(page)
                
                if method == 'native':
                    regions.extend(self._extract_native_annotations(page, page_number, envelopes=page_envelopes))
                    regions.extend(self._extract_text_regions(page, page_number, envelopes=page_envelopes))
                    regions.extend(self._detect_redline_regions(page, page_number, envelopes=page_envelopes))
                    
                elif method == 'color':
                    regions = self._detect_by_color_segmentation(page, page_number, envelopes=page_envelopes)
                    
                elif method == 'connected':
                    regions = self._detect_by_connected_components(page, page_number)
                    
                elif method == 'region':
                    regions = self._detect_by_region_proposals(page, page_number, envelopes=page_envelopes)
                    
                elif method == 'hybrid':
                    # Fast & comprehensive markup detection:
                    # 1. Native PDF callouts, stamps, FreeText & polygon annotations
                    # 2. Vector text colored markup (red / blue / yellow / green text)
                    # 3. Vector path redlines, clouds & leaders
                    # 4. Rasterized high-sensitivity color segmentation (HSV/RGB)
                    native = self._extract_native_annotations(page, page_number, envelopes=page_envelopes)
                    native.extend(self._extract_text_regions(page, page_number, envelopes=page_envelopes))
                    native.extend(self._detect_redline_regions(page, page_number, envelopes=page_envelopes))
                    
                    color = self._detect_by_color_segmentation(page, page_number, envelopes=page_envelopes)
                    
                    # Merge and deduplicate
                    all_regions = native + color
                    regions = self._deduplicate_regions(all_regions)
                    
                    # Final safety pass: strictly filter out title blocks and review status stamps
                    regions = [
                        r for r in regions 
                        if not self._is_title_block_or_status_stamp(page, fitz.Rect(r.x0, r.y0, r.x1, r.y1), envelopes=page_envelopes)
                    ]
            
            doc.close()
            
        except Exception as e:
            logger.error(f"Error detecting annotations on {pdf_path}: {e}")

        processing_time_ms = (time.time() - start_time) * 1000
        
        return AnnotationResultDTO(
            drawing_id=pdf_path.name,
            page_number=page_number,
            regions=regions,
            detection_method=method,
            processing_time_ms=processing_time_ms
        )

    def detect_all_pages(
        self, 
        pdf_path: Path,
        method: ExtractionMethod = 'hybrid',
        filter_template_regions: bool = True,
        progress_callback=None
    ) -> DocumentAnnotationDTO:
        """
        Detect annotations across all pages using multi-threaded page parallelism.
        
        Args:
            pdf_path: Path to PDF file
            method: Detection method to use
            filter_template_regions: If True, removes regions that appear at identical 
                                     positions across all pages (likely template elements)
            progress_callback: Optional callback(page_num, total_pages) called after each page
            
        Returns:
            DocumentAnnotationDTO with all results
        """
        logger.info(f"Detecting annotations across all pages of {pdf_path.name} using {method}")
        page_results = []
        total_regions = 0
        total_pages = 0
        
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            doc.close()
            
            if total_pages == 0:
                return DocumentAnnotationDTO(
                    file_name=pdf_path.name,
                    total_pages=0,
                    page_results=[],
                    total_regions=0
                )

            # Use thread pool with bounded workers (prevents CPU oversubscription with OpenCV SIMD)
            num_workers = min(6, max(1, os.cpu_count() or 2))
            if total_pages == 1 or num_workers == 1:
                for page_num in range(total_pages):
                    result = self.detect_annotations_on_page(pdf_path, page_num, method)
                    page_results.append(result)
                    total_regions += len(result.regions)
                    if progress_callback:
                        progress_callback(page_num + 1, total_pages)
            else:
                completed_count = 0
                results_by_page = {}
                with ThreadPoolExecutor(max_workers=num_workers) as executor:
                    future_to_page = {
                        executor.submit(self.detect_annotations_on_page, pdf_path, p_num, method): p_num
                        for p_num in range(total_pages)
                    }
                    for future in as_completed(future_to_page):
                        p_num = future_to_page[future]
                        try:
                            res = future.result()
                            results_by_page[p_num] = res
                        except Exception as p_err:
                            logger.error(f"Error processing page {p_num}: {p_err}")
                            results_by_page[p_num] = AnnotationResultDTO(
                                drawing_id=pdf_path.name,
                                page_number=p_num,
                                regions=[],
                                detection_method=method,
                                processing_time_ms=0.0
                            )
                        completed_count += 1
                        if progress_callback:
                            progress_callback(completed_count, total_pages)
                
                # Assemble results in sequential page order
                for p_num in range(total_pages):
                    res = results_by_page.get(p_num)
                    if res:
                        page_results.append(res)
                        total_regions += len(res.regions)
            
            # Filter out template regions if enabled and we have multiple pages
            if filter_template_regions and total_pages > 1:
                page_results = self._filter_template_regions(page_results)
                # Recalculate total after filtering
                total_regions = sum(len(r.regions) for r in page_results)
                logger.info(f"After filtering template regions: {total_regions} regions remain")
                
        except Exception as e:
            logger.error(f"Error processing document {pdf_path}: {e}")
            
        return DocumentAnnotationDTO(
            file_name=pdf_path.name,
            total_pages=total_pages,
            page_results=page_results,
            total_regions=total_regions
        )
    
    def _filter_template_regions(self, page_results: List[AnnotationResultDTO], 
                                  position_tolerance: float = 5.0) -> List[AnnotationResultDTO]:
        """
        Remove regions that appear at the same position on ALL pages (template elements).
        
        Engineering drawings often have title blocks with colored fields that appear at
        identical positions on every page. These are template elements, not markup.
        Real annotations/redlines vary by page.
        
        Args:
            page_results: List of per-page detection results
            position_tolerance: Maximum distance (in PDF points) to consider regions "same position"
            
        Returns:
            Filtered page results with template regions removed
        """
        if len(page_results) <= 1:
            return page_results
        
        # Build position frequency map: how many pages have a region at each position
        position_counts = {}  # (x0_rounded, y0_rounded) -> count
        position_to_regions = {}  # (x0_rounded, y0_rounded) -> list of (page_idx, region_idx)
        
        for page_idx, page_result in enumerate(page_results):
            for region_idx, region in enumerate(page_result.regions):
                # Round position to tolerance grid
                pos_key = (
                    round(region.x0 / position_tolerance),
                    round(region.y0 / position_tolerance)
                )
                
                position_counts[pos_key] = position_counts.get(pos_key, 0) + 1
                
                if pos_key not in position_to_regions:
                    position_to_regions[pos_key] = []
                position_to_regions[pos_key].append((page_idx, region_idx))
        
        # Find positions that appear on ALL pages (these are templates)
        total_pages = len(page_results)
        template_positions = {
            pos for pos, count in position_counts.items() 
            if count >= total_pages * 0.8  # 80% threshold (allows for slight variations)
        }
        
        if not template_positions:
            return page_results  # No template regions found
        
        logger.info(f"Found {len(template_positions)} template positions to filter out")
        
        # Create filtered results
        filtered_results = []
        for page_idx, page_result in enumerate(page_results):
            filtered_regions = []
            
            for region in page_result.regions:
                pos_key = (
                    round(region.x0 / position_tolerance),
                    round(region.y0 / position_tolerance)
                )
                
                # Keep region if it's NOT a template position
                if pos_key not in template_positions:
                    filtered_regions.append(region)
            
            # Create new result with filtered regions
            filtered_results.append(
                AnnotationResultDTO(
                    drawing_id=page_result.drawing_id,
                    page_number=page_result.page_number,
                    regions=filtered_regions,
                    detection_method=page_result.detection_method,
                    processing_time_ms=page_result.processing_time_ms
                )
            )
        
        return filtered_results

    # ========================================================================
    # COLOR CHECK UTILITIES (STRICT RED, BLUE, GREEN)
    # ========================================================================

    @staticmethod
    def _is_red_rgb(r: int, g: int, b: int) -> bool:
        """Strict red reviewer markup check: high red dominance and minimum chromatic difference."""
        if r < 110:
            return False
        max_gb = max(g, b)
        return (r - max_gb >= 24) and (r >= max_gb * 1.20)

    @staticmethod
    def _is_blue_rgb(r: int, g: int, b: int) -> bool:
        """Strict blue reviewer markup check: high blue dominance and minimum chromatic difference."""
        if b < 105:
            return False
        max_rg = max(r, g)
        return (b - max_rg >= 24) and (b >= max_rg * 1.20)

    @staticmethod
    def _is_green_rgb(r: int, g: int, b: int) -> bool:
        """Strict green reviewer markup check: high green dominance and minimum chromatic difference."""
        if g < 95:
            return False
        max_rb = max(r, b)
        return (g - max_rb >= 24) and (g >= max_rb * 1.20)

    TITLE_BLOCK_PHRASES = (
        "DOCUMENT RETURN REVIEW STATUS",
        "REVIEW STATUS",
        "APPROVAL STATUS",
        "STATUS STAMP",
        "SUBMITTAL REVIEW",
        "SHOP DRAWING REVIEW",
        "1. NO EXCEPTIONS NOTED",
        "NO EXCEPTIONS NOTED",
        "PROCEED WITH ENGINEERING",
        "2. ENGINEERING/PROCUREMENT/FABRICATION",
        "MAY PROCEED BASED ON",
        "MAKING REVISIONS NOTED",
        "SUBMIT FINAL DOCUMENT",
        "3. NOT APPROVED",
        "CORRECT AS NOTED",
        "DO NOT PROCEED WITH",
        "4. NO APPROVAL REQUIRED",
        "DESIGN CONSISTENCY",
        "FOR DESIGN CONSISTENCY",
        "GENERAL ALIGNMENT WITH CONTRACT",
        "HAS REVIEWED THIS DOCUMENT",
        "RESPONSIBLE FOR MEETING ALL REQUIREMENTS",
        "PURCHASE ORDER, CONTRACT DOCUMENTS",
        "PURCHASE ORDER, CONTRACT",
        "APPLICABLE CODES AND STANDARDS",
        "ENGINEERING/PROCUREMENT/FABRICATION",
        "ENGINEER OF RECORD",
        "CONSULTING ENGINEERS",
        "ENVIRONMENTAL",
        "NORMAN DRIVE",
        "WAUKEGAN",
        "DO NOT SCALE",
        "DO NOT SCALE DRAWING",
        "PROPRIETARY AND CONFIDENTIAL",
        "CONFIDENTIAL AND PROPRIETARY",
        "ALL RIGHTS RESERVED",
    )

    TITLE_BLOCK_FIELD_LABELS = (
        "DESIGNED BY", "CHECKED BY", "APPROVED BY", "DRAWN BY",
        "DWN", "CHK", "APVD", "ENGR", "DRAWING SIZE", "SHEET NO", "PROJECT NO", "JOB NO",
        "CONTRACT NUMBER", "DRAWING NUMBER", "DWG NO", "CAD FILE", "CONTRACT NO", "DWG."
    )

    @classmethod
    def _get_rgb_color_label(cls, r: int, g: int, b: int) -> Optional[str]:
        if cls._is_red_rgb(r, g, b):
            return "comment_red"
        if cls._is_blue_rgb(r, g, b):
            return "comment_blue"
        if cls._is_green_rgb(r, g, b):
            return "comment_green"
        return None

    @classmethod
    def _get_title_block_and_stamp_envelopes(cls, page: fitz.Page) -> List[fitz.Rect]:
        """
        Identify the bounding boxes of all engineering Title Blocks, Document Review Status Stamps,
        and margin metadata grids on the page.
        """
        envelopes: List[fitz.Rect] = []
        pw, ph = page.rect.width, page.rect.height

        # 1. Native Stamp Annotations
        try:
            for annot in page.annots():
                annot_type = annot.type[1] if annot.type else ""
                annot_subj = (annot.info.get("subject") or "").lower()
                annot_name = (annot.info.get("name") or "").lower()
                if annot_type == "Stamp" or any(k in annot_subj or k in annot_name for k in ("stamp", "status stamp", "approval stamp", "review status", "approval status")):
                    r = annot.rect
                    envelopes.append(fitz.Rect(max(0.0, r.x0 - 20.0), max(0.0, r.y0 - 20.0), min(pw, r.x1 + 20.0), min(ph, r.y1 + 20.0)))
        except Exception:
            pass

        # 2. Text blocks for Review Status Stamps and Title Blocks grouped by quadrant/margin
        try:
            blocks = page.get_text("blocks")
        except Exception:
            blocks = []

        corner_rects: Dict[str, List[Tuple[fitz.Rect, bool]]] = {
            "top_left": [],
            "top_right": [],
            "bottom_left": [],
            "bottom_right": [],
            "left_margin": [],
            "right_margin": [],
            "bottom_margin": []
        }

        for b in blocks:
            txt = b[4].upper()
            bx0, by0, bx1, by1 = b[0], b[1], b[2], b[3]
            r = fitz.Rect(bx0, by0, bx1, by1)
            
            is_stamp_phrase = any(p in txt for p in cls.TITLE_BLOCK_PHRASES) or (("EXP:" in txt or "EXP." in txt) and "DATE" in txt)
            label_matches = sum(1 for label in cls.TITLE_BLOCK_FIELD_LABELS if re.search(r'\b' + re.escape(label) + r'\b', txt))
            
            # Require stamp phrase or explicit title block labels
            if is_stamp_phrase or label_matches >= 1:
                item = (r, is_stamp_phrase)
                if bx0 < pw * 0.45 and by0 < ph * 0.45:
                    corner_rects["top_left"].append(item)
                if bx1 > pw * 0.55 and by0 < ph * 0.45:
                    corner_rects["top_right"].append(item)
                if bx0 < pw * 0.45 and by1 > ph * 0.55:
                    corner_rects["bottom_left"].append(item)
                if bx1 > pw * 0.55 and by1 > ph * 0.55:
                    corner_rects["bottom_right"].append(item)
                if bx0 < pw * 0.20:
                    corner_rects["left_margin"].append(item)
                if bx1 > pw * 0.80:
                    corner_rects["right_margin"].append(item)
                if by1 > ph * 0.80:
                    corner_rects["bottom_margin"].append(item)

        # 3. Include corner logo images
        try:
            for img_info in page.get_image_info():
                ibox = img_info.get("bbox")
                if ibox:
                    ir = fitz.Rect(ibox)
                    img_item = (ir, True)
                    if ir.x0 < pw * 0.45 and ir.y0 < ph * 0.45:
                        corner_rects["top_left"].append(img_item)
                    if ir.x1 > pw * 0.55 and ir.y0 < ph * 0.45:
                        corner_rects["top_right"].append(img_item)
                    if ir.x0 < pw * 0.45 and ir.y1 > ph * 0.55:
                        corner_rects["bottom_left"].append(img_item)
                    if ir.x1 > pw * 0.55 and ir.y1 > ph * 0.55:
                        corner_rects["bottom_right"].append(img_item)
        except Exception:
            pass

        for group_name, items in corner_rects.items():
            if not items:
                continue
            has_stamp = any(is_s for _, is_s in items)
            # Require either a review stamp phrase or at least 2 title block fields in the same corner
            if has_stamp or len(items) >= 2:
                u = items[0][0]
                for r, _ in items[1:]:
                    u = u | r
                envelopes.append(fitz.Rect(max(0.0, u.x0 - 30.0), max(0.0, u.y0 - 30.0), min(pw, u.x1 + 30.0), min(ph, u.y1 + 30.0)))

        return envelopes

    @classmethod
    def _is_title_block_or_status_stamp(
        cls, 
        page: fitz.Page, 
        rect: fitz.Rect, 
        annot: Optional[fitz.Annot] = None,
        envelopes: Optional[List[fitz.Rect]] = None
    ) -> bool:
        """
        Detect if a candidate bounding box is an engineering Title Block, Document Review Status Stamp,
        or corner/margin metadata box (always in a corner/edge and inside a rectangular boundary).
        """
        if annot is not None:
            annot_type = annot.type[1] if annot.type else ""
            annot_subj = (annot.info.get("subject") or "").lower()
            annot_name = (annot.info.get("name") or "").lower()
            if annot_type == "Stamp" or any(k in annot_subj or k in annot_name for k in ("stamp", "status stamp", "approval stamp", "review status", "approval status")):
                return True

        if envelopes is None:
            envelopes = cls._get_title_block_and_stamp_envelopes(page)

        # 1. Envelope containment / intersection check
        for env in envelopes:
            intersect = fitz.Rect(rect).intersect(env)
            if not intersect.is_empty:
                overlap_area = intersect.width * intersect.height
                rect_area = rect.width * rect.height
                if rect_area > 0 and (overlap_area / rect_area >= 0.10 or overlap_area > 40):
                    return True
                cx, cy = (rect.x0 + rect.x1) / 2.0, (rect.y0 + rect.y1) / 2.0
                if env.contains(fitz.Point(cx, cy)):
                    return True

        # 2. Extract text inside the candidate rectangle
        try:
            text = page.get_text("text", clip=rect).upper()
        except Exception:
            return False

        if not text:
            return False

        # 3. Review status stamp boilerplate phrases
        for phrase in cls.TITLE_BLOCK_PHRASES:
            if phrase in text:
                return True

        # 4. Engineering title block field clusters (e.g. DWN, APVD, CHK, ENGR, DRAWING NUMBER)
        label_matches = sum(1 for label in cls.TITLE_BLOCK_FIELD_LABELS if re.search(r'\b' + re.escape(label) + r'\b', text))
        if label_matches >= 3:
            return True

        # 5. Corner / border edge check with 2+ title block labels
        pw, ph = page.rect.width, page.rect.height
        is_corner = (rect.x0 < pw * 0.35 or rect.x1 > pw * 0.65) and (rect.y0 < ph * 0.35 or rect.y1 > ph * 0.65)
        if is_corner and label_matches >= 2 and any(k in text for k in ("DWN", "APVD", "CHK", "ENGR", "DRAWING NUMBER", "DWG NO", "CONTRACT")):
            return True

        return False

    # ========================================================================
    # METHOD 1: NATIVE PDF ANNOTATION EXTRACTION
    # ========================================================================
    
    def _extract_native_annotations(self, page: fitz.Page, page_num: int, envelopes: Optional[List[fitz.Rect]] = None) -> List[BoundingBoxDTO]:
        """
        Extract genuine native PDF review markup annotations (callouts, comments, stamps, redlines).
        Strictly rejects AutoCAD grid markers (A, B, C, 1, 2), SHX text boxes, and monochrome elements.
        """
        regions = []
        for annot in page.annots():
            rect = annot.rect
            info = annot.info or {}
            
            # Filter out Title Blocks and Review Status Stamps (e.g. DOCUMENT RETURN REVIEW STATUS)
            if self._is_title_block_or_status_stamp(page, rect, annot, envelopes=envelopes):
                continue
                
            # Filter out AutoCAD SHX text font placeholder boxes
            if info.get('title') == 'AutoCAD SHX Text':
                continue
                
            content = (info.get('content') or '').strip()
            subject = (info.get('subject') or '').strip()
            
            # Filter out single-character drawing grid reference markers (A, B, C, 1, 2...)
            if len(content) <= 2 and content.upper() in [
                'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'J', 'K',
                '1', '2', '3', '4', '5', '6', '7', '8', '9', '10'
            ]:
                continue
                
            annot_type = annot.type[1] if annot.type else "annotation"
            
            # Check stroke and fill colors
            colors = annot.colors or {}
            stroke = colors.get('stroke', [])
            fill = colors.get('fill', [])
            
            is_red = False
            is_blue = False
            is_green = False
            
            for col in [stroke, fill]:
                if col and len(col) >= 3:
                    cr, cg, cb = int(col[0] * 255), int(col[1] * 255), int(col[2] * 255)
                    if self._is_red_rgb(cr, cg, cb):
                        is_red = True
                        break
                    elif self._is_blue_rgb(cr, cg, cb):
                        is_blue = True
                        break
                    elif self._is_green_rgb(cr, cg, cb):
                        is_green = True
                        break
                        
            # If color was not explicitly in stroke/fill (e.g. FreeText callouts), inspect digital text spans inside
            if not (is_red or is_blue or is_green):
                try:
                    annot_text_dict = page.get_text("dict", clip=rect)
                    for b in annot_text_dict.get("blocks", []):
                        if b.get("type") == 0:
                            for l in b.get("lines", []):
                                for s in l.get("spans", []):
                                    c_int = s.get("color", 0)
                                    sr = (c_int >> 16) & 0xFF
                                    sg = (c_int >> 8) & 0xFF
                                    sb = c_int & 0xFF
                                    if self._is_red_rgb(sr, sg, sb):
                                        is_red = True
                                        break
                                    elif self._is_blue_rgb(sr, sg, sb):
                                        is_blue = True
                                        break
                                    elif self._is_green_rgb(sr, sg, sb):
                                        is_green = True
                                        break
                                if is_red or is_blue or is_green:
                                    break
                        if is_red or is_blue or is_green:
                            break
                except Exception:
                    pass
                
            # If still not qualified by color, check if it's a known reviewer callout or cloud with content
            if not (is_red or is_blue or is_green):
                # Only accept FreeText callouts if they have actual multi-word reviewer text
                if annot_type.lower() in ("freetext", "text") and len(content.split()) >= 2:
                    # Treat standard reviewer callout as redline markup default
                    is_red = True
                else:
                    # Reject monochrome/black AutoCAD geometry and uncolored stamps
                    continue
                
            if is_red:
                label = "native_redline"
            elif is_blue:
                label = "comment_blue"
            elif is_green:
                label = "comment_green"
            else:
                label = f"native_{annot_type}"
            
            # Ignore microscopic annotation rectangles (< 6 pt)
            w = rect.x1 - rect.x0
            h = rect.y1 - rect.y0
            if w < 6 or h < 6:
                continue

            regions.append(
                BoundingBoxDTO(
                    x0=float(rect.x0),
                    y0=float(rect.y0),
                    x1=float(rect.x1),
                    y1=float(rect.y1),
                    page_number=page_num,
                    confidence=1.0,
                    label=label
                )
            )
        return regions

    def _extract_text_regions(self, page: fitz.Page, page_num: int, envelopes: Optional[List[fitz.Rect]] = None) -> List[BoundingBoxDTO]:
        """
        Extract whole comment text blocks (paragraphs/lines) representing reviewer markup
        specifically in Red, Blue, or Green text.
        """
        blocks = page.get_text('dict').get('blocks', [])
        colored_lines = []
        
        for block in blocks:
            if block.get('type') == 0:  # Text block
                for line in block.get('lines', []):
                    line_text = ""
                    line_bbox = None
                    line_color_label = None
                    
                    for span in line.get('spans', []):
                        txt = span.get('text', '').strip()
                        if not txt:
                            continue
                        color = span.get('color', 0)
                        r = (color >> 16) & 0xFF
                        g = (color >> 8) & 0xFF
                        b = color & 0xFF
                        
                        col_lbl = self._get_rgb_color_label(r, g, b)
                        if col_lbl:
                            line_color_label = col_lbl
                            line_text += (" " if line_text else "") + txt
                            sb = span['bbox']
                            if line_bbox is None:
                                line_bbox = list(sb)
                            else:
                                line_bbox[0] = min(line_bbox[0], sb[0])
                                line_bbox[1] = min(line_bbox[1], sb[1])
                                line_bbox[2] = max(line_bbox[2], sb[2])
                                line_bbox[3] = max(line_bbox[3], sb[3])
                    
                    if line_bbox and line_text and line_color_label:
                        # Exclude single character grid tags (A, B, C...)
                        clean_line = line_text.strip()
                        if len(clean_line) <= 2 and clean_line.upper() in [
                            'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', '1', '2', '3', '4', '5', '6', '7', '8'
                        ]:
                            continue
                        colored_lines.append({
                            "text": clean_line,
                            "bbox": line_bbox,
                            "color": line_color_label
                        })
        
        # Cluster vertically and horizontally adjacent lines into whole comment blocks
        clusters = []
        for line in colored_lines:
            merged = False
            l_box = line["bbox"]
            l_col = line["color"]
            l_h = l_box[3] - l_box[1]
            
            for c in clusters:
                if c["color"] != l_col:
                    continue
                c_box = c["bbox"]
                
                # Check spatial proximity
                h_overlap = max(0, min(c_box[2], l_box[2]) - max(c_box[0], l_box[0]))
                h_dist = max(0, max(c_box[0], l_box[0]) - min(c_box[2], l_box[2]))
                v_dist = max(0, max(c_box[1], l_box[1]) - min(c_box[3], l_box[3]))
                
                # If lines are vertically close (within 2 line heights) and aligned/overlapping horizontally
                if v_dist <= max(20.0, l_h * 2.2) and (h_overlap > 0 or h_dist <= 35.0):
                    c["bbox"][0] = min(c_box[0], l_box[0])
                    c["bbox"][1] = min(c_box[1], l_box[1])
                    c["bbox"][2] = max(c_box[2], l_box[2])
                    c["bbox"][3] = max(c_box[3], l_box[3])
                    c["text"] += " " + line["text"]
                    merged = True
                    break
                    
            if not merged:
                clusters.append({
                    "color": l_col,
                    "bbox": list(l_box),
                    "text": line["text"]
                })
        
        regions = []
        for c in clusters:
            clean_txt = c["text"].strip()
            if len(clean_txt) == 0:
                continue
            pad_x = 2.0
            pad_y = 2.0
            r_rect = fitz.Rect(c["bbox"][0] - pad_x, c["bbox"][1] - pad_y, c["bbox"][2] + pad_x, c["bbox"][3] + pad_y)
            if self._is_title_block_or_status_stamp(page, r_rect, envelopes=envelopes):
                continue
            regions.append(
                BoundingBoxDTO(
                    x0=float(r_rect.x0),
                    y0=float(r_rect.y0),
                    x1=float(r_rect.x1),
                    y1=float(r_rect.y1),
                    page_number=page_num,
                    confidence=0.98,
                    label=c["color"]
                )
            )
        return regions

    def _detect_redline_regions(self, page: fitz.Page, page_num: int, envelopes: Optional[List[fitz.Rect]] = None) -> List[BoundingBoxDTO]:
        """Detect red, blue, and green vector markup (paths, clouds, arrows, leaders)"""
        raw_paths = []
        paths = page.get_drawings()
        
        for path in paths:
            is_red = False
            is_blue = False
            is_green = False
            
            # Check stroke color
            stroke_color = path.get('color')
            if stroke_color and len(stroke_color) >= 3:
                cr, cg, cb = int(stroke_color[0] * 255), int(stroke_color[1] * 255), int(stroke_color[2] * 255)
                if self._is_red_rgb(cr, cg, cb):
                    is_red = True
                elif self._is_blue_rgb(cr, cg, cb):
                    is_blue = True
                elif self._is_green_rgb(cr, cg, cb):
                    is_green = True
                    
            # Check fill color
            fill_color = path.get('fill')
            if not (is_red or is_blue or is_green) and fill_color and len(fill_color) >= 3:
                cr, cg, cb = int(fill_color[0] * 255), int(fill_color[1] * 255), int(fill_color[2] * 255)
                if self._is_red_rgb(cr, cg, cb):
                    is_red = True
                elif self._is_blue_rgb(cr, cg, cb):
                    is_blue = True
                elif self._is_green_rgb(cr, cg, cb):
                    is_green = True
                    
            if is_red or is_blue or is_green:
                rect = path['rect']
                w = rect[2] - rect[0]
                h = rect[3] - rect[1]
                # Filter out microscopic zero-length noise (< 2pt x 2pt)
                if w >= 2 and h >= 2:
                    col_label = "native_redline" if is_red else ("comment_blue" if is_blue else "comment_green")
                    raw_paths.append({
                        "bbox": [rect[0], rect[1], rect[2], rect[3]],
                        "color": col_label
                    })
        
        if not raw_paths:
            return []
            
        # Cluster adjacent vector segments (clouds, arrows) into cohesive markup boundaries
        clusters = []
        for item in raw_paths:
            merged = False
            ibox = item["bbox"]
            icol = item["color"]
            
            for c in clusters:
                if c["color"] != icol:
                    continue
                cbox = c["bbox"]
                # Spatial proximity within 30 pt
                dx = max(0.0, max(cbox[0], ibox[0]) - min(cbox[2], ibox[2]))
                dy = max(0.0, max(cbox[1], ibox[1]) - min(cbox[3], ibox[3]))
                if dx <= 30.0 and dy <= 30.0:
                    c["bbox"][0] = min(cbox[0], ibox[0])
                    c["bbox"][1] = min(cbox[1], ibox[1])
                    c["bbox"][2] = max(cbox[2], ibox[2])
                    c["bbox"][3] = max(cbox[3], ibox[3])
                    c["count"] += 1
                    merged = True
                    break
            if not merged:
                clusters.append({
                    "bbox": list(ibox),
                    "color": icol,
                    "count": 1
                })
        
        regions = []
        for c in clusters:
            cbox = c["bbox"]
            w = cbox[2] - cbox[0]
            h = cbox[3] - cbox[1]
            # Minimum substantial markup geometry (e.g. at least 10 pt wide/high or multiple clustered strokes)
            if (w >= 10 and h >= 6) or c["count"] >= 2:
                r_rect = fitz.Rect(cbox[0], cbox[1], cbox[2], cbox[3])
                if self._is_title_block_or_status_stamp(page, r_rect, envelopes=envelopes):
                    continue
                regions.append(
                    BoundingBoxDTO(
                        x0=float(cbox[0]),
                        y0=float(cbox[1]),
                        x1=float(cbox[2]),
                        y1=float(cbox[3]),
                        page_number=page_num,
                        confidence=0.90,
                        label=c["color"]
                    )
                )
        return regions

    # ========================================================================
    # METHOD 2: COLOR SEGMENTATION (RED, BLUE, GREEN MARKUP)
    # ========================================================================
    
    def _detect_by_color_segmentation(self, page: fitz.Page, page_num: int, envelopes: Optional[List[fitz.Rect]] = None) -> List[BoundingBoxDTO]:
        """
        Detect annotations using strict RGB + HSV color segmentation.
        Precisely targets Red, Blue, and Green reviewer comments while rejecting
        black CAD lines, neutral gray title blocks, and border lines.
        Accelerated with 72 DPI rendering and native C++/SIMD OpenCV vector operations.
        """
        try:
            detection_dpi = 72
            pix = page.get_pixmap(dpi=detection_dpi, alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            
            if pix.n == 3:
                img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            elif pix.n == 4:
                img_bgr = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
            else:
                img_bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            
            scale_factor = 72.0 / detection_dpi  # 1.0 at 72 DPI
            px_scale = detection_dpi / 72.0      # 1.0 at 72 DPI
            regions = []
            
            # Identify title block & review status stamp envelopes if not passed
            if envelopes is None:
                envelopes = self._get_title_block_and_stamp_envelopes(page)

            hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
            s = hsv[:, :, 1]
            
            # Ultra fast-path: if page has no color saturation (max s < 35), skip heavy contour search
            max_s_val = cv2.minMaxLoc(s)[1]
            if max_s_val < 35:
                return []

            b = img_bgr[:, :, 0]
            g = img_bgr[:, :, 1]
            r = img_bgr[:, :, 2]
            v = hsv[:, :, 2]
            
            h_px, w_px = img_bgr.shape[:2]
            max_area_px = int(h_px * w_px * 0.70)
            
            # ── 1. Strict Red Color Mask (OpenCV SIMD accelerated) ──
            # HSV Red: (h <= 12 or h >= 165) and s >= 45 and v >= 60
            hsv_red1 = cv2.inRange(hsv, np.array([0, 45, 60], dtype=np.uint8), np.array([12, 255, 255], dtype=np.uint8))
            hsv_red2 = cv2.inRange(hsv, np.array([165, 45, 60], dtype=np.uint8), np.array([180, 255, 255], dtype=np.uint8))
            hsv_red = cv2.bitwise_or(hsv_red1, hsv_red2)
            
            # RGB Red: r >= 115, r - max(g,b) >= 20, s >= 35, v >= 55
            max_gb = cv2.max(g, b)
            diff_r_gb = cv2.subtract(r, max_gb)
            r_ge_115 = cv2.inRange(r, 115, 255)
            diff_ge_20 = cv2.inRange(diff_r_gb, 20, 255)
            s_ge_35 = cv2.inRange(s, 35, 255)
            v_ge_55 = cv2.inRange(v, 55, 255)
            rgb_red = cv2.bitwise_and(cv2.bitwise_and(r_ge_115, diff_ge_20), cv2.bitwise_and(s_ge_35, v_ge_55))
            red_mask = cv2.bitwise_or(rgb_red, hsv_red)
            
            # ── 2. Strict Blue Color Mask (OpenCV SIMD accelerated) ──
            # HSV Blue: 95 <= h <= 135, s >= 60, v >= 60
            hsv_blue = cv2.inRange(hsv, np.array([95, 60, 60], dtype=np.uint8), np.array([135, 255, 255], dtype=np.uint8))
            # RGB Blue: b >= 115, b - max(r,g) >= 25, s >= 45
            max_rg = cv2.max(r, g)
            diff_b_rg = cv2.subtract(b, max_rg)
            b_ge_115 = cv2.inRange(b, 115, 255)
            diff_b_ge_25 = cv2.inRange(diff_b_rg, 25, 255)
            s_ge_45 = cv2.inRange(s, 45, 255)
            rgb_blue = cv2.bitwise_and(cv2.bitwise_and(b_ge_115, diff_b_ge_25), s_ge_45)
            blue_mask = cv2.bitwise_or(rgb_blue, hsv_blue)
            
            # ── 3. Strict Green Color Mask (OpenCV SIMD accelerated) ──
            # HSV Green: 35 <= h <= 85, s >= 60, v >= 60
            hsv_green = cv2.inRange(hsv, np.array([35, 60, 60], dtype=np.uint8), np.array([85, 255, 255], dtype=np.uint8))
            # RGB Green: g >= 110, g - max(r,b) >= 25, s >= 45
            max_rb = cv2.max(r, b)
            diff_g_rb = cv2.subtract(g, max_rb)
            g_ge_110 = cv2.inRange(g, 110, 255)
            diff_g_ge_25 = cv2.inRange(diff_g_rb, 25, 255)
            rgb_green = cv2.bitwise_and(cv2.bitwise_and(g_ge_110, diff_g_ge_25), s_ge_45)
            green_mask = cv2.bitwise_or(rgb_green, hsv_green)

            # Blank out title block and stamp envelopes so no contours are generated within them
            for env in envelopes:
                ex0 = max(0, int(env.x0 * px_scale))
                ey0 = max(0, int(env.y0 * px_scale))
                ex1 = min(w_px, int(env.x1 * px_scale))
                ey1 = min(h_px, int(env.y1 * px_scale))
                if ex1 > ex0 and ey1 > ey0:
                    red_mask[ey0:ey1, ex0:ex1] = 0
                    blue_mask[ey0:ey1, ex0:ex1] = 0
                    green_mask[ey0:ey1, ex0:ex1] = 0

            # SIMD Fast-path: if total colored markup pixels < 10, bypass morphology & contour finding
            total_colored_px = cv2.countNonZero(red_mask) + cv2.countNonZero(blue_mask) + cv2.countNonZero(green_mask)
            if total_colored_px < 10:
                return []

            color_masks = [
                ("comment_red", red_mask),
                ("comment_blue", blue_mask),
                ("comment_green", green_mask),
            ]
            
            kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (14, 8))
            kernel_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (6, 5))
            
            for col_lbl, raw_mask in color_masks:
                closed = cv2.morphologyEx(raw_mask, cv2.MORPH_CLOSE, kernel_close)
                clustered = cv2.dilate(closed, kernel_dilate, iterations=1)
                
                contours, _ = cv2.findContours(clustered, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for c in contours:
                    x, y, w, h = cv2.boundingRect(c)
                    area_px = w * h
                    
                    # Accept genuine annotations: minimum 30 px area, minimum 4px dimension, max_area_px
                    if 30 <= area_px <= max_area_px and max(w, h) >= 8 and min(w, h) >= 4:
                        # Reject long thin CAD drawing lines / border edges (aspect ratio > 20)
                        aspect_ratio = max(w, h) / float(min(w, h))
                        if aspect_ratio > 20.0:
                            continue
                            
                        # Verify colored pixel density inside the bounding box
                        roi_mask = raw_mask[y:y+h, x:x+w]
                        colored_pixels = cv2.countNonZero(roi_mask)
                        
                        # Perimeter-aware density check:
                        # Solid text blocks have area density, while revision clouds & callout boxes have perimeter density
                        perimeter_est = 2 * (w + h)
                        min_area_pixels = min(6, int(area_px * 0.02))
                        min_perimeter_pixels = max(5, int(perimeter_est * 0.12))
                        
                        if colored_pixels < min(min_area_pixels, min_perimeter_pixels) and colored_pixels < 6:
                            continue
                            
                        x0_pt = float(max(0, x - 2) * scale_factor)
                        y0_pt = float(max(0, y - 2) * scale_factor)
                        x1_pt = float((x + w + 2) * scale_factor)
                        y1_pt = float((y + h + 2) * scale_factor)
                        
                        r_rect = fitz.Rect(x0_pt, y0_pt, x1_pt, y1_pt)
                        if self._is_title_block_or_status_stamp(page, r_rect, envelopes=envelopes):
                            continue
                            
                        regions.append(
                            BoundingBoxDTO(
                                x0=x0_pt,
                                y0=y0_pt,
                                x1=x1_pt,
                                y1=y1_pt,
                                page_number=page_num,
                                confidence=0.92,
                                label=col_lbl
                            )
                        )
            
            logger.info(f"  Color segmentation found {len(regions)} verified regions on page {page_num}")
            return regions
            
        except Exception as e:
            logger.error(f"Error in color segmentation: {e}")
            return []

    # ========================================================================
    # METHOD 3: CONNECTED COMPONENTS ANALYSIS (REDUCED WEIGHT / COLOR GATED)
    # ========================================================================
    
    def _detect_by_connected_components(self, page: fitz.Page, page_num: int) -> List[BoundingBoxDTO]:
        """
        Detect candidate annotation regions using connected components analysis.
        Gated by non-black content check to prevent CAD drawing clutter.
        """
        try:
            pix = page.get_pixmap(dpi=self.default_dpi)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            
            if pix.n == 4:
                img_rgb = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
            else:
                img_rgb = img.copy()
            
            gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY_INV, 11, 2
            )
            
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            morph = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
            
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
                morph, connectivity=8, ltype=cv2.CV_32S
            )
            
            regions = []
            scale_factor = 72.0 / self.default_dpi
            
            for i in range(1, num_labels):
                x, y, w, h, area = stats[i]
                if 400 <= area <= 35000 and 15 <= w <= 450 and 15 <= h <= 450:
                    aspect_ratio = max(w, h) / float(min(w, h))
                    if aspect_ratio < 8.0:
                        # Verify presence of red/blue/green color in this component
                        roi = img_rgb[y:y+h, x:x+w]
                        rr = roi[:, :, 0].astype(int)
                        gg = roi[:, :, 1].astype(int)
                        bb = roi[:, :, 2].astype(int)
                        
                        has_color = (
                            np.any((rr >= 120) & ((rr - np.maximum(gg, bb)) >= 28)) or
                            np.any((bb >= 110) & ((bb - np.maximum(rr, gg)) >= 28)) or
                            np.any((gg >= 100) & ((gg - np.maximum(rr, bb)) >= 28))
                        )
                        if has_color:
                            regions.append(
                                BoundingBoxDTO(
                                    x0=float(x * scale_factor),
                                    y0=float(y * scale_factor),
                                    x1=float((x + w) * scale_factor),
                                    y1=float((y + h) * scale_factor),
                                    page_number=page_num,
                                    confidence=0.70,
                                    label="connected_component"
                                )
                            )
            return regions
        except Exception as e:
            logger.error(f"Error in connected components: {e}")
            return []

    # ========================================================================
    # METHOD 4: ADVANCED REGION DETECTION (COLOR GATED)
    # ========================================================================
    
    def _detect_by_region_proposals(self, page: fitz.Page, page_num: int, envelopes: Optional[List[fitz.Rect]] = None) -> List[BoundingBoxDTO]:
        """Color-gated region proposals to avoid full drawing clutter."""
        # Color segmentation and native methods provide superior precision for engineering markups
        return self._detect_by_color_segmentation(page, page_num, envelopes=envelopes)

    # ========================================================================
    # UTILITY METHODS (DEDUPLICATION & MERGING)
    # ========================================================================
    
    def _deduplicate_regions(self, regions: List[BoundingBoxDTO], iou_threshold: float = 0.40) -> List[BoundingBoxDTO]:
        """
        Remove duplicate regions and consolidate multi-line comment text + revision clouds.
        Strictly preserves distinct red, blue, and green comments.
        """
        if not regions:
            return []
        
        def rank_confidence(r: BoundingBoxDTO) -> float:
            score = r.confidence
            lbl = r.label.lower()
            if "red" in lbl:
                score += 0.25
            elif "blue" in lbl:
                score += 0.25
            elif "green" in lbl:
                score += 0.25
            return score
            
        sorted_regions = sorted(regions, key=rank_confidence, reverse=True)
        keep = []
        
        for region in sorted_regions:
            reg_lbl = region.label.lower()
            reg_color = "red" if ("red" in reg_lbl) else ("blue" if ("blue" in reg_lbl) else ("green" if ("green" in reg_lbl) else "other"))
            
            is_duplicate = False
            for kept_region in keep:
                kept_lbl = kept_region.label.lower()
                kept_color = "red" if ("red" in kept_lbl) else ("blue" if ("blue" in kept_lbl) else ("green" if ("green" in kept_lbl) else "other"))
                
                # Check spatial containment and overlap
                c_reg_in_kept = self._calculate_containment(region, kept_region)
                c_kept_in_reg = self._calculate_containment(kept_region, region)
                iou = self._calculate_iou(region, kept_region)
                
                # Different colors are not merged unless one literally encapsulates the other (> 85%)
                if reg_color != kept_color and (reg_color in ("red", "blue", "green") and kept_color in ("red", "blue", "green")):
                    if c_reg_in_kept > 0.85 or c_kept_in_reg > 0.85:
                        is_duplicate = True
                        break
                    continue
                
                # If candidate is contained or overlapping with an existing kept comment of the same color
                if c_reg_in_kept > 0.30 or c_kept_in_reg > 0.30 or iou > iou_threshold:
                    # Encompass the full comment + markup area
                    kept_region.x0 = min(kept_region.x0, region.x0)
                    kept_region.y0 = min(kept_region.y0, region.y0)
                    kept_region.x1 = max(kept_region.x1, region.x1)
                    kept_region.y1 = max(kept_region.y1, region.y1)
                    if kept_color == "other" and reg_color in ("red", "blue", "green"):
                        kept_region.label = region.label
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                keep.append(region)
        
        return keep
    
    def _calculate_containment(self, small_box: BoundingBoxDTO, large_box: BoundingBoxDTO) -> float:
        """Calculate what fraction of small_box is contained inside large_box."""
        if small_box.x1 <= large_box.x0 or large_box.x1 <= small_box.x0 or small_box.y1 <= large_box.y0 or large_box.y1 <= small_box.y0:
            return 0.0
        xi_min = max(small_box.x0, large_box.x0)
        yi_min = max(small_box.y0, large_box.y0)
        xi_max = min(small_box.x1, large_box.x1)
        yi_max = min(small_box.y1, large_box.y1)
        inter_area = max(0.0, xi_max - xi_min) * max(0.0, yi_max - yi_min)
        small_area = (small_box.x1 - small_box.x0) * (small_box.y1 - small_box.y0)
        return (inter_area / small_area) if small_area > 0 else 0.0

    def _calculate_iou(self, box1: BoundingBoxDTO, box2: BoundingBoxDTO) -> float:
        """Calculate Intersection over Union between two bounding boxes with fast rejection."""
        if box1.x1 <= box2.x0 or box2.x1 <= box1.x0 or box1.y1 <= box2.y0 or box2.y1 <= box1.y0:
            return 0.0
            
        xi_min = max(box1.x0, box2.x0)
        yi_min = max(box1.y0, box2.y0)
        xi_max = min(box1.x1, box2.x1)
        yi_max = min(box1.y1, box2.y1)
        
        inter_width = max(0.0, xi_max - xi_min)
        inter_height = max(0.0, yi_max - yi_min)
        inter_area = inter_width * inter_height
        if inter_area <= 0.0:
            return 0.0
        
        box1_area = (box1.x1 - box1.x0) * (box1.y1 - box1.y0)
        box2_area = (box2.x1 - box2.x0) * (box2.y1 - box2.y0)
        union_area = box1_area + box2_area - inter_area
        
        return inter_area / union_area if union_area > 0 else 0.0


