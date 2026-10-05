"""
comment_table.py — Custom cell delegates for the comment data tables.

Provides:
    ConfidenceDelegate
        Renders a confidence float (0–1) as a threshold-coloured progress
        bar with a centred percentage label.

    StatusDelegate
        Renders a status string as a rounded pill with status-keyed colours.

    CategoryDelegate
        Renders a category string as a rounded pill with category-keyed colours.

    ClassificationMethodDelegate
        Renders an AI vs. Fallback classification method pill badge (AI Model, Rule Fallback, Manual).

    EngineDelegate
        Renders an OCR engine name as an attributed pill badge (Tesseract, Native, OCR Failed).

    PageDelegate
        Renders a drawing page indicator as a compact styled chip.
"""
from __future__ import annotations
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtCore import Qt, QModelIndex, QRect


class ConfidenceDelegate(QStyledItemDelegate):
    """
    Cell delegate that renders a confidence score as a coloured bar + text.

    The cell must store a ``float`` in ``Qt.ItemDataRole.UserRole``.
    Colour thresholds: ≥ 0.90 → green, ≥ 0.70 → amber, < 0.70 → red.
    """

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        val = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(val, float):
            super().paint(painter, option, index)
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if option.state & QStyle.StateFlag.State_Selected:   # selected
            painter.fillRect(option.rect, QColor("#3E9BFF22"))

        # Track
        bar = QRect(
            option.rect.x() + 8,
            option.rect.y() + 18,
            option.rect.width() - 16,
            8,
        )
        painter.setBrush(QColor("#3A3C42"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bar, 4, 4)

        # Fill
        fill_w = int(bar.width() * val)
        if fill_w > 0:
            fill_c = (
                "#4ADE80" if val >= 0.9
                else "#FBBF24" if val >= 0.7
                else "#F87171"
            )
            painter.setBrush(QColor(fill_c))
            painter.drawRoundedRect(
                QRect(bar.x(), bar.y(), fill_w, bar.height()), 4, 4
            )

        painter.setPen(QColor("#F2F3F5"))
        painter.setFont(QFont("Cascadia Code", 11))
        painter.drawText(
            option.rect, Qt.AlignmentFlag.AlignCenter, f"{int(val * 100)}%"
        )


class StatusDelegate(QStyledItemDelegate):
    """
    Cell delegate that renders a status string as a coloured pill badge.

    Supported statuses: Pending, Approved, Rejected, Flagged.
    """

    _STATUS_COLORS: dict[str, tuple[str, str]] = {
        "Pending":    ("#A6A9B1", "#3A3C42"),
        "Approved":   ("#4ADE80", "#1a3d26"),
        "Rejected":   ("#F87171", "#3d1a1a"),
        "Flagged":    ("#FBBF24", "#3d2e0a"),
        "OCR Failed": ("#F87171", "#3d1a1a"),
        "Failed":     ("#F87171", "#3d1a1a"),
    }

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        status = index.data()
        if not status:
            super().paint(painter, option, index)
            return

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor("#3E9BFF22"))

        text_c, bg_c = self._STATUS_COLORS.get(status, ("#A6A9B1", "#3A3C42"))

        # Pill: at least 100 px wide, but never wider than the cell minus 16 px padding
        pill_h = 24
        pill_w = min(max(100, len(status) * 12), option.rect.width() - 16)
        x = option.rect.x() + (option.rect.width() - pill_w) // 2
        y = option.rect.y() + (option.rect.height() - pill_h) // 2

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(bg_c))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(x, y, pill_w, pill_h, 5, 5)
        painter.setPen(QColor(text_c))
        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        painter.drawText(
            QRect(x, y, pill_w, pill_h),
            Qt.AlignmentFlag.AlignCenter,
            status.upper(),
        )


class CategoryDelegate(QStyledItemDelegate):
    """
    Cell delegate that renders a category string as a coloured pill badge.

    Each engineering discipline has its own accent and background colour.
    """

    _CAT_BG: dict[str, tuple[str, str]] = {
        "Dimensional":   ("#3E9BFF", "#0d2540"),
        "Structural":    ("#A78BFA", "#2a1a4d"),
        "Electrical":    ("#FBBF24", "#3d2e0a"),
        "Material":      ("#2DD4BF", "#0a2d2a"),
        "Documentation": ("#A6A9B1", "#2d2f34"),
        "Other":         ("#94A3B8", "#252b35"),
        "Mechanical":    ("#FB923C", "#3d1f0a"),
    }

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        cat = index.data()
        if not cat:
            super().paint(painter, option, index)
            return

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor("#3E9BFF22"))

        text_c, bg_c = self._CAT_BG.get(cat, ("#A6A9B1", "#2d2f34"))
        pill_w = min(120, option.rect.width() - 16)
        pill_h = 22
        x = option.rect.x() + 8
        y = option.rect.y() + (option.rect.height() - pill_h) // 2

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(bg_c))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(x, y, pill_w, pill_h, 4, 4)
        painter.setPen(QColor(text_c))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(
            QRect(x, y, pill_w, pill_h),
            Qt.AlignmentFlag.AlignCenter,
            cat.upper(),
        )


