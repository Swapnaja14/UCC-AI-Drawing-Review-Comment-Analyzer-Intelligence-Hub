"""
upload_widget.py — Drag-and-drop PDF upload zone.

Provides:
    DropZone(QFrame)
        Renders a dashed drop target; emits ``file_dropped(str)`` when
        a valid ``.pdf`` file is released onto it.
"""
from __future__ import annotations
from PySide6.QtWidgets import QFrame
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPainter, QPen, QColor


class DropZone(QFrame):
    """
    Drag-and-drop zone that accepts PDF files.

    The border transitions from a neutral dashed line to an accent-blue
    highlight while the user drags a file over the widget.

    Signals
    -------
    file_dropped : str
        Emitted with the local file-system path of the dropped PDF.
    """

    file_dropped = Signal(str)
    files_dropped = Signal(list)

    _DASH_COLOR_IDLE   = "#3A3C42"
    _DASH_COLOR_ACTIVE = "#3E9BFF"

    def __init__(self, parent=None, allow_zips: bool = False):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(240)
        self._active = False
        self._allow_zips = allow_zips

    # ── Drag helpers ──────────────────────────────────────────────

    def _set_active(self, v: bool) -> None:
        self._active = v
        self.update()

    # ── Qt overrides ──────────────────────────────────────────────

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._set_active(True)

    def dragLeaveEvent(self, e) -> None:
        self._set_active(False)

    def dropEvent(self, e: QDropEvent) -> None:
        self._set_active(False)
        urls = e.mimeData().urls()
        if not urls:
            return

        valid_paths = []
        for url in urls:
            path = url.toLocalFile()
            ext = path.lower()
            if ext.endswith(".pdf") or (self._allow_zips and ext.endswith(".zip")):
                valid_paths.append(path)

        if valid_paths:
            self.file_dropped.emit(valid_paths[0])
            self.files_dropped.emit(valid_paths)

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color_hex = (
            self._DASH_COLOR_ACTIVE if self._active else self._DASH_COLOR_IDLE
        )
        pen = QPen(QColor(color_hex))
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        bg = QColor("#3E9BFF" if self._active else "#26272B")
        bg.setAlphaF(0.06 if self._active else 0.0)
        p.setBrush(bg)
        p.drawRoundedRect(2, 2, self.width() - 4, self.height() - 4, 10, 10)
        p.end()
