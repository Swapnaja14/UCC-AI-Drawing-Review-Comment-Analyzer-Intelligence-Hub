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
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
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

def _styled_chart(title: str = "") -> "QChart":
    from app.theme import CURRENT_THEME, THEMES
    t = THEMES[CURRENT_THEME]
    chart = QChart()
    chart.setTitle(title)
    chart.setBackgroundBrush(QColor(t['bg_elevated']))
    chart.setPlotAreaBackgroundBrush(QColor(t['bg_secondary']))
    chart.setPlotAreaBackgroundVisible(True)
    chart.legend().setLabelColor(QColor(t['text_secondary']))
    chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
    if title:
        chart.setTitleBrush(QColor(t['text_primary']))
        chart.setTitleFont(
            QFont("Segoe UI Variable", 13, QFont.Weight.DemiBold)
        )
    chart.setAnimationOptions(QChart.AnimationOption.AllAnimations)
    chart.setAnimationDuration(600)
    return chart


def _chart_view(chart: "QChart") -> "QChartView":
    from app.theme import CURRENT_THEME, THEMES
    t = THEMES[CURRENT_THEME]
    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setStyleSheet(f"background: {t['bg_elevated']}; border:none; border-radius: 12px;")
    return view


def _axis_style(axis) -> None:
    from app.theme import CURRENT_THEME, THEMES
    t = THEMES[CURRENT_THEME]
    axis.setLabelsColor(QColor(t['text_secondary']))
    axis.setGridLineColor(QColor(t['border']))
    axis.setLabelsFont(QFont("Segoe UI", 10))


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
    lbl.setObjectName("SubCaption")
    lay.addWidget(lbl)
    return f



def build_pareto_chart(
    data: Optional[Union[List[Any], Dict[str, Any]]] = None
) -> "QChartView | QFrame":
    """
    Build a Pareto chart: bar series for category counts with a
    cumulative-percentage line overlay.

    Parameters
    ----------
    data:
        Either a list of CategoryDistributionDTO objects, a list of dicts,
        or a dict containing 'categories', 'counts', and optional 'cumulative' keys.

    Returns
    -------
    QChartView | QFrame
        QChartView if QtCharts is available, fallback QFrame otherwise.
    """
    if not _HAS_CHARTS:
        return no_chart_label("Pareto Chart")

    chart = _styled_chart("Pareto — Comments by Category")
    chart.legend().hide()

    cats: List[str] = []
    counts: List[int] = []
    cumuls: List[float] = []

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
            cats.append(str(c_name))
            counts.append(int(c_count))

        total = sum(counts)
        running = 0.0
        for c in counts:
            running += c
            cumuls.append((running / total * 100.0) if total > 0 else 0.0)

    elif isinstance(data, dict) and data:
        if "categories" in data and "counts" in data:
            cats = [str(c) for c in data["categories"]]
            counts = [int(v) for v in data["counts"]]
            cumuls = [float(v) for v in data.get("cumulative", [])]
            if not cumuls and sum(counts) > 0:
                total = sum(counts)
                running = 0.0
                for c in counts:
                    running += c
                    cumuls.append(running / total * 100.0)
        else:
            for k, v in data.items():
                cats.append(str(k))
                counts.append(int(v))
            total = sum(counts)
            running = 0.0
            for c in counts:
                running += c
                cumuls.append((running / total * 100.0) if total > 0 else 0.0)

    if not cats or not counts or sum(counts) == 0:
        cats = ["No Data"]
        counts = [0]
        cumuls = [0.0]

    bar_set = QBarSet("Count")
    bar_set.setColor(QColor("#3E9BFF"))
    bar_set.setBorderColor(QColor("#60A5FA"))
    for v in counts:
        bar_set.append(v)

    bar_series = QBarSeries()
    bar_series.append(bar_set)
    chart.addSeries(bar_series)

    max_count = max(counts) if max(counts) > 0 else 10

    line_series = QLineSeries()
    line_series.setName("Cumulative %")
    line_series.setColor(QColor("#FBBF24"))
    pen = line_series.pen()
    pen.setWidth(2)
    line_series.setPen(pen)
    for i, pct in enumerate(cumuls):
        line_series.append(i + 0.5, pct * max_count / 100.0)
    chart.addSeries(line_series)

    ax_cat = QBarCategoryAxis()
    ax_cat.append(cats)
    _axis_style(ax_cat)
    chart.addAxis(ax_cat, Qt.AlignmentFlag.AlignBottom)
    bar_series.attachAxis(ax_cat)

    ax_val = QValueAxis()
    ax_val.setRange(0, max_count * 1.15)
    ax_val.setLabelFormat("%d")
    _axis_style(ax_val)
    chart.addAxis(ax_val, Qt.AlignmentFlag.AlignLeft)
    bar_series.attachAxis(ax_val)
    line_series.attachAxis(ax_cat)
    line_series.attachAxis(ax_val)

    return _chart_view(chart)


