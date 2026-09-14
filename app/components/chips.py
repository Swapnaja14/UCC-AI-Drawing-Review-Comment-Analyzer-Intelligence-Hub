"""Status chip and category badge components."""
from __future__ import annotations
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

_STATUS_COLORS = {
    "Pending":    ("#A6A9B1", "#3A3C42"),
    "Approved":   ("#4ADE80", "#1a3d26"),
    "Rejected":   ("#F87171", "#3d1a1a"),
    "Flagged":    ("#FBBF24", "#3d2e0a"),
    "Ready":      ("#4ADE80", "#1a3d26"),
    "Active":     ("#3E9BFF", "#0f2b48"),
    "Running":    ("#38BDF8", "#0d2a3d"),
    "Processing": ("#FBBF24", "#3d2e0a"),
    "Completed":  ("#4ADE80", "#1a3d26"),
    "Done":       ("#4ADE80", "#1a3d26"),
    "Analyzed":   ("#8B9CFF", "#1c204d"),
    "Reviewed":   ("#4ADE80", "#1a3d26"),
}
_STATUS_COLORS_LIGHT = {
    "Pending":    ("#5B5F6A", "#E8E9EC"),
    "Approved":   ("#1E8E3E", "#D4F2DC"),
    "Rejected":   ("#D93025", "#FAD5D3"),
    "Flagged":    ("#E8A000", "#FDF0CD"),
    "Ready":      ("#1E8E3E", "#D4F2DC"),
    "Active":     ("#0284C7", "#E0F2FE"),
    "Running":    ("#0284C7", "#E0F2FE"),
    "Processing": ("#D97706", "#FEF3C7"),
    "Completed":  ("#1E8E3E", "#D4F2DC"),
    "Done":       ("#1E8E3E", "#D4F2DC"),
    "Analyzed":   ("#4F46E5", "#EEF2FF"),
    "Reviewed":   ("#1E8E3E", "#D4F2DC"),
}

_CATEGORY_COLORS = {
    "Technical":     ("#F87171", "#3d1a1a"),
    "Drafting":      ("#A78BFA", "#2a1a4d"),
    "Dimension":     ("#38BDF8", "#0d2a3d"),
    "Cosmetic":      ("#F472B6", "#3d1a2d"),
    "Standards":     ("#FBBF24", "#3d2e0a"),
    "Coordination":  ("#34D399", "#0a2d1e"),
    "Documentation": ("#94A3B8", "#252b35"),
    "Revision":      ("#FB923C", "#3d1f0a"),
    "Calculation":   ("#818CF8", "#1e1b4b"),
    "Feasibility":   ("#2DD4BF", "#0a2d2a"),
    "Material":      ("#06B6D4", "#083344"),
    "Notes":         ("#A3E635", "#24330a"),
    "BOM":           ("#C084FC", "#3b0764"),
    # Backwards compatibility
    "Dimensional":   ("#38BDF8", "#0d2a3d"),
    "Structural":    ("#A78BFA", "#2a1a4d"),
    "Electrical":    ("#FBBF24", "#3d2e0a"),
    "Other":         ("#94A3B8", "#252b35"),
    "Mechanical":    ("#FB923C", "#3d1f0a"),
}
_CATEGORY_COLORS_LIGHT = {
    "Technical":     ("#DC2626", "#FEE2E2"),
    "Drafting":      ("#7C3AED", "#EDE9FE"),
    "Dimension":     ("#0284C7", "#E0F2FE"),
    "Cosmetic":      ("#DB2777", "#FCE7F3"),
    "Standards":     ("#D97706", "#FEF3C7"),
    "Coordination":  ("#059669", "#D1FAE5"),
    "Documentation": ("#475569", "#F1F5F9"),
    "Revision":      ("#EA580C", "#FFEDD5"),
    "Calculation":   ("#4F46E5", "#EEF2FF"),
    "Feasibility":   ("#0D9488", "#CCFBF1"),
    "Material":      ("#0891B2", "#CFFAFE"),
    "Notes":         ("#65A30D", "#ECFCCB"),
    "BOM":           ("#9333EA", "#F3E8FF"),
    # Backwards compatibility
    "Dimensional":   ("#0067C5", "#DCEEFF"),
    "Structural":    ("#7C3AED", "#EDE9FE"),
    "Electrical":    ("#D97706", "#FEF3C7"),
    "Other":         ("#64748B", "#F1F5F9"),
    "Mechanical":    ("#EA580C", "#FFF7ED"),
}


class StatusChip(QLabel):
    def __init__(self, status: str, dark: bool = True, parent=None):
        super().__init__(parent)
        self.set_status(status, dark)

    def set_status(self, status: str, dark: bool = True):
        palette = _STATUS_COLORS if dark else _STATUS_COLORS_LIGHT
        text_c, bg_c = palette.get(status, ("#A6A9B1", "#3A3C42"))
        self.setText(status.upper())
        self.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"color:{text_c}; background-color:{bg_c};"
            f"border-radius:4px; padding:2px 8px;"
        )
        self.setFixedHeight(22)


class CategoryBadge(QLabel):
    def __init__(self, category: str, dark: bool = True, parent=None):
        super().__init__(parent)
        self.set_category(category, dark)

    def set_category(self, category: str, dark: bool = True):
        palette = _CATEGORY_COLORS if dark else _CATEGORY_COLORS_LIGHT
        text_c, bg_c = palette.get(category, ("#A6A9B1", "#2d2f34"))
        self.setText(category.upper())
        self.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"color:{text_c}; background-color:{bg_c};"
            f"border-radius:4px; padding:2px 10px;"
        )
        self.setFixedHeight(22)
