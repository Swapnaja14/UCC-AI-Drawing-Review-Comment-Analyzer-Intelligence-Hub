"""
ThemeManager — generates and applies QSS stylesheets for light / dark themes.
All color tokens live here; no hard-coded hex values in widget code.
"""
from __future__ import annotations
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal

# ── Color tokens ──────────────────────────────────────────────────────────────

THEMES = {
    "dark": {
        "bg_primary":    "#1E1F22",
        "bg_secondary":  "#26272B",
        "bg_elevated":   "#2D2F34",
        "border":        "#3A3C42",
        "text_primary":  "#F2F3F5",
        "text_secondary":"#A6A9B1",
        "accent":        "#3E9BFF",
        "accent_hover":  "#5FAEFF",
        "success":       "#4ADE80",
        "warning":       "#FBBF24",
        "danger":        "#F87171",
        "info":          "#8B9CFF",
        "shadow":        "rgba(0,0,0,0.35)",
        "scrim":         "rgba(0,0,0,0.55)",
    },
    "light": {
        "bg_primary":    "#FFFFFF",
        "bg_secondary":  "#F5F6F8",
        "bg_elevated":   "#FFFFFF",
        "border":        "#E2E4E8",
        "text_primary":  "#1B1D21",
        "text_secondary":"#5B5F6A",
        "accent":        "#0067C5",
        "accent_hover":  "#0052A0",
        "success":       "#1E8E3E",
        "warning":       "#E8A000",
        "danger":        "#D93025",
        "info":          "#5B6EF5",
        "shadow":        "rgba(0,0,0,0.08)",
        "scrim":         "rgba(0,0,0,0.35)",
    },
}

