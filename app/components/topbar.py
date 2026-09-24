"""
TopBar - 72px enterprise header with page title / branding, responsive global search,
notifications, theme toggle, and user profile avatar menu.
"""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QLineEdit, QToolButton,
                                QPushButton, QLabel, QMenu, QFrame, QSizePolicy)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QIcon, QAction

class TopBar(QWidget):
    search_changed = Signal(str)
    theme_toggled  = Signal()
    notification_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(72)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 0, 24, 0)
        lay.setSpacing(14)

        self._breadcrumb = QLabel("Dashboard")
        self._breadcrumb.setFont(QFont("Inter", 16, QFont.Weight.Bold))
        self._breadcrumb.setObjectName("PageTitle")
        lay.addWidget(self._breadcrumb)
        lay.addStretch()

        search = QLineEdit()
        search.setPlaceholderText("Search drawings, comments, projects...")
        search.setFixedWidth(300)
        search.setFixedHeight(38)
        search.setObjectName("SearchBox")
        search.textChanged.connect(self.search_changed)
        lay.addWidget(search)
        lay.addSpacing(16)

        notif = QToolButton()
        notif.setText("🔔")
        notif.setToolTip("Notifications")
        notif.setFixedSize(38, 38)
        notif.clicked.connect(self.notification_clicked)
        lay.addWidget(notif)

        self._theme_btn = QPushButton("🌙  Dark")
        self._theme_btn.setObjectName("SecondaryBtn")
        self._theme_btn.setFixedHeight(38)
        self._theme_btn.setCheckable(True)
        self._theme_btn.clicked.connect(self._on_theme_click)
        lay.addWidget(self._theme_btn)
        lay.addSpacing(16)

        avatar_btn = QToolButton()
        avatar_btn.setText("  AM  Alex M. ▾  ")
        avatar_btn.setFont(QFont("Inter", 12, QFont.Weight.Medium))
        avatar_btn.setObjectName("TopAvatarBtn")
        avatar_btn.setFixedHeight(38)

        menu = QMenu(avatar_btn)
        menu.addAction("My Profile")
        menu.addAction("Settings")
        menu.addSeparator()
        menu.addAction("Log Out")
        avatar_btn.setMenu(menu)
        avatar_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        lay.addWidget(avatar_btn)

    def set_breadcrumb(self, text: str):
        self._breadcrumb.setText(text)

    def _on_theme_click(self, checked: bool):
        self._theme_btn.setText("☀  Light" if checked else "🌙  Dark")
        self.theme_toggled.emit()
