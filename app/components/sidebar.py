"""
SidebarNav — collapsible left navigation panel with 240px enterprise layout,
app branding, bottom version status, and animated toggle.
"""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QListWidget, QListWidgetItem, QToolButton,
                                QSizePolicy, QFrame)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import QFont, QColor, QIcon
try:
    import qtawesome as qta
    _HAS_QTA = True
except ImportError:
    _HAS_QTA = False

_NAV_ITEMS = [
    ("Dashboard",       "fa5s.th-large",        0),
    ("Upload",          "fa5s.cloud-upload-alt", 1),
    ("PDF Viewer",      "fa5s.file-pdf",         2),
    ("Comment Viewer",  "fa5s.highlighter",      3),
    ("OCR Results",     "fa5s.font",             4),
    ("Classification",  "fa5s.tags",             5),
    ("Human Review",    "fa5s.user-check",       6),
    ("Analytics",       "fa5s.chart-bar",        7),
    ("Export",          "fa5s.file-export",      8),
    ("Settings",        "fa5s.cog",              9),
]

EXPANDED_W  = 240
COLLAPSED_W = 72


class SidebarNav(QWidget):
    nav_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(EXPANDED_W)
        self._expanded = True

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Logo area ────────────────────────────────────────────
        logo_frame = QFrame()
        logo_frame.setFixedHeight(72)
        logo_frame.setStyleSheet("background: transparent;")
        logo_lay = QHBoxLayout(logo_frame)
        logo_lay.setContentsMargins(18, 0, 18, 0)
        logo_lay.setSpacing(12)

        self._logo_icon = QLabel("📐")
        self._logo_icon.setFont(QFont("Segoe UI Emoji", 20))
        logo_lay.addWidget(self._logo_icon)

        self._logo_text = QLabel("UCC Analyzer")
        self._logo_text.setFont(QFont("Inter", 16, QFont.Weight.Bold))
        self._logo_text.setStyleSheet("color: #3B82F6; letter-spacing: -0.3px;")
        logo_lay.addWidget(self._logo_text, 1)
        root.addWidget(logo_frame)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2F3545; background-color: #2F3545;")
        root.addWidget(sep)

        # ── Navigation list ──────────────────────────────────────
        self._nav = QListWidget()
        self._nav.setObjectName("NavList")
        self._nav.setIconSize(QSize(18, 18))
        self._nav.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav.setSpacing(3)

        for label, icon_name, idx in _NAV_ITEMS:
            item = QListWidgetItem(label)
            if _HAS_QTA:
                try:
                    item.setIcon(qta.icon(icon_name, color="#9CA3AF"))
                except Exception:
                    pass
            item.setSizeHint(QSize(EXPANDED_W - 20, 44))
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self._nav.addItem(item)

        self._nav.setCurrentRow(0)
        self._nav.currentRowChanged.connect(self._on_nav_change)
        root.addWidget(self._nav, 1)

        # ── Bottom status & version ──────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #2F3545; background-color: #2F3545;")
        root.addWidget(sep2)

        self._status_frame = QFrame()
        self._status_frame.setStyleSheet("background: transparent;")
        status_lay = QVBoxLayout(self._status_frame)
        status_lay.setContentsMargins(16, 12, 16, 12)
        status_lay.setSpacing(6)

        # Backend connection indicator
        conn_row = QHBoxLayout()
        conn_row.setSpacing(8)
        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet("color: #10B981; font-size: 11px;")
        conn_row.addWidget(self._status_dot)

        self._conn_lbl = QLabel("Backend Connected")
        self._conn_lbl.setFont(QFont("Inter", 12, QFont.Weight.Medium))
        self._conn_lbl.setStyleSheet("color: #10B981;")
        conn_row.addWidget(self._conn_lbl)
        conn_row.addStretch()
        status_lay.addLayout(conn_row)

        # Version string
        self._ver_lbl = QLabel("UCC AI Review · v1.0.0")
        self._ver_lbl.setFont(QFont("Inter", 11))
        self._ver_lbl.setStyleSheet("color: #6B7280;")
        status_lay.addWidget(self._ver_lbl)

        root.addWidget(self._status_frame)

        # ── Collapse toggle ──────────────────────────────────────
        self._toggle_btn = QToolButton()
        self._toggle_btn.setFixedHeight(40)
        self._toggle_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._toggle_btn.setStyleSheet(
            "border: none; color: #9CA3AF; font-size: 13px; font-weight: 500; padding: 4px;"
        )
        self._toggle_btn.setText("◀  Collapse Menu")
        self._toggle_btn.clicked.connect(self.toggle_collapse)
        root.addWidget(self._toggle_btn)

        # Width animation
        self._anim = QPropertyAnimation(self, b"minimumWidth")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_max = QPropertyAnimation(self, b"maximumWidth")
        self._anim_max.setDuration(180)
        self._anim_max.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _on_nav_change(self, row: int):
        if 0 <= row < len(_NAV_ITEMS):
            self.nav_changed.emit(_NAV_ITEMS[row][2])

    def set_page(self, idx: int):
        for i, (_, __, page_idx) in enumerate(_NAV_ITEMS):
            if page_idx == idx:
                self._nav.setCurrentRow(i)
                break

    def toggle_collapse(self):
        self._expanded = not self._expanded
        target = EXPANDED_W if self._expanded else COLLAPSED_W

        self._anim.setStartValue(self.width())
        self._anim.setEndValue(target)
        self._anim.start()
        self._anim_max.setStartValue(self.width())
        self._anim_max.setEndValue(target)
        self._anim_max.start()

        self._logo_text.setVisible(self._expanded)
        self._status_frame.setVisible(self._expanded)
        self._toggle_btn.setText("◀  Collapse Menu" if self._expanded else "▶")
        for i in range(self._nav.count()):
            item = self._nav.item(i)
            if item:
                item.setText(_NAV_ITEMS[i][0] if self._expanded else "")
