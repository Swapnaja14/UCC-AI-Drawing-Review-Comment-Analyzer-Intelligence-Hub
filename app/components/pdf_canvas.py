"""
pdf_canvas.py — PDF page rendering and annotation canvas utilities.

Provides:
    make_page_pixmap(width, height, comments=None) -> QPixmap
        Renders a simulated engineering drawing page with title block,
        grid lines, and comment bounding boxes.

    draw_bounding_boxes(pixmap, comments=None) -> QPixmap
        Draws semi-transparent bounding-box rectangles onto a QPixmap using QPainter.
    
    draw_annotation_regions(pixmap, annotation_regions, page_width_pt, page_height_pt) -> QPixmap
        Draws detected annotation regions from annotation detection service.

    BBoxItem(QGraphicsRectItem)
        Hover-highlighted bounding-box overlay for an annotated comment
        on a QGraphicsScene canvas.
"""
# ARCHITECTURE WARNING:
# This module previously imported mock_data at module level and used
# md.COMMENTS[:5] inside make_page_pixmap(). This has been refactored so
# make_page_pixmap() accepts an optional 'comments' parameter.
#
# When comment_viewer_screen.py and review_screen.py are integrated with
# database-sourced comments, callers must pass real comment data (normalised
# display dicts from AppController.normalise_comment()) or an empty list.
#
# BOUNDING BOX NOTE:
# The mock_data Comment.bbox format is (x, y, width, height) normalised 0-1.
# The database CommentModel stores (bbox_x0, bbox_y0, bbox_x1, bbox_y1) in
# absolute PDF point coordinates.
# These are NOT interchangeable. See docs/AGENT_INTEGRATION_GUIDELINES.md
# WARNING-001 and WARNING-009 for the conversion formula.
#
# This warning is for all development agents — do not silently mix coordinate
# systems when passing comments to make_page_pixmap() or BBoxItem.
from __future__ import annotations
from typing import List, Any, Optional
from PySide6.QtWidgets import QGraphicsRectItem
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QPixmap, QPainter, QPen, QBrush, QColor, QFont,
)

from app import mock_data as md


# ── Status-to-colour mapping ──────────────────────────────────────────────────

_BOX_COLORS: dict[str, tuple[str, float]] = {
    "Approved": ("#4EDEA3", 0.25),
    "Pending":  ("#ADC6FF", 0.25),
    "Flagged":  ("#FFB95F", 0.30),
    "Rejected": ("#FFB4AB", 0.20),
}

# Annotation region colors by detection method/label
_ANNOTATION_COLORS: dict[str, tuple[str, float]] = {
    # Redline and comment markups
    "comment_red": ("#EF4444", 0.25),        # Red
    "native_redline": ("#EF4444", 0.25),     # Red
    "redline": ("#EF4444", 0.25),            # Red
    "comment_yellow": ("#FBBF24", 0.20),     # Yellow
    "comment_blue": ("#3B82F6", 0.25),       # Blue
    "native_blue_markup": ("#3B82F6", 0.25), # Blue
    "comment_green": ("#10B981", 0.20),      # Green
    
    # Native methods (high confidence)
    "native_annotation": ("#3B82F6", 0.15),  # Blue
    "native_text_block": ("#8B5CF6", 0.15),  # Purple
    
    # Detection methods (lower confidence)
    "color_segment": ("#10B981", 0.15),      # Green
    "connected_component": ("#F59E0B", 0.12),# Orange
    "mser_region": ("#EC4899", 0.12),        # Pink
    "edge_region": ("#06B6D4", 0.12),        # Cyan
    "blob": ("#6366F1", 0.12),               # Indigo
    
    # Default
    "default": ("#EF4444", 0.20),            # Red default for comment markup
}


# ── Bounding box painter ───────────────────────────────────────────────────

