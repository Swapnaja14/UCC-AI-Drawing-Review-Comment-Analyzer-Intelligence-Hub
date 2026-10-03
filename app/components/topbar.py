"""
TopBar — search field, notification button, theme toggle, user avatar.
"""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QLineEdit, QToolButton,
                                QPushButton, QLabel, QMenu, QFrame)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QIcon, QAction
try:
    import qtawesome as qta
    _HAS_QTA = True
except ImportError:
    _HAS_QTA = False


class TopBar(QWidget):
    search_changed = Signal(str)
    theme_toggled  = Signal()
    notification_clicked = Signal()
    logout_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(56)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 0, 24, 0)
        lay.setSpacing(12)

        # ── Breadcrumb / page title ──────────────────────────────
        self._breadcrumb = QLabel("Dashboard")
        self._breadcrumb.setFont(QFont("Segoe UI Variable", 15, QFont.Weight.DemiBold))
        self._breadcrumb.setStyleSheet("color: #F2F3F5;")
        lay.addWidget(self._breadcrumb)
        lay.addStretch()

        # ── Search field ─────────────────────────────────────────
        self._search = QLineEdit()
        self._search.setPlaceholderText("  🔍  Search projects, drawings, comments…")
        self._search.setFixedWidth(300)
        self._search.setFixedHeight(36)
        self._search.textChanged.connect(self.search_changed)
        lay.addWidget(self._search)

        # ── Notification button ──────────────────────────────────
        notif = QToolButton()
        notif.setFixedSize(36, 36)
        notif.setToolTip("Notifications")
        if _HAS_QTA:
            try:
                notif.setIcon(qta.icon("fa5s.bell", color="#A6A9B1"))
                notif.setIconSize(QSize(18, 18))
            except Exception:
                notif.setText("🔔")
        else:
            notif.setText("🔔")
        notif.clicked.connect(self.notification_clicked)
        lay.addWidget(notif)

        # ── Theme toggle ─────────────────────────────────────────
        self._theme_btn = QPushButton("☀  Light")
        self._theme_btn.setObjectName("SecondaryBtn")
        self._theme_btn.setFixedHeight(32)
        self._theme_btn.setCheckable(True)
        self._theme_btn.clicked.connect(self._on_theme_click)
        lay.addWidget(self._theme_btn)

        # ── User Name / Dept Label ──────────────────────────────
        self._user_info_lbl = QLabel("")
        self._user_info_lbl.setFont(QFont("Segoe UI Variable", 12, QFont.Weight.Medium))
        self._user_info_lbl.setStyleSheet("color: #E2E8F0; margin-left: 4px;")
        lay.addWidget(self._user_info_lbl)

        # ── User avatar ──────────────────────────────────────────
        self._avatar = QToolButton()
        self._avatar.setFixedSize(36, 36)
        self._avatar.setStyleSheet(
            "QToolButton { background:#3E9BFF; border-radius:18px;"
            "color:#fff; font-weight:700; font-size:13px; }"
        )
        self._avatar.setText("US")
        
        self._menu = QMenu(self._avatar)
        self._logout_action = QAction("🚪 Sign Out", self)
        self._logout_action.triggered.connect(self.logout_requested)
        self._menu.addAction(self._logout_action)
        self._avatar.setMenu(self._menu)
        self._avatar.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        lay.addWidget(self._avatar)

        # ── Explicit Logout Button ───────────────────────────────
        self._logout_btn = QPushButton("🚪 Sign Out")
        self._logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._logout_btn.setFixedHeight(32)
        self._logout_btn.setStyleSheet(
            "QPushButton { background:#DC2626; color:#FFFFFF; border:none; border-radius:6px;"
            " padding:0 12px; font-weight:600; font-size:12px; }"
            "QPushButton:hover { background:#EF4444; }"
        )
        self._logout_btn.clicked.connect(self.logout_requested)
        lay.addWidget(self._logout_btn)

    def set_breadcrumb(self, text: str):
        self._breadcrumb.setText(text)

    def set_user_info(self, name: str, department: str = ""):
        self.set_user(name, department)

    def set_user(self, name: str, department: str = ""):
        parts = name.strip().split()
        if len(parts) >= 2:
            initials = f"{parts[0][0]}{parts[1][0]}".upper()
        elif parts:
            initials = parts[0][:2].upper()
        else:
            initials = "US"
        self._avatar.setText(initials)
        
        display_str = name
        if department and department != "Unassigned":
            display_str += f" ({department})"
        self._user_info_lbl.setText(display_str)
        self._avatar.setToolTip(f"{name}\nDepartment: {department or 'Unassigned'}")

    def _on_theme_click(self, checked: bool):
        self._theme_btn.setText("🌙  Dark" if checked else "☀  Light")
        self.theme_toggled.emit()

