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
                                QDateEdit, QGridLayout, QSizePolicy)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont

from app.components.kpi_card import KpiCard
from app.components.overlays import EmptyState
from app.components.charts import (
    build_pareto_chart,
    build_monthly_chart,
    build_category_pie,
)
from src.core.dtos.analytics_dtos import KPISummaryDTO
from src.core.metric_definitions import (
    AI_CONFIDENCE_CAVEAT,
    CATEGORY_AGREEMENT_TOOLTIP_HEADER,
    REVIEW_PROGRESS_TOOLTIP,
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

_EMPTY_KPIS = KPISummaryDTO(
    total_projects=0, total_drawings=0, total_comments=0, total_pages=0,
    approved_count=0, rejected_count=0, pending_count=0, flagged_count=0,
    avg_confidence=0.0, high_confidence_pct=0.0, low_confidence_pct=0.0,
)

#: Data value carried by the "current batch" entry in the Batch dropdown.
CURRENT_BATCH = "CURRENT_BATCH"

#: Sentinel labels in the Department dropdown. "Unassigned" is a real filter
#: value — it selects comments with no department — not a synonym for "All".
ALL_DEPARTMENTS = "All Departments"
UNASSIGNED_DEPARTMENT = "Unassigned"

#: Shown instead of the charts when Current Batch is selected but the session has
#: not processed any drawing. The KPIs stay at zero because the underlying query
#: is restricted to an empty drawing list — never widened to "everything".
EMPTY_BATCH_MESSAGE = "No drawings processed this session"
EMPTY_BATCH_SUB = (
    "Current Batch is selected, so nothing is counted. Process a drawing, or "
    "switch the Batch filter to All Uploads / Batches."
)


def batch_option_label(count: int) -> str:
    """Label for the Current Batch dropdown entry, with correct singular/plural."""
    noun = "Drawing" if count == 1 else "Drawings"
    return f"⚡ Current Batch ({count} {noun})"


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
        # ── Filter card container ────────────────────────────────
        filter_card = QFrame()
        filter_card.setObjectName("Card")
        filter_layout = QVBoxLayout(filter_card)
        filter_layout.setContentsMargins(16, 12, 16, 12)
        filter_layout.setSpacing(10)

        # Row 1: Primary Entity Filters (Project, Batch, Drawing, Department, Category)
        fb1 = QHBoxLayout()
        fb1.setSpacing(12)

        self._proj_cb = QComboBox()
        self._proj_cb.hide()

        b_lbl = QLabel("Batch:")
        b_lbl.setObjectName("SubCaption")
        fb1.addWidget(b_lbl)
        self._batch_cb = QComboBox()
        self._batch_cb.setFixedHeight(36)
        self._batch_cb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        fb1.addWidget(self._batch_cb)

        dwg_lbl = QLabel("Drawing:")
        dwg_lbl.setObjectName("SubCaption")
        fb1.addWidget(dwg_lbl)
        self._dwg_cb = QComboBox()
        self._dwg_cb.setFixedHeight(36)
        self._dwg_cb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        fb1.addWidget(self._dwg_cb)

        dept_lbl = QLabel("Department:")
        dept_lbl.setObjectName("SubCaption")
        fb1.addWidget(dept_lbl)
        self._dept_cb = QComboBox()
        self._dept_cb.setFixedHeight(36)
        self._dept_cb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        fb1.addWidget(self._dept_cb)

        c_lbl = QLabel("Category:")
        c_lbl.setObjectName("SubCaption")
        fb1.addWidget(c_lbl)
        self._cat_cb = QComboBox()
        self._cat_cb.setFixedHeight(36)
        self._cat_cb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        fb1.addWidget(self._cat_cb)

        filter_layout.addLayout(fb1)

        # Row 2: Date Filters & Action Buttons
        fb2 = QHBoxLayout()
        fb2.setSpacing(12)

        from_lbl = QLabel("From Date:")
        from_lbl.setObjectName("SubCaption")
        fb2.addWidget(from_lbl)
        self._date_from = QDateEdit(QDate.currentDate().addYears(-1))
        self._date_from.setFixedHeight(36)
        self._date_from.setMinimumWidth(130)
        self._date_from.setCalendarPopup(True)
        self._date_from.dateChanged.connect(self._apply_filters)
        fb2.addWidget(self._date_from)

        to_lbl = QLabel("To Date:")
        to_lbl.setObjectName("SubCaption")
        fb2.addWidget(to_lbl)
        self._date_to = QDateEdit(QDate.currentDate())
        self._date_to.setFixedHeight(36)
        self._date_to.setMinimumWidth(130)
        self._date_to.setCalendarPopup(True)
        self._date_to.dateChanged.connect(self._apply_filters)
        fb2.addWidget(self._date_to)

        fb2.addStretch()

        reset_btn = QPushButton("Reset Filters")
        reset_btn.setObjectName("SecondaryBtn")
        reset_btn.setFixedHeight(36)
        reset_btn.setMinimumWidth(110)
        reset_btn.clicked.connect(self._reset_filters)
        fb2.addWidget(reset_btn)

        apply_btn = QPushButton("Apply Filters")
        apply_btn.setObjectName("PrimaryBtn")
        apply_btn.setFixedHeight(36)
        apply_btn.setMinimumWidth(110)
        apply_btn.clicked.connect(self._apply_filters)
        fb2.addWidget(apply_btn)

        filter_layout.addLayout(fb2)
        root.addWidget(filter_card)

        self._populate_filters()

        # Connect filter widgets to auto-update charts & cascading drawings
        self._proj_cb.currentIndexChanged.connect(self._on_project_changed)
        self._batch_cb.currentIndexChanged.connect(self._on_batch_changed)
        self._dwg_cb.currentIndexChanged.connect(self._apply_filters)
        self._dept_cb.currentIndexChanged.connect(self._on_department_changed)
        self._cat_cb.currentIndexChanged.connect(self._apply_filters)

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
        """Populate project, batch, drawing, department, and category filter dropdowns."""
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

        # Populate batch combobox
        self._refresh_batch_options()

        self._populate_drawings_for_selected_project()

        previous_dept = self._dept_cb.currentText()
        self._dept_cb.blockSignals(True)
        self._dept_cb.clear()
        departments = [ALL_DEPARTMENTS]
        options: Dict[str, Any] = {}
        if self._controller:
            try:
                options = self._controller.get_department_options() or {}
            except Exception:
                options = {}
        for name in options.get("departments", []):
            if name and name not in departments:
                departments.append(name)
        # Offered when it would return rows — and kept while it is the current
        # selection, since dropping it would silently widen the filter to All.
        if options.get("has_unassigned") or previous_dept == UNASSIGNED_DEPARTMENT:
            departments.append(UNASSIGNED_DEPARTMENT)
        self._dept_cb.addItems(departments)

        user_dept = self._controller.current_department_name if self._controller and getattr(self._controller, "current_department_name", None) else None
        if user_dept:
            idx = self._dept_cb.findText(user_dept)
            if idx >= 0:
                self._dept_cb.setCurrentIndex(idx)
            self._dept_cb.setEnabled(False)
        else:
            idx = self._dept_cb.findText(previous_dept)
            if idx >= 0:
                self._dept_cb.setCurrentIndex(idx)
            self._dept_cb.setEnabled(True)
        self._dept_cb.blockSignals(False)

        self._cat_cb.blockSignals(True)
        self._cat_cb.clear()
        categories = ["All Categories"]
        cat_options = []
        if self._controller:
            try:
                cat_options = self._controller.get_category_options()
            except Exception:
                cat_options = []
        if not cat_options:
            cat_options = STANDARD_CATEGORIES
        for c_name in cat_options:
            if c_name not in categories:
                categories.append(c_name)
        self._cat_cb.addItems(categories)
        self._cat_cb.blockSignals(False)

    def _refresh_batch_options(self) -> None:
        """
        Rebuild the Batch dropdown without losing the user's selection.

        The Current Batch entry always exists while a controller is attached, even
        when the session has processed nothing, so the selection can never be
        silently replaced by "All Uploads / Batches" — which would quietly widen
        the population from zero drawings to every drawing in the database.
        """
        previous = self._batch_cb.currentData()
        self._batch_cb.blockSignals(True)
        self._batch_cb.clear()
        self._batch_cb.addItem("All Uploads / Batches", "")
        if self._controller:
            count = len(getattr(self._controller, "current_batch_drawing_ids", None) or [])
            self._batch_cb.addItem(batch_option_label(count), CURRENT_BATCH)
            idx = self._batch_cb.findData(previous)
            if idx >= 0:
                self._batch_cb.setCurrentIndex(idx)
        self._batch_cb.blockSignals(False)

    def _populate_drawings_for_selected_project(self) -> None:
        """
        Rebuild the drawing dropdown for the current project / batch / department
        scope.

        The list comes from one query that returns id, name and comment count —
        it never loads comment rows — and it filters on the department recorded
        on the comment, the same semantic the KPIs and charts use.
        """
        proj_id = self._proj_cb.currentData() if hasattr(self, "_proj_cb") else ""
        batch_selection = self._batch_cb.currentData() if hasattr(self, "_batch_cb") else ""
        dept_text = self._dept_cb.currentText() if hasattr(self, "_dept_cb") else ALL_DEPARTMENTS
        user_dept = self._controller.current_department_name if self._controller and getattr(self._controller, "current_department_name", None) else None
        active_dept = user_dept or (None if dept_text in (ALL_DEPARTMENTS, "") else dept_text)

        prev_dwg_id = self._dwg_cb.currentData() if hasattr(self, "_dwg_cb") else None

        if batch_selection == CURRENT_BATCH:
            all_label = "All Drawings in Batch"
            scope_ids = getattr(self._controller, "current_batch_drawing_ids", None) or []
        else:
            all_label = "All Drawings"
            scope_ids = None

        self._dwg_cb.blockSignals(True)
        self._dwg_cb.clear()
        self._dwg_cb.addItem(all_label, "")

        drawings: List[Dict[str, Any]] = []
        if self._controller:
            try:
                drawings = self._controller.get_drawing_options(
                    project_id=proj_id if proj_id else None,
                    department_name=active_dept,
                    drawing_ids=scope_ids,
                ) or []
            except Exception:
                drawings = []
        for d in drawings:
            self._dwg_cb.addItem(d.get("file_name") or "Drawing", d.get("id", ""))

        # Restore previous selection if still in list
        idx = self._dwg_cb.findData(prev_dwg_id) if prev_dwg_id else -1
        self._dwg_cb.setCurrentIndex(idx if idx >= 0 else 0)
        self._dwg_cb.blockSignals(False)

    def _on_department_changed(self, index: int) -> None:
        """Cascade department filter to available drawings and refresh."""
        self._populate_drawings_for_selected_project()
        self._apply_filters()

    def _on_project_changed(self, index: int) -> None:
        """Update drawing combobox options when selected project changes and reload data."""
        self._populate_drawings_for_selected_project()
        self._apply_filters()

    def _on_batch_changed(self, index: int) -> None:
        """Update drawing combobox options when batch filter changes and reload data."""
        self._populate_drawings_for_selected_project()
        self._apply_filters()

    def _reset_filters(self) -> None:
        """Reset all filter controls to their default initial state and refresh views."""
        self._proj_cb.blockSignals(True)
        self._proj_cb.setCurrentIndex(0)
        self._proj_cb.blockSignals(False)

        self._batch_cb.blockSignals(True)
        self._batch_cb.setCurrentIndex(0)
        self._batch_cb.blockSignals(False)

        self._populate_drawings_for_selected_project()

        self._dwg_cb.blockSignals(True)
        self._dwg_cb.setCurrentIndex(0)
        self._dwg_cb.blockSignals(False)

        self._cat_cb.blockSignals(True)
        self._cat_cb.setCurrentIndex(0)
        self._cat_cb.blockSignals(False)

        user_dept = self._controller.current_department_name if self._controller and getattr(self._controller, "current_department_name", None) else None
        self._dept_cb.blockSignals(True)
        if user_dept:
            idx = self._dept_cb.findText(user_dept)
            if idx >= 0:
                self._dept_cb.setCurrentIndex(idx)
        else:
            self._dept_cb.setCurrentIndex(0)
        self._dept_cb.blockSignals(False)

        self._date_from.blockSignals(True)
        self._date_from.setDate(QDate.currentDate().addYears(-1))
        self._date_from.blockSignals(False)

        self._date_to.blockSignals(True)
        self._date_to.setDate(QDate.currentDate())
        self._date_to.blockSignals(False)

        self.reload_data()

    def _get_active_filters(self) -> dict:
        """Read current filter state from all widgets."""
        proj_id = self._proj_cb.currentData() if hasattr(self, "_proj_cb") else ""
        batch_selection = self._batch_cb.currentData() if hasattr(self, "_batch_cb") else ""
        dwg_id  = self._dwg_cb.currentData() if hasattr(self, "_dwg_cb") else ""
        user_dept = self._controller.current_department_name if self._controller and getattr(self._controller, "current_department_name", None) else None
        dept_text = self._dept_cb.currentText() if hasattr(self, "_dept_cb") else ALL_DEPARTMENTS
        dept    = user_dept or dept_text
        cat     = self._cat_cb.currentText() if hasattr(self, "_cat_cb") else "All Categories"

        # Read date limits from QDateEdit
        qfrom = self._date_from.date() if hasattr(self, "_date_from") else None
        qto   = self._date_to.date() if hasattr(self, "_date_to") else None

        from_dt = datetime(qfrom.year(), qfrom.month(), qfrom.day()) if qfrom and qfrom.isValid() else None
        to_dt   = datetime(qto.year(), qto.month(), qto.day(), 23, 59, 59) if qto and qto.isValid() else None

        # Determine batch drawing IDs if Current Batch is selected. An empty
        # batch stays an empty list — the service turns that into a zero-row
        # filter rather than dropping the restriction entirely.
        batch_drawing_ids = None
        is_current_batch = False
        if batch_selection == CURRENT_BATCH and self._controller:
            batch_drawing_ids = getattr(self._controller, "current_batch_drawing_ids", None) or []
            is_current_batch = True

        return {
            "project_id": proj_id if proj_id else None,
            "drawing_id": dwg_id if dwg_id else None,
            "drawing_ids": (batch_drawing_ids if not dwg_id else None) if is_current_batch else None,
            "is_current_batch": is_current_batch,
            "department_name": None if dept in (ALL_DEPARTMENTS, "") else dept,
            "category_name": None if cat in ("All Categories", "") else cat,
            "date_from": from_dt,
            "date_to": to_dt,
        }

    def _build_kpi_cards(self) -> None:
        """Build the KPI cards from the filtered population.

        Three separate concepts are reported and never merged or called
        "accuracy": review progress, AI confidence, and category agreement.
        """
        while self._kpi_row.count():
            item = self._kpi_row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._kpi_cards.clear()

        filters = self._get_active_filters()
        kpi = self._controller.get_dashboard_kpis(
            project_id=filters["project_id"],
            drawing_id=filters["drawing_id"],
            drawing_ids=filters.get("drawing_ids"),
            department_name=filters["department_name"],
            category_name=filters["category_name"],
            date_from=filters["date_from"],
            date_to=filters["date_to"],
        ) if self._controller else None
        if kpi is None:
            kpi = _EMPTY_KPIS

        total = kpi.total_comments
        pct = lambda n: f"{(n / total * 100):.1f}%" if total > 0 else "0.0%"

        reviewed = kpi.reviewed_count or 0
        pending = kpi.pending_count
        approved = kpi.approved_count
        rejected = kpi.rejected_count
        flagged = kpi.flagged_count
        auto_approved = kpi.auto_approved_count or 0
        human_approved = max(0, approved - auto_approved)
        human_reviewed = kpi.human_reviewed_count or 0
        flagged_manual = kpi.flagged_manual_count or 0
        flagged_ocr = kpi.flagged_ocr_failed_count or 0
        high_t = kpi.high_confidence_threshold
        low_t = kpi.low_confidence_threshold
        ai_conf = kpi.ai_confidence_avg
        ai_n = kpi.ai_confidence_sample_size or 0
        agreement = kpi.category_agreement_pct
        agreement_n = kpi.category_agreement_sample_size or 0
        population = "including rejected" if kpi.include_rejected else "excluding rejected"

        review_progress_str = f"{(kpi.review_progress or 0.0):.1f}%" if total > 0 else "—"
        ai_conf_str = f"{ai_conf * 100.0:.1f}%" if ai_conf is not None and ai_n > 0 else "—"
        agreement_str = f"{agreement:.1f}%" if agreement is not None else "—"

        high_band = f"≥{high_t * 100:.0f}%" if high_t is not None else "high"
        low_band = f"<{low_t * 100:.0f}%" if low_t is not None else "low"

        kpi_items = [
            ("fa5s.comments",      f"{total:,}",            "Total Comments",    f"in filter · {population}", "#3E9BFF"),
            ("fa5s.tasks",         review_progress_str,     "Review Progress",   f"{reviewed:,} of {total:,} decided", "#60A5FA"),
            ("fa5s.check-circle",  f"{approved:,}",         "Approved",          pct(approved),               "#4ADE80"),
            ("fa5s.times-circle",  f"{rejected:,}",         "Rejected",          pct(rejected),               "#F87171"),
            ("fa5s.flag",          f"{flagged:,}",          "Flagged",           pct(flagged),                "#FBBF24"),
            ("fa5s.robot",         ai_conf_str,             "AI Confidence",     f"n={ai_n:,} model-scored",   "#A78BFA"),
            ("fa5s.balance-scale", agreement_str,           "Category Agreement", f"n={agreement_n:,} reviewed", "#2DD4BF"),
        ]

        tooltips = [
            (
                f"Total Comments: {total:,}\n"
                f"Population: {population}\n"
                f"Pending: {pending:,} · Approved: {approved:,} · Rejected: {rejected:,} · Flagged: {flagged:,}\n"
                f"Same population as the KPI cards, status donut and trend chart."
            ),
            (
                f"Review Progress: {review_progress_str}\n"
                f"{REVIEW_PROGRESS_TOOLTIP}\n"
                f"= (Approved + Rejected) / Total = {reviewed:,} / {total:,}\n"
                f"Pending: {pending:,} ({pct(pending)})\n"
                f"Human-reviewed (a person confirmed the decision): {human_reviewed:,}"
            ),
            (
                f"Approved: {approved:,} ({pct(approved)})\n"
                f"Auto-approved (no human): {auto_approved:,} ({(kpi.auto_approval_rate or 0.0):.1f}%)\n"
                f"Human-approved: {human_approved:,}\n"
                f"Approval rate: {(kpi.approval_rate or 0.0):.1f}%"
            ),
            f"Rejected: {rejected:,} ({pct(rejected)})\nMarked invalid or not applicable.",
            (
                f"Flagged: {flagged:,} ({pct(flagged)})\n"
                f"Manual flag by a reviewer: {flagged_manual:,}\n"
                f"OCR extraction failed: {flagged_ocr:,}\n"
                f"Flagged comments are excluded from Review Progress."
            ),
            (
                f"Average AI confidence: {ai_conf_str} over {ai_n:,} model-scored comments.\n"
                f"High band {high_band}: {(kpi.high_confidence_pct or 0.0):.1f}% of the population\n"
                f"Low band {low_band}: {(kpi.low_confidence_pct or 0.0):.1f}% of the population\n"
                f"Bands come from ai.auto_approve_threshold / ai.low_confidence_threshold in config.\n\n"
                f"{AI_CONFIDENCE_CAVEAT}"
            ),
            (
                f"{CATEGORY_AGREEMENT_TOOLTIP_HEADER}\n"
                f"Agreement in this filter: {agreement_str} over {agreement_n:,} rows.\n"
                f"Not comparable to the AI confidence score above — different population."
                if agreement is not None else
                "Category agreement: no human-reviewed rows with a recorded initial category\n"
                "in this population yet."
            ),
        ]

        for i, (icon, val, lbl, trend, color) in enumerate(kpi_items):
            card = KpiCard(icon, val, lbl, trend, color)
            card.setMinimumHeight(120)
            card.setMinimumWidth(132)
            card.setToolTip(tooltips[i])
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
        dwg_ids   = filters.get("drawing_ids")
        is_cur_b  = filters.get("is_current_batch", False)
        dept_name = filters["department_name"]
        cat_name  = filters["category_name"]
        d_from    = filters["date_from"]
        d_to      = filters["date_to"]

        # Current Batch selected with nothing in it: say so instead of drawing
        # three blank charts that read like a failed query.
        if is_cur_b and not dwg_ids and not dwg_id:
            empty = EmptyState(icon="fa5s.inbox",
                               message=EMPTY_BATCH_MESSAGE,
                               sub=EMPTY_BATCH_SUB)
            empty.setMinimumHeight(320)
            self._grid.addWidget(empty, 0, 0, 2, 2)
            return

        pareto_data = self._controller.get_pareto_analysis(
            project_id=proj_id,
            drawing_id=dwg_id,
            drawing_ids=dwg_ids,
            department_name=dept_name,
            category_name=cat_name,
            date_from=d_from,
            date_to=d_to,
            include_rejected=True,
        ) if self._controller else None

        category_data = self._controller.get_category_distribution(
            project_id=proj_id,
            drawing_id=dwg_id,
            drawing_ids=dwg_ids,
            department_name=dept_name,
            category_name=cat_name,
            date_from=d_from,
            date_to=d_to,
            include_rejected=True,
        ) if self._controller else None

        trend_data = self._controller.get_status_trend(
            project_id=proj_id,
            drawing_id=dwg_id,
            drawing_ids=dwg_ids,
            department_name=dept_name,
            category_name=cat_name,
            date_from=d_from,
            date_to=d_to,
        ) if self._controller else None

        if cat_name:
            pareto_title = f"Pareto — Category: {cat_name}"
            pie_title = f"Category Distribution ({cat_name})"
        else:
            pareto_title = "Pareto — Comments by Category"
            pie_title = "Category Distribution"

        pareto_view  = build_pareto_chart(
            pareto_data,
            title=pareto_title,
            # The Pareto may be a top-N slice; the cumulative line must still be
            # measured against the whole population the slice came from.
            total=sum(getattr(d, "count", 0) for d in (category_data or [])) or None,
        )
        timeline_view = build_monthly_chart(trend_data, title="Comment Timeline (by Creation Date)")
        pie_view     = build_category_pie(category_data, title=pie_title)

        def _wrap(view, min_h: int = 280) -> QFrame:
            f = QFrame()
            f.setObjectName("Card")
            lay = QVBoxLayout(f)
            lay.setContentsMargins(8, 8, 8, 8)
            view.setMinimumHeight(min_h)
            lay.addWidget(view)
            return f

        self._grid.addWidget(_wrap(pareto_view,   320), 0, 0, 2, 1)
        self._grid.addWidget(_wrap(timeline_view, 220), 0, 1)
        self._grid.addWidget(_wrap(pie_view,      220), 1, 1)

    def _apply_filters(self, *args) -> None:
        """Trigger reload of KPIs and charts based on current filter state."""
        self.reload_data()

    def reload_data(self) -> None:
        """Reload live KPI metrics, charts, and filter options from the controller."""
        # Refresh batch dropdown in case a new batch was processed, keeping the
        # user's selection even when the batch is empty.
        self._refresh_batch_options()

        # Refresh drawings dropdown so newly processed drawings are never stale
        self._populate_drawings_for_selected_project()

        self._build_kpi_cards()
        self._build_charts()

    def reload_comments(self) -> None:
        """Alias to refresh analytics when comments or drawings update."""
        self.reload_data()