def draw_bounding_boxes(
    pixmap: QPixmap,
    comments: Optional[List[Any]] = None,
) -> QPixmap:
    """
    Draw semi-transparent bounding box rectangles onto a QPixmap using QPainter.

    Parameters
    ----------
    pixmap : QPixmap
        The target pixmap to draw rectangles on.
    comments : list, optional
        List of comment objects or dicts with normalized 'bbox' coordinates (0..1).

    Returns
    -------
    QPixmap
        The pixmap with bounding boxes drawn.
    """
    if not comments:
        return pixmap

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    width = pixmap.width()
    height = pixmap.height()

    for c in comments:
        if isinstance(c, dict):
            status = c.get("status", "Pending")
            bbox   = c.get("bbox", (0, 0, 0, 0))
            label  = c.get("label", "")
        else:
            status = getattr(c, "status", "Pending")
            bbox   = getattr(c, "bbox", (0, 0, 0, 0))
            label  = getattr(c, "label", "")

        x     = int(bbox[0] * width)
        y     = int(bbox[1] * height)
        w     = int(bbox[2] * width)
        h_box = int(bbox[3] * height)

        if "blue" in label.lower() or label in ("comment_blue", "native_blue_markup"):
            color = QColor("#3B82F6")
        elif "red" in label.lower() or label in ("redline", "comment_red", "native_redline") or status in ("Flagged", "Rejected"):
            color = QColor("#EF4444")
        elif status == "Approved":
            color = QColor("#4ADE80")
        elif "yellow" in label.lower():
            color = QColor("#FBBF24")
        elif "green" in label.lower():
            color = QColor("#10B981")
        else:
            color = QColor("#EF4444")

        fill_color = QColor(color)
        fill_color.setAlphaF(0.25)
        p.setBrush(QBrush(fill_color))

        border_color = QColor(color)
        border_color.setAlphaF(0.9)
        p.setPen(QPen(border_color, 1.5))

        p.drawRect(x, y, w, h_box)

    p.end()
    return pixmap


def draw_annotation_regions(
    pixmap: QPixmap,
    annotation_regions: Optional[List[Any]] = None,
    page_width_pt: float = 612.0,
    page_height_pt: float = 792.0,
) -> QPixmap:
    """
    Draw detected annotation regions from annotation detection service.
    
    Parameters
    ----------
    pixmap : QPixmap
        The target pixmap to draw rectangles on.
    annotation_regions : list, optional
        List of BoundingBoxDTO objects from annotation detection service.
        Each region has: x0, y0, x1, y1 (PDF coordinates in points), 
        confidence, and label.
    page_width_pt : float
        Original PDF page width in points (for coordinate conversion).
    page_height_pt : float
        Original PDF page height in points (for coordinate conversion).
    
    Returns
    -------
    QPixmap
        The pixmap with annotation regions drawn.
    
    Notes
    -----
    Annotation regions use absolute PDF coordinates (x0, y0, x1, y1) in points.
    These are converted to pixel coordinates based on the pixmap dimensions.
    
    Color coding by detection method:
    - Blue: Native PDF annotations (high confidence)
    - Purple: Text blocks
    - Red: Redline markup
    - Green: Color segmentation detections
    - Orange: Connected components
    - Others: Various detection methods
    """
    if not annotation_regions:
        return pixmap
    
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Calculate scaling factors from PDF points to pixmap pixels
    width_px = pixmap.width()
    height_px = pixmap.height()
    scale_x = width_px / page_width_pt if page_width_pt > 0 else 1.0
    scale_y = height_px / page_height_pt if page_height_pt > 0 else 1.0
    
    for region in annotation_regions:
        # Get region coordinates (PDF points)
        if hasattr(region, 'x0'):
            x0, y0, x1, y1 = region.x0, region.y0, region.x1, region.y1
            confidence = getattr(region, 'confidence', 1.0)
            label = getattr(region, 'label', 'default')
        else:
            # Fallback for dict format
            x0 = region.get('x0', 0)
            y0 = region.get('y0', 0)
            x1 = region.get('x1', 0)
            y1 = region.get('y1', 0)
            confidence = region.get('confidence', 1.0)
            label = region.get('label', 'default')
        
        # Convert PDF points to pixel coordinates
        x_px = int(x0 * scale_x)
        y_px = int(y0 * scale_y)
        w_px = int((x1 - x0) * scale_x)
        h_px = int((y1 - y0) * scale_y)
        
        # Skip invalid regions
        if w_px <= 0 or h_px <= 0:
            continue
        
        # Get color based on detection method/label
        lbl_lower = str(label).lower()
        if "blue" in lbl_lower:
            color_hex, base_alpha = "#3B82F6", 0.25
        elif "red" in lbl_lower:
            color_hex, base_alpha = "#EF4444", 0.25
        elif "yellow" in lbl_lower:
            color_hex, base_alpha = "#FBBF24", 0.20
        elif "green" in lbl_lower:
            color_hex, base_alpha = "#10B981", 0.20
        else:
            color_hex, base_alpha = _ANNOTATION_COLORS.get(label, _ANNOTATION_COLORS.get(lbl_lower, _ANNOTATION_COLORS["default"]))

        
        # Adjust alpha based on confidence
        # High confidence = more opaque, low confidence = more transparent
        adjusted_alpha = base_alpha * (0.5 + 0.5 * confidence)
        
        # Draw filled rectangle
        fill_color = QColor(color_hex)
        fill_color.setAlphaF(adjusted_alpha)
        p.setBrush(QBrush(fill_color))
        
        # Draw border (slightly more opaque)
        border_color = QColor(color_hex)
        border_width = 2.0 if confidence >= 0.8 else 1.0
        border_color.setAlphaF(min(1.0, adjusted_alpha * 1.5))
        p.setPen(QPen(border_color, border_width))
        
        p.drawRect(x_px, y_px, w_px, h_px)
        
        # Draw confidence score for low-confidence regions (helps debugging)
        if confidence < 0.7:
            p.setFont(QFont("Arial", 7))
            text_color = QColor(color_hex)
            text_color.setAlphaF(0.8)
            p.setPen(QPen(text_color, 1))
            p.drawText(x_px + 2, y_px + 10, f"{confidence:.0%}")
    
    p.end()
    return pixmap


