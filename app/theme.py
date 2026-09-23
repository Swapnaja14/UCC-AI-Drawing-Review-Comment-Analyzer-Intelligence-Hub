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
        "bg_primary":    "#070B12",  # Deep Obsidian Ground
        "bg_secondary":  "#0F172A",  # Obsidian Surface 1
        "bg_elevated":   "#1E293B",  # Obsidian Elevated Panel
        "bg_hover":      "#334155",  # Obsidian Hover State
        "border":        "#334155",  # Obsidian Divider
        "border_subtle": "#1E293B",  # Inner Sub-border
        "text_primary":  "#F8FAFC",  # Obsidian Ice White
        "text_secondary":"#94A3B8",  # Cyber Slate Text
        "text_muted":    "#64748B",  # Muted Slate
        "accent":        "#06B6D4",  # Electric Cyber Teal
        "accent_hover":  "#2DD4BF",  # Bright Cyber Teal
        "accent_muted":  "rgba(6, 182, 212, 0.18)", # Cyber Teal Glow
        "success":       "#10B981",  # Cyber Emerald
        "success_muted": "rgba(16, 185, 129, 0.18)",
        "warning":       "#F59E0B",  # Cyber Amber
        "warning_muted": "rgba(245, 158, 11, 0.18)",
        "danger":        "#F43F5E",  # Cyber Crimson
        "danger_muted":  "rgba(244, 63, 94, 0.18)",
        "info":          "#00F2FE",  # Neon Cyan
        "shadow":        "rgba(0, 0, 0, 0.65)",
        "scrim":         "rgba(7, 11, 18, 0.85)",
    },
    "light": {
        "bg_primary":    "#FAF8FF",
        "bg_secondary":  "#F2F3FF",
        "bg_elevated":   "#FFFFFF",
        "bg_hover":      "#EAEDFF",
        "border":        "#C2C6D4",
        "border_subtle": "#E2E7FF",
        "text_primary":  "#131B2E",
        "text_secondary":"#424752",
        "text_muted":    "#727784",
        "accent":        "#0057B8",
        "accent_hover":  "#00408B",
        "accent_muted":  "rgba(0, 87, 184, 0.12)",
        "success":       "#10B981",
        "success_muted": "rgba(16, 185, 129, 0.12)",
        "warning":       "#F59E0B",
        "warning_muted": "rgba(245, 158, 11, 0.12)",
        "danger":        "#BA1A1A",
        "danger_muted":  "rgba(186, 26, 26, 0.12)",
        "info":          "#006688",
        "shadow":        "rgba(19, 27, 46, 0.08)",
        "scrim":         "rgba(19, 27, 46, 0.35)",
    },
}

