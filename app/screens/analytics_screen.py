"""
analytics_screen.py — Dashboard Analytics screen.

Provides:
    AnalyticsPage(QWidget)
        Filter bar, KPI summary cards, and a grid of Pareto, status trend,
        and category distribution charts connected to AppController & SQLite database.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame,
                                QLabel, QPushButton, QComboBox,
                                QDateEdit, QGridLayout)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont

from app.components.kpi_card import KpiCard
from app.components.charts import (
    build_pareto_chart,
    build_monthly_chart,
    build_category_pie,
)

from datetime import datetime

STANDARD_CATEGORIES: List[str] = [
    "Technical",
    "Drafting",
    "Dimension",
    "Cosmetic",
    "Standards",
    "Coordination",
    "Documentation",
    "Revision",
    "Calculation",
    "Feasibility",
    "Material",
    "Notes",
    "BOM",
    "Uncategorized",
]


class AnalyticsPage(QWidget):
    """
    Analytics Dashboard — filter bar, KPI cards, Pareto + line + donut charts
    connected to AppController backend.
    """

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._kpi_cards: List[KpiCard] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # ── Filter bar ────────────────────────────────────────────
        fb = QHBoxLayout()
        fb.setSpacing(12)

        # Project combobox
        p_lbl = QLabel("Project:")
        p_lbl.setObjectName("SubCaption")
        fb.addWidget(p_lbl)
        self._proj_cb = QComboBox()
        self._proj_cb.setFixedHeight(36)
        fb.addWidget(self._proj_cb)

        # Drawing combobox (for drawing-level Pareto & category distribution)
        dwg_lbl = QLabel("Drawing:")
        dwg_lbl.setObjectName("SubCaption")
        fb.addWidget(dwg_lbl)
        self._dwg_cb = QComboBox()
        self._dwg_cb.setFixedHeight(36)
        fb.addWidget(self._dwg_cb)

        # Department combobox (for per-department Pareto analysis)
        d_lbl = QLabel("Department:")
        d_lbl.setObjectName("SubCaption")
        fb.addWidget(d_lbl)
        self._dept_cb = QComboBox()
        self._dept_cb.setFixedHeight(36)
        fb.addWidget(self._dept_cb)

        # Category combobox
        c_lbl = QLabel("Category:")
        c_lbl.setObjectName("SubCaption")
        fb.addWidget(c_lbl)
        self._cat_cb = QComboBox()
        self._cat_cb.setFixedHeight(36)
        fb.addWidget(self._cat_cb)

        self._populate_filters()

        # Connect filter widgets to auto-update charts & cascading drawings
        self._proj_cb.currentIndexChanged.connect(self._on_project_changed)
        self._dwg_cb.currentIndexChanged.connect(self._apply_filters)
        self._dept_cb.currentIndexChanged.connect(self._apply_filters)
        self._cat_cb.currentIndexChanged.connect(self._apply_filters)

        from_lbl = QLabel("From:")
        from_lbl.setObjectName("SubCaption")
        fb.addWidget(from_lbl)
        # Default start date: 1 year prior to today
        self._date_from = QDateEdit(QDate.currentDate().addYears(-1))
        self._date_from.setFixedHeight(36)
        self._date_from.setCalendarPopup(True)
        self._date_from.dateChanged.connect(self._apply_filters)
        fb.addWidget(self._date_from)

        to_lbl = QLabel("To:")
        to_lbl.setObjectName("SubCaption")
        fb.addWidget(to_lbl)
        self._date_to = QDateEdit(QDate.currentDate())
        self._date_to.setFixedHeight(36)
        self._date_to.setCalendarPopup(True)
        self._date_to.dateChanged.connect(self._apply_filters)
        fb.addWidget(self._date_to)

        fb.addStretch()

        apply_btn = QPushButton("Apply Filters")
        apply_btn.setObjectName("PrimaryBtn")
        apply_btn.setFixedHeight(36)
        apply_btn.clicked.connect(self._apply_filters)
        fb.addWidget(apply_btn)
        root.addLayout(fb)

        # ── KPI summary ───────────────────────────────────────────
        self._kpi_row = QHBoxLayout()
        self._kpi_row.setSpacing(16)
        self._build_kpi_cards()
        root.addLayout(self._kpi_row)

        # ── Chart grid ────────────────────────────────────────────
        self._grid = QGridLayout()
        self._grid.setSpacing(16)
        self._build_charts()
        root.addLayout(self._grid, 1)

    def _populate_filters(self) -> None:
        """Populate project, drawing, department, and category filter dropdowns."""
        self._proj_cb.blockSignals(True)
        self._proj_cb.clear()
        self._proj_cb.addItem("All Projects", "")
        if self._controller:
            try:
                records = self._controller.get_all_projects()
                for p in records:
                    pid = p.get("id", "") if isinstance(p, dict) else getattr(p, "id", "")
                    name = p.get("name", pid) if isinstance(p, dict) else getattr(p, "name", pid)
                    self._proj_cb.addItem(name, pid)
            except Exception:
                pass
        self._proj_cb.blockSignals(False)

        self._populate_drawings_for_selected_project()

        self._dept_cb.blockSignals(True)
        self._dept_cb.clear()
        departments = ["All Departments"]
        if self._controller:
            try:
                records = self._controller.get_all_departments()
                for d in records:
                    name = d.get("name") if isinstance(d, dict) else getattr(d, "name", "")
                    if name and name not in departments:
                        departments.append(name)
            except Exception:
                pass
        if len(departments) == 1:
            departments.extend([
                "Electrical Engineering",
                "GPD",
                "Pipe Support Engineering",
                "Piping Engineering",
                "Plakon",
                "Structural & Physical Design",
                "System Engineering",
                "Unassigned",
            ])
        self._dept_cb.addItems(departments)
        self._dept_cb.blockSignals(False)

        self._cat_cb.blockSignals(True)
        self._cat_cb.clear()
        categories = ["All Categories"]
        if self._controller:
            try:
                cat_records = self._controller.get_all_categories()
                for c in cat_records:
                    c_name = c.get("name") if isinstance(c, dict) else getattr(c, "name", "")
                    if c_name and c_name not in categories:
                        categories.append(c_name)
            except Exception:
                pass
        if len(categories) == 1:
            categories.extend(STANDARD_CATEGORIES)
        self._cat_cb.addItems(categories)
        self._cat_cb.blockSignals(False)

    def _populate_drawings_for_selected_project(self) -> None:
        """Populate drawing dropdown filtered by current project selection."""
        proj_id = self._proj_cb.currentData() if hasattr(self, "_proj_cb") else ""
        self._dwg_cb.blockSignals(True)
        self._dwg_cb.clear()
        self._dwg_cb.addItem("All Drawings", "")
        if self._controller:
            try:
                drawings = self._controller.get_all_drawings(project_id=proj_id if proj_id else None)
                for d in drawings:
                    did = d.get("id", "")
                    fname = d.get("file_name", "Drawing")
                    self._dwg_cb.addItem(fname, did)
            except Exception:
                pass
        self._dwg_cb.blockSignals(False)

    def _on_project_changed(self, index: int) -> None:
        """Update drawing combobox options when selected project changes and reload data."""
        self._populate_drawings_for_selected_project()
        self._apply_filters()

    def _get_active_filters(self) -> dict:
        """Read current filter state from all widgets."""
        proj_id = self._proj_cb.currentData() if hasattr(self, "_proj_cb") else ""
        dwg_id  = self._dwg_cb.currentData() if hasattr(self, "_dwg_cb") else ""
        dept    = self._dept_cb.currentText() if hasattr(self, "_dept_cb") else "All Departments"
        cat     = self._cat_cb.currentText() if hasattr(self, "_cat_cb") else "All Categories"

        # Read date limits from QDateEdit
        qfrom = self._date_from.date() if hasattr(self, "_date_from") else None
        qto   = self._date_to.date() if hasattr(self, "_date_to") else None

        from_dt = datetime(qfrom.year(), qfrom.month(), qfrom.day()) if qfrom and qfrom.isValid() else None
        to_dt   = datetime(qto.year(), qto.month(), qto.day(), 23, 59, 59) if qto and qto.isValid() else None

        return {
            "project_id": proj_id if proj_id else None,
            "drawing_id": dwg_id if dwg_id else None,
            "department_name": None if dept in ("All Departments", "") else dept,
            "category_name": None if cat in ("All Categories", "") else cat,
            "date_from": from_dt,
            "date_to": to_dt,
        }

    def _build_kpi_cards(self) -> None:
        """Fetch real KPI summary data using active filters and build KPI cards."""
        while self._kpi_row.count():
            item = self._kpi_row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._kpi_cards.clear()

        filters = self._get_active_filters()
        kpi_data = self._controller.get_dashboard_kpis(
            project_id=filters["project_id"],
            drawing_id=filters["drawing_id"],
            department_name=filters["department_name"],
            category_name=filters["category_name"],
            date_from=filters["date_from"],
            date_to=filters["date_to"],
        ) if self._controller else None

        if kpi_data is not None:
            if hasattr(kpi_data, "total_comments"):
                total_comments = kpi_data.total_comments
                approved_count = kpi_data.approved_count
                rejected_count = kpi_data.rejected_count
                flagged_count  = kpi_data.flagged_count
            elif isinstance(kpi_data, dict):
                total_comments = kpi_data.get("total_comments", 0)
                approved_count = kpi_data.get("approved_count", 0)
                rejected_count = kpi_data.get("rejected_count", 0)
                flagged_count  = kpi_data.get("flagged_count", 0)
            else:
                total_comments, approved_count, rejected_count, flagged_count = 0, 0, 0, 0
        else:
            total_comments, approved_count, rejected_count, flagged_count = 0, 0, 0, 0

        approved_pct = f"{(approved_count / total_comments * 100):.1f}%" if total_comments > 0 else "0%"
        rejected_pct = f"{(rejected_count / total_comments * 100):.1f}%" if total_comments > 0 else "0%"
        flagged_pct  = f"{(flagged_count / total_comments * 100):.1f}%" if total_comments > 0 else "0%"

        kpi_items = [
            ("fa5s.comments",     f"{total_comments:,}", "Total Comments", "Total in Query", "#3E9BFF"),
            ("fa5s.check-circle", f"{approved_count:,}", "Approved",       approved_pct,     "#4ADE80"),
            ("fa5s.times-circle", f"{rejected_count:,}", "Rejected",       rejected_pct,     "#F87171"),
            ("fa5s.flag",         f"{flagged_count:,}",  "Flagged",        flagged_pct,      "#FBBF24"),
        ]

        for icon, val, lbl, trend, color in kpi_items:
            card = KpiCard(icon, val, lbl, trend, color)
            card.setMinimumHeight(120)
            self._kpi_cards.append(card)
            self._kpi_row.addWidget(card, 1)

    def _build_charts(self) -> None:
        """Fetch real data for charts and populate grid using all active filters."""
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        filters = self._get_active_filters()
        proj_id   = filters["project_id"]
        dwg_id    = filters["drawing_id"]
        dept_name = filters["department_name"]
        cat_name  = filters["category_name"]
        d_from    = filters["date_from"]
        d_to      = filters["date_to"]

        pareto_data = self._controller.get_pareto_analysis(
            project_id=proj_id,
            drawing_id=dwg_id,
            department_name=dept_name,
            category_name=cat_name,
            date_from=d_from,
            date_to=d_to,
        ) if self._controller else None

        category_data = self._controller.get_category_distribution(
            project_id=proj_id,
            drawing_id=dwg_id,
            department_name=dept_name,
            category_name=cat_name,
            date_from=d_from,
            date_to=d_to,
        ) if self._controller else None

        trend_data = self._controller.get_status_trend(
            project_id=proj_id,
            drawing_id=dwg_id,
            department_name=dept_name,
            category_name=cat_name,
            date_from=d_from,
            date_to=d_to,
        ) if self._controller else None

        pareto_view  = build_pareto_chart(pareto_data)
        monthly_view = build_monthly_chart(trend_data)
        pie_view     = build_category_pie(category_data)

        def _wrap(view, min_h: int = 280) -> QFrame:
            f = QFrame()
            f.setObjectName("Card")
            lay = QVBoxLayout(f)
            lay.setContentsMargins(8, 8, 8, 8)
            view.setMinimumHeight(min_h)
            lay.addWidget(view)
            return f

        self._grid.addWidget(_wrap(pareto_view,  320), 0, 0, 2, 1)
        self._grid.addWidget(_wrap(monthly_view, 220), 0, 1)
        self._grid.addWidget(_wrap(pie_view,     220), 1, 1)

    def _apply_filters(self, *args) -> None:
        """Trigger reload of KPIs and charts based on current filter state."""
        self.reload_data()

    def reload_data(self) -> None:
        """Reload live KPI metrics, charts, and filter options from the controller."""
        self._build_kpi_cards()
        self._build_charts()

    def reload_comments(self) -> None:
        """Alias to refresh analytics when comments or drawings update."""
        self.reload_data()

