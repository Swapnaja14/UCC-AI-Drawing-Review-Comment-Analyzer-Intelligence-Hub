"""
classification_screen.py — Classification screen.

Provides:
    ClassificationPage(QWidget)
        Category summary cards, search / filter toolbar, sortable table
        with category + confidence delegates, and a slide-in inspector drawer.

ARCHITECTURE NOTE:
This screen loads comments and category counts through AppController.
It must NOT import or instantiate CommentRepository or CategoryRepository
directly. All data must flow through AppController → Repository → SQLAlchemy.

MOCK DATA FALLBACK:
When no controller is provided, or the database has no comments for the
loaded drawing, the screen falls back to mock_data.CATEGORY_COUNTS and
mock_data.COMMENTS. This fallback is intentional during Week 3 development.

INTEGRATION WARNING — inspector drawer row indexing:
The drawer previously used md.COMMENTS[row] as a direct list index, which
is fragile when a QSortFilterProxyModel filter is active. The fixed
implementation stores the comment object against the model row using a
separate instance list and looks up by matching to the source row index.
See _open_drawer() and _build_model() below.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Union

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame,
                                QLabel, QTableView, QPushButton, QComboBox,
                                QHeaderView, QAbstractItemView,
                                QSizePolicy)
from PySide6.QtGui import QFont, QStandardItemModel, QStandardItem
from PySide6.QtCore import Qt, QSortFilterProxyModel, QModelIndex, Signal

from app import mock_data as md
from app.components.chips import CategoryBadge
from app.components.drawer import InspectorDrawer
from app.components.comment_table import ConfidenceDelegate, CategoryDelegate
from app.components.statistics_cards import CategorySummaryCard
from app.components.search_bar import SearchBar

_CATEGORY_ICONS = {
    "Technical":     ("🔧", "#F87171"),
    "Drafting":      ("📐", "#A78BFA"),
    "Dimension":     ("📏", "#38BDF8"),
    "Cosmetic":      ("🎨", "#F472B6"),
    "Standards":     ("📋", "#FBBF24"),
    "Coordination":  ("🔄", "#34D399"),
    "Documentation": ("📄", "#94A3B8"),
    "Revision":      ("🏷",  "#FB923C"),
    "Calculation":   ("🔢", "#818CF8"),
    "Feasibility":   ("🏗",  "#2DD4BF"),
    "Material":      ("🧱", "#06B6D4"),
    "Notes":         ("📝", "#A3E635"),
    "BOM":           ("📦", "#C084FC"),
    # Backwards compatibility
    "Dimensional":   ("📏", "#38BDF8"),
    "Structural":    ("🏗",  "#A78BFA"),
    "Electrical":    ("⚡",  "#FBBF24"),
    "Other":         ("❓",  "#94A3B8"),
    "Mechanical":    ("⚙",   "#FB923C"),
}


def _get(c: Union[Dict[str, Any], Any], field: str, default: Any = "") -> Any:
    """Access a field from either a normalised display dict or a mock dataclass."""
    if isinstance(c, dict):
        return c.get(field, default)
    return getattr(c, field, default)


class ClassificationPage(QWidget):
    """
    Classification — category summary cards, comment table with badges,
    and a slide-in inspector drawer.
    """
    comment_selected = Signal(str)

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self._controller = controller

        # Load category counts: prefer DB, fall back to empty
        if self._controller and self._controller.current_drawing_id:
            db_counts = self._controller.get_category_counts(
                self._controller.current_drawing_id
            )
            category_counts = db_counts if db_counts else {}
        elif self._controller:
            db_counts = self._controller.get_category_counts()
            category_counts = db_counts if db_counts else {}
        else:
            category_counts = md.CATEGORY_COUNTS

        # Load comments: prefer DB, fall back to mock only in standalone
        if self._controller and self._controller.current_drawing_id:
            db_comments = self._controller.get_comments_for_drawing(
                self._controller.current_drawing_id
            )
            self._comments_data: List[Any] = db_comments if db_comments else []
        elif self._controller:
            self._comments_data = []
        else:
            self._comments_data = list(md.COMMENTS)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Main content ──────────────────────────────────────────
        main = QWidget()
        root = QVBoxLayout(main)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Category summary cards
        cat_row = QHBoxLayout()
        cat_row.setSpacing(12)
        self._cat_cards: Dict[str, CategorySummaryCard] = {}
        display_cats = list(category_counts.keys()) if category_counts else list(md.CATEGORIES)
        for cat in display_cats:
            count = category_counts.get(cat, 0)
            icon_text, color = _CATEGORY_ICONS.get(cat, ("●", "#A6A9B1"))
            card = CategorySummaryCard(icon_text, count, cat, color)
            self._cat_cards[cat] = card
            cat_row.addWidget(card, 1)
        root.addLayout(cat_row)

        # Toolbar
        tb = QHBoxLayout()
        tb.setSpacing(12)

        search = SearchBar(
            placeholder="  🔍  Search comments, categories…",
            fixed_width=300,
        )
        tb.addWidget(search)
        tb.addStretch()

        self._dept_filt = QComboBox()
        dept_options = ["All Departments"]
        if self._controller and hasattr(self._controller, "get_all_departments"):
            try:
                db_depts = self._controller.get_all_departments()
                for d in db_depts:
                    if d.get("name") and d.get("name") not in dept_options:
                        dept_options.append(d.get("name"))
            except Exception:
                pass
        if len(dept_options) <= 1:
            dept_options = [
                "All Departments",
                "Electrical Engineering",
                "GPD",
                "Pipe Support Engineering",
                "Piping Engineering",
                "Plakon",
                "Structural & Physical Design",
                "System Engineering",
                "Unassigned",
            ]
        self._dept_filt.addItems(dept_options)
        self._dept_filt.setFixedHeight(36)
        self._dept_filt.currentTextChanged.connect(self._on_dept_filter_changed)
        tb.addWidget(self._dept_filt)

        self._cat_filt = QComboBox()
        self._cat_filt.addItems(["All Categories"] + list(category_counts.keys()))
        self._cat_filt.setFixedHeight(36)
        self._cat_filt.currentTextChanged.connect(self._on_cat_filter_changed)
        tb.addWidget(self._cat_filt)

        self._st_filt = QComboBox()
        self._st_filt.addItems(["All Status", "Pending", "Approved", "Rejected", "Flagged"])
        self._st_filt.setFixedHeight(36)
        self._st_filt.currentTextChanged.connect(self._on_status_filter_changed)
        tb.addWidget(self._st_filt)

        review_btn = QPushButton("🔍 View in Review")
        review_btn.setObjectName("SecondaryBtn")
        review_btn.setFixedHeight(36)
        review_btn.setToolTip("Open currently selected comment in Human Review")
        review_btn.clicked.connect(self.view_selected_in_review)
        tb.addWidget(review_btn)

        root.addLayout(tb)

        # Table
        table_card = QFrame()
        table_card.setObjectName("Card")
        tc_lay = QVBoxLayout(table_card)
        tc_lay.setContentsMargins(0, 0, 0, 0)

        self._model = self._build_model()
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterKeyColumn(-1)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        search.search_changed.connect(self._proxy.setFilterFixedString)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().hide()
        self._table.setShowGrid(False)
        self._table.setItemDelegateForColumn(1, CategoryDelegate(self._table))
        self._table.setItemDelegateForColumn(2, ConfidenceDelegate(self._table))

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(1, 150)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(2, 130)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(3, 120)
        hdr.setStretchLastSection(False)
        self._table.clicked.connect(self._open_drawer)
        self._table.doubleClicked.connect(self._on_table_double_clicked)

        tc_lay.addWidget(self._table)
        root.addWidget(table_card, 1)

        outer.addWidget(main, 1)

        # ── Inspector drawer ──────────────────────────────────────
        self._drawer = InspectorDrawer("Comment Inspector")
        outer.addWidget(self._drawer)

    def reload_comments(self) -> None:
        """Reload comments and category counts from DB for the loaded drawing."""
        if self._controller and self._controller.current_drawing_id:
            db_comments = self._controller.get_comments_for_drawing(
                self._controller.current_drawing_id
            )
            self._comments_data = db_comments if db_comments else []
            db_counts = self._controller.get_category_counts(
                self._controller.current_drawing_id
            )
            category_counts = db_counts if db_counts else {}

            # Auto-select the drawing's department if available
            if hasattr(self, "_dept_filt") and self._controller.drawing_repo:
                try:
                    dwg = self._controller.drawing_repo.get_drawing_by_id(self._controller.current_drawing_id)
                    if dwg and dwg.get("department_name") and dwg.get("department_name") != "Unassigned":
                        dept_name = dwg.get("department_name")
                        idx = self._dept_filt.findText(dept_name)
                        if idx >= 0:
                            self._dept_filt.blockSignals(True)
                            self._dept_filt.setCurrentIndex(idx)
                            self._dept_filt.blockSignals(False)
                except Exception:
                    pass
        elif self._controller:
            self._comments_data = []
            category_counts = self._controller.get_category_counts() or {}
        else:
            self._comments_data = list(md.COMMENTS)
            category_counts = md.CATEGORY_COUNTS

        self._model = self._build_model()
        self._proxy.setSourceModel(self._model)

        if hasattr(self, "_cat_cards"):
            for cat, card in self._cat_cards.items():
                card.set_count(category_counts.get(cat, 0))

        # Re-apply combined filters to match current department/category/status selections
        self._apply_table_filter()

    # ── Model / drawer helpers ────────────────────────────────────

    def _build_model(self) -> QStandardItemModel:
        model = QStandardItemModel(0, 4)
        model.setHorizontalHeaderLabels(
            ["Comment", "Category", "Confidence", "Status"]
        )
        for c in self._comments_data:
            ocr_text   = _get(c, "ocr_text", "")
            cid        = _get(c, "id", "")
            category   = _get(c, "category", "Other")
            confidence = _get(c, "confidence", 0.0)
            status     = _get(c, "status", "Pending")

            text_item = QStandardItem(str(ocr_text)[:80])
            text_item.setData(cid, Qt.ItemDataRole.UserRole)
            cat_item  = QStandardItem(str(category))
            conf_item = QStandardItem()
            conf_item.setData(float(confidence), Qt.ItemDataRole.UserRole)
            st_item   = QStandardItem(str(status))
            for item in [text_item, cat_item, conf_item, st_item]:
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )
            model.appendRow([text_item, cat_item, conf_item, st_item])
        return model

    def _open_drawer(self, index: QModelIndex) -> None:
        """
        Open the inspector drawer for the selected comment.

        INTEGRATION NOTE:
        The source row index is used to look up the comment from
        self._comments_data — NOT from md.COMMENTS directly. This is correct
        because self._comments_data is built in the same order as the model
        rows, and it works for both DB dicts and mock objects.

        This replaces the previous pattern of md.COMMENTS[row] which was
        fragile when a QSortFilterProxyModel filter was active.
        """
        source_row = self._proxy.mapToSource(index).row()
        item = self._model.item(source_row, 0)
        cid = item.data(Qt.ItemDataRole.UserRole) if item else None

        c = None
        if cid:
            for cand in self._comments_data:
                if _get(cand, "id") == cid:
                    c = cand
                    break
        if not c:
            if 0 <= source_row < len(self._comments_data):
                c = self._comments_data[source_row]
            else:
                return

        cid        = _get(c, "id", "")
        drawing_no = _get(c, "drawing_no", _get(c, "drawing_id", ""))
        project_id = _get(c, "drawing_id", "")
        ocr_text   = _get(c, "ocr_text", "")
        category   = _get(c, "category", "Other")
        confidence = _get(c, "confidence", 0.0)

        lay = self._drawer.content_layout
        while lay.count():
            child = lay.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self._drawer.set_title(f"Inspector — {cid}")

        def _row(key: str, val: str) -> None:
            k = QLabel(key)
            k.setObjectName("FormLabel")
            lay.addWidget(k)
            v = QLabel(val)
            v.setFont(QFont("Cascadia Code", 12))
            v.setWordWrap(True)
            lay.addWidget(v)

        _row("Drawing", drawing_no)
        _row("Project", project_id)

        full_text = QLabel(str(ocr_text))
        full_text.setWordWrap(True)
        full_text.setStyleSheet(
            "color:#F2F3F5; font-size:13px; padding:8px;"
            " background:#2D2F34; border-radius:6px;"
        )
        lay.addWidget(full_text)

        cat_lbl = QLabel("Category")
        cat_lbl.setObjectName("FormLabel")
        lay.addWidget(cat_lbl)
        lay.addWidget(CategoryBadge(str(category)))

        cat_override = QComboBox()
        db_cats = [cat.get("name") for cat in self._controller.get_all_categories()] if self._controller else []
        all_cats = list(db_cats) if db_cats else list(md.CATEGORIES)
        if str(category) not in all_cats:
            all_cats.insert(0, str(category))
        cat_override.addItems(all_cats)
        cat_override.setCurrentText(str(category))
        cat_override.setFixedHeight(36)

        def _on_cat_override_changed(new_category: str):
            if not new_category or new_category == str(category):
                return
            if isinstance(c, dict):
                c["category"] = new_category
            else:
                setattr(c, "category", new_category)
            if self._controller and cid and not cid.startswith("C-"):
                self._controller.update_comment_category(cid, new_category)
            self._apply_table_filter()

        cat_override.currentTextChanged.connect(_on_cat_override_changed)
        lay.addWidget(cat_override)

        conf_lbl = QLabel(f"Confidence: {int(float(confidence) * 100)}%")
        conf_lbl.setObjectName("SubCaption")
        lay.addWidget(conf_lbl)

        review_btn = QPushButton("🔍 Open in Human Review →")
        review_btn.setObjectName("PrimaryBtn")
        review_btn.setFixedHeight(38)
        review_btn.setToolTip("Jump directly to Human Review screen to review and edit this comment")
        review_btn.clicked.connect(lambda: self._emit_comment_selected(str(cid)))
        lay.addWidget(review_btn)

        self._drawer.open_drawer()

    def _emit_comment_selected(self, cid: Optional[str]) -> None:
        if not cid:
            return
        cid_str = str(cid)
        # Find comment object to locate drawing_id
        c_dwg_id = None
        for c in self._comments_data:
            if str(_get(c, "id")) == cid_str:
                c_dwg_id = _get(c, "drawing_id")
                break
        if c_dwg_id and self._controller and c_dwg_id != self._controller.current_drawing_id:
            self._controller.switch_current_drawing(c_dwg_id)
        self.comment_selected.emit(cid_str)

    def _on_table_double_clicked(self, index: QModelIndex) -> None:
        """Double clicking any row in the classification table jumps directly to Human Review."""
        source_row = self._proxy.mapToSource(index).row()
        item = self._model.item(source_row, 0)
        cid = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not cid and 0 <= source_row < len(self._comments_data):
            cid = _get(self._comments_data[source_row], "id", "")
        if cid:
            self._emit_comment_selected(cid)

    def view_selected_in_review(self) -> None:
        """Emit comment_selected for the currently selected row in classification table."""
        selection = self._table.selectionModel().selectedRows()
        if selection:
            source_row = self._proxy.mapToSource(selection[0]).row()
            item = self._model.item(source_row, 0)
            cid = item.data(Qt.ItemDataRole.UserRole) if item else None
            if cid:
                self._emit_comment_selected(cid)
                return
        curr = self._table.currentIndex()
        if curr.isValid():
            source_row = self._proxy.mapToSource(curr).row()
            item = self._model.item(source_row, 0)
            cid = item.data(Qt.ItemDataRole.UserRole) if item else None
            if cid:
                self._emit_comment_selected(cid)
                return
        if self._model.rowCount() > 0:
            item = self._model.item(0, 0)
            if item:
                cid = item.data(Qt.ItemDataRole.UserRole)
                if cid:
                    self._emit_comment_selected(cid)

    def _apply_table_filter(self) -> None:
        """Apply combined department + category + status filter."""
        dept_text = self._dept_filt.currentText() if hasattr(self, "_dept_filt") else "All Departments"
        cat_text = self._cat_filt.currentText() if hasattr(self, "_cat_filt") else "All Categories"
        st_text = self._st_filt.currentText() if hasattr(self, "_st_filt") else "All Status"

        # Determine current drawing department if available
        drawing_dept = ""
        if self._controller and self._controller.current_drawing_id and self._controller.drawing_repo:
            try:
                dwg = self._controller.drawing_repo.get_drawing_by_id(self._controller.current_drawing_id)
                if dwg:
                    drawing_dept = dwg.get("department_name", "") or ""
            except Exception:
                drawing_dept = ""

        # Rebuild the model from self._comments_data with combined filters
        self._model.removeRows(0, self._model.rowCount())
        for c in self._comments_data:
            ocr_text   = _get(c, "ocr_text", "")
            cid        = _get(c, "id", "")
            category   = _get(c, "category", "Other")
            confidence = _get(c, "confidence", 0.0)
            status     = _get(c, "status", "Pending")

            # Check department
            c_dept = _get(c, "department_name", "") or _get(c, "department_id", "") or drawing_dept
            if dept_text != "All Departments" and dept_text:
                if str(c_dept).strip().lower() != dept_text.strip().lower() and dept_text.strip().lower() not in str(c_dept).strip().lower():
                    continue

            # Apply category filter
            if cat_text != "All Categories" and str(category) != cat_text:
                continue
            # Apply status filter
            if st_text != "All Status" and str(status) != st_text:
                continue

            text_item = QStandardItem(str(ocr_text)[:80])
            text_item.setData(cid, Qt.ItemDataRole.UserRole)
            cat_item  = QStandardItem(str(category))
            conf_item = QStandardItem()
            conf_item.setData(float(confidence), Qt.ItemDataRole.UserRole)
            st_item   = QStandardItem(str(status))
            for item in [text_item, cat_item, conf_item, st_item]:
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )
            self._model.appendRow([text_item, cat_item, conf_item, st_item])

    def _on_dept_filter_changed(self, text: str) -> None:
        """Department filter — rebuilds table with only matching departments."""
        self._apply_table_filter()

    def _on_cat_filter_changed(self, text: str) -> None:
        """Category filter — rebuilds table with only matching categories."""
        self._apply_table_filter()

    def _on_status_filter_changed(self, text: str) -> None:
        """Status filter — rebuilds table with only matching statuses."""
        self._apply_table_filter()
