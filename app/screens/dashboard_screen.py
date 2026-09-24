"""
dashboard_screen.py — Redesigned Dashboard screen matching enterprise Stitch UI.

Provides:
    DashboardPage(QWidget)
        Overview dashboard with live KPI cards, interactive analytics charts,
        Projects & Drawings tables, real-time activity feed, and processing engine status.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QTableView,
    QHeaderView,
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QButtonGroup,
    QGraphicsDropShadowEffect,
)
from PySide6.QtGui import QFont, QStandardItemModel, QStandardItem, QColor
from PySide6.QtCore import Qt, QTimer, Signal, QSize

try:
    import qtawesome as qta
    _HAS_QTA = True
except ImportError:
    _HAS_QTA = False

from app.components.kpi_card import KpiCard
from app.components.chips import StatusChip
from app.components.charts import (
    build_pareto_chart,
    build_category_pie,
    build_monthly_chart,
)

DEFAULT_ACTIVITIES = [
    {
        "time": "10 mins ago",
        "text": "Completed OCR extraction on DWG-8802 (42 comments identified)",
        "tag": "OCR Pipeline",
        "color": "#0284C7",
    },
    {
        "time": "45 mins ago",
        "text": "Human Reviewer Elena Vance approved 14 comments on Sheet A-104",
        "tag": "Review",
        "color": "#16A34A",
    },
    {
        "time": "2 hours ago",
        "text": "Batch zip package 'Terminal_Expansion_Phase1.zip' uploaded (5 drawings)",
        "tag": "Batch Upload",
        "color": "#9333EA",
    },
    {
        "time": "3 hours ago",
        "text": "System generated Error Tracker Multi-Tier Excel export for Hudson Yards Phase 2",
        "tag": "Export",
        "color": "#D97706",
    },
]


def _card(parent=None) -> QFrame:
    """Creates a light rounded card with soft drop shadow matching Stitch theme."""
    f = QFrame(parent)
    f.setObjectName("StitchCard")
    f.setStyleSheet(
        """
        QFrame#StitchCard {
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
        }
        """
    )
    shadow = QGraphicsDropShadowEffect(f)
    shadow.setBlurRadius(12)
    shadow.setColor(QColor(15, 23, 42, 10))
    shadow.setOffset(0, 3)
    f.setGraphicsEffect(shadow)
    return f


def _h2(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Inter", 13, QFont.Weight.Bold))
    lbl.setStyleSheet("color: #0F172A;")
    return lbl


def _format_relative_time(raw_dt: Any) -> str:
    if not raw_dt:
        return "recently"
    if isinstance(raw_dt, str):
        try:
            dt = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
        except Exception:
            return raw_dt
    elif isinstance(raw_dt, datetime):
        dt = raw_dt
    else:
        return "recently"

    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    diff = (now - dt).total_seconds()
    if diff < 60:
        return "just now"
    elif diff < 3600:
        mins = int(diff / 60)
        return f"{mins} min{'s' if mins > 1 else ''} ago"
    elif diff < 86400:
        hours = int(diff / 3600)
        return f"{hours} hr{'s' if hours > 1 else ''} ago"
    else:
        days = int(diff / 86400)
        return f"{days} day{'s' if days > 1 else ''} ago"


class DashboardPage(QWidget):
    """
    Home Dashboard — Live KPI cards, Recent Projects & Drawings table,
    dynamic Activity Feed, and Real-Time Processing Status connected to AppController.
    """

    open_project = Signal(str)
    open_drawing = Signal(dict)

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._kpi_cards: List[KpiCard] = []
        self._view_mode = "drawings"
        self._job_rows: Dict[str, tuple[QProgressBar, StatusChip, QLabel]] = {}

        self.setObjectName("DashboardRoot")
        self.setStyleSheet(
            """
            QWidget#DashboardRoot {
                background-color: #F8FAFC;
            }
            """
        )

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; }")

        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        root = QVBoxLayout(container)
        root.setContentsMargins(32, 24, 32, 36)
        root.setSpacing(22)

        # ── Dashboard Title ───────────────────────────────────────
        hdr_box = QVBoxLayout()
        hdr_box.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)

        title = QLabel("Engineering Drawing Review Dashboard")
        title.setFont(QFont("Inter", 20, QFont.Weight.Bold))
        title.setStyleSheet("color: #0F172A;")
        title_row.addWidget(title)

        sync_badge = QLabel("● Live Sync")
        sync_badge.setFont(QFont("Inter", 8, QFont.Weight.Bold))
        sync_badge.setStyleSheet(
            "color: #059669; background-color: #ECFDF5; "
            "border: 1px solid #A7F3D0; border-radius: 12px; "
            "padding: 2px 10px;"
        )
        title_row.addWidget(sync_badge)
        title_row.addStretch()

        self._last_refresh_lbl = QLabel("Updated just now")
        self._last_refresh_lbl.setStyleSheet("color: #64748B; font-size: 11px;")
        title_row.addWidget(self._last_refresh_lbl)

        self._refresh_btn = QPushButton(" Refresh")
        self._refresh_btn.setFixedHeight(30)
        self._refresh_btn.setStyleSheet(
            "QPushButton { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; color: #334155; font-size: 11px; font-weight: 600; padding: 0 12px; }"
            "QPushButton:hover { background: #F8FAFC; border-color: #94A3B8; }"
        )
        if _HAS_QTA:
            try:
                self._refresh_btn.setIcon(qta.icon("fa5s.sync-alt", color="#475569"))
            except Exception:
                pass
        self._refresh_btn.clicked.connect(self.reload_data)
        title_row.addWidget(self._refresh_btn)

        hdr_box.addLayout(title_row)

        subtitle = QLabel("AI-driven drawing review comment analysis, OCR extraction status, and verification metrics.")
        subtitle.setFont(QFont("Inter", 9.5))
        subtitle.setStyleSheet("color: #64748B;")
        hdr_box.addWidget(subtitle)

        root.addLayout(hdr_box)

        # ── KPI Cards Row ─────────────────────────────────────────
        self._kpi_row = QHBoxLayout()
        self._kpi_row.setSpacing(16)
        self._build_kpi_cards()
        root.addLayout(self._kpi_row)

        # ── Analytics Charts Section ──────────────────────────────
        charts_row = QHBoxLayout()
        charts_row.setSpacing(16)

        c1 = _card()
        c1_lay = QVBoxLayout(c1)
        c1_lay.setContentsMargins(18, 18, 18, 18)
        c1_lay.setSpacing(12)
        c1_lay.addWidget(_h2("Comments by Category"))
        cat_data = self._controller.get_category_distribution() if self._controller else None
        c1_lay.addWidget(build_pareto_chart(cat_data), 1)
        charts_row.addWidget(c1, 4)

        c2 = _card()
        c2_lay = QVBoxLayout(c2)
        c2_lay.setContentsMargins(18, 18, 18, 18)
        c2_lay.setSpacing(12)
        c2_lay.addWidget(_h2("Category Distribution"))
        c2_lay.addWidget(build_category_pie(cat_data), 1)
        charts_row.addWidget(c2, 3)

        c3 = _card()
        c3_lay = QVBoxLayout(c3)
        c3_lay.setContentsMargins(18, 18, 18, 18)
        c3_lay.setSpacing(12)
        c3_lay.addWidget(_h2("Comment Trend Over Time"))
        c3_lay.addWidget(build_monthly_chart(), 1)
        charts_row.addWidget(c3, 3)

        root.addLayout(charts_row)

        # ── Tables & Feed Split ───────────────────────────────────
        split = QHBoxLayout()
        split.setSpacing(16)

        table_card = _card()
        table_card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        table_lay = QVBoxLayout(table_card)
        table_lay.setContentsMargins(18, 16, 18, 16)
        table_lay.setSpacing(12)

        table_hdr = QHBoxLayout()
        self._table_title = _h2("Recent Drawings")
        table_hdr.addWidget(self._table_title)
        table_hdr.addStretch()

        self._btn_group = QButtonGroup(self)
        self._drawings_btn = QPushButton("Recent Drawings")
        self._drawings_btn.setCheckable(True)
        self._drawings_btn.setChecked(True)
        self._drawings_btn.setFixedHeight(28)
        self._drawings_btn.setStyleSheet(self._get_toggle_btn_style(True))

        self._projects_btn = QPushButton("Projects")
        self._projects_btn.setCheckable(True)
        self._projects_btn.setFixedHeight(28)
        self._projects_btn.setStyleSheet(self._get_toggle_btn_style(False))

        self._btn_group.addButton(self._drawings_btn, 0)
        self._btn_group.addButton(self._projects_btn, 1)
        self._drawings_btn.clicked.connect(lambda: self._set_view_mode("drawings"))
        self._projects_btn.clicked.connect(lambda: self._set_view_mode("projects"))

        table_hdr.addWidget(self._drawings_btn)
        table_hdr.addWidget(self._projects_btn)
        table_lay.addLayout(table_hdr)

        self._data_table = QTableView()
        self._data_table.setAlternatingRowColors(True)
        self._data_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._data_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._data_table.horizontalHeader().setStretchLastSection(True)
        self._data_table.verticalHeader().hide()
        self._data_table.setShowGrid(False)
        self._data_table.doubleClicked.connect(self._on_table_double_clicked)
        self._data_table.setStyleSheet(
            """
            QTableView {
                background-color: #FFFFFF;
                border: none;
                gridline-color: #F1F5F9;
                selection-background-color: #F0F9FF;
                selection-color: #0F172A;
                font-family: 'Inter';
                font-size: 11px;
            }
            QTableView::item {
                padding: 8px 10px;
                border-bottom: 1px solid #F1F5F9;
            }
            QHeaderView::section {
                background-color: #F8FAFC;
                color: #64748B;
                padding: 8px 10px;
                font-weight: 700;
                font-size: 10px;
                border: none;
                border-bottom: 2px solid #E2E8F0;
            }
            """
        )

        table_lay.addWidget(self._data_table)
        split.addWidget(table_card, 6)

        right_col = QVBoxLayout()
        right_col.setSpacing(16)

        act_card = _card()
        act_lay = QVBoxLayout(act_card)
        act_lay.setContentsMargins(18, 16, 18, 16)
        act_lay.setSpacing(10)

        act_hdr = QHBoxLayout()
        act_hdr.addWidget(_h2("Recent Activity"))
        act_hdr.addStretch()
        live_dot = QLabel("● Live")
        live_dot.setStyleSheet("color: #059669; font-size: 11px; font-weight: bold;")
        act_hdr.addWidget(live_dot)
        act_lay.addLayout(act_hdr)

        self._act_list = QListWidget()
        self._act_list.setSpacing(4)
        self._act_list.setStyleSheet(
            "QListWidget { background: transparent; border: none; outline: none; }"
            "QListWidget::item { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 10px; margin-bottom: 2px; color: #0F172A; }"
            "QListWidget::item:hover { background: #F1F5F9; border-color: #CBD5E1; }"
        )
        act_lay.addWidget(self._act_list, 1)
        right_col.addWidget(act_card, 1)

        proc_card = _card()
        proc_lay = QVBoxLayout(proc_card)
        proc_lay.setContentsMargins(18, 16, 18, 16)
        proc_lay.setSpacing(12)

        proc_hdr = QHBoxLayout()
        proc_hdr.addWidget(_h2("Processing Engines"))
        proc_hdr.addStretch()
        self._status_summary_lbl = QLabel("All Systems Ready")
        self._status_summary_lbl.setStyleSheet("color: #059669; font-size: 12px; font-weight: 600;")
        proc_hdr.addWidget(self._status_summary_lbl)
        proc_lay.addLayout(proc_hdr)

        self._init_pipeline_jobs(proc_lay)
        right_col.addWidget(proc_card)

        split.addLayout(right_col, 4)
        root.addLayout(split)

        scroll.setWidget(container)

        page_lay = QVBoxLayout(self)
        page_lay.setContentsMargins(0, 0, 0, 0)
        page_lay.addWidget(scroll)

        self.reload_data()

        if self._controller:
            self._controller.workflow_step_signal.connect(self._on_workflow_step)
            self._controller.workflow_completed_signal.connect(self._on_workflow_completed)
            self._controller.document_loaded_signal.connect(lambda _: self.reload_data())

        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(8000)
        self._auto_timer.timeout.connect(self.reload_data)
        self._auto_timer.start()

    def showEvent(self, event):
        """Auto-refresh dashboard data whenever this screen becomes visible."""
        super().showEvent(event)
        self.reload_data()

    def _get_toggle_btn_style(self, is_active: bool) -> str:
        if is_active:
            return (
                "QPushButton { background-color: #0284C7; color: #FFFFFF; font-weight: bold; "
                "border-radius: 4px; padding: 4px 12px; font-size: 12px; border: none; }"
            )
        return (
            "QPushButton { background-color: #FFFFFF; color: #475569; "
            "border-radius: 4px; padding: 4px 12px; font-size: 12px; border: 1px solid #CBD5E1; }"
            "QPushButton:hover { background-color: #F1F5F9; color: #0F172A; }"
        )

    def _set_view_mode(self, mode: str):
        self._view_mode = mode
        self._drawings_btn.setChecked(mode == "drawings")
        self._projects_btn.setChecked(mode == "projects")
        self._drawings_btn.setStyleSheet(self._get_toggle_btn_style(mode == "drawings"))
        self._projects_btn.setStyleSheet(self._get_toggle_btn_style(mode == "projects"))
        self._table_title.setText("Recent Drawings" if mode == "drawings" else "Projects Overview")
        self._populate_active_table()

    # ── KPI Calculations ──────────────────────────────────────────

    def _get_kpi_values(self) -> tuple[int, int, int, str, str]:
        """Query KPI aggregates from controller analytics service."""
        kpi_data = self._controller.get_dashboard_kpis() if self._controller else None
        if kpi_data is not None:
            total_projects = getattr(kpi_data, "total_projects", 0)
            total_drawings = getattr(kpi_data, "total_drawings", 0)
            total_comments = getattr(kpi_data, "total_comments", 0)
            avg_conf = getattr(kpi_data, "avg_confidence", 0.0) or 0.0
            acc_val = getattr(kpi_data, "accuracy_rate", None)

            if acc_val is not None and acc_val > 0.0:
                accuracy_str = f"{acc_val:.1f}%"
                trend_label = "Verified"
            elif avg_conf > 0.0:
                accuracy_str = f"{(avg_conf * 100.0 if avg_conf <= 1.0 else avg_conf):.1f}%"
                trend_label = "OCR Conf"
            else:
                accuracy_str = "—"
                trend_label = "Ready"
        else:
            total_projects, total_drawings, total_comments = 0, 0, 0
            accuracy_str, trend_label = "—", "Ready"

        return total_projects, total_drawings, total_comments, accuracy_str, trend_label

    def _build_kpi_cards(self) -> None:
        """Build or refresh KPI cards with accurate live database metrics."""
        while self._kpi_row.count():
            item = self._kpi_row.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._kpi_cards.clear()

        total_projects, total_drawings, total_comments, accuracy_str, accuracy_trend = self._get_kpi_values()

        kpis = [
            ("fa5s.folder-open",  str(total_projects), "Total Projects",     "Active",      "#0284C7"),
            ("fa5s.file-pdf",     str(total_drawings), "Drawings Processed", "In Database", "#2563EB"),
            ("fa5s.comments",     str(total_comments), "Comments Detected",  "Live Extracted", "#D97706"),
            ("fa5s.check-circle", accuracy_str,        "OCR Accuracy",       accuracy_trend, "#16A34A"),
        ]
        for icon, val, lbl, trend, color in kpis:
            card = KpiCard(icon, val, lbl, trend, color)
            card.setMinimumHeight(125)
            self._kpi_cards.append(card)
            self._kpi_row.addWidget(card, 1)

    # ── Table Population ──────────────────────────────────────────

    def _populate_active_table(self) -> None:
        if self._view_mode == "projects":
            self._populate_projects_table()
        else:
            self._populate_drawings_table()

    def _populate_projects_table(self) -> None:
        """Populate the projects table with accurate drawing and comment counts."""
        model = QStandardItemModel(0, 6)
        model.setHorizontalHeaderLabels(
            ["Project", "Drawings", "Comments", "Progress", "Status", "Lead Engineer"]
        )

        projects_list = self._controller.get_all_projects() if self._controller else []
        if not projects_list:
            from app.mock_data import PROJECTS
            projects_list = [
                {
                    "name": p.name,
                    "drawings": p.drawings,
                    "comments": p.comments,
                    "progress": p.progress,
                    "status": p.status,
                    "lead_engineer": p.engineer,
                }
                for p in PROJECTS
            ]

        for p in projects_list:
            if isinstance(p, dict):
                p_name = p.get("name", p.get("id", "—"))
                p_drawings = str(p.get("drawings", p.get("total_drawings", "0")))
                p_comments = str(p.get("comments", p.get("total_comments", "0")))
                p_progress = f"{p.get('progress', 0)}%"
                p_status = p.get("status", "Active")
                p_engineer = p.get("lead_engineer", p.get("engineer", "—")) or "—"
            else:
                p_name = getattr(p, "name", "—")
                p_drawings = str(getattr(p, "drawings", "0"))
                p_comments = str(getattr(p, "comments", "0"))
                p_progress = f"{getattr(p, 'progress', 0)}%"
                p_status = getattr(p, "status", "Active")
                p_engineer = getattr(p, "engineer", "—")

            row_items = [
                QStandardItem(p_name),
                QStandardItem(p_drawings),
                QStandardItem(p_comments),
                QStandardItem(p_progress),
                QStandardItem(p_status),
                QStandardItem(p_engineer),
            ]
            row_items[0].setFont(QFont("Inter", 11, QFont.Weight.Bold))
            for item in row_items:
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            model.appendRow(row_items)

        self._data_table.setModel(model)
        hdr = self._data_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 6):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

    def _populate_drawings_table(self) -> None:
        """Populate the drawings table with recently processed drawing records."""
        model = QStandardItemModel(0, 7)
        model.setHorizontalHeaderLabels(
            ["Drawing File", "Department", "Pages", "Comments", "Avg Conf.", "Uploaded", "Status"]
        )

        drawings_list = self._controller.get_recent_drawings(limit=25) if self._controller else []

        for d in drawings_list:
            fname = d.get("file_name", "—")
            dept = d.get("department_name", "Unassigned")
            pages = str(d.get("total_pages", 1))
            cmts = str(d.get("comments_count", 0))
            avg_c = d.get("avg_confidence", 0.0)
            conf_str = f"{(avg_c * 100 if avg_c <= 1.0 else avg_c):.1f}%" if avg_c > 0 else "—"
            uploaded = _format_relative_time(d.get("uploaded_at", ""))
            status = d.get("status", "Ready")

            row = [
                QStandardItem(fname),
                QStandardItem(dept),
                QStandardItem(pages),
                QStandardItem(cmts),
                QStandardItem(conf_str),
                QStandardItem(uploaded),
                QStandardItem(status),
            ]
            row[0].setFont(QFont("Cascadia Code", 10, QFont.Weight.Bold))
            row[0].setForeground(QColor("#0284C7"))
            row[0].setData(d, Qt.ItemDataRole.UserRole)
            for item in row:
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            model.appendRow(row)

        self._data_table.setModel(model)
        hdr = self._data_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 7):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

    def _on_table_double_clicked(self, index):
        """Handle double-clicking a drawing or project row."""
        if self._view_mode == "drawings":
            model = self._data_table.model()
            if model:
                dwg_data = model.data(model.index(index.row(), 0), Qt.ItemDataRole.UserRole)
                if dwg_data and isinstance(dwg_data, dict):
                    self.open_drawing.emit(dwg_data)
        elif self._view_mode == "projects":
            model = self._data_table.model()
            if model:
                proj_name = model.data(model.index(index.row(), 0))
                if proj_name:
                    self.open_project.emit(proj_name)

    # ── Activity Feed ─────────────────────────────────────────────

    def _populate_activity_feed(self) -> None:
        """Populate live activity feed from controller."""
        self._act_list.clear()
        activities = self._controller.get_recent_activity(limit=10) if self._controller else []

        if not activities:
            for act in DEFAULT_ACTIVITIES:
                item = QListWidgetItem(f"  {act['text']}   •   {act['time']}")
                item.setSizeHint(QSize(0, 36))
                self._act_list.addItem(item)
            return

        for act in activities:
            text = act.get("text", "")
            time_rel = _format_relative_time(act.get("time", ""))
            icon_name = act.get("icon", "fa5s.history")
            color_hex = act.get("color", "#0284C7")

            display_str = f"  {text}   •   {time_rel}"
            item = QListWidgetItem(display_str)
            if _HAS_QTA:
                try:
                    item.setIcon(qta.icon(icon_name, color=color_hex))
                except Exception:
                    pass
            item.setSizeHint(QSize(0, 38))
            self._act_list.addItem(item)

    # ── Pipeline & Engine Status ──────────────────────────────────

    def _init_pipeline_jobs(self, layout: QVBoxLayout) -> None:
        """Create real-time pipeline status rows."""
        jobs = [
            ("ocr_pipeline",    "OCR Processing Pipeline"),
            ("cloud_detector",  "Color & Cloud Detection"),
            ("ai_classifier",   "AI Comment Classifier"),
            ("drawing_hub",     "Drawing Intelligence Hub"),
        ]
        for key, name in jobs:
            row = QHBoxLayout()
            row.setSpacing(10)

            name_lbl = QLabel(name)
            name_lbl.setFixedWidth(180)
            name_lbl.setFont(QFont("Inter", 9))
            name_lbl.setStyleSheet("color: #475569;")
            row.addWidget(name_lbl)

            bar = QProgressBar()
            bar.setValue(100)
            bar.setFixedHeight(6)
            bar.setTextVisible(False)
            bar.setStyleSheet(
                "QProgressBar { background: #E2E8F0; border-radius: 3px; border: none; }"
                "QProgressBar::chunk { background: #059669; border-radius: 3px; }"
            )
            row.addWidget(bar, 1)

            chip = StatusChip("Ready")
            chip.setMinimumWidth(75)
            row.addWidget(chip)

            self._job_rows[key] = (bar, chip, name_lbl)
            layout.addLayout(row)

    def _on_workflow_step(self, step_dto: Any) -> None:
        """Real-time slot triggered as background workflow steps execute."""
        step_name = getattr(step_dto, "step_name", "")
        progress = getattr(step_dto, "progress", 0)

        self._status_summary_lbl.setText(f"Processing: {step_name} ({progress}%)")
        self._status_summary_lbl.setStyleSheet("color: #0284C7; font-size: 12px; font-weight: bold;")

        if "Ingest" in step_name or "Color" in step_name:
            self._update_job_row("cloud_detector", progress, "Running", "#0284C7")
        elif "OCR" in step_name or "Text" in step_name:
            self._update_job_row("ocr_pipeline", progress, "Running", "#0284C7")
        elif "Classif" in step_name:
            self._update_job_row("ai_classifier", progress, "Running", "#0284C7")
        else:
            self._update_job_row("drawing_hub", progress, "Running", "#0284C7")

    def _on_workflow_completed(self, result_dto: Any) -> None:
        """Real-time slot triggered when workflow pipeline execution finishes."""
        self._status_summary_lbl.setText("Pipeline Complete • 100%")
        self._status_summary_lbl.setStyleSheet("color: #059669; font-size: 12px; font-weight: bold;")

        for key in self._job_rows:
            self._update_job_row(key, 100, "Done", "#059669")

        self.reload_data()

    def _update_job_row(self, key: str, progress: int, status: str, color: str) -> None:
        if key in self._job_rows:
            bar, chip, _ = self._job_rows[key]
            bar.setValue(progress)
            bar.setStyleSheet(
                "QProgressBar { background: #E2E8F0; border-radius: 3px; border: none; }"
                f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
            )
            chip.set_status(status)

    # ── Public Reload ─────────────────────────────────────────────

    def reload_data(self) -> None:
        """Full refresh of KPI cards, active table view, and activity feed."""
        self._build_kpi_cards()
        self._populate_active_table()
        self._populate_activity_feed()
        self._last_refresh_lbl.setText(f"Updated {datetime.now().strftime('%H:%M:%S')}")

    def reload_comments(self) -> None:
        """Alias for controller / main window refresh triggers."""
        self.reload_data()