class EngineDelegate(QStyledItemDelegate):
    """
    Cell delegate that renders an OCR engine name as an attributed pill badge.
    Supported engines: Tesseract / Tesseract OCR, Native (PDF text layer), Failed / OCR Failed.
    """

    _ENGINE_STYLES: dict[str, tuple[str, str, str, str]] = {
        # key: (display_label, text_color, bg_color, border_color)
        "tesseract": ("⚡ Tesseract",  "#38BDF8", "#0e2c45", "#1e4976"),
        "native":    ("📄 Native",     "#34D399", "#064e3b", "#047857"),
        "failed":    ("⚠️ OCR Failed", "#F87171", "#3d1a1a", "#7f1d1d"),
    }

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        raw_val = str(index.data() or "")
        if not raw_val:
            super().paint(painter, option, index)
            return

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor("#3E9BFF22"))

        low_val = raw_val.lower()
        if "fail" in low_val or "unreadable" in low_val or "error" in low_val:
            label, text_c, bg_c, border_c = self._ENGINE_STYLES["failed"]
        elif "native" in low_val:
            label, text_c, bg_c, border_c = self._ENGINE_STYLES["native"]
        else:
            label, text_c, bg_c, border_c = self._ENGINE_STYLES["tesseract"]

        pill_h = 24
        pill_w = min(110, option.rect.width() - 12)
        x = option.rect.x() + (option.rect.width() - pill_w) // 2
        y = option.rect.y() + (option.rect.height() - pill_h) // 2

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(bg_c))
        painter.setPen(QColor(border_c))
        painter.drawRoundedRect(x, y, pill_w, pill_h, 5, 5)

        painter.setPen(QColor(text_c))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(
            QRect(x, y, pill_w, pill_h),
            Qt.AlignmentFlag.AlignCenter,
            label,
        )


class ClassificationMethodDelegate(QStyledItemDelegate):
    """
    Cell delegate that renders an AI vs. Fallback classification method pill badge.
    Supported methods:
        - "ai_model" / "distilbert" -> "🤖 AI Model"
        - "rule_based_fallback" / "fallback" -> "📋 Rule Fallback"
        - "rule_based" -> "⚡ Rule-Based"
        - "manual" / "human_verified" -> "✍️ Manual"
        - "error_fallback" -> "⚠️ Fallback"
        - "manual_transcription_required" -> "⚠️ Needs Transc."
    """

    _METHOD_STYLES: dict[str, tuple[str, str, str, str]] = {
        # key: (display_label, text_color, bg_color, border_color)
        "ai_model":      ("🤖 AI Model",      "#818CF8", "#1E1B4B", "#4338CA"),
        "rule_fallback": ("📋 Rule Fallback", "#FBBF24", "#3D2E0A", "#78350F"),
        "rule_based":    ("⚡ Rule-Based",    "#F59E0B", "#2A1F05", "#B45309"),
        "manual":        ("✍️ Manual",        "#34D399", "#064E3B", "#047857"),
        "error":         ("⚠️ Fallback",      "#F87171", "#3D1A1A", "#7F1D1D"),
        "transcription": ("⚠️ Needs Transc.", "#F87171", "#3D1A1A", "#7F1D1D"),
    }

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        raw_val = str(index.data() or "").strip()
        fallback_used = bool(index.data(Qt.ItemDataRole.UserRole + 1) or False)

        if not raw_val:
            super().paint(painter, option, index)
            return

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor("#3E9BFF22"))

        low_val = raw_val.lower()
        if "transcription" in low_val:
            label, text_c, bg_c, border_c = self._METHOD_STYLES["transcription"]
        elif "error" in low_val:
            label, text_c, bg_c, border_c = self._METHOD_STYLES["error"]
        elif "manual" in low_val or "human" in low_val:
            label, text_c, bg_c, border_c = self._METHOD_STYLES["manual"]
        elif "fallback" in low_val or fallback_used:
            label, text_c, bg_c, border_c = self._METHOD_STYLES["rule_fallback"]
        elif "rule" in low_val:
            label, text_c, bg_c, border_c = self._METHOD_STYLES["rule_based"]
        elif "ai" in low_val or "model" in low_val or "distilbert" in low_val:
            label, text_c, bg_c, border_c = self._METHOD_STYLES["ai_model"]
        else:
            label, text_c, bg_c, border_c = self._METHOD_STYLES["ai_model"]

        pill_h = 24
        pill_w = min(120, option.rect.width() - 12)
        x = option.rect.x() + (option.rect.width() - pill_w) // 2
        y = option.rect.y() + (option.rect.height() - pill_h) // 2

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(bg_c))
        painter.setPen(QColor(border_c))
        painter.drawRoundedRect(x, y, pill_w, pill_h, 5, 5)

        painter.setPen(QColor(text_c))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(
            QRect(x, y, pill_w, pill_h),
            Qt.AlignmentFlag.AlignCenter,
            label,
        )


class PageDelegate(QStyledItemDelegate):
    """
    Cell delegate that renders a drawing page indicator as a compact styled chip.
    """

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        val = str(index.data() or "").strip()
        if not val:
            super().paint(painter, option, index)
            return

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor("#3E9BFF22"))

        # Format label e.g. "1" -> "P. 1", "Page 2" -> "P. 2"
        digits = "".join(ch for ch in val if ch.isdigit())
        display_label = f"P. {digits}" if digits else val

        pill_h = 22
        pill_w = min(64, option.rect.width() - 8)
        x = option.rect.x() + (option.rect.width() - pill_w) // 2
        y = option.rect.y() + (option.rect.height() - pill_h) // 2

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#1E293B"))
        painter.setPen(QColor("#475569"))
        painter.drawRoundedRect(x, y, pill_w, pill_h, 4, 4)

        painter.setPen(QColor("#CBD5E1"))
        painter.setFont(QFont("Cascadia Code", 10, QFont.Weight.Bold))
        painter.drawText(
            QRect(x, y, pill_w, pill_h),
            Qt.AlignmentFlag.AlignCenter,
            display_label,
        )
