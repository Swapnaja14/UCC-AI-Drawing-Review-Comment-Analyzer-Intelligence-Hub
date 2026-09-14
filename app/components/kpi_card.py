"""
KpiCard — metric card with icon badge, value, label, trend.
"""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QFont
import qtawesome as qta


class _IconBadge(QWidget):
    def __init__(self, icon_name: str, color: str, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._icon_name = icon_name
        self.setFixedSize(44, 44)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(self._color)
        bg.setAlphaF(0.15)
        path = QPainterPath()
        path.addRoundedRect(0, 0, 44, 44, 10, 10)
        p.fillPath(path, bg)
        p.end()
        try:
            icon = qta.icon(self._icon_name, color=self._color.name())
            icon.paint(QPainter(self), 10, 10, 24, 24)
        except Exception:
            pass


class KpiCard(QFrame):
    def __init__(self, icon: str, value: str, label: str, trend: str = "",
                 color: str = "#3E9BFF", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumWidth(160)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)

        # Icon badge
        try:
            badge = _IconBadge(icon, color)
            root.addWidget(badge)
        except Exception:
            lbl = QLabel(label[0])
            lbl.setFixedSize(44, 44)
            root.addWidget(lbl)

        # Value
        val_lbl = QLabel(value)
        val_lbl.setFont(QFont("Segoe UI Variable", 26, QFont.Weight.Bold))
        val_lbl.setStyleSheet(f"color: {'#F2F3F5' if True else '#1B1D21'};")
        val_lbl.setObjectName("KpiValue")
        root.addWidget(val_lbl)

        # Label + trend row
        row = QHBoxLayout()
        row.setSpacing(8)
        cap = QLabel(label)
        cap.setObjectName("SubCaption")
        row.addWidget(cap)
        if trend:
            is_down = trend.startswith("-") or any(neg in trend.lower() for neg in ["error", "fail", "rejected"])
            if is_down:
                trend_color = "#F87171"
            elif trend.startswith("+"):
                trend_color = "#4ADE80"
            else:
                trend_color = color

            t_lbl = QLabel(trend)
            t_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
            t_lbl.setStyleSheet(
                f"color: {trend_color}; "
                f"border-radius: 4px; padding: 1px 6px; font-weight: 600;"
            )
            row.addWidget(t_lbl)
        row.addStretch()
        root.addLayout(row)
        root.addStretch()