def _build_qss(t: dict) -> str:
    return f"""
/* ── Base ──────────────────────────────────────────────────────── */
QWidget {{
    background-color: {t['bg_primary']};
    color: {t['text_primary']};
    font-family: "Inter", "Segoe UI Variable", "Segoe UI", -apple-system, BlinkMacSystemFont, "Arial", sans-serif;
    font-size: 14px;
    border: none;
    outline: none;
}}

/* ── Main window ────────────────────────────────────────────────── */
QMainWindow {{
    background-color: {t['bg_primary']};
}}

/* ── Content Area & Scroll Areas ────────────────────────────────── */
#ContentArea {{
    background-color: {t['bg_primary']};
}}

QScrollArea {{
    background-color: transparent;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background-color: transparent;
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
    height: 44px;
    padding-left: 16px;
    border-radius: 8px;
    margin: 3px 10px;
    color: {t['text_secondary']};
    font-weight: 500;
    font-size: 14px;
}}
#NavList::item:hover {{
    background-color: {t['accent_muted']};
    color: {t['text_primary']};
}}
#NavList::item:selected {{
    background-color: {t['accent']};
    color: #FFFFFF;
    font-weight: 600;
}}

/* ── Top bar ────────────────────────────────────────────────────── */
#TopBar {{
    background-color: {t['bg_secondary']};
    border-bottom: 1px solid {t['border']};
}}

/* ── Cards / Frames ─────────────────────────────────────────────── */
#Card {{
    background-color: {t['bg_elevated']};
    border: 1px solid {t['border']};
    border-radius: 12px;
}}
#CardHeader {{
    font-size: 18px;
    font-weight: 600;
    color: {t['text_primary']};
}}

/* ── Typography Tokens ───────────────────────────────────────────── */
QLabel#PageTitle {{
    font-size: 26px;
    font-weight: 700;
    color: {t['text_primary']};
}}
QLabel#PageSubtitle {{
    font-size: 14px;
    color: {t['text_secondary']};
}}
QLabel#SectionTitle {{
    color: {t['text_primary']};
    font-size: 18px;
    font-weight: 600;
    padding-bottom: 4px;
}}
QLabel#FormLabel {{
    color: {t['text_secondary']};
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QLabel#SubCaption {{
    color: {t['text_secondary']};
    font-size: 13px;
}}
QLabel#MutedLabel {{
    color: {t['text_muted']};
    font-size: 12px;
}}

/* ── Buttons ────────────────────────────────────────────────────── */
QPushButton#PrimaryBtn {{
    background-color: {t['accent']};
    color: #FFFFFF;
    border-radius: 10px;
    padding: 0 22px;
    min-height: 44px;
    font-weight: 600;
    font-size: 14px;
    border: 1px solid transparent;
}}
QPushButton#PrimaryBtn:hover {{
    background-color: {t['accent_hover']};
}}
QPushButton#PrimaryBtn:pressed {{
    background-color: {t['accent']};
}}
QPushButton#PrimaryBtn:disabled {{
    background-color: {t['border']};
    color: {t['text_muted']};
}}

QPushButton#SecondaryBtn {{
    background-color: {t['bg_elevated']};
    color: {t['text_primary']};
    border: 1px solid {t['border']};
    border-radius: 10px;
    padding: 0 20px;
    min-height: 44px;
    font-weight: 600;
    font-size: 14px;
}}
QPushButton#SecondaryBtn:hover {{
    background-color: {t['bg_hover']};
    border-color: {t['accent']};
    color: {t['accent']};
}}
QPushButton#SecondaryBtn:pressed {{
    background-color: {t['accent_muted']};
}}

QPushButton#DangerBtn {{
    background-color: {t['danger_muted']};
    color: {t['danger']};
    border: 1px solid {t['danger']};
    border-radius: 10px;
    padding: 0 20px;
    min-height: 44px;
    font-weight: 600;
    font-size: 14px;
}}
QPushButton#DangerBtn:hover {{
    background-color: {t['danger']};
    color: #FFFFFF;
}}

QPushButton#SuccessBtn {{
    background-color: {t['success']};
    color: #FFFFFF;
    border-radius: 10px;
    padding: 0 20px;
    min-height: 44px;
    font-weight: 600;
    font-size: 14px;
}}
QPushButton#SuccessBtn:hover {{
    background-color: #059669;
}}

QPushButton#GhostBtn {{
    background-color: transparent;
    color: {t['text_secondary']};
    border-radius: 8px;
    padding: 0 16px;
    min-height: 38px;
    font-weight: 500;
    font-size: 14px;
}}
QPushButton#GhostBtn:hover {{
    background-color: {t['bg_hover']};
    color: {t['text_primary']};
}}

QToolButton {{
    background-color: transparent;
    border-radius: 8px;
    padding: 6px;
    color: {t['text_secondary']};
}}
QToolButton:hover {{
    background-color: {t['bg_hover']};
    color: {t['text_primary']};
}}

/* ── Input fields ───────────────────────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {t['bg_secondary']};
    color: {t['text_primary']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 8px 14px;
    min-height: 24px;
    font-size: 14px;
    selection-background-color: {t['accent_muted']};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1.5px solid {t['accent']};
    background-color: {t['bg_elevated']};
}}
QLineEdit:disabled, QTextEdit:disabled {{
    background-color: {t['bg_secondary']};
    color: {t['text_muted']};
}}

/* ── ComboBox ───────────────────────────────────────────────────── */
QComboBox {{
    background-color: {t['bg_secondary']};
    color: {t['text_primary']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 6px 14px;
    min-height: 28px;
    font-size: 14px;
}}
QComboBox:hover {{
    border-color: {t['accent']};
}}
QComboBox:focus {{
    border: 1.5px solid {t['accent']};
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox::down-arrow {{
    width: 12px;
    height: 12px;
}}
QComboBox QAbstractItemView {{
    background-color: {t['bg_elevated']};
    color: {t['text_primary']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    selection-background-color: {t['accent_muted']};
    selection-color: {t['accent']};
    padding: 6px;
    outline: none;
}}

/* ── Date edit ───────────────────────────────────────────────────── */
QDateEdit {{
    background-color: {t['bg_secondary']};
    color: {t['text_primary']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 6px 14px;
    min-height: 28px;
    font-size: 14px;
}}
QDateEdit:hover {{
    border-color: {t['accent']};
}}
QDateEdit::drop-down {{
    border: none;
    width: 28px;
}}

/* ── Tables ─────────────────────────────────────────────────────── */
QTableView {{
    background-color: {t['bg_elevated']};
    gridline-color: {t['border_subtle']};
    alternate-background-color: {t['bg_secondary']};
    border: 1px solid {t['border']};
    border-radius: 10px;
    font-size: 14px;
    selection-background-color: {t['accent_muted']};
    selection-color: {t['text_primary']};
    outline: none;
}}
QTableView::item {{
    padding: 8px 14px;
    min-height: 40px;
    border-bottom: 1px solid {t['border_subtle']};
}}
QTableView::item:selected {{
    background-color: {t['accent_muted']};
}}
QHeaderView::section {{
    background-color: {t['bg_secondary']};
    color: {t['text_secondary']};
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 8px 14px;
    min-height: 36px;
    border: none;
    border-bottom: 1px solid {t['border']};
    border-right: 1px solid {t['border_subtle']};
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
    background-color: {t['bg_hover']};
    border-radius: 8px;
}}

/* ── Scroll bars ─────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {t['border']};
    border-radius: 5px;
    min-height: 40px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t['text_muted']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {t['border']};
    border-radius: 5px;
    min-width: 40px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {t['text_muted']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Progress bar ────────────────────────────────────────────────── */
QProgressBar {{
    background-color: {t['border']};
    border-radius: 5px;
    min-height: 10px;
    max-height: 10px;
    text-align: center;
    font-size: 0px;
}}
QProgressBar::chunk {{
    background-color: {t['accent']};
    border-radius: 5px;
}}

/* ── Checkbox ────────────────────────────────────────────────────── */
QCheckBox {{
    spacing: 10px;
    color: {t['text_primary']};
    font-size: 14px;
}}
QCheckBox::indicator {{
    width: 20px;
    height: 20px;
    border: 1.5px solid {t['border']};
    border-radius: 5px;
    background: {t['bg_secondary']};
}}
QCheckBox::indicator:hover {{
    border-color: {t['accent']};
}}
QCheckBox::indicator:checked {{
    background: {t['accent']};
    border-color: {t['accent']};
}}

/* ── RadioButton ─────────────────────────────────────────────────── */
QRadioButton {{
    spacing: 10px;
    color: {t['text_primary']};
    font-size: 14px;
    font-weight: 500;
}}
QRadioButton::indicator {{
    width: 20px;
    height: 20px;
    border: 2px solid {t['border']};
    border-radius: 10px;
    background: {t['bg_secondary']};
}}
QRadioButton::indicator:hover {{
    border-color: {t['accent']};
}}
QRadioButton::indicator:checked {{
    background: {t['accent']};
    border-color: {t['accent']};
}}

/* ── Graphics view ───────────────────────────────────────────────── */
QGraphicsView {{
    background-color: {t['bg_secondary']};
    border: 1px solid {t['border']};
    border-radius: 10px;
}}

/* ── Tooltip ─────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {t['bg_elevated']};
    color: {t['text_primary']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
}}

/* ── Status bar ──────────────────────────────────────────────────── */
QStatusBar {{
    background-color: {t['bg_secondary']};
    color: {t['text_secondary']};
    font-size: 13px;
    border-top: 1px solid {t['border']};
    padding: 4px 12px;
}}
/* ── Semantic Application Components ────────────────────────────── */
#DashedDropZone {{ background-color: {t['bg_secondary']}; border: 2px dashed {t['border']}; border-radius: 16px; }}
#DashedDropZone:hover {{ border-color: {t['accent']}; background-color: {t['bg_hover']}; }}
#DropZoneIcon {{ color: {t['accent']}; }}

#ActivityList {{ border: none; background: transparent; }}
#ActivityList::item {{ background: {t['bg_elevated']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 10px; margin-bottom: 4px; }}
#ActivityList::item:hover {{ border-color: {t['accent']}; background: {t['bg_hover']}; }}

#ActivityTag {{ color: {t['accent']}; background: {t['accent_muted']}; border-radius: 4px; padding: 2px 6px; }}

#StatusReady {{ color: {t['success']}; background: {t['success_muted']}; border-radius: 6px; padding: 4px 10px; }}
#RemoveBtn {{ background: transparent; color: {t['text_secondary']}; font-size: 14px; border-radius: 6px; }}
#RemoveBtn:hover {{ background: {t['danger_muted']}; color: {t['danger']}; }}

#ProgressBar {{ background: {t['bg_secondary']}; border-radius: 3px; }}
#ProgressBar::chunk {{ background: {t['accent']}; border-radius: 3px; }}
#ProgressBarSuccess {{ background: {t['bg_secondary']}; border-radius: 4px; }}
#ProgressBarSuccess::chunk {{ background: {t['success']}; border-radius: 4px; }}

#Toolbar {{ background: {t['bg_secondary']}; border-bottom: 1px solid {t['border']}; border-top: none; border-left: none; border-right: none; border-radius: 0; }}
#FilterBar {{ background: {t['bg_secondary']}; border-bottom: 1px solid {t['border']}; }}
#FilterButton {{ background: {t['bg_hover']}; color: {t['text_secondary']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 2px 10px; font-size: 12px; font-weight: 600; }}
#FilterButton:hover {{ color: {t['text_primary']}; border-color: {t['accent']}; }}
#FilterButton:checked {{ background: {t['accent']}; color: #FFFFFF; border-color: {t['accent']}; }}

#CommentList {{ border: none; background: {t['bg_secondary']}; padding: 12px; }}
#CommentList::item {{ background: transparent; border-radius: 10px; padding: 0px; margin-bottom: 6px; }}
#CommentList::item:hover {{ background: {t['bg_hover']}; }}
#CommentList::item:selected {{ background: {t['accent_muted']}; }}

#ThumbnailList {{ border-top: 1px solid {t['border']}; border-radius: 0; background: {t['bg_secondary']}; padding: 4px; }}
#ThumbnailList::item {{ border: 2px solid transparent; border-radius: 6px; margin: 4px; color: {t['text_secondary']}; font-size: 11px; font-weight: 600; }}
#ThumbnailList::item:hover {{ background: {t['bg_hover']}; border-color: {t['border']}; }}
#ThumbnailList::item:selected {{ border-color: {t['accent']}; background: {t['accent_muted']}; color: {t['accent']}; }}

#ReviewPanel {{ background: {t['bg_secondary']}; border: none; }}
#ReviewScroll {{ background: {t['bg_secondary']}; border-left: 1px solid {t['border']}; }}
#OcrBox {{ background: {t['bg_primary']}; border: 1px solid {t['border']}; border-radius: 8px; color: {t['text_primary']}; padding: 10px; }}

#FormatCard {{ background-color: {t['bg_elevated']}; border: 1px solid {t['border']}; border-radius: 12px; }}
#FormatCard:hover {{ border-color: {t['accent']}; background-color: {t['bg_hover']}; }}
#FormatCardSelected {{ background-color: {t['accent_muted']}; border: 2px solid {t['accent']}; border-radius: 12px; }}

#Indicator {{ color: {t['text_secondary']}; background-color: {t['bg_hover']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 4px 12px; }}
#IndicatorSelected {{ color: #FFFFFF; background-color: {t['accent']}; border-radius: 6px; padding: 4px 14px; font-weight: bold; }}

#TopAvatarBtn {{ background: {t['bg_elevated']}; border: 1px solid {t['border']}; border-radius: 10px; color: {t['text_primary']}; padding: 4px 12px; }}
#TopAvatarBtn:hover {{ background: {t['bg_hover']}; border-color: {t['accent']}; }}

#SearchBox {{ background: {t['bg_hover']}; border: 1px solid transparent; border-radius: 8px; color: {t['text_primary']}; padding: 6px 14px 6px 32px; font-size: 13px; }}
#SearchBox:focus {{ background: {t['bg_elevated']}; border: 1px solid {t['accent']}; }}
"""

CURRENT_THEME = 'dark'
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
        global CURRENT_THEME
        CURRENT_THEME = theme
        self._app.setStyleSheet(_build_qss(THEMES[theme]))
        self.theme_changed.emit(theme)

    def toggle(self) -> None:
        self.apply("light" if self._current == "dark" else "dark")