def _build_qss(t: dict) -> str:
    return f"""
/* ── Base ──────────────────────────────────────────────────────── */
QWidget {{
    background-color: {t['bg_primary']};
    color: {t['text_primary']};
    font-family: "Segoe UI Variable", "Segoe UI", "Inter", "Arial";
    font-size: 14px;
    border: none;
    outline: none;
}}

/* ── Main window ────────────────────────────────────────────────── */
QMainWindow {{
    background-color: {t['bg_primary']};
}}

/* ── Sidebar ────────────────────────────────────────────────────── */
#Sidebar {{
    background-color: {t['bg_secondary']};
    border-right: 1px solid {t['border']};
}}
#NavList {{
    background-color: transparent;
    border: none;
    outline: none;
}}
#NavList::item {{
    height: 40px;
    padding-left: 16px;
    border-radius: 6px;
    margin: 2px 8px;
    color: {t['text_secondary']};
}}
#NavList::item:hover {{
    background-color: {t['accent']}1A;
    color: {t['text_primary']};
}}
#NavList::item:selected {{
    background-color: {t['accent']}2A;
    color: {t['accent']};
    font-weight: 600;
}}

/* ── Top bar ────────────────────────────────────────────────────── */
#TopBar {{
    background-color: {t['bg_primary']};
    border-bottom: 1px solid {t['border']};
}}

/* ── Cards / Frames ─────────────────────────────────────────────── */
#Card {{
    background-color: {t['bg_elevated']};
    border: 1px solid {t['border']};
    border-radius: 8px;
}}
#CardHeader {{
    font-size: 17px;
    font-weight: 600;
    color: {t['text_primary']};
}}

/* ── Buttons ────────────────────────────────────────────────────── */
QPushButton#PrimaryBtn {{
    background-color: {t['accent']};
    color: #FFFFFF;
    border-radius: 8px;
    padding: 0 20px;
    height: 36px;
    font-weight: 600;
    font-size: 14px;
}}
QPushButton#PrimaryBtn:hover {{
    background-color: {t['accent_hover']};
}}
QPushButton#PrimaryBtn:disabled {{
    background-color: {t['border']};
    color: {t['text_secondary']};
}}

QPushButton#SecondaryBtn {{
    background-color: transparent;
    color: {t['accent']};
    border: 1px solid {t['accent']};
    border-radius: 8px;
    padding: 0 20px;
    height: 36px;
    font-weight: 600;
}}
QPushButton#SecondaryBtn:hover {{
    background-color: {t['accent']}1A;
}}

QPushButton#DangerBtn {{
    background-color: transparent;
    color: {t['danger']};
    border: 1px solid {t['danger']};
    border-radius: 8px;
    padding: 0 20px;
    height: 36px;
    font-weight: 600;
}}
QPushButton#DangerBtn:hover {{
    background-color: {t['danger']}1A;
}}

QPushButton#SuccessBtn {{
    background-color: {t['success']};
    color: #FFFFFF;
    border-radius: 8px;
    padding: 0 20px;
    height: 36px;
    font-weight: 600;
}}
QPushButton#SuccessBtn:hover {{
    background-color: {t['success']}CC;
}}

QPushButton#GhostBtn {{
    background-color: transparent;
    color: {t['text_secondary']};
    border-radius: 8px;
    padding: 0 16px;
    height: 36px;
}}
QPushButton#GhostBtn:hover {{
    background-color: {t['border']};
    color: {t['text_primary']};
}}

QToolButton {{
    background-color: transparent;
    border-radius: 6px;
    padding: 4px;
    color: {t['text_secondary']};
}}
QToolButton:hover {{
    background-color: {t['border']};
    color: {t['text_primary']};
}}

/* ── Input fields ───────────────────────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {t['bg_secondary']};
    color: {t['text_primary']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 6px 12px;
    height: 36px;
    font-size: 14px;
    selection-background-color: {t['accent']}44;
}}
QLineEdit:focus, QTextEdit:focus {{
    border: 1.5px solid {t['accent']};
    background-color: {t['bg_elevated']};
}}
QTextEdit {{
    height: auto;
    padding: 8px 12px;
}}

/* ── ComboBox ───────────────────────────────────────────────────── */
QComboBox {{
    background-color: {t['bg_secondary']};
    color: {t['text_primary']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 4px 32px 4px 12px;
    height: 36px;
}}
QComboBox:hover {{
    border-color: {t['accent']};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 32px;
    border: none;
    background: transparent;
}}
QComboBox::drop-down:hover {{
    background-color: {t['accent']}1A;
    border-top-right-radius: 7px;
    border-bottom-right-radius: 7px;
}}
QComboBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {t['text_secondary']};
    margin-right: 10px;
}}
QComboBox::down-arrow:hover, QComboBox:hover::down-arrow {{
    border-top-color: {t['accent']};
}}
QComboBox::down-arrow:on {{
    border-top: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-bottom: 6px solid {t['accent']};
}}
QComboBox QAbstractItemView {{
    background-color: {t['bg_elevated']};
    color: {t['text_primary']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    selection-background-color: {t['accent']}2A;
    selection-color: {t['accent']};
    padding: 4px;
}}

/* ── Tables ─────────────────────────────────────────────────────── */
QTableView {{
    background-color: {t['bg_primary']};
    gridline-color: {t['border']};
    alternate-background-color: {t['bg_secondary']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    font-size: 14px;
    selection-background-color: {t['accent']}22;
    selection-color: {t['text_primary']};
}}
QTableView::item {{
    padding: 0 12px;
    height: 44px;
    border-bottom: 1px solid {t['border']};
}}
QTableView::item:selected {{
    background-color: {t['accent']}22;
}}
QHeaderView::section {{
    background-color: {t['bg_secondary']};
    color: {t['text_secondary']};
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    padding: 0 12px;
    height: 40px;
    border: none;
    border-bottom: 1px solid {t['border']};
    border-right: 1px solid {t['border']};
}}
QHeaderView::section:last {{
    border-right: none;
}}

/* ── List views ─────────────────────────────────────────────────── */
QListView, QListWidget {{
    background-color: transparent;
    border: none;
    outline: none;
}}
QListView::item:hover, QListWidget::item:hover {{
    background-color: {t['accent']}12;
    border-radius: 6px;
}}

/* ── Scroll bars ─────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {t['border']};
    border-radius: 4px;
    min-height: 40px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t['text_secondary']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: {t['border']};
    border-radius: 4px;
    min-width: 40px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {t['text_secondary']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Progress bar ────────────────────────────────────────────────── */
QProgressBar {{
    background-color: {t['border']};
    border-radius: 4px;
    height: 8px;
    text-align: center;
    font-size: 0px;
}}
QProgressBar::chunk {{
    background-color: {t['accent']};
    border-radius: 4px;
}}

/* ── Separator ───────────────────────────────────────────────────── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {t['border']};
    background-color: {t['border']};
}}

/* ── Splitter ────────────────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {t['border']};
    width: 1px;
}}

/* ── Status bar ──────────────────────────────────────────────────── */
QStatusBar {{
    background-color: {t['bg_secondary']};
    color: {t['text_secondary']};
    font-size: 12px;
    border-top: 1px solid {t['border']};
}}

/* ── Slider ──────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: {t['border']};
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {t['accent']};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}
QSlider::sub-page:horizontal {{
    background: {t['accent']};
    border-radius: 2px;
}}

/* ── Checkbox ────────────────────────────────────────────────────── */
QCheckBox {{
    spacing: 8px;
    color: {t['text_primary']};
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {t['border']};
    border-radius: 4px;
    background: {t['bg_secondary']};
}}
QCheckBox::indicator:checked {{
    background: {t['accent']};
    border-color: {t['accent']};
}}

/* ── RadioButton ─────────────────────────────────────────────────── */
QRadioButton {{
    spacing: 8px;
    color: {t['text_primary']};
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {t['border']};
    border-radius: 8px;
    background: {t['bg_secondary']};
}}
QRadioButton::indicator:checked {{
    background: {t['accent']};
    border-color: {t['accent']};
}}

/* ── Graphics view ───────────────────────────────────────────────── */
QGraphicsView {{
    background-color: {t['bg_secondary']};
    border: 1px solid {t['border']};
    border-radius: 8px;
}}

/* ── Tooltip ─────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {t['bg_elevated']};
    color: {t['text_primary']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
}}

/* ── Date edit ───────────────────────────────────────────────────── */
QDateEdit {{
    background-color: {t['bg_secondary']};
    color: {t['text_primary']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 4px 12px;
    height: 36px;
}}
QDateEdit::drop-down {{
    border: none;
    width: 28px;
}}

/* ── FormLayout labels ───────────────────────────────────────────── */
QLabel#FormLabel {{
    color: {t['text_secondary']};
    font-size: 13px;
    font-weight: 600;
}}
QLabel#SectionTitle {{
    color: {t['text_primary']};
    font-size: 17px;
    font-weight: 600;
    padding-bottom: 4px;
}}
QLabel#SubCaption {{
    color: {t['text_secondary']};
    font-size: 12px;
}}
"""

class ThemeManager(QObject):
    theme_changed = Signal(str)

    def __init__(self, app: QApplication):
        super().__init__()
        self._app = app
        self._current = "dark"

    @property
    def current(self) -> str:
        return self._current

    @property
    def colors(self) -> dict:
        return THEMES[self._current]

    def apply(self, theme: str = "dark") -> None:
        self._current = theme
        self._app.setStyleSheet(_build_qss(THEMES[theme]))
        self.theme_changed.emit(theme)

    def toggle(self) -> None:
        self.apply("light" if self._current == "dark" else "dark")
