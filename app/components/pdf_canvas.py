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
    "Approved": ("#4ADE80", 0.25),
    "Pending":  ("#FBBF24", 0.25),
    "Flagged":  ("#F87171", 0.30),
    "Rejected": ("#F87171", 0.20),
}

# Annotation region colors by detection method/label
_ANNOTATION_COLORS: dict[str, tuple[str, float]] = {
    # Redline and comment markups
    "comment_red": ("#EF4444", 0.25),        # Red
    "native_redline": ("#EF4444", 0.25),     # Red
    "redline": ("#EF4444", 0.25),            # Red
    "comment_orange": ("#F97316", 0.25),     # Orange
    "comment_yellow": ("#FBBF24", 0.20),     # Yellow
    "comment_green": ("#10B981", 0.20),      # Green
    "comment_cyan": ("#06B6D4", 0.25),       # Cyan
    "comment_blue": ("#3B82F6", 0.25),       # Blue
    "native_blue_markup": ("#3B82F6", 0.25), # Blue
    "comment_purple": ("#8B5CF6", 0.25),     # Purple
    "comment_magenta": ("#D946EF", 0.25),    # Magenta
    "highlight": ("#FEF08A", 0.35),          # Semi-transparent yellow
    "marker": ("#F59E0B", 0.25),             # Amber marker
    "markup_without_text": ("#94A3B8", 0.20),# Slate / Gray
    
    # Native methods (high confidence)
    "native_annotation": ("#3B82F6", 0.15),  # Blue
    "native_text_block": ("#8B5CF6", 0.15),  # Purple
    
    # Detection methods (lower confidence)
    "color_segment": ("#10B981", 0.15),      # Green
    "connected_component": ("#F59E0B", 0.12),# Orange
    "mser_region": ("#EC4899", 0.12),        # Pink
    "edge_region": ("#06B6D4", 0.12),        # Cyan
    "blob": ("#6366F1", 0.12),               # Indigo
    
    # Cross marks and plain strikeout lines
    "cross_mark": ("#F59E0B", 0.25),         # Amber/Orange for cross mark
    "plane_line": ("#EC4899", 0.25),         # Pink/Rose for plane/strikeout line
    
    # Default
    "default": ("#EF4444", 0.20),            # Red default for comment markup
}

# ── Unique Extraction Color Palette ──────────────────────────────────────────
# Distinct, accessible colors for individual comment extractions
# so every extraction and its identifying number badge share a unique matching color
EXTRACTION_PALETTE: list[str] = [
    "#D81C60",  # 1. Vibrant Magenta / Crimson
    "#1E87E5",  # 2. Azure / Cobalt Blue
    "#19BC9B",  # 3. Turquoise / Emerald Teal
    "#F29B11",  # 4. Bright Warm Amber / Gold
    "#9938D8",  # 5. Vivid Purple / Violet
    "#E54C19",  # 6. Deep Sunset Orange / Vermilion
    "#0CA54C",  # 7. Forest Green
    "#26ADE0",  # 8. Electric Cyan / Sky Blue
    "#CC2699",  # 9. Fuchsia Pink
    "#667FE5",  # 10. Cornflower / Royal Periwinkle
    "#D8720C",  # 11. Bronze / Burnt Orange
    "#198C8C",  # 12. Deep Sea Blue / Dark Cyan
    "#E63946",  # 13. Coral Red
    "#8338EC",  # 14. Deep Iris
    "#3A86FF",  # 15. Bright Dodger Blue
    "#FB5607",  # 16. International Orange
    "#06D6A0",  # 17. Mint Green
    "#FF006E",  # 18. Neon Hot Pink
]


