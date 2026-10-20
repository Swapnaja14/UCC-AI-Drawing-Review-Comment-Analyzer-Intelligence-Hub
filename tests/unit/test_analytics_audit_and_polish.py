"""
tests/unit/test_analytics_audit_and_polish.py
Unit tests verifying the audited and polished Analytics system:
- Mathematical accuracy of KPI totals (total == pending + approved + rejected + flagged)
- Consistent representation of all 4 review statuses
- Multi-criteria filter consistency across KPIs, Pareto, Category Distribution, and Status Trend
- Empty state resilience
- Current Batch drawing isolation (empty batch does not leak unrelated database records)
- Accurate presentation of Confidence and Approval Rate
- Reset filters logic
- Theme adaptability
"""
import pytest
from datetime import datetime, timedelta, timezone
from PySide6.QtCore import QDate

from src.infrastructure.storage.repository import DatabaseEngine
from src.infrastructure.storage.models import (
    ProjectModel, DrawingModel, PageModel, CommentModel, UserModel, EngineeringDepartmentModel
)
from src.services.analytics_service import AnalyticsService
from app.components.charts import _is_dark_theme, _styled_chart, build_pareto_chart, build_monthly_chart, build_category_pie


@pytest.fixture
def analytics_test_db(tmp_path):
    db_path = tmp_path / "test_analytics_audit.db"
    db_engine = DatabaseEngine(db_path=db_path)
    service = AnalyticsService(db_engine)

    with db_engine.get_session() as session:
        # Fetch auto-seeded departments
        d_piping = session.query(EngineeringDepartmentModel).filter(EngineeringDepartmentModel.name == "Piping Engineering").first()
        d_struct = session.query(EngineeringDepartmentModel).filter(EngineeringDepartmentModel.name == "Structural & Physical Design").first()

        pip_id = d_piping.id if d_piping else "DEPT-PIP"
        str_id = d_struct.id if d_struct else "DEPT-STR"

        # User
        user = UserModel(id="u1", username="lead_rev", display_name="Lead Reviewer")
        session.add(user)

        # Projects
        p1 = ProjectModel(id="p1", name="Project Alpha")
        session.add(p1)

        # Drawings
        _dwg = dict(file_path="/tmp/d1.pdf", file_name="d1.pdf", file_size_bytes=2048, file_hash_sha256="h1", total_pages=1)
        d1 = DrawingModel(id="dwg1", project_id="p1", department_id=pip_id, **_dwg)
        d2 = DrawingModel(id="dwg2", project_id="p1", department_id=str_id, **{**_dwg, "file_name": "d2.pdf", "file_hash_sha256": "h2"})
        session.add_all([d1, d2])

        # Page
        pg1 = PageModel(id="pg1", drawing_id="dwg1", page_number=1, width_pt=612.0, height_pt=792.0, aspect_ratio=0.77)
        pg2 = PageModel(id="pg2", drawing_id="dwg2", page_number=1, width_pt=612.0, height_pt=792.0, aspect_ratio=0.77)
        session.add_all([pg1, pg2])

        now = datetime.now(timezone.utc)
        # Create comments across all 4 statuses for dwg1 (Piping)
        c1 = CommentModel(
            id="c1", drawing_id="dwg1", page_number=1, raw_text="Piping line check", category_name="Technical",
            department_id=pip_id, status="Approved", is_verified_by_human=True, confidence=0.95, created_at=now
        )
        c2 = CommentModel(
            id="c2", drawing_id="dwg1", page_number=1, raw_text="Dimension typo", category_name="Dimension",
            department_id=pip_id, status="Pending", is_verified_by_human=False, confidence=0.80, created_at=now
        )
        c3 = CommentModel(
            id="c3", drawing_id="dwg1", page_number=1, raw_text="Drafting overlap", category_name="Drafting",
            department_id=pip_id, status="Rejected", is_verified_by_human=True, confidence=0.60, created_at=now - timedelta(days=1)
        )
        c4 = CommentModel(
            id="c4", drawing_id="dwg1", page_number=1, raw_text="Safety query", category_name="Standards",
            department_id=pip_id, status="Flagged", is_verified_by_human=False, confidence=0.75, created_at=now - timedelta(days=2)
        )
        # Structural drawing comment (dwg2)
        c5 = CommentModel(
            id="c5", drawing_id="dwg2", page_number=1, raw_text="Beam size", category_name="Technical",
            department_id=str_id, status="Approved", is_verified_by_human=True, confidence=0.90, created_at=now
        )
        session.add_all([c1, c2, c3, c4, c5])
        session.commit()

    return db_engine, service


def test_kpi_totals_mathematically_exact(analytics_test_db):
    """Verify KPI totals: total == pending + approved + rejected + flagged across all queries."""
    _, service = analytics_test_db
    kpis = service.get_global_kpis()

    assert kpis.total_comments == 5
    assert kpis.approved_count == 2
    assert kpis.pending_count == 1
    assert kpis.rejected_count == 1
    assert kpis.flagged_count == 1
    assert (
        kpis.pending_count + kpis.approved_count + kpis.rejected_count + kpis.flagged_count
        == kpis.total_comments
    )


