"""
charts.py — QtCharts chart factory functions.

Provides:
    build_pareto_chart()   -> QChartView | QFrame
    build_monthly_chart()  -> QChartView | QFrame
    build_category_pie()   -> QChartView | QFrame
    no_chart_label(text)   -> QFrame   (fallback when QtCharts unavailable)

All functions return a QWidget ready to embed directly in any layout.
When ``PySide6.QtCharts`` is not installed, each chart function falls back
to ``no_chart_label()`` so the rest of the UI remains functional.
"""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QPainter

from typing import Any, Dict, List, Optional, Union

try:
    from PySide6.QtCharts import (
        QChart, QChartView,
        QBarSeries, QBarSet,
        QLineSeries, QPieSeries,
        QValueAxis, QBarCategoryAxis,
    )
    _HAS_CHARTS = True
except ImportError:
    _HAS_CHARTS = False


__all__ = [
    "build_pareto_chart",
    "build_monthly_chart",
    "build_status_trend_chart",
    "build_category_pie",
    "build_confidence_distribution_chart",
    "build_status_distribution_chart",
    "no_chart_label",
]


# ── Per-category accent colours ───────────────────────────────────────────────

_CAT_COLORS: dict[str, str] = {
    "Dimensional":              "#3E9BFF",
    "Dimensional/Tolerancing":  "#3E9BFF",
    "Structural":               "#A78BFA",
    "Structural/Civil":         "#10B981",
    "Electrical":               "#FBBF24",
    "Electrical/Instrumentation":"#F59E0B",
    "Material":                 "#2DD4BF",
    "Safety/HSE":               "#EF4444",
    "Documentation":            "#A6A9B1",
    "General/Administrative":   "#6B7280",
    "Uncategorized":            "#9CA3AF",
    "Other":                    "#94A3B8",
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _is_dark_theme() -> bool:
    """Detect whether dark theme is currently active in the application."""
    app = QApplication.instance()
    if not app:
        return True
    ss = getattr(app, "styleSheet", lambda: "")() or ""
    if "background-color: #FFFFFF" in ss or "background-color: #ffffff" in ss:
        return False
    pal = app.palette()
    win_col = pal.color(pal.ColorRole.Window)
    return win_col.lightness() < 128


def _styled_chart(title: str = "") -> "QChart":
    """Return a QChart dynamically styled for the active dark or light theme."""
    chart = QChart()
    chart.setTitle(title)
    dark = _is_dark_theme()
    bg_chart = QColor("#2D2F34") if dark else QColor("#FFFFFF")
    bg_plot  = QColor("#26272B") if dark else QColor("#F5F6F8")
    fg_title = QColor("#F2F3F5") if dark else QColor("#1B1D21")
    fg_text  = QColor("#A6A9B1") if dark else QColor("#5B5F6A")

    chart.setBackgroundBrush(bg_chart)
    chart.setPlotAreaBackgroundBrush(bg_plot)
    chart.setPlotAreaBackgroundVisible(True)
    chart.legend().setLabelColor(fg_text)
    chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
    if title:
        chart.setTitleBrush(fg_title)
        chart.setTitleFont(
            QFont("Segoe UI Variable", 13, QFont.Weight.DemiBold)
        )
    chart.setAnimationOptions(QChart.AnimationOption.AllAnimations)
    chart.setAnimationDuration(600)
    return chart


def _chart_view(chart: "QChart") -> "QChartView":
    """Wrap a QChart in a transparent, antialiased QChartView."""
    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setStyleSheet("background: transparent; border:none;")
    return view


def _axis_style(axis, color: Optional[str] = None) -> None:
    """Apply consistent axis label, title and grid-line styling adhering to theme."""
    dark = _is_dark_theme()
    lbl_color = color or ("#A6A9B1" if dark else "#5B5F6A")
    grid_color = "#3A3C42" if dark else "#E2E4E8"
    axis.setLabelsColor(QColor(lbl_color))
    axis.setGridLineColor(QColor(grid_color))
    axis.setLabelsFont(QFont("Segoe UI", 10))
    axis.setTitleBrush(QColor(lbl_color))
    axis.setTitleFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))


def _make_integer_value_axis(max_val: int) -> "QValueAxis":
    """Create a QValueAxis with strict integer tick marks, preventing fractional tick alignment."""
    import math
    ax = QValueAxis()
    int_max = max(int(max_val), 1)
    if int_max <= 10:
        ax.setRange(0, int_max)
        ax.setTickCount(int_max + 1)
    else:
        step = max(1, math.ceil(int_max / 5.0))
        y_max = step * 5
        ax.setRange(0, y_max)
        ax.setTickCount(6)
    ax.setLabelFormat("%d")
    _axis_style(ax)
    return ax


