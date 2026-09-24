"""
KpiCard — metric card with icon badge, value, label, and trend/status badge.
"""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QFont
try:
    import qtawesome as qta
    _HAS_QTA = True
except ImportError:
    _HAS_QTA = False


class _IconBadge(QWidget):
    def __init__(self, icon_name: str, color: str, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._icon_name = icon_name
        self.setFixedSize(48, 48)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(self._color)
        bg.setAlphaF(0.15)
        path = QPainterPath()
        path.addRoundedRect(0, 0, 48, 48, 12, 12)
        p.fillPath(path, bg)
        p.end()

        if _HAS_QTA:
            try:
                icon = qta.icon(self._icon_name, color=self._color.name())
                icon.paint(QPainter(self), 12, 12, 24, 24)
            except Exception:
                pass


class KpiCard(QFrame):
    def __init__(self, icon: str, value: str, label: str, trend: str = "",
                 color: str = "#3B82F6", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumWidth(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

        # Header: Icon badge + Trend pill
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        if _HAS_QTA and "." in icon:
            try:
                badge = _IconBadge(icon, color)
                top_row.addWidget(badge)
            except Exception:
                lbl = QLabel(icon)
                lbl.setFont(QFont("Segoe UI Emoji", 20))
                top_row.addWidget(lbl)
        else:
            lbl = QLabel(icon)
            lbl.setFont(QFont("Segoe UI Emoji", 20))
            top_row.addWidget(lbl)

        top_row.addStretch()

        if trend:
            is_up = trend.startswith("+")
            is_down = trend.startswith("-") or any(neg in trend.lower() for neg in ["error", "fail", "rejected"])
            if is_up:
                t_color, t_bg = "#4EDEA3", "rgba(78, 222, 163, 0.15)"
            elif is_down:
                t_color, t_bg = "#FFB4AB", "rgba(255, 180, 171, 0.15)"
            else:
                t_color, t_bg = color, "rgba(59, 130, 246, 0.15)"

            t_lbl = QLabel(f" {trend} ")
            t_lbl.setFont(QFont("Inter", 11, QFont.Weight.Bold))
            t_lbl.setStyleSheet(
                f"color: {t_color}; background-color: {t_bg};"
                f"border-radius: 6px; padding: 3px 8px;"
            )
            top_row.addWidget(t_lbl)

        root.addLayout(top_row)

        # Metric Value
        self.val_lbl = QLabel(value)
        self.val_lbl.setFont(QFont("Inter", 28, QFont.Weight.Bold))
        self.val_lbl.setObjectName("KpiValue")
        root.addWidget(self.val_lbl)

        # Descriptive Label
        self.cap_lbl = QLabel(label)
        self.cap_lbl.setFont(QFont("Inter", 13, QFont.Weight.Medium))
        self.cap_lbl.setObjectName("SubCaption")
        self.cap_lbl.setWordWrap(True)
        root.addWidget(self.cap_lbl)

    def set_value(self, value: str):
        self.val_lbl.setText(value)
