"""
metadata_panel.py — Redesigned Drawing metadata side panel.

Provides:
    DrawingMetadataPanel(QScrollArea)
        Renders a labelled list of engineering drawing metadata fields
        in a dedicated, scrollable right-side panel with distinct label/value hierarchy.
"""
from __future__ import annotations
from typing import Sequence, Tuple
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                                QScrollArea, QWidget, QSizePolicy)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

_DEFAULT_FIELDS: Sequence[Tuple[str, str]] = (
    ("Drawing Number", "UCC-E-101"),
    ("Drawing Title",  "P&ID Unit 4-A Process Flow"),
    ("Revision",       "Rev A"),
    ("Project Name",   "UCC Site-4 Expansion"),
    ("Discipline",     "Process / Piping"),
    ("Sheet Number",   "1 of 7"),
    ("Scale",          "1:50 Engineering"),
    ("Date Processed", "2026-07-28"),
    ("Detected Regions","71 Annotation Regions"),
    ("Detection Method","Color Segmentation (HSV)"),
    ("Coverage",       "All Colored Markup & Text"),
)


class DrawingMetadataPanel(QScrollArea):
    """
    Scrollable right-side panel displaying drawing metadata with high contrast
    and zero vertical overflow/clipping.
    """

    def __init__(
        self,
        fields: Sequence[Tuple[str, str]] | None = None,
        fixed_width: int = 300,
        parent=None,
    ):
        super().__init__(parent)
        self.setFixedWidth(fixed_width)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(
            "QScrollArea { background: #FFFFFF; border-left: 1px solid #E2E8F0; }"
            "QWidget { background: #FFFFFF; }"
        )

        self._container = QWidget()
        self._lay = QVBoxLayout(self._container)
        self._lay.setContentsMargins(18, 16, 18, 20)
        self._lay.setSpacing(14)

        # Header
        hdr_row = QHBoxLayout()
        hdr = QLabel("Drawing Properties")
        hdr.setFont(QFont("Inter", 15, QFont.Weight.Bold))
        hdr.setStyleSheet("color: #F3F4F6;")
        hdr_row.addWidget(hdr)
        hdr_row.addStretch()
        self._lay.addLayout(hdr_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2F3545; background-color: #2F3545;")
        self._lay.addWidget(sep)

        self._field_start_index = self._lay.count()
        self._append_fields(fields or _DEFAULT_FIELDS)
        self._lay.addStretch()

        self.setWidget(self._container)

    def update_fields(self, fields: Sequence[Tuple[str, str]]) -> None:
        """Replace all field rows with new data without recreating the header."""
        while self._lay.count() > self._field_start_index:
            item = self._lay.takeAt(self._lay.count() - 1)
            if item.widget():
                item.widget().deleteLater()

        self._append_fields(fields)
        self._lay.addStretch()

    def _append_fields(self, fields: Sequence[Tuple[str, str]]) -> None:
        for key, val in fields:
            row_card = QFrame()
            row_card.setObjectName("Card")
            r_lay = QVBoxLayout(row_card)
            r_lay.setContentsMargins(12, 10, 12, 10)
            r_lay.setSpacing(4)

            k_lbl = QLabel(key.upper())
            k_lbl.setObjectName("FormLabel")
            k_lbl.setFont(QFont("Inter", 10, QFont.Weight.Bold))
            r_lay.addWidget(k_lbl)

            v_lbl = QLabel(str(val))
            v_lbl.setFont(QFont("Inter", 13, QFont.Weight.Medium))
            v_lbl.setWordWrap(True)
            v_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            r_lay.addWidget(v_lbl)

            self._lay.addWidget(row_card)