# ── Public chart builders ─────────────────────────────────────────────────────

def no_chart_label(text: str) -> QFrame:
    """
    Return a placeholder card shown when QtCharts is not installed.

    Parameters
    ----------
    text:
        Short description of the missing chart (e.g. ``"Pareto Chart"``).
    """
    f = QFrame()
    f.setObjectName("Card")
    lay = QVBoxLayout(f)
    lbl = QLabel(f"📊  {text}\n(PySide6.QtCharts not available)")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet("color:#A6A9B1; font-size:14px;")
    lay.addWidget(lbl)
    return f


def build_pareto_chart(
    data: Optional[Union[List[Any], Dict[str, Any]]] = None,
    title: str = "Pareto — Comments by Category",
    total: Optional[int] = None,
    reference_line: Optional[float] = 80.0,
) -> "QChartView | QFrame":
    """
    Build a Pareto chart: bars for category counts plus a cumulative-% line.

    Parameters
    ----------
    data:
        Either a list of CategoryDistributionDTO objects, a list of dicts,
        or a dict containing 'categories', 'counts' and optional 'cumulative'.
    title:
        Custom title for the Pareto chart.
    total:
        Size of the FULL population the bars were drawn from. Required when
        ``data`` is a truncated top-N slice, otherwise the cumulative line would
        be measured against the visible bars only and reach 100% too early.
        Items that already carry ``cumulative_percentage`` take precedence.
    reference_line:
        Percentage at which to draw a dashed reference line on the right-hand
        axis, or None to leave it out.

    Returns
    -------
    QChartView | QFrame
        QChartView if QtCharts is available, fallback QFrame otherwise.
    """
    if not _HAS_CHARTS:
        return no_chart_label(title)

    chart = _styled_chart(title)

    cats: List[str] = []
    counts: List[int] = []
    provided: List[Optional[float]] = []

    if isinstance(data, list) and data:
        for item in data:
            c_name = (
                getattr(item, "category_name", None)
                or (item.get("category_name") if isinstance(item, dict) else str(item))
            )
            c_count = (
                getattr(item, "count", 0)
                if hasattr(item, "count")
                else (item.get("count", 0) if isinstance(item, dict) else 0)
            )
            c_cum = getattr(item, "cumulative_percentage", None)
            if c_cum is None and isinstance(item, dict):
                c_cum = item.get("cumulative_percentage")
            cats.append(str(c_name))
            counts.append(int(c_count))
            provided.append(float(c_cum) if c_cum is not None else None)

    elif isinstance(data, dict) and data:
        if "categories" in data and "counts" in data:
            cats = [str(c) for c in data["categories"]]
            counts = [int(v) for v in data["counts"]]
            provided = [float(v) for v in data.get("cumulative", [])]
        else:
            for k, v in data.items():
                cats.append(str(k))
                counts.append(int(v))

    if not cats or not counts or sum(counts) == 0:
        cats, counts, provided = ["No Data"], [0], [None]

    if total is None:
        total = sum(counts)
    if len(provided) != len(cats) or any(p is None for p in provided):
        running = 0.0
        provided = []
        for c in counts:
            running += c
            provided.append((running / total * 100.0) if total > 0 else 0.0)
    cumuls = [float(p) for p in provided]

    bar_set = QBarSet("Comments")
    bar_set.setColor(QColor("#3E9BFF"))
    bar_set.setBorderColor(QColor("#60A5FA"))
    for v in counts:
        bar_set.append(v)

    bar_series = QBarSeries()
    bar_series.append(bar_set)
    chart.addSeries(bar_series)

    max_count = max(counts) if max(counts) > 0 else 10
    ax_val = _make_integer_value_axis(max_count)
    ax_val.setTitleText("Comments")

    # The cumulative line is a percentage, so it gets its own 0–100 axis on the
    # right instead of being rescaled onto the count axis.
    ax_pct = QValueAxis()
    ax_pct.setRange(0, 100)
    ax_pct.setTickCount(6)
    ax_pct.setLabelFormat("%d%%")
    ax_pct.setTitleText("Cumulative %")
    _axis_style(ax_pct)

    line_series = QLineSeries()
    line_series.setName("Cumulative %")
    line_series.setColor(QColor("#FBBF24"))
    line_series.setPointsVisible(True)
    pen = line_series.pen()
    pen.setWidth(2)
    line_series.setPen(pen)
    for i, pct in enumerate(cumuls):
        line_series.append(i, pct)
    chart.addSeries(line_series)

    ax_cat = QBarCategoryAxis()
    ax_cat.append(cats)
    ax_cat.setTitleText("Category")
    _axis_style(ax_cat)
    if any(len(c) > 10 for c in cats) or len(cats) > 5:
        ax_cat.setLabelsAngle(-25)
    chart.addAxis(ax_cat, Qt.AlignmentFlag.AlignBottom)
    bar_series.attachAxis(ax_cat)

    chart.addAxis(ax_val, Qt.AlignmentFlag.AlignLeft)
    bar_series.attachAxis(ax_val)

    chart.addAxis(ax_pct, Qt.AlignmentFlag.AlignRight)
    line_series.attachAxis(ax_cat)
    line_series.attachAxis(ax_pct)

    if reference_line is not None:
        ref_series = QLineSeries()
        ref_series.setName(f"{reference_line:.0f}% reference")
        ref_pen = ref_series.pen()
        ref_pen.setStyle(Qt.PenStyle.DashLine)
        ref_pen.setWidth(1)
        ref_pen.setColor(QColor("#A6A9B1"))
        ref_series.setPen(ref_pen)
        ref_series.append(0, float(reference_line))
        ref_series.append(max(len(cats) - 1, 0), float(reference_line))
        chart.addSeries(ref_series)
        ref_series.attachAxis(ax_cat)
        ref_series.attachAxis(ax_pct)

    chart.legend().setVisible(True)
    chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)

    return _chart_view(chart)


