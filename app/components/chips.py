"""Status chip and category badge components."""
from __future__ import annotations
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

_STATUS_COLORS = {
    "Pending":    ("#C2C6D6", "rgba(194, 198, 214, 0.12)", "#424754"),
    "Approved":   ("#4EDEA3", "rgba(78, 222, 163, 0.12)", "rgba(78, 222, 163, 0.3)"),
    "Rejected":   ("#FFB4AB", "rgba(255, 180, 171, 0.12)", "rgba(255, 180, 171, 0.3)"),
    "Flagged":    ("#FFB95F", "rgba(255, 185, 95, 0.12)", "rgba(255, 185, 95, 0.3)"),
    "Ready":      ("#4EDEA3", "rgba(78, 222, 163, 0.12)", "rgba(78, 222, 163, 0.3)"),
    "Active":     ("#38BDF8", "rgba(56, 189, 248, 0.12)", "rgba(56, 189, 248, 0.3)"),
    "Running":    ("#38BDF8", "rgba(56, 189, 248, 0.12)", "rgba(56, 189, 248, 0.3)"),
    "Processing": ("#FFB95F", "rgba(255, 185, 95, 0.12)", "rgba(255, 185, 95, 0.3)"),
    "Completed":  ("#4EDEA3", "rgba(78, 222, 163, 0.12)", "rgba(78, 222, 163, 0.3)"),
    "Done":       ("#4EDEA3", "rgba(78, 222, 163, 0.12)", "rgba(78, 222, 163, 0.3)"),
    "Analyzed":   ("#8B9CFF", "rgba(139, 156, 255, 0.12)", "rgba(139, 156, 255, 0.3)"),
    "Reviewed":   ("#4EDEA3", "rgba(78, 222, 163, 0.12)", "rgba(78, 222, 163, 0.3)"),
}
_STATUS_COLORS_LIGHT = {
    "Pending":    ("#475569", "#F1F5F9", "#CBD5E1"),
    "Approved":   ("#059669", "#D1FAE5", "#A7F3D0"),
    "Rejected":   ("#DC2626", "#FEE2E2", "#FECACA"),
    "Flagged":    ("#D97706", "#FEF3C7", "#FDE68A"),
    "Ready":      ("#059669", "#D1FAE5", "#A7F3D0"),
    "Active":     ("#0284C7", "#E0F2FE", "#BAE6FD"),
    "Running":    ("#0284C7", "#E0F2FE", "#BAE6FD"),
    "Processing": ("#D97706", "#FEF3C7", "#FDE68A"),
    "Completed":  ("#059669", "#D1FAE5", "#A7F3D0"),
    "Done":       ("#059669", "#D1FAE5", "#A7F3D0"),
    "Analyzed":   ("#4F46E5", "#EEF2FF", "#C7D2FE"),
    "Reviewed":   ("#059669", "#D1FAE5", "#A7F3D0"),
}