def build_monthly_chart(
    data: Optional[Union[List[Any], Dict[str, Any]]] = None
) -> "QChartView | QFrame":
    """
    Build a comment trend line chart.

    Parameters
    ----------
    data:
        Either a list of TrendDataPointDTO objects (period_label, count),
        a dictionary with 'months', 'comments', 'approved' lists,
        or a date/label to count dict.

    Returns
    -------
    QChartView | QFrame
    """
    if not _HAS_CHARTS:
        return no_chart_label("Comment Trend")

    chart = _styled_chart("Comment Trend Over Time")

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

        ax_val = QValueAxis()
        ax_val.setRange(0, max_val * 1.15)
        ax_val.setLabelFormat("%d")
        _axis_style(ax_val)
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

            ax_val = QValueAxis()
            ax_val.setRange(0, max_val * 1.15)
            ax_val.setLabelFormat("%d")
            _axis_style(ax_val)
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

            ax_val = QValueAxis()
            ax_val.setRange(0, max_val * 1.15)
            ax_val.setLabelFormat("%d")
            _axis_style(ax_val)
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
    data: Optional[Union[List[Any], Dict[str, Any]]] = None
) -> "QChartView | QFrame":
    """
    Build a category distribution donut chart.

    Parameters
    ----------
    data:
        Either a list of CategoryDistributionDTO objects (category_name, count, color_hex),
        or a dict mapping category name to count.

    Returns
    -------
    QChartView | QFrame
    """
    if not _HAS_CHARTS:
        return no_chart_label("Category Distribution")

    chart = _styled_chart("Category Distribution")
    chart.legend().setAlignment(Qt.AlignmentFlag.AlignRight)

    series = QPieSeries()
    series.setHoleSize(0.45)   # donut style

    has_slices = False

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
                has_slices = True
                slice_ = series.append(f"{cat_name} ({count})", count)
                slice_.setColor(QColor(color))
                from app.theme import THEMES, CURRENT_THEME; slice_.setLabelColor(QColor(THEMES[CURRENT_THEME]['text_primary']))
                slice_.setLabelFont(QFont("Segoe UI", 10))

    elif isinstance(data, dict) and data:
        for cat, count in data.items():
            if count > 0:
                has_slices = True
                slice_ = series.append(f"{cat} ({count})", count)
                slice_.setColor(QColor(_CAT_COLORS.get(cat, "#A6A9B1")))
                from app.theme import THEMES, CURRENT_THEME; slice_.setLabelColor(QColor(THEMES[CURRENT_THEME]['text_primary']))
                slice_.setLabelFont(QFont("Segoe UI", 10))

    if not has_slices:
        slice_ = series.append("No Data", 1)
        from app.theme import THEMES, CURRENT_THEME; slice_.setColor(QColor(THEMES[CURRENT_THEME]['bg_hover']))
        from app.theme import THEMES, CURRENT_THEME; slice_.setLabelColor(QColor(THEMES[CURRENT_THEME]['text_secondary']))
        slice_.setLabelFont(QFont("Segoe UI", 10))

    chart.addSeries(series)
    return _chart_view(chart)

