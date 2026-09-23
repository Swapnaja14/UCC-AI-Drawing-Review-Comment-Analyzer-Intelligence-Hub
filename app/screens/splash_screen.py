"""
splash_screen.py — Splash screen shown while the application initialises.

Provides:
    SplashScreen(QWidget) — frameless, translucent window with gradient
    background, logo, tagline, indeterminate progress bar, and version label.
    Auto-dismissed by MainWindow after 2.2 s.
"""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar, QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QPainter, QPainterPath, QLinearGradient


class SplashScreen(QWidget):
    """
    Frameless splash screen displayed during application startup.

    Renders a dark rounded card with an accent glow, application logo,
    tagline, indeterminate progress bar, and version string.
    """

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(520, 340)

        # Centre on primary screen
        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.geometry()
            self.move(sg.center() - self.rect().center())

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 32)
        root.setSpacing(0)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Logo
        logo = QLabel("🔍")
        logo.setFont(QFont("Segoe UI", 52))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(logo)

        root.addSpacing(8)

        # App name
        title = QLabel("UCC Analyzer")
        title.setFont(QFont("Inter", 28, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #DAE2FD;")
        root.addWidget(title)

        # Tagline
        tag = QLabel("AI-Powered Drawing Review & Comment Analysis")
        tag.setFont(QFont("Inter", 12))
        tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tag.setStyleSheet("color: #C2C6D6;")
        root.addWidget(tag)

        root.addSpacing(28)

        # Indeterminate progress bar
        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        self._bar.setFixedHeight(4)
        self._bar.setStyleSheet(
            "QProgressBar { background:#2D3449; border-radius:2px; }"
            "QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #3B82F6, stop:1 #ADC6FF); border-radius:2px; }"
        )
        root.addWidget(self._bar)

        root.addSpacing(16)

        # Version
        ver = QLabel("v1.0.0  ·  © 2026 UCC Engineering")
        ver.setFont(QFont("Inter", 10))
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet("color: #8C909F;")
        root.addWidget(ver)

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 16, 16)

        # Background gradient
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0, QColor("#131B2E"))
        grad.setColorAt(1, QColor("#0B1326"))
        p.fillPath(path, grad)

        # Subtle accent glow at top-centre
        glow = QLinearGradient(
            self.width() // 2 - 100, 0,
            self.width() // 2 + 100, 80,
        )
        glow.setColorAt(0,   QColor(59, 130, 246, 0))
        glow.setColorAt(0.5, QColor(59, 130, 246, 35))
        glow.setColorAt(1,   QColor(59, 130, 246, 0))
        p.fillPath(path, glow)
        p.end()
