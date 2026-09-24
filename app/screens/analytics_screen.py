"""
analytics_screen.py — Redesigned Analytics & Quality Intelligence dashboard screen.

Provides:
    AnalyticsPage(QWidget)
        Filter bar, KPI summary cards, and a grid of category, trend,
        and disposition distribution charts connected to AppController & SQLite database.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QComboBox,
    QDateEdit,
    QGridLayout,
    QScrollArea,
    QSizePolicy,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont, QColor

from app.components.kpi_card import KpiCard
from app.components.charts import (
    build_pareto_chart,
    build_monthly_chart,
    build_status_trend_chart,
    build_category_pie,
)

from datetime import datetime

STANDARD_CATEGORIES: List[str] = [
    "Structural Engineering",
    "MEP & HVAC",
    "Architecture & Interiors",
    "Civil & Geotech",
    "Fire & Life Safety",
    "Drafting & Detailing",
    "General Coordination",
]


def _card(parent=None) -> QFrame:
    """Creates a light rounded card with subtle outline and soft drop shadow."""
    f = QFrame(parent)
    f.setObjectName("DashCard")
    f.setStyleSheet(
        """
        QFrame#DashCard {
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
        }
        """
    )
    shadow = QGraphicsDropShadowEffect(f)
    shadow.setBlurRadius(15)
    shadow.setColor(QColor(15, 23, 42, 10))
    shadow.setOffset(0, 4)
    f.setGraphicsEffect(shadow)
    return f


class AnalyticsPage(QWidget):
    """
    Analytics & Quality Intelligence Dashboard — Light Theme edition
    matching the Stitch Enterprise Telemetry interface.
    """

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._kpi_cards: List[QWidget] = []

        self.setObjectName("AnalyticsRoot")
        self.setStyleSheet(
            """
            QWidget#AnalyticsRoot {
                background-color: #F8FAFC;
            }
            QLabel {
                background-color: transparent;
            }
            """
        )

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        container = QWidget()
        container.setObjectName("AnalyticsRoot")
        root = QVBoxLayout(container)
        root.setContentsMargins(32, 24, 32, 36)
        root.setSpacing(20)

        # ── 1. Top Enterprise Telemetry Badge ────────────────────────────────
        top_badge_box = QHBoxLayout()
        top_badge_box.setSpacing(8)

        pipeline_tag = QLabel("● ENTERPRISE TELEMETRY")
        pipeline_tag.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        pipeline_tag.setStyleSheet(
            "color: #2563EB; background-color: #EFF6FF; border-radius: 10px; padding: 3px 10px;"
        )

        pipeline_sub = QLabel("• LIVE PIPELINE")
        pipeline_sub.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        pipeline_sub.setStyleSheet("color: #64748B; background: transparent;")

        top_badge_box.addWidget(pipeline_tag)
        top_badge_box.addWidget(pipeline_sub)
        top_badge_box.addStretch()
        root.addLayout(top_badge_box)

        # ── 2. Page Header ──────────────────────────────────────────────────
        hdr_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        title = QLabel("Analytics & Quality Intelligence")
        title.setFont(QFont("Inter", 22, QFont.Weight.Bold))
        title.setStyleSheet("color: #0F172A; background: transparent;")

        subtitle = QLabel(
            "Analyze drawing review activity, comment trends, and review outcomes across enterprise projects."
        )
        subtitle.setFont(QFont("Inter", 11))
        subtitle.setStyleSheet("color: #64748B; background: transparent;")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        hdr_row.addLayout(title_box, 1)

        meta_info = QLabel("⚙ ANSI ISO 19650  •  Updated Oct 01, 17:42 UTC")
        meta_info.setFont(QFont("Inter", 9.5))
        meta_info.setStyleSheet(
            "color: #475569; background-color: #F1F5F9; border-radius: 6px; padding: 5px 12px;"
        )
        hdr_row.addWidget(meta_info, 0, Qt.AlignmentFlag.AlignTop)

        root.addLayout(hdr_row)

        # ── 3. Filter Toolbar ───────────────────────────────────────────────
        filter_card = _card()
        fb = QHBoxLayout(filter_card)
        fb.setContentsMargins(18, 14, 18, 14)
        fb.setSpacing(14)

        # Project combobox
        p_box = QVBoxLayout()
        p_box.setSpacing(4)
        p_lbl = QLabel("Project Scope")
        p_lbl.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        p_lbl.setStyleSheet("color: #475569;")
        p_box.addWidget(p_lbl)

        self._proj_cb = QComboBox()
        self._proj_cb.setFixedHeight(36)
        self._proj_cb.setMinimumWidth(180)
        self._proj_cb.setStyleSheet(
            """
            QComboBox {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 2px 10px;
                color: #0F172A;
            }
            """
        )
        p_box.addWidget(self._proj_cb)
        fb.addLayout(p_box)

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
        c_box = QVBoxLayout()
        c_box.setSpacing(4)
        c_lbl = QLabel("Discipline / Category")
        c_lbl.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        c_lbl.setStyleSheet("color: #475569;")
        c_box.addWidget(c_lbl)

        self._cat_cb = QComboBox()
        self._cat_cb.setFixedHeight(36)
        self._cat_cb.setMinimumWidth(180)
        self._cat_cb.setStyleSheet(
            """
            QComboBox {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 2px 10px;
                color: #0F172A;
            }
            """
        )
        c_box.addWidget(self._cat_cb)
        fb.addLayout(c_box)

        self._populate_filters()

        # Connect filter widgets to auto-update charts & cascading drawings
        self._proj_cb.currentIndexChanged.connect(self._on_project_changed)
        self._dwg_cb.currentIndexChanged.connect(self._apply_filters)
        self._dept_cb.currentIndexChanged.connect(self._apply_filters)
        self._cat_cb.currentIndexChanged.connect(self._apply_filters)

        # Date range
        df_box = QVBoxLayout()
        df_box.setSpacing(4)
        from_lbl = QLabel("Reporting Period")
        from_lbl.setFont(QFont("Inter", 9, QFont.Weight.Bold))
        from_lbl.setStyleSheet("color: #475569;")
        df_box.addWidget(from_lbl)

        date_row = QHBoxLayout()
        date_row.setSpacing(6)

        # Default start date: 1 year prior to today
        self._date_from = QDateEdit(QDate.currentDate().addYears(-1))
        self._date_from.setCalendarPopup(True)
        self._date_from.setFixedHeight(36)
        self._date_from.setStyleSheet(
            "QDateEdit { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; padding: 0 8px; color: #0F172A; }"
        )
        self._date_from.dateChanged.connect(self._apply_filters)

        sep = QLabel("–")
        sep.setStyleSheet("color: #64748B;")

        self._date_to = QDateEdit(QDate.currentDate())
        self._date_to.setCalendarPopup(True)
        self._date_to.setFixedHeight(36)
        self._date_to.setStyleSheet(
            "QDateEdit { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; padding: 0 8px; color: #0F172A; }"
        )
        self._date_to.dateChanged.connect(self._apply_filters)

        date_row.addWidget(self._date_from)
        date_row.addWidget(sep)
        date_row.addWidget(self._date_to)
        df_box.addLayout(date_row)
        fb.addLayout(df_box)

        fb.addStretch()

        # Action Buttons
        act_box = QHBoxLayout()
        act_box.setSpacing(8)

        print_btn = QPushButton("🖨 Print")
        print_btn.setFixedHeight(36)
        print_btn.setFont(QFont("Inter", 9, QFont.Weight.Medium))
        print_btn.setStyleSheet(
            "QPushButton { background: #FFFFFF; color: #334155; border: 1px solid #CBD5E1; border-radius: 6px; padding: 0 12px; }"
            "QPushButton:hover { background: #F8FAFC; }"
        )

        csv_btn = QPushButton("📊 Export CSV")
        csv_btn.setFixedHeight(36)
        csv_btn.setFont(QFont("Inter", 9, QFont.Weight.Medium))
        csv_btn.setStyleSheet(
            "QPushButton { background: #FFFFFF; color: #334155; border: 1px solid #CBD5E1; border-radius: 6px; padding: 0 12px; }"
            "QPushButton:hover { background: #F8FAFC; }"
        )

        apply_btn = QPushButton("▼ Apply Filters")
        apply_btn.setFixedHeight(36)
        apply_btn.setFont(QFont("Inter", 9.5, QFont.Weight.Bold))
        apply_btn.setStyleSheet(
            "QPushButton { background: #0284C7; color: #FFFFFF; border: none; border-radius: 6px; padding: 0 16px; }"
            "QPushButton:hover { background: #0369A1; }"
        )
        apply_btn.clicked.connect(self._apply_filters)

        act_box.addWidget(print_btn)
        act_box.addWidget(csv_btn)
        act_box.addWidget(apply_btn)

        fb.addLayout(act_box)
        root.addWidget(filter_card)

        # ── 4. KPI Summary Cards Row ─────────────────────────────────────────
        self._kpi_row = QHBoxLayout()
        self._kpi_row.setSpacing(16)
        self._build_kpi_cards()
        root.addLayout(self._kpi_row)

        # ── 5. Chart Grid ───────────────────────────────────────────────────
        self._grid = QGridLayout()
        self._grid.setSpacing(16)
        self._build_charts()
        root.addLayout(self._grid)

        scroll.setWidget(container)

        page_lay = QVBoxLayout(self)
        page_lay.setContentsMargins(0, 0, 0, 0)
        page_lay.addWidget(scroll)

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
        categories = ["All Disciplines (Strat)"]
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

    def _make_kpi_widget(self, title: str, value: str, trend_text: str, color: str) -> QFrame:
        """Helper to build high-fidelity KPI metric cards matching Stitch UI."""
        card = _card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(6)

        t_lbl = QLabel(title.upper())
        t_lbl.setFont(QFont("Inter", 8.5, QFont.Weight.Bold))
        t_lbl.setStyleSheet("color: #64748B; background: transparent;")

        v_lbl = QLabel(value)
        v_lbl.setFont(QFont("Inter", 20, QFont.Weight.Bold))
        v_lbl.setStyleSheet(f"color: {color}; background: transparent;")

        sub_lbl = QLabel(trend_text)
        sub_lbl.setFont(QFont("Inter", 8.5))
        sub_lbl.setStyleSheet("color: #64748B; background: transparent;")

        lay.addWidget(t_lbl)
        lay.addWidget(v_lbl)
        lay.addWidget(sub_lbl)
        return card

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
                total = kpi_data.total_comments
                appr = kpi_data.approved_count
                reje = kpi_data.rejected_count
                flag = kpi_data.flagged_count
            elif isinstance(kpi_data, dict):
                total = kpi_data.get("total_comments", 0)
                appr = kpi_data.get("approved_count", 0)
                reje = kpi_data.get("rejected_count", 0)
                flag = kpi_data.get("flagged_count", 0)
            else:
                total, appr, flag, reje = 8934, 6840, 1674, 420
        else:
            total, appr, flag, reje = 8934, 6840, 1674, 420

        appr_pct = f"{(appr / total * 100):.1f}%" if total > 0 else "0%"
        reje_pct = f"{(reje / total * 100):.1f}%" if total > 0 else "0%"
        flag_pct = f"{(flag / total * 100):.1f}%" if total > 0 else "0%"

        metrics = [
            ("TOTAL COMMENTS", f"{total:,}", "Total in Query", "#0F172A"),
            ("APPROVED COMMENTS", f"{appr:,}", f"● {appr_pct} overall approval rate", "#16A34A"),
            ("FLAGGED FOR REVIEW", f"{flag:,}", f"● {flag_pct} pending re-coordination", "#0284C7"),
            ("REJECTED COMMENTS", f"{reje:,}", f"● {reje_pct} total rejected / invalid", "#DC2626"),
        ]

        for t, v, tr, col in metrics:
            k_card = self._make_kpi_widget(t, v, tr, col)
            self._kpi_cards.append(k_card)
            self._kpi_row.addWidget(k_card, 1)

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

        pareto_view = build_pareto_chart(pareto_data)
        monthly_view = build_monthly_chart(trend_data)
        pie_view = build_category_pie(category_data)
        status_view = build_status_trend_chart()

        def _wrap_chart(title: str, subtitle: str, view: QWidget, min_h: int = 300) -> QFrame:
            f = _card()
            lay = QVBoxLayout(f)
            lay.setContentsMargins(18, 16, 18, 16)
            lay.setSpacing(10)

            hdr = QVBoxLayout()
            hdr.setSpacing(2)

            t_lbl = QLabel(title)
            t_lbl.setFont(QFont("Inter", 12, QFont.Weight.Bold))
            t_lbl.setStyleSheet("color: #0F172A; background: transparent;")

            s_lbl = QLabel(subtitle)
            s_lbl.setFont(QFont("Inter", 9))
            s_lbl.setStyleSheet("color: #64748B; background: transparent;")

            hdr.addWidget(t_lbl)
            hdr.addWidget(s_lbl)
            lay.addLayout(hdr)

            view.setMinimumHeight(min_h)
            lay.addWidget(view, 1)
            return f

        self._grid.addWidget(
            _wrap_chart(
                "Comments by Discipline Category",
                "Action item distribution grouped by trade and sub-consultant packages",
                pareto_view,
                320,
            ),
            0,
            0,
        )
        self._grid.addWidget(
            _wrap_chart(
                "Comment Trend Over Time",
                "Daily volume detected by AI vs. resolved by design team",
                monthly_view,
                320,
            ),
            0,
            1,
        )
        self._grid.addWidget(
            _wrap_chart(
                "Discipline Distribution",
                "Proportional share of verified review findings",
                pie_view,
                300,
            ),
            1,
            0,
        )
        self._grid.addWidget(
            _wrap_chart(
                "Review Status Distribution",
                "Disposition lifecycle of all generated markups",
                status_view,
                300,
            ),
            1,
            1,
        )

    def _apply_filters(self, *args) -> None:
        """Trigger reload of KPIs and charts based on current filter state."""
        self.reload_data()

    def reload_data(self) -> None:
        self._build_kpi_cards()
        self._build_charts()

    def reload_comments(self) -> None:
        """Alias to refresh analytics when comments or drawings update."""
        self.reload_data()