def get_extraction_color(item: Any, index: Optional[int] = None) -> str:
    """
    Return a consistent, unique color hex for an extraction comment or annotation.
    Ensures that an extraction box and its number badge share the exact same unique color.
    """
    if index is not None and index >= 0:
        return EXTRACTION_PALETTE[index % len(EXTRACTION_PALETTE)]

    cid = ""
    if isinstance(item, dict):
        cid = str(item.get("id") or "")
    elif item is not None:
        cid = str(getattr(item, "id", "") or "")

    # If ID ends with or contains numbers, use that to index into palette
    digits = "".join(ch for ch in cid if ch.isdigit())
    if digits:
        try:
            num = int(digits)
            # 1-indexed to 0-indexed
            return EXTRACTION_PALETTE[(num - 1) % len(EXTRACTION_PALETTE)]
        except Exception:
            pass

    if cid:
        import hashlib
        idx = int(hashlib.md5(cid.encode("utf-8")).hexdigest(), 16) % len(EXTRACTION_PALETTE)
        return EXTRACTION_PALETTE[idx]

    return EXTRACTION_PALETTE[0]



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

    for i, c in enumerate(comments):
        if isinstance(c, dict):
            status = c.get("status", "Pending")
            bbox   = c.get("bbox", (0, 0, 0, 0))
            label  = c.get("label", "")
            cid    = c.get("id", "")
        else:
            status = getattr(c, "status", "Pending")
            bbox   = getattr(c, "bbox", (0, 0, 0, 0))
            label  = getattr(c, "label", "")
            cid    = getattr(c, "id", "")

        x     = int(bbox[0] * width)
        y     = int(bbox[1] * height)
        w     = int(bbox[2] * width)
        h_box = int(bbox[3] * height)

        if w <= 0 or h_box <= 0:
            continue

        # Use distinct unique color for each extraction matching its badge number
        col_hex = get_extraction_color(c, index=i)

        fill_color = QColor(col_hex)
        fill_color.setAlphaF(0.25)
        p.setBrush(QBrush(fill_color))

        border_color = QColor(col_hex)
        border_color.setAlphaF(0.9)
        p.setPen(QPen(border_color, 2.0))

        p.drawRect(x, y, w, h_box)

        # Draw matching numbered badge for this extraction in the exact same unique color
        digits = "".join(ch for ch in str(cid) if ch.isdigit())
        num_str = f"#{digits}" if digits else f"#{i + 1}"

        badge_w = 32 if len(num_str) <= 3 else 42
        badge_h = 18
        badge_x = x
        badge_y = max(0, y - badge_h)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(col_hex)))
        p.drawRoundedRect(badge_x, badge_y, badge_w, badge_h, 3, 3)

        p.setPen(QPen(QColor("#FFFFFF"), 1))
        p.setFont(QFont("Cascadia Code", 8, QFont.Weight.Bold))
        p.drawText(QRect(badge_x, badge_y, badge_w, badge_h), Qt.AlignmentFlag.AlignCenter, num_str)

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

    for i, c in enumerate(render_comments):
        # Support both mock dataclass objects and normalised display dicts
        if isinstance(c, dict):
            status = c.get("status", "Pending")
            bbox   = c.get("bbox", (0, 0, 0, 0))
            label  = c.get("label", "")
            cid    = c.get("id", "")
        else:
            status = getattr(c, "status", "Pending")
            bbox   = getattr(c, "bbox", (0, 0, 0, 0))
            label  = getattr(c, "label", "")
            cid    = getattr(c, "id", "")

        x     = int(bbox[0] * width)
        y     = int(bbox[1] * height)
        w     = int(bbox[2] * width)
        h_box = int(bbox[3] * height)

        if w <= 0 or h_box <= 0:
            continue

        # Use unique color for each extraction matching its badge number
        col_hex = get_extraction_color(c, index=i)

        fill_color = QColor(col_hex)
        fill_color.setAlphaF(0.25)
        p.setBrush(QBrush(fill_color))

        border_color = QColor(col_hex)
        border_color.setAlphaF(0.9)
        p.setPen(QPen(border_color, 2.0))

        p.drawRect(x, y, w, h_box)

        # Draw matching numbered badge for this extraction
        digits = "".join(ch for ch in str(cid) if ch.isdigit())
        num_str = f"#{digits}" if digits else f"#{i + 1}"

        badge_w = 32 if len(num_str) <= 3 else 42
        badge_h = 18
        badge_x = x
        badge_y = max(0, y - badge_h)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(col_hex)))
        p.drawRoundedRect(badge_x, badge_y, badge_w, badge_h, 3, 3)

        p.setPen(QPen(QColor("#FFFFFF"), 1))
        p.setFont(QFont("Cascadia Code", 8, QFont.Weight.Bold))
        p.drawText(QRect(badge_x, badge_y, badge_w, badge_h), Qt.AlignmentFlag.AlignCenter, num_str)

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

        # Use unique color for each extraction matching its badge number
        col_hex = get_extraction_color(comment)
        self.col_hex = col_hex

        fill = QColor(col_hex)
        fill.setAlphaF(0.20)
        border = QColor(col_hex)
        border.setAlphaF(0.9)

        self.setData(0, cid)
        self.setBrush(QBrush(fill))
        self.setPen(QPen(border, 2.0))
        self.setToolTip(f"{cid}: {str(ocr_text)[:60]}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptHoverEvents(True)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        # Draw matching numbered badge for this extraction in the exact same color
        cid = str(self.data(0) or "")
        digits = "".join(ch for ch in cid if ch.isdigit())
        num_str = f"#{digits}" if digits else "#"

        rect = self.rect()
        badge_w = 30 if len(num_str) <= 3 else 40
        badge_h = 16
        badge_x = rect.x()
        badge_y = max(0.0, rect.y() - badge_h)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        badge_col = QColor(getattr(self, "col_hex", "#3B82F6"))
        painter.setBrush(QBrush(badge_col))
        painter.drawRoundedRect(QRectF(badge_x, badge_y, badge_w, badge_h), 3, 3)

        painter.setPen(QPen(QColor("#FFFFFF"), 1))
        painter.setFont(QFont("Cascadia Code", 8, QFont.Weight.Bold))
        painter.drawText(QRectF(badge_x, badge_y, badge_w, badge_h), Qt.AlignmentFlag.AlignCenter, num_str)
        painter.restore()

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
            pen.setWidth(2.0)
        self.setPen(pen)
        super().hoverLeaveEvent(e)