_CATEGORY_COLORS = {
    "Technical":     ("#EF4444", "#451A1A", "#7F1D1D"),
    "Drafting":      ("#A78BFA", "#2E1065", "#4C1D95"),
    "Dimension":     ("#38BDF8", "#082F49", "#0369A1"),
    "Cosmetic":      ("#F472B6", "#500724", "#831843"),
    "Standards":     ("#F59E0B", "#452F0A", "#78350F"),
    "Coordination":  ("#34D399", "#064E3B", "#065F46"),
    "Documentation": ("#94A3B8", "#1E293B", "#334155"),
    "Revision":      ("#FB923C", "#431407", "#7C2D12"),
    "Calculation":   ("#818CF8", "#1E1B4B", "#312E81"),
    "Feasibility":   ("#2DD4BF", "#042F2E", "#115E59"),
    "Material":      ("#06B6D4", "#083344", "#155E75"),
    "Notes":         ("#A3E635", "#1A2E05", "#365314"),
    "BOM":           ("#C084FC", "#3B0764", "#581C87"),
    # Backwards compatibility
    "Dimensional":   ("#38BDF8", "#082F49", "#0369A1"),
    "Structural":    ("#A78BFA", "#2E1065", "#4C1D95"),
    "Electrical":    ("#F59E0B", "#452F0A", "#78350F"),
    "Other":         ("#94A3B8", "#1E293B", "#334155"),
    "Mechanical":    ("#FB923C", "#431407", "#7C2D12"),
}
_CATEGORY_COLORS_LIGHT = {
    "Technical":     ("#DC2626", "#FEE2E2", "#FECACA"),
    "Drafting":      ("#7C3AED", "#EDE9FE", "#DDD6FE"),
    "Dimension":     ("#0284C7", "#E0F2FE", "#BAE6FD"),
    "Cosmetic":      ("#DB2777", "#FCE7F3", "#FBCFE8"),
    "Standards":     ("#D97706", "#FEF3C7", "#FDE68A"),
    "Coordination":  ("#059669", "#D1FAE5", "#A7F3D0"),
    "Documentation": ("#475569", "#F1F5F9", "#E2E8F0"),
    "Revision":      ("#EA580C", "#FFEDD5", "#FED7AA"),
    "Calculation":   ("#4F46E5", "#EEF2FF", "#E0E7FF"),
    "Feasibility":   ("#0D9488", "#CCFBF1", "#99F6E4"),
    "Material":      ("#0891B2", "#CFFAFE", "#A5F3FC"),
    "Notes":         ("#65A30D", "#ECFCCB", "#D9F99D"),
    "BOM":           ("#9333EA", "#F3E8FF", "#E9D5FF"),
    # Backwards compatibility
    "Dimensional":   ("#0284C7", "#E0F2FE", "#BAE6FD"),
    "Structural":    ("#7C3AED", "#EDE9FE", "#DDD6FE"),
    "Electrical":    ("#D97706", "#FEF3C7", "#FDE68A"),
    "Other":         ("#475569", "#F1F5F9", "#E2E8F0"),
    "Mechanical":    ("#EA580C", "#FFEDD5", "#FED7AA"),
}


class StatusChip(QLabel):
    def __init__(self, status: str, dark: bool | None = None, parent=None):
        super().__init__(parent)
        from app.theme import CURRENT_THEME
        if dark is None:
            dark = (CURRENT_THEME == "dark")
        self.set_status(status, dark)

    def set_status(self, status: str, dark: bool = True):
        palette = _STATUS_COLORS if dark else _STATUS_COLORS_LIGHT
        text_c, bg_c, border_c = palette.get(status, ("#C2C6D6", "#171F33", "#424754"))
        self.setText(status.upper())
        self.setFont(QFont("Inter", 11, QFont.Weight.Bold))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"color: {text_c}; background-color: {bg_c};"
            f"border: 1px solid {border_c};"
            f"border-radius: 6px; padding: 3px 10px;"
        )
        self.setMinimumHeight(24)


class CategoryBadge(QLabel):
    def __init__(self, category: str, dark: bool | None = None, parent=None):
        super().__init__(parent)
        from app.theme import CURRENT_THEME
        if dark is None:
            dark = (CURRENT_THEME == "dark")
        self.set_category(category, dark)

    def set_category(self, category: str, dark: bool = True):
        palette = _CATEGORY_COLORS if dark else _CATEGORY_COLORS_LIGHT
        text_c, bg_c, border_c = palette.get(category, ("#C2C6D6", "#171F33", "#424754"))
        self.setText(category.upper())
        self.setFont(QFont("Inter", 11, QFont.Weight.Bold))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"color: {text_c}; background-color: {bg_c};"
            f"border: 1px solid {border_c};"
            f"border-radius: 6px; padding: 3px 10px;"
        )
        self.setMinimumHeight(24)
