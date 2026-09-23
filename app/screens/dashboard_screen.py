"""
dashboard_screen.py — Redesigned Home Dashboard screen with Modern Light Theme UI.

Displays:
    - 4 KPI metric cards (Total Projects, Drawings Processed, Comments Detected, OCR Accuracy)
    - 3 Analytics charts (Category Pareto, Donut Distribution, Monthly Trend)
    - Recent Projects table & Recent Drawings table
    - Recent Activity feed & System Processing Status
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame,
                                QLabel, QTableView, QListWidget, QListWidgetItem,
                                QPushButton, QProgressBar, QHeaderView, QSizePolicy,
                                QAbstractItemView, QScrollArea, QGraphicsDropShadowEffect)
from PySide6.QtGui import QFont, QStandardItemModel, QStandardItem, QColor
from PySide6.QtCore import Qt, Signal, QSize

from app.components.kpi_card import KpiCard
from app.components.chips import StatusChip
from app.components.charts import (
    build_pareto_chart,
    build_monthly_chart,
    build_category_pie,
)

try:
    import qtawesome as qta
    _HAS_QTA = True
except ImportError:
    _HAS_QTA = False


DEFAULT_ACTIVITIES: List[Dict[str, str]] = [
    {"text": "UCC AI Analysis complete for drawing DWG-5-3552-12", "time": "Just now", "tag": "OCR"},
    {"text": "DistilBERT Classifier mapped 13 technical engineering categories", "time": "4 min ago", "tag": "AI/NLP"},
    {"text": "Auto-detected 71 multi-color comment annotations on sheet 1", "time": "12 min ago", "tag": "Vision"},
    {"text": "Export generated: PRJ-001_Comments_Dataset_2026-07-28.csv", "time": "25 min ago", "tag": "Export"},
    {"text": "SQLite database verified & synced with backend repository", "time": "1 hr ago", "tag": "Database"},
]

DEFAULT_JOBS: List[Dict[str, Any]] = [
    {"name": "Hybrid OCR Engine (Tesseract + TrOCR)", "progress": 100, "status": "Active"},
    {"name": "Comment Classifier (DistilBERT 13-Class)", "progress": 100, "status": "Active"},
    {"name": "Drawing Intelligence Hub & PyMuPDF Worker", "progress": 100, "status": "Active"},
]


def _card(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setObjectName("Card")
    f.setStyleSheet("""
        QFrame#Card {
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 14px;
        }
    """)
    # Add subtle soft shadow to replicate modern SaaS elevation
    shadow = QGraphicsDropShadowEffect(f)
    shadow.setBlurRadius(16)
    shadow.setColor(QColor(15, 23, 42, 10))
    shadow.setOffset(0, 4)
    f.setGraphicsEffect(shadow)
    return f


def _h2(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Inter", 15, QFont.Weight.Bold))
    lbl.setStyleSheet("color: #0F172A; background: transparent; border: none;")
    lbl.setObjectName("CardHeader")
    return lbl


class DashboardPage(QWidget):
    """
    Home Dashboard — KPI cards, responsive charts, recent tables,
    and processing activity.
    """

    open_project = Signal(str)

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._kpi_cards: List[KpiCard] = []

        self.setStyleSheet("""
            QWidget {
                background-color: #F8FAFC;
                font-family: 'Inter', system-ui, -apple-system, sans-serif;
            }
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QLabel#PageTitle {
                color: #0F172A;
                font-weight: 700;
                background: transparent;
            }
            QLabel#PageSubtitle {
                color: #64748B;
                font-size: 13px;
                background: transparent;
            }
            QLabel#SubCaption {
                color: #0284C7;
                background: #F0F9FF;
                border: 1px solid #BAE6FD;
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: 600;
            }
            QTableView {
                background-color: #FFFFFF;
                border: 1px solid #F1F5F9;
                border-radius: 8px;
                gridline-color: transparent;
                color: #334155;
                font-size: 12px;
                selection-background-color: #F0F9FF;
                selection-color: #0369A1;
            }
            QTableView::item {
                padding: 8px;
                border-bottom: 1px solid #F8FAFC;
            }
            QHeaderView::section {
                background-color: #F8FAFC;
                color: #475569;
                padding: 8px;
                font-weight: 600;
                font-size: 11px;
                border: none;
                border-bottom: 1px solid #E2E8F0;
                text-transform: uppercase;
            }
        """)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        container.setStyleSheet("background-color: #F8FAFC;")
        root = QVBoxLayout(container)
        root.setContentsMargins(32, 28, 32, 36)
        root.setSpacing(24)

        # ── Dashboard Title ───────────────────────────────────────
        hdr_box = QVBoxLayout()
        hdr_box.setSpacing(6)
        title = QLabel("Engineering Drawing Review Dashboard")
        title.setFont(QFont("Inter", 22, QFont.Weight.Bold))
        title.setObjectName("PageTitle")
        hdr_box.addWidget(title)

        subtitle = QLabel("AI-driven drawing review comment analysis, OCR extraction status, and verification metrics.")
        subtitle.setObjectName("PageSubtitle")
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

        # Chart 1: Pareto Bar
        c1 = _card()
        c1_lay = QVBoxLayout(c1)
        c1_lay.setContentsMargins(18, 18, 18, 18)
        c1_lay.setSpacing(12)
        c1_lay.addWidget(_h2("Comments by Category"))
        cat_data = self._controller.get_category_distribution() if self._controller else None
        c1_lay.addWidget(build_pareto_chart(cat_data), 1)
        charts_row.addWidget(c1, 4)

        # Chart 2: Donut Distribution
        c2 = _card()
        c2_lay = QVBoxLayout(c2)
        c2_lay.setContentsMargins(18, 18, 18, 18)
        c2_lay.setSpacing(12)
        c2_lay.addWidget(_h2("Category Distribution"))
        c2_lay.addWidget(build_category_pie(cat_data), 1)
        charts_row.addWidget(c2, 3)

        # Chart 3: Monthly Trend
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

        # Left Column: Recent Projects & Drawings Tables
        left_col = QVBoxLayout()
        left_col.setSpacing(16)

        # Recent Projects Table Card
        proj_card = _card()
        proj_lay = QVBoxLayout(proj_card)
        proj_lay.setContentsMargins(20, 18, 20, 20)
        proj_lay.setSpacing(14)

        proj_hdr = QHBoxLayout()
        proj_hdr.addWidget(_h2("Recent Projects"))
        proj_hdr.addStretch()
        p_count = QLabel("7 Projects Active")
        p_count.setObjectName("SubCaption")
        proj_hdr.addWidget(p_count)
        proj_lay.addLayout(proj_hdr)

        self._proj_table = QTableView()
        self._proj_table.setAlternatingRowColors(True)
        self._proj_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._proj_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._proj_table.horizontalHeader().setStretchLastSection(True)
        self._proj_table.verticalHeader().hide()
        self._proj_table.setShowGrid(False)
        self._populate_projects_table()
        proj_lay.addWidget(self._proj_table)
        left_col.addWidget(proj_card, 1)

        # Recent Drawings Table Card
        dwg_card = _card()
        dwg_lay = QVBoxLayout(dwg_card)
        dwg_lay.setContentsMargins(20, 18, 20, 20)
        dwg_lay.setSpacing(14)

        dwg_hdr = QHBoxLayout()
        dwg_hdr.addWidget(_h2("Recent Drawings Processed"))
        dwg_hdr.addStretch()
        d_count = QLabel("Latest Loaded")
        d_count.setObjectName("SubCaption")
        dwg_hdr.addWidget(d_count)
        dwg_lay.addLayout(dwg_hdr)

        self._dwg_table = QTableView()
        self._dwg_table.setAlternatingRowColors(True)
        self._dwg_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._dwg_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._dwg_table.horizontalHeader().setStretchLastSection(True)
        self._dwg_table.verticalHeader().hide()
        self._dwg_table.setShowGrid(False)
        self._populate_drawings_table()
        dwg_lay.addWidget(self._dwg_table)
        left_col.addWidget(dwg_card, 1)

        split.addLayout(left_col, 6)

        # Right Column: Activity Feed & Processing Status
        right_col = QVBoxLayout()
        right_col.setSpacing(16)

        # Activity Feed Card
        act_card = _card()
        act_lay = QVBoxLayout(act_card)
        act_lay.setContentsMargins(20, 18, 20, 20)
        act_lay.setSpacing(14)
        act_lay.addWidget(_h2("Recent Activity"))
        act_lay.addWidget(self._build_activity_list(), 1)
        right_col.addWidget(act_card, 1)

        # Processing Status Card
        proc_card = _card()
        proc_lay = QVBoxLayout(proc_card)
        proc_lay.setContentsMargins(20, 18, 20, 20)
        proc_lay.setSpacing(14)
        proc_lay.addWidget(_h2("System Processing Status"))
        for job in DEFAULT_JOBS:
            proc_lay.addLayout(self._build_job_row(job))
        right_col.addWidget(proc_card)

        split.addLayout(right_col, 4)
        root.addLayout(split)

        scroll.setWidget(container)

        page_lay = QVBoxLayout(self)
        page_lay.setContentsMargins(0, 0, 0, 0)
        page_lay.addWidget(scroll)

    # ── Sub-builders ──────────────────────────────────────────────

    def _get_kpi_values(self) -> tuple[int, int, int, str]:
        kpi_data = self._controller.get_dashboard_kpis() if self._controller else None
        if kpi_data is not None:
            if hasattr(kpi_data, "total_projects"):
                total_projects = kpi_data.total_projects
                total_drawings = kpi_data.total_drawings
                total_comments = kpi_data.total_comments
                accuracy_val = kpi_data.accuracy_rate
            elif isinstance(kpi_data, dict):
                total_projects = kpi_data.get("total_projects", 0)
                total_drawings = kpi_data.get("drawings_processed", kpi_data.get("total_drawings", 0))
                total_comments = kpi_data.get("comments_detected", kpi_data.get("total_comments", 0))
                accuracy_val = kpi_data.get("accuracy", kpi_data.get("accuracy_rate"))
            else:
                total_projects, total_drawings, total_comments, accuracy_val = 0, 0, 0, None
        else:
            total_projects, total_drawings, total_comments, accuracy_val = 7, 302, 2036, 91.4

        accuracy_str = f"{accuracy_val:.1f}%" if accuracy_val is not None else "91.4%"
        return total_projects, total_drawings, total_comments, accuracy_str

    def _build_kpi_cards(self) -> None:
        while self._kpi_row.count():
            item = self._kpi_row.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._kpi_cards.clear()

        total_projects, total_drawings, total_comments, accuracy_str = self._get_kpi_values()

        # Modern vibrant primary and accent color pairings
        kpis = [
            ("fa5s.folder-open", str(total_projects), "Total Projects",    "+2",       "#0284C7"),
            ("fa5s.file-alt",    str(total_drawings), "Drawings Processed", "+18",      "#2563EB"),
            ("fa5s.comments",    str(total_comments), "Comments Detected", "+143",     "#D97706"),
            ("fa5s.check-circle", accuracy_str,       "OCR Accuracy",      "+0.8%",    "#16A34A"),
        ]
        for icon, val, lbl, trend, color in kpis:
            card = KpiCard(icon, val, lbl, trend, color)
            card.setMinimumHeight(135)
            self._kpi_cards.append(card)
            self._kpi_row.addWidget(card, 1)

    def _populate_projects_table(self) -> None:
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
                p_drawings = str(p.get("drawings", p.get("total_drawings", "—")))
                p_comments = str(p.get("comments", p.get("total_comments", "—")))
                p_progress = f"{p.get('progress', 0)}%"
                p_status = p.get("status", "Active")
                p_engineer = p.get("lead_engineer", p.get("engineer", "—")) or "—"
            else:
                p_name = getattr(p, "name", "—")
                p_drawings = str(getattr(p, "drawings", "—"))
                p_comments = str(getattr(p, "comments", "—"))
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
            for it in row_items:
                it.setTextAlignment(Qt.AlignmentFlag.AlignVCenter)
            model.appendRow(row_items)

        self._proj_table.setModel(model)
        self._proj_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._proj_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def _populate_drawings_table(self) -> None:
        model = QStandardItemModel(0, 5)
        model.setHorizontalHeaderLabels(
            ["Drawing No", "File Name", "Pages", "Comments", "Status"]
        )

        drawings = [
            ("5-3552-12", "5-3552-12_COMBINE.pdf", "7", "71", "Processed"),
            ("UCC-E-101", "UCC-E-101_PID_Unit4.pdf", "3", "28", "Processed"),
            ("RU7-P-201", "Refinery_Unit7_Piping.pdf", "5", "42", "Reviewing"),
            ("LNG-T-501", "LNG_Terminal_Vessel.pdf", "4", "35", "Queued"),
        ]

        for dwg, fn, pgs, cmts, st in drawings:
            row_items = [
                QStandardItem(dwg),
                QStandardItem(fn),
                QStandardItem(pgs),
                QStandardItem(cmts),
                QStandardItem(st),
            ]
            for it in row_items:
                it.setTextAlignment(Qt.AlignmentFlag.AlignVCenter)
            model.appendRow(row_items)

        self._dwg_table.setModel(model)
        self._dwg_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._dwg_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def _build_activity_list(self) -> QListWidget:
        lst = QListWidget()
        lst.setSpacing(8)
        lst.setObjectName("ActivityList")
        lst.setStyleSheet("""
            QListWidget#ActivityList {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget#ActivityList::item {
                background: transparent;
                border: none;
            }
        """)
        
        for act in DEFAULT_ACTIVITIES:
            item = QListWidgetItem()
            item.setSizeHint(QSize(280, 68))
            card = QFrame()
            card.setStyleSheet("""
                QFrame {
                    background-color: #F8FAFC;
                    border: 1px solid #E2E8F0;
                    border-radius: 8px;
                }
            """)
            lay = QVBoxLayout(card)
            lay.setContentsMargins(10, 8, 10, 8)
            lay.setSpacing(4)

            top = QHBoxLayout()
            tag = QLabel(act.get("tag", "System"))
            tag.setFont(QFont("Inter", 9, QFont.Weight.Bold))
            tag.setStyleSheet(
                "color: #0284C7; background: #E0F2FE; border-radius: 4px; padding: 2px 6px; border: none;"
            )
            top.addWidget(tag)
            top.addStretch()

            t_lbl = QLabel(act["time"])
            t_lbl.setFont(QFont("Inter", 10))
            t_lbl.setStyleSheet("color: #94A3B8; background: transparent; border: none;")
            top.addWidget(t_lbl)
            lay.addLayout(top)

            desc = QLabel(act["text"])
            desc.setFont(QFont("Inter", 11))
            desc.setWordWrap(True)
            desc.setStyleSheet("color: #334155; background: transparent; border: none;")
            lay.addWidget(desc)

            lst.addItem(item)
            lst.setItemWidget(item, card)

        return lst

    def _build_job_row(self, job: Dict[str, Any]) -> QVBoxLayout:
        lay = QVBoxLayout()
        lay.setSpacing(6)

        hdr = QHBoxLayout()
        name = QLabel(job["name"])
        name.setFont(QFont("Inter", 12, QFont.Weight.Medium))
        name.setStyleSheet("color: #1E293B; background: transparent; border: none;")
        hdr.addWidget(name)
        hdr.addStretch()

        stat = QLabel("● Active")
        stat.setFont(QFont("Inter", 11, QFont.Weight.Bold))
        stat.setStyleSheet("color: #16A34A; background: transparent; border: none;")
        hdr.addWidget(stat)
        lay.addLayout(hdr)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(job["progress"])
        bar.setFixedHeight(6)
        bar.setTextVisible(False)
        bar.setStyleSheet("""
            QProgressBar {
                background: #E2E8F0;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: #16A34A;
                border-radius: 3px;
            }
        """)
        lay.addWidget(bar)
        lay.addSpacing(4)
        return lay

    def refresh_data(self) -> None:
        self._build_kpi_cards()
        self._populate_projects_table()