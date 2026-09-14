"""
dashboard_screen.py — Home Dashboard screen.

Displays real-time KPI metric cards, recent projects & drawings table with view switcher,
live activity feed, and real-time processing-status panel connected to AppController & SQLite backend.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame,
                                QLabel, QTableView, QListWidget, QListWidgetItem,
                                QPushButton, QProgressBar, QHeaderView, QSizePolicy,
                                QAbstractItemView, QButtonGroup)
from PySide6.QtGui import QFont, QStandardItemModel, QStandardItem
from PySide6.QtCore import Qt, Signal, QSize, QTimer

from app.components.kpi_card import KpiCard
from app.components.chips import StatusChip

try:
    import qtawesome as qta
    _HAS_QTA = True
except ImportError:
    _HAS_QTA = False


def _card(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setObjectName("Card")
    return f


def _h2(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI Variable", 16, QFont.Weight.DemiBold))
    lbl.setObjectName("CardHeader")
    return lbl


def _format_relative_time(dt_str: str) -> str:
    """Convert ISO or standard timestamp string to user-friendly relative time."""
    if not dt_str or dt_str == "System Ready":
        return dt_str or "Just now"
    try:
        if "T" in dt_str:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(dt_str[:19], "%Y-%m-%d %H:%M:%S")

        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        diff = now - dt
        seconds = int(diff.total_seconds())

        if seconds < 60:
            return "Just now"
        elif seconds < 3600:
            mins = max(1, seconds // 60)
            return f"{mins}m ago"
        elif seconds < 86400:
            hours = max(1, seconds // 3600)
            return f"{hours}h ago"
        elif seconds < 172800:
            return "Yesterday"
        else:
            return dt.strftime("%b %d, %H:%M")
    except Exception:
        return dt_str[:16] if len(dt_str) >= 16 else dt_str


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
        self._view_mode = "drawings"  # "projects" | "drawings"
        self._job_rows: Dict[str, tuple[QProgressBar, StatusChip, QLabel]] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(18)

        # ── Header Row ────────────────────────────────────────────
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_lbl = QLabel("Dashboard Overview")
        title_lbl.setFont(QFont("Segoe UI Variable", 20, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #F2F3F5;")
        header_row.addWidget(title_lbl)

        # Live sync indicator
        sync_badge = QLabel("● Live Sync")
        sync_badge.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        sync_badge.setStyleSheet(
            "color: #4ADE80; background-color: rgba(74, 222, 128, 0.12); "
            "border: 1px solid rgba(74, 222, 128, 0.3); border-radius: 12px; "
            "padding: 2px 10px;"
        )
        header_row.addWidget(sync_badge)
        header_row.addStretch()

        self._last_refresh_lbl = QLabel("Updated just now")
        self._last_refresh_lbl.setStyleSheet("color: #6E7280; font-size: 12px;")
        header_row.addWidget(self._last_refresh_lbl)

        self._refresh_btn = QPushButton(" Refresh")
        self._refresh_btn.setObjectName("GhostBtn")
        self._refresh_btn.setFixedHeight(30)
        if _HAS_QTA:
            self._refresh_btn.setIcon(qta.icon("fa5s.sync-alt", color="#A6A9B1"))
        self._refresh_btn.clicked.connect(self.reload_data)
        header_row.addWidget(self._refresh_btn)

        root.addLayout(header_row)

        # ── KPI row ───────────────────────────────────────────────
        self._kpi_row = QHBoxLayout()
        self._kpi_row.setSpacing(16)
        self._build_kpi_cards()
        root.addLayout(self._kpi_row)

        # ── Main split ────────────────────────────────────────────
        split = QHBoxLayout()
        split.setSpacing(16)

        # Left panel: Projects & Drawings table (stretch 2)
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

        # View mode toggle buttons
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

        table_lay.addWidget(self._data_table)
        split.addWidget(table_card, 2)

        # Right column (stretch 1)
        right_col = QVBoxLayout()
        right_col.setSpacing(16)

        # Card 1: Activity feed
        act_card = _card()
        act_lay = QVBoxLayout(act_card)
        act_lay.setContentsMargins(18, 16, 18, 16)
        act_lay.setSpacing(10)

        act_hdr = QHBoxLayout()
        act_hdr.addWidget(_h2("Recent Activity"))
        act_hdr.addStretch()
        live_dot = QLabel("● Live")
        live_dot.setStyleSheet("color: #4ADE80; font-size: 11px; font-weight: bold;")
        act_hdr.addWidget(live_dot)
        act_lay.addLayout(act_hdr)

        self._act_list = QListWidget()
        self._act_list.setSpacing(4)
        self._act_list.setStyleSheet(
            "QListWidget { background: transparent; border: none; outline: none; }"
            "QListWidget::item { background: #252830; border-radius: 6px; padding: 8px 10px; margin-bottom: 2px; }"
            "QListWidget::item:hover { background: #2F333E; }"
        )
        act_lay.addWidget(self._act_list, 1)
        right_col.addWidget(act_card, 1)

        # Card 2: Processing Status & Engines
        proc_card = _card()
        proc_lay = QVBoxLayout(proc_card)
        proc_lay.setContentsMargins(18, 16, 18, 16)
        proc_lay.setSpacing(12)

        proc_hdr = QHBoxLayout()
        proc_hdr.addWidget(_h2("Processing Engines"))
        proc_hdr.addStretch()
        self._status_summary_lbl = QLabel("All Systems Ready")
        self._status_summary_lbl.setStyleSheet("color: #4ADE80; font-size: 12px; font-weight: 600;")
        proc_hdr.addWidget(self._status_summary_lbl)
        proc_lay.addLayout(proc_hdr)

        self._init_pipeline_jobs(proc_lay)
        right_col.addWidget(proc_card)

        split.addLayout(right_col, 1)
        root.addLayout(split, 1)

        # ── Populate initial data ──────────────────────────────────
        self.reload_data()

        # ── Wire Real-time Signals ─────────────────────────────────
        if self._controller:
            self._controller.workflow_step_signal.connect(self._on_workflow_step)
            self._controller.workflow_completed_signal.connect(self._on_workflow_completed)
            self._controller.document_loaded_signal.connect(lambda _: self.reload_data())

        # ── Auto-Refresh Timer (every 8 seconds) ───────────────────
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
                "QPushButton { background-color: #3E9BFF; color: #FFFFFF; font-weight: bold; "
                "border-radius: 4px; padding: 4px 12px; font-size: 12px; border: none; }"
            )
        return (
            "QPushButton { background-color: #2D3038; color: #A6A9B1; "
            "border-radius: 4px; padding: 4px 12px; font-size: 12px; border: 1px solid #3A3D46; }"
            "QPushButton:hover { background-color: #363A44; color: #F2F3F5; }"
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
            ("fa5s.folder-open",  str(total_projects), "Total Projects",     "Active",      "#3E9BFF"),
            ("fa5s.file-pdf",     str(total_drawings), "Drawings Processed", "In Database", "#8B9CFF"),
            ("fa5s.comments",     str(total_comments), "Comments Detected",  "Live Extracted", "#FBBF24"),
            ("fa5s.check-circle", accuracy_str,        "OCR Accuracy",       accuracy_trend, "#4ADE80"),
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

        for p in projects_list:
            p_name = p.get("name", p.get("id", "—"))
            p_drawings = str(p.get("drawings", p.get("total_drawings", "0")))
            p_comments = str(p.get("comments", p.get("total_comments", "0")))
            p_progress = f"{p.get('progress', 0)}%"
            p_status = p.get("status", "Active")
            p_engineer = p.get("lead_engineer", p.get("engineer", "—")) or "—"

            row = [
                QStandardItem(p_name),
                QStandardItem(p_drawings),
                QStandardItem(p_comments),
                QStandardItem(p_progress),
                QStandardItem(p_status),
                QStandardItem(p_engineer),
            ]
            row[0].setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
            for item in row:
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            model.appendRow(row)

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
            row[0].setFont(QFont("Cascadia Code", 12))
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
            item = QListWidgetItem("  No recent activity recorded")
            item.setSizeHint(QSize(0, 36))
            self._act_list.addItem(item)
            return

        for act in activities:
            text = act.get("text", "")
            time_rel = _format_relative_time(act.get("time", ""))
            icon_name = act.get("icon", "fa5s.history")
            color_hex = act.get("color", "#3E9BFF")

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
            name_lbl.setFixedWidth(190)
            name_lbl.setStyleSheet("color: #C0C3CC; font-size: 13px; font-weight: 500;")
            row.addWidget(name_lbl)

            bar = QProgressBar()
            bar.setValue(100)
            bar.setFixedHeight(6)
            bar.setTextVisible(False)  # Prevents overlapping text and font warnings
            bar.setStyleSheet(
                "QProgressBar { background: #32353E; border-radius: 3px; border: none; }"
                "QProgressBar::chunk { background: #4ADE80; border-radius: 3px; }"
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
        self._status_summary_lbl.setStyleSheet("color: #3E9BFF; font-size: 12px; font-weight: bold;")

        # Update specific engine rows according to active step
        if "Ingest" in step_name or "Color" in step_name:
            self._update_job_row("cloud_detector", progress, "Running", "#3E9BFF")
        elif "OCR" in step_name or "Text" in step_name:
            self._update_job_row("ocr_pipeline", progress, "Running", "#3E9BFF")
        elif "Classif" in step_name:
            self._update_job_row("ai_classifier", progress, "Running", "#3E9BFF")
        else:
            self._update_job_row("drawing_hub", progress, "Running", "#3E9BFF")

    def _on_workflow_completed(self, result_dto: Any) -> None:
        """Real-time slot triggered when workflow pipeline execution finishes."""
        self._status_summary_lbl.setText("Pipeline Complete • 100%")
        self._status_summary_lbl.setStyleSheet("color: #4ADE80; font-size: 12px; font-weight: bold;")

        for key in self._job_rows:
            self._update_job_row(key, 100, "Done", "#4ADE80")

        self.reload_data()

    def _update_job_row(self, key: str, progress: int, status: str, color: str) -> None:
        if key in self._job_rows:
            bar, chip, _ = self._job_rows[key]
            bar.setValue(progress)
            bar.setStyleSheet(
                "QProgressBar { background: #32353E; border-radius: 3px; border: none; }"
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

