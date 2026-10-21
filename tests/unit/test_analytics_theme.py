"""
Unit tests for A11: ThemeManager integration with analytics charts.
"""
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor

from app.theme import ThemeManager, THEMES
from app.components import charts
from app.components.charts import (
    get_theme_colors,
    build_pareto_chart,
    build_monthly_chart,
    build_category_pie,
)
from app.screens.analytics_screen import AnalyticsPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_no_is_dark_theme_function():
    """Verify that the string-sniffing _is_dark_theme() heuristic is completely deleted."""
    assert not hasattr(charts, "_is_dark_theme"), "_is_dark_theme should be removed from charts.py"


def test_get_theme_colors_defaults_and_overrides(qapp):
    """Verify get_theme_colors respects explicit dict, ThemeManager, and defaults."""
    # Custom colors override
    custom = {"bg_elevated": "#112233", "bg_secondary": "#223344", "text_primary": "#FFFFFF", "text_secondary": "#888888", "border": "#334455"}
    assert get_theme_colors(custom) == custom

    # Singleton ThemeManager
    tm = ThemeManager(qapp)
    tm.apply("dark")
    assert get_theme_colors()["bg_elevated"] == THEMES["dark"]["bg_elevated"]

    tm.apply("light")
    assert get_theme_colors()["bg_elevated"] == THEMES["light"]["bg_elevated"]


def test_chart_builders_accept_theme_colors(qapp):
    """Verify charts accept theme_colors parameter."""
    light_colors = THEMES["light"]
    data = [{"category_name": "Civil", "count": 10, "color_hex": "#3E9BFF"}]

    view = build_pareto_chart(data, theme_colors=light_colors)
    assert view is not None

    timeline = build_monthly_chart(data=[], theme_colors=light_colors)
    assert timeline is not None

    pie = build_category_pie(data, theme_colors=light_colors)
    assert pie is not None


def test_analytics_page_connects_to_theme_changed(qapp):
    """Verify AnalyticsPage connects to theme_manager.theme_changed signal."""
    tm = ThemeManager(qapp)
    reloaded = False

    class MockController:
        current_department_name = None
        current_batch_drawing_ids = []

        def get_all_projects(self):
            return []

        def get_department_options(self):
            return {"departments": [], "has_unassigned": False}

        def get_category_options(self):
            return []

        def get_all_categories(self):
            return []

        def get_min_comment_date(self):
            return None

        def get_drawing_options(self, **kwargs):
            return []

        def get_dashboard_kpis(self, **kwargs):
            return None

        def get_pareto_analysis(self, **kwargs):
            return []

        def get_category_distribution(self, **kwargs):
            return []

        def get_status_trend(self, **kwargs):
            return []

    page = AnalyticsPage(controller=MockController(), theme_manager=tm)

    original_reload = page.reload_data
    call_count = 0

    def mock_reload():
        nonlocal call_count
        call_count += 1
        original_reload()

    page.reload_data = mock_reload

    # Trigger theme change
    tm.theme_changed.emit("light")
    assert call_count == 1
