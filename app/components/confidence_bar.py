"""ConfidenceBar — mini threshold-colored progress bar (custom paintEvent)."""
from __future__ import annotations
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPainterPath


class ConfidenceBar(QWidget):
    def __init__(self, value: float = 0.0, parent=None):
        """value: 0.0–1.0"""
        super().__init__(parent)
        self._value = max(0.0, min(1.0, value))
        self.setFixedHeight(8)
        self.setMinimumWidth(60)

    def set_value(self, v: float):
        self._value = max(0.0, min(1.0, v))
        self.update()

    def _color(self) -> str:
        pct = round(self._value * 100)
        if pct >= 85:
            return "#4ADE80"
        if pct >= 70:
            return "#FBBF24"
        return "#F87171"

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Track
        track = QPainterPath()
        track.addRoundedRect(QRectF(0, 0, w, h), 4, 4)
        p.fillPath(track, QColor("#3A3C42"))

        # Fill
        fill_w = int(w * self._value)
        if fill_w > 0:
            fill = QPainterPath()
            fill.addRoundedRect(QRectF(0, 0, fill_w, h), 4, 4)
            p.fillPath(fill, QColor(self._color()))
        p.end()