def build_monthly_chart(
    data: Optional[Union[List[Any], Dict[str, Any]]] = None,
    title: str = "Comment Timeline (by Creation Date)",
) -> "QChartView | QFrame":
    """
    Build a comment creation timeline chart.

    Parameters
    ----------
    data:
        Either a list of TrendDataPointDTO objects (period_label, count),
        a dictionary with 'months', 'comments', 'approved' lists,
        or a date/label to count dict.
    title:
        Custom title for the timeline chart.

    Returns
    -------
    QChartView | QFrame
    """
    if not _HAS_CHARTS:
        return no_chart_label(title)

    chart = _styled_chart(title)

    if isinstance(data, list) and data:
        labels = [
            getattr(d, "period_label", None)
            or (d.get("period_label") if isinstance(d, dict) else str(d))
            for d in data
        ]
        counts = [
            getattr(d, "count", 0)
            if hasattr(d, "count")
            else (d.get("count", 0) if isinstance(d, dict) else 0)
            for d in data
        ]

        series = QLineSeries()
        series.setName("Comments")
        series.setColor(QColor("#3E9BFF"))
        series.setPointsVisible(True)
        pen = series.pen()
        pen.setWidth(2)
        series.setPen(pen)
        for i, v in enumerate(counts):
            series.append(i, v)
        chart.addSeries(series)

        max_val = max(counts) if counts and max(counts) > 0 else 10

        ax_cat = QBarCategoryAxis()
        ax_cat.append(labels if labels else ["No Data"])
        _axis_style(ax_cat)
        chart.addAxis(ax_cat, Qt.AlignmentFlag.AlignBottom)

        ax_val = _make_integer_value_axis(max_val)
        chart.addAxis(ax_val, Qt.AlignmentFlag.AlignLeft)

        series.attachAxis(ax_cat)
        series.attachAxis(ax_val)

    elif isinstance(data, dict) and data:
        if "months" in data:
            months = data.get("months", [])
            total = data.get("comments", [])
            approved = data.get("approved", [])

            for s_data, color, name in [
                (total,    "#3E9BFF", "Total"),
                (approved, "#4ADE80", "Approved"),
            ]:
                if s_data:
                    series = QLineSeries()
                    series.setName(name)
                    series.setColor(QColor(color))
                    pen = series.pen()
                    pen.setWidth(2)
                    series.setPen(pen)
                    for i, v in enumerate(s_data):
                        series.append(i, v)
                    chart.addSeries(series)

            max_val = max(total) if total and max(total) > 0 else 10

            ax_cat = QBarCategoryAxis()
            ax_cat.append(months if months else ["No Data"])
            _axis_style(ax_cat)
            chart.addAxis(ax_cat, Qt.AlignmentFlag.AlignBottom)

            ax_val = _make_integer_value_axis(max_val)
            chart.addAxis(ax_val, Qt.AlignmentFlag.AlignLeft)

            for s in chart.series():
                s.attachAxis(ax_cat)
                s.attachAxis(ax_val)
        else:
            labels = list(data.keys())
            counts = [int(v) for v in data.values()]
            series = QLineSeries()
            series.setName("Comments")
            series.setColor(QColor("#3E9BFF"))
            pen = series.pen()
            pen.setWidth(2)
            series.setPen(pen)
            for i, v in enumerate(counts):
                series.append(i, v)
            chart.addSeries(series)

            max_val = max(counts) if counts and max(counts) > 0 else 10

            ax_cat = QBarCategoryAxis()
            ax_cat.append(labels if labels else ["No Data"])
            _axis_style(ax_cat)
            chart.addAxis(ax_cat, Qt.AlignmentFlag.AlignBottom)

            ax_val = _make_integer_value_axis(max_val)
            chart.addAxis(ax_val, Qt.AlignmentFlag.AlignLeft)

            series.attachAxis(ax_cat)
            series.attachAxis(ax_val)

    else:
        # Default / Empty state
        labels = ["No Data"]
        series = QLineSeries()
        series.setName("Comments")
        series.setColor(QColor("#3E9BFF"))
        series.append(0, 0)
        chart.addSeries(series)

        ax_cat = QBarCategoryAxis()
        ax_cat.append(labels)
        _axis_style(ax_cat)
        chart.addAxis(ax_cat, Qt.AlignmentFlag.AlignBottom)

        ax_val = QValueAxis()
        ax_val.setRange(0, 10)
        ax_val.setLabelFormat("%d")
        _axis_style(ax_val)
        chart.addAxis(ax_val, Qt.AlignmentFlag.AlignLeft)

        series.attachAxis(ax_cat)
        series.attachAxis(ax_val)

    return _chart_view(chart)