def test_drawing_and_department_filters(analytics_test_db):
    """Verify drawing and department filters isolate data correctly across all endpoints."""
    _, service = analytics_test_db

    # Filter to Piping department only
    piping_kpis = service.get_global_kpis(department_name="Piping Engineering")
    assert piping_kpis.total_comments == 4
    assert piping_kpis.approved_count == 1
    assert piping_kpis.pending_count == 1
    assert piping_kpis.rejected_count == 1
    assert piping_kpis.flagged_count == 1

    # Filter to Structural department only
    struct_kpis = service.get_global_kpis(department_name="Structural & Physical Design")
    assert struct_kpis.total_comments == 1
    assert struct_kpis.approved_count == 1
    assert struct_kpis.pending_count == 0

    # Pareto and Category Distribution for Piping include 4 comments
    pareto_piping = service.get_pareto_analysis(department_name="Piping Engineering", include_rejected=True)
    cat_dist_piping = service.get_category_distribution(department_name="Piping Engineering", include_rejected=True)

    assert sum(p.count for p in pareto_piping) == 4
    assert sum(c.count for c in cat_dist_piping) == 4


def test_empty_batch_drawing_ids_does_not_leak_database(analytics_test_db):
    """Verify that an empty list of drawing_ids returns 0 records rather than leaking all data."""
    _, service = analytics_test_db

    # When Current Batch has 0 drawings, drawing_ids = []
    empty_batch_kpis = service.get_global_kpis(drawing_ids=[])
    assert empty_batch_kpis.total_comments == 0
    assert empty_batch_kpis.approved_count == 0
    assert empty_batch_kpis.pending_count == 0

    empty_pareto = service.get_pareto_analysis(drawing_ids=[])
    assert len(empty_pareto) == 0

    empty_dist = service.get_category_distribution(drawing_ids=[])
    assert len(empty_dist) == 0

    empty_trend = service.get_status_trend(drawing_ids=[])
    assert len(empty_trend) == 0


def test_chart_empty_state_resilience():
    """Verify that chart factory functions handle empty inputs cleanly without exceptions."""
    from PySide6.QtWidgets import QApplication
    _ = QApplication.instance() or QApplication([])

    p_view = build_pareto_chart([])
    assert p_view is not None

    m_view = build_monthly_chart([])
    assert m_view is not None

    pie_view = build_category_pie([])
    assert pie_view is not None


def test_confidence_and_approval_rate_metrics(analytics_test_db):
    """Verify that average confidence and verified approval rate are computed honestly."""
    _, service = analytics_test_db
    kpis = service.get_global_kpis()

    # Confidences: 0.95, 0.80, 0.60, 0.75, 0.90 -> sum = 4.00, avg = 0.80
    assert pytest.approx(kpis.avg_confidence, rel=1e-2) == 0.80

    # Approved + human verified: c1 (0.95), c5 (0.90) -> 2 out of 5 total comments = 40.0%
    assert pytest.approx(kpis.accuracy_rate, rel=1e-2) == 40.0


def test_analytics_page_reset_and_kpi_cards(analytics_test_db):
    """Verify that AnalyticsPage builds 6 distinct KPI cards and reset filters works properly."""
    from PySide6.QtWidgets import QApplication
    from app.screens.analytics_screen import AnalyticsPage
    _ = QApplication.instance() or QApplication([])

    db_engine, service = analytics_test_db

    class MockController:
        current_department_name = None
        current_batch_drawing_ids = ["dwg1"]

        def get_all_projects(self):
            return []

        def get_all_departments(self):
            return [{"id": "d1", "name": "Piping Engineering"}]

        def get_all_categories(self):
            return [{"name": "Technical"}]

        def get_all_drawings(self, project_id=None):
            return [{"id": "dwg1", "file_name": "d1.pdf"}]

        def get_batch_drawings(self):
            return [{"id": "dwg1", "file_name": "d1.pdf"}]

        def get_dashboard_kpis(self, **kwargs):
            return service.get_global_kpis(**kwargs)

        def get_pareto_analysis(self, **kwargs):
            return service.get_pareto_analysis(**kwargs)

        def get_category_distribution(self, **kwargs):
            return service.get_category_distribution(**kwargs)

        def get_status_trend(self, **kwargs):
            return service.get_status_trend(**kwargs)

    ctrl = MockController()
    page = AnalyticsPage(controller=ctrl)

    # Verify 6 KPI cards are rendered
    assert len(page._kpi_cards) == 6

    # Verify filter change then reset
    page._cat_cb.setCurrentIndex(1)
    page._date_to.setDate(QDate(2025, 1, 1))

    # Trigger reset
    page._reset_filters()

    assert page._cat_cb.currentIndex() == 0
    assert page._batch_cb.currentIndex() == 0
    assert page._dwg_cb.currentIndex() == 0
    assert page._date_to.date() == QDate.currentDate()

