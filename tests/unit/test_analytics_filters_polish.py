"""
Tests for A8, A9, A10:
- A8: Date validation (From <= To) and default all-time date
- A9: Debounce timer and project dropdown surfacing
- A10: Refresh button and filter summary text
"""
import pytest
from datetime import datetime, timezone
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from PySide6.QtCore import QDate

from src.infrastructure.storage.repository import DatabaseEngine
from src.infrastructure.storage.models import ProjectModel, DrawingModel, CommentModel
from src.services.analytics_service import AnalyticsService
from app.screens.analytics_screen import AnalyticsPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page_and_controller(qapp, tmp_path):
    db_engine = DatabaseEngine(db_path=tmp_path / "polish.db")
    earliest = datetime(2023, 5, 10, 10, 0, 0, tzinfo=timezone.utc)
    with db_engine.get_session() as session:
        session.add(ProjectModel(id="p1", name="Alpha Project"))
        session.add(DrawingModel(
            id="d1", project_id="p1", file_path="/tmp/d1.pdf",
            file_name="d1.pdf", file_size_bytes=100, file_hash_sha256="h1", total_pages=1
        ))
        session.add(CommentModel(
            id="c1", drawing_id="d1", page_number=1, raw_text="note 1",
            category_name="Technical", status="Pending", created_at=earliest
        ))
        session.commit()

    service = AnalyticsService(db_engine)

    class MockController:
        current_department_name = None
        current_batch_drawing_ids = ["d1"]

        def get_all_projects(self):
            return [{"id": "p1", "name": "Alpha Project"}]

        def get_all_departments(self):
            return []

        def get_department_options(self):
            return {"departments": [], "has_unassigned": False}

        def get_category_options(self):
            return ["Technical"]

        def get_all_categories(self):
            return [{"name": "Technical"}]

        def get_min_comment_date(self):
            return earliest

        def get_drawing_options(self, project_id=None, department_name=None, drawing_ids=None):
            return [{"id": "d1", "file_name": "d1.pdf", "comments_count": 1}]

        def get_dashboard_kpis(self, **kwargs):
            return service.get_global_kpis(**kwargs)

        def get_category_distribution(self, **kwargs):
            return service.get_category_distribution(**kwargs)

        def get_pareto_analysis(self, **kwargs):
            return service.get_pareto_analysis(**kwargs)

        def get_status_trend(self, **kwargs):
            return service.get_status_trend(**kwargs)

    ctrl = MockController()
    p = AnalyticsPage(controller=ctrl)
    p.show()
    return p, ctrl


def test_a8_date_validation_error(page_and_controller):
    page, _ = page_and_controller
    # Set From date later than To date
    page._date_from.setDate(QDate(2026, 12, 31))
    page._date_to.setDate(QDate(2026, 1, 1))

    assert page._validate_date_range() is False
    assert not page._date_err_lbl.isHidden()
    assert "Invalid date range" in page._date_err_lbl.text()

    # Valid range
    page._date_from.setDate(QDate(2026, 1, 1))
    page._date_to.setDate(QDate(2026, 12, 31))
    assert page._validate_date_range() is True
    assert page._date_err_lbl.isHidden()


def test_a8_default_from_date(page_and_controller):
    page, _ = page_and_controller
    default_d = page._get_default_from_date()
    assert default_d == QDate(2023, 5, 10)


def test_a9_project_combo_surfaced_when_projects_exist(page_and_controller):
    page, _ = page_and_controller
    assert not page._proj_cb.isHidden()
    assert page._proj_cb.count() == 2  # All Projects + Alpha Project


def test_a10_refresh_button_and_filter_summary(page_and_controller):
    page, _ = page_and_controller
    page.reload_data()
    # Check filter summary label is updated and not hidden
    assert not page._filter_summary_lbl.isHidden()
    text = page._filter_summary_lbl.text()
    assert "Showing 1 comments" in text

    # Check Refresh button exists
    refresh_btns = [b for b in page.findChildren(QPushButton) if b.text() == "Refresh"]
    assert len(refresh_btns) == 1