build_status_trend_chart = build_monthly_chart


def build_category_pie(
    data: Optional[Union[List[Any], Dict[str, Any]]] = None,
    title: str = "Category Distribution",
) -> "QChartView | QFrame":
    """
    Build a category distribution donut chart.

    Parameters
    ----------
    data:
        Either a list of CategoryDistributionDTO objects (category_name, count, color_hex),
        or a dict mapping category name to count.
    title:
        Custom title for the category donut chart.

    Returns
    -------
    QChartView | QFrame
    """
    if not _HAS_CHARTS:
        return no_chart_label(title)

    chart = _styled_chart(title)
    chart.legend().setAlignment(Qt.AlignmentFlag.AlignRight)
    chart.legend().setFont(QFont("Segoe UI", 9))

    series = QPieSeries()
    series.setHoleSize(0.45)   # donut style

    has_slices = False

    raw_items: List[tuple[str, int, str]] = []
    if isinstance(data, list) and data:
        for item in data:
            cat_name = (
                getattr(item, "category_name", None)
                or (item.get("category_name") if isinstance(item, dict) else str(item))
            )
            count = (
                getattr(item, "count", 0)
                if hasattr(item, "count")
                else (item.get("count", 0) if isinstance(item, dict) else 0)
            )
            color = (
                getattr(item, "color_hex", None)
                or (item.get("color_hex") if isinstance(item, dict) else None)
                or _CAT_COLORS.get(cat_name, "#A6A9B1")
            )
            if count > 0:
                raw_items.append((str(cat_name), int(count), str(color)))
    elif isinstance(data, dict) and data:
        for cat, count in data.items():
            if count > 0:
                raw_items.append((str(cat), int(count), _CAT_COLORS.get(cat, "#A6A9B1")))

    total_count = sum(cnt for _, cnt, _ in raw_items)

    for cat_name, count, color in raw_items:
        has_slices = True
        pct = (count / total_count * 100.0) if total_count > 0 else 0.0
        slice_ = series.append(f"{cat_name}: {count} ({pct:.1f}%)", count)
        slice_.setColor(QColor(color))
        slice_.setLabelColor(QColor("#F2F3F5") if _is_dark_theme() else QColor("#1B1D21"))
        slice_.setLabelFont(QFont("Segoe UI", 10))

    if not has_slices:
        slice_ = series.append("No Data", 1)
        slice_.setColor(QColor("#4A4D55") if _is_dark_theme() else QColor("#E2E4E8"))
        slice_.setLabelColor(QColor("#A6A9B1") if _is_dark_theme() else QColor("#5B5F6A"))
        slice_.setLabelFont(QFont("Segoe UI", 10))

    chart.addSeries(series)
    return _chart_view(chart)