# ── Page pixmap factory ───────────────────────────────────────────────────────

def make_page_pixmap(
    width: int = 700,
    height: int = 900,
    comments: Optional[List[Any]] = None,
) -> QPixmap:
    """
    Render a simulated engineering drawing page.

    Draws a white sheet with:
    - A grey title block at the bottom.
    - A double-line drawing border.
    - Light grid lines.
    - Coloured comment bounding boxes.
    - Title block text (drawing number, title, scale, date).

    Parameters
    ----------
    width, height:
        Pixel dimensions of the generated pixmap (default 700 × 900).
    comments:
        Optional list of comment objects/dicts to render as bounding boxes.
        Each item must expose .status and .bbox (mock objects) OR be a
        normalised display dict with keys "status" and "bbox"
        (x_norm, y_norm, w_norm, h_norm in 0-1 range).
        If None, falls back to md.COMMENTS[:5] for backward compatibility
        during development. Pass an empty list [] to render no bounding boxes.

    Returns
    -------
    QPixmap
        Ready-to-use pixmap for display in a QGraphicsView or QListWidget.
    """
    pm = QPixmap(width, height)
    pm.fill(QColor("#FFFFFF"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Title block
    p.setPen(QPen(QColor("#CCCCCC"), 1))
    p.setBrush(QColor("#F5F6F8"))
    p.drawRect(0, height - 100, width, 100)

    # Drawing border
    p.setPen(QPen(QColor("#999999"), 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(20, 20, width - 40, height - 40)

    # Grid lines
    p.setPen(QPen(QColor("#888888"), 1))
    for y_off in range(80, height - 120, 40):
        p.drawLine(40, y_off, width - 40, y_off)
    for x_off in range(80, width - 40, 60):
        p.drawLine(x_off, 40, x_off, height - 120)

    # Comment bounding boxes
    # Real comments are passed as normalised display dicts (from AppController.normalise_comment()).
    # If comments is None or empty, no dummy bounding boxes are drawn.
    # Normalised bbox format: (x_norm, y_norm, w_norm, h_norm) in range 0-1.
    render_comments = comments if comments is not None else []

    for c in render_comments:
        # Support both mock dataclass objects and normalised display dicts
        if isinstance(c, dict):
            status = c.get("status", "Pending")
            bbox   = c.get("bbox", (0, 0, 0, 0))
            label  = c.get("label", "")
        else:
            status = getattr(c, "status", "Pending")
            bbox   = getattr(c, "bbox", (0, 0, 0, 0))
            label  = getattr(c, "label", "")

        x     = int(bbox[0] * width)
        y     = int(bbox[1] * height)
        w     = int(bbox[2] * width)
        h_box = int(bbox[3] * height)

        if "blue" in label.lower() or label in ("comment_blue", "native_blue_markup"):
            color = QColor("#3B82F6")
        elif "red" in label.lower() or label in ("redline", "comment_red", "native_redline") or status in ("Flagged", "Rejected"):
            color = QColor("#EF4444")
        elif status == "Approved":
            color = QColor("#4ADE80")
        elif "yellow" in label.lower():
            color = QColor("#FBBF24")
        elif "green" in label.lower():
            color = QColor("#10B981")
        else:
            color = QColor("#EF4444")

        fill_color = QColor(color)
        fill_color.setAlphaF(0.25)
        p.setBrush(QBrush(fill_color))

        border_color = QColor(color)
        border_color.setAlphaF(0.9)
        p.setPen(QPen(border_color, 1.5))

        p.drawRect(x, y, w, h_box)

    # Title block text
    p.setPen(QPen(QColor("#333333"), 1))
    p.setFont(QFont("Cascadia Code", 8))
    p.drawText(
        30, height - 80,
        "Drawing No: UCC-E-101   Rev: A   Project: UCC Site-4 Expansion",
    )
    p.drawText(
        30, height - 60,
        "Title: Piping & Instrumentation Diagram — Unit 4-A",
    )
    p.drawText(
        30, height - 40,
        "Scale: 1:50   Sheet: 1 of 3   Date: 2026-07-28",
    )
    p.end()
    return pm


# ── BBoxItem ──────────────────────────────────────────────────────────────────

class BBoxItem(QGraphicsRectItem):
    """
    Hoverable, coloured bounding-box overlay for a comment annotation.

    Colour is keyed to the comment's status. The border thickens on
    hover to provide visual feedback. Supports on_click callback.
    """

    def __init__(self, comment, rect: QRectF, parent=None, on_click=None):
        super().__init__(rect, parent)
        self.comment = comment
        self.on_click = on_click

        if isinstance(comment, dict):
            label = comment.get('label', '')
            status = comment.get('status', 'Pending')
            ocr_text = comment.get('ocr_text', '')
            cid = comment.get('id', '')
        else:
            label = getattr(comment, 'label', '')
            status = getattr(comment, 'status', 'Pending')
            ocr_text = getattr(comment, 'ocr_text', '')
            cid = getattr(comment, 'id', '')

        if "blue" in str(label).lower() or str(label) in ("comment_blue", "native_blue_markup"):
            col_hex, alpha = ("#3B82F6", 0.25)
        elif "red" in str(label).lower() or str(label) in ("redline", "comment_red", "native_redline") or status in ("Flagged", "Rejected"):
            col_hex, alpha = ("#EF4444", 0.25)
        elif status == "Approved":
            col_hex, alpha = ("#4ADE80", 0.25)
        elif "yellow" in str(label).lower():
            col_hex, alpha = ("#FBBF24", 0.25)
        elif "green" in str(label).lower():
            col_hex, alpha = ("#10B981", 0.25)
        else:
            col_hex, alpha = _BOX_COLORS.get(status, ("#EF4444", 0.25))

        fill = QColor(col_hex)
        fill.setAlphaF(alpha)
        border = QColor(col_hex)
        border.setAlphaF(0.9)

        self.setData(0, cid)
        self.setBrush(QBrush(fill))
        self.setPen(QPen(border, 1.5))
        self.setToolTip(f"{cid}: {str(ocr_text)[:60]}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptHoverEvents(True)

    def mousePressEvent(self, e) -> None:
        if self.on_click and self.data(0):
            self.on_click(str(self.data(0)))
        super().mousePressEvent(e)

    def hoverEnterEvent(self, e) -> None:
        pen = self.pen()
        pen.setWidth(3)
        self.setPen(pen)
        super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e) -> None:
        pen = self.pen()
        if self.zValue() < 5:
            pen.setWidth(1.5)
        self.setPen(pen)
        super().hoverLeaveEvent(e)