def build_confidence_distribution_chart(
    data: Optional[Union[List[Any], Dict[str, Any]]] = None,
    title: str = "Confidence Distribution",
) -> "QChartView | QFrame":
    """
    Build a confidence distribution bar chart (0.0-0.2, 0.2-0.4, ..., 0.8-1.0).
    """
    if not _HAS_CHARTS:
        return no_chart_label(title)

    chart = _styled_chart(title)
    chart.legend().hide()

    labels = ["0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"]
    counts = [0, 0, 0, 0, 0]

    if isinstance(data, list) and data:
        for item in data:
            lbl = getattr(item, "range_label", None) or (item.get("range_label") if isinstance(item, dict) else "")
            cnt = getattr(item, "count", 0) if hasattr(item, "count") else (item.get("count", 0) if isinstance(item, dict) else 0)
            if lbl in labels:
                counts[labels.index(lbl)] = int(cnt)
    elif isinstance(data, dict) and data:
        for lbl, cnt in data.items():
            if lbl in labels:
                counts[labels.index(lbl)] = int(cnt)

    bar_set = QBarSet("Comments")
    bar_set.setColor(QColor("#8B5CF6"))
    bar_set.setBorderColor(QColor("#A78BFA"))
    for v in counts:
        bar_set.append(v)

    bar_series = QBarSeries()
    bar_series.append(bar_set)
    chart.addSeries(bar_series)

    ax_cat = QBarCategoryAxis()
    ax_cat.append(labels)
    _axis_style(ax_cat)
    chart.addAxis(ax_cat, Qt.AlignmentFlag.AlignBottom)
    bar_series.attachAxis(ax_cat)

    max_count = max(counts) if max(counts) > 0 else 10
    ax_val = _make_integer_value_axis(max_count)
    chart.addAxis(ax_val, Qt.AlignmentFlag.AlignLeft)
    bar_series.attachAxis(ax_val)

    return _chart_view(chart)


def build_status_distribution_chart(
    data: Optional[Union[List[Any], Dict[str, Any]]] = None,
    title: str = "Status Distribution",
) -> "QChartView | QFrame":
    """
    Build a status distribution donut chart (Pending, Approved, Rejected, Flagged).
    """
    if not _HAS_CHARTS:
        return no_chart_label(title)

    chart = _styled_chart(title)
    chart.legend().setAlignment(Qt.AlignmentFlag.AlignRight)
    chart.legend().setFont(QFont("Segoe UI", 9))

    series = QPieSeries()
    series.setHoleSize(0.45)

    status_colors = {
        "Pending": "#60A5FA",
        "Approved": "#4ADE80",
        "Rejected": "#F87171",
        "Flagged": "#FBBF24",
    }

    counts: Dict[str, int] = {"Pending": 0, "Approved": 0, "Rejected": 0, "Flagged": 0}
    if isinstance(data, dict):
        for k, v in data.items():
            cap_k = k.capitalize() if isinstance(k, str) else str(k)
            if cap_k in counts:
                counts[cap_k] = int(v)
    elif isinstance(data, list):
        for item in data:
            st = getattr(item, "status", None) or (item.get("status") if isinstance(item, dict) else str(item))
            cnt = getattr(item, "count", 0) if hasattr(item, "count") else (item.get("count", 0) if isinstance(item, dict) else 0)
            cap_st = str(st).capitalize()
            if cap_st in counts:
                counts[cap_st] = int(cnt)

    total = sum(counts.values())
    has_slices = False

    for st_name in ["Pending", "Approved", "Rejected", "Flagged"]:
        cnt = counts[st_name]
        if cnt > 0:
            has_slices = True
            pct = (cnt / total * 100.0) if total > 0 else 0.0
            slice_ = series.append(f"{st_name}: {cnt} ({pct:.1f}%)", cnt)
            slice_.setColor(QColor(status_colors.get(st_name, "#9CA3AF")))
            slice_.setLabelColor(QColor("#F2F3F5") if _is_dark_theme() else QColor("#1B1D21"))
            slice_.setLabelFont(QFont("Segoe UI", 10))

    if not has_slices:
        slice_ = series.append("No Data", 1)
        slice_.setColor(QColor("#4A4D55") if _is_dark_theme() else QColor("#E2E4E8"))
        slice_.setLabelColor(QColor("#A6A9B1") if _is_dark_theme() else QColor("#5B5F6A"))
        slice_.setLabelFont(QFont("Segoe UI", 10))

    chart.addSeries(series)
    return _chart_view(chart)
