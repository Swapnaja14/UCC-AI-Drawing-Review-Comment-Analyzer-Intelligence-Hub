"""
Unit tests for A13: Surface existing backend metrics (status donut, confidence chart, reviewer metrics, project analytics).
"""
import pytest
from datetime import datetime, timezone
from PySide6.QtWidgets import QApplication

from src.infrastructure.storage.repository import DatabaseEngine
from src.infrastructure.storage.models import (
    ProjectModel, DrawingModel, CommentModel, UserModel, EngineeringDepartmentModel, AuditLogModel
)
from src.services.analytics_service import AnalyticsService
from app.screens.analytics_screen import AnalyticsPage
from app.controllers.app_controller import AppController


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def a13_db_and_service(tmp_path):
    db_path = tmp_path / "a13_test.db"
    engine = DatabaseEngine(db_path=db_path)
    service = AnalyticsService(engine)

    with engine.get_session() as session:
        # Projects
        p1 = ProjectModel(id="proj_1", name="Project 1")
        p2 = ProjectModel(id="proj_2", name="Project 2")
        session.add_all([p1, p2])

        # Users
        u1 = UserModel(id="u1", username="alice", display_name="Alice Reviewer")
        u2 = UserModel(id="u2", username="bob", display_name="Bob Reviewer")
        session.add_all([u1, u2])

        # Drawings
        d1 = DrawingModel(id="d1", project_id="proj_1", file_path="/tmp/d1.pdf", file_name="d1.pdf",
                          file_size_bytes=100, file_hash_sha256="h1", total_pages=1)
        d2 = DrawingModel(id="d2", project_id="proj_2", file_path="/tmp/d2.pdf", file_name="d2.pdf",
                          file_size_bytes=200, file_hash_sha256="h2", total_pages=1)
        session.add_all([d1, d2])

        # Comments on proj_1 (d1):
        # c1: Approved, confidence 0.95, reviewed by Alice
        c1 = CommentModel(id="c1", drawing_id="d1", page_number=1, raw_text="note 1",
                          category_name="Technical", status="Approved", confidence=0.95,
                          is_verified_by_human=True, user_id="u1", created_at=datetime(2024, 1, 10, tzinfo=timezone.utc))
        # c2: Rejected, confidence 0.85, reviewed by Alice
        c2 = CommentModel(id="c2", drawing_id="d1", page_number=1, raw_text="note 2",
                          category_name="Technical", status="Rejected", confidence=0.85,
                          is_verified_by_human=True, user_id="u1", created_at=datetime(2024, 1, 11, tzinfo=timezone.utc))
        # c3: Pending, confidence 0.50
        c3 = CommentModel(id="c3", drawing_id="d1", page_number=1, raw_text="note 3",
                          category_name="Dimension", status="Pending", confidence=0.50,
                          created_at=datetime(2024, 1, 12, tzinfo=timezone.utc))
        # c4: Flagged, confidence 0.10, reviewed by Bob
        c4 = CommentModel(id="c4", drawing_id="d1", page_number=1, raw_text="note 4",
                          category_name="Dimension", status="Flagged", confidence=0.10,
                          is_verified_by_human=True, user_id="u2", created_at=datetime(2024, 1, 13, tzinfo=timezone.utc))

        # Comments on proj_2 (d2):
        # c5: Approved, confidence 0.75, reviewed by Bob
        c5 = CommentModel(id="c5", drawing_id="d2", page_number=1, raw_text="note 5",
                          category_name="Safety", status="Approved", confidence=0.75,
                          is_verified_by_human=True, user_id="u2", created_at=datetime(2024, 1, 14, tzinfo=timezone.utc))
        session.add_all([c1, c2, c3, c4, c5])

        # Audit logs
        a1 = AuditLogModel(id="a1", comment_id="c1", action="APPROVE", user_id="u1", reviewer_name="Alice Reviewer", timestamp=datetime(2024, 1, 10))
        a2 = AuditLogModel(id="a2", comment_id="c2", action="reject", user_id="u1", reviewer_name="Alice Reviewer", timestamp=datetime(2024, 1, 11))
        a3 = AuditLogModel(id="a3", comment_id="c4", action="flag", user_id="u2", reviewer_name="Bob Reviewer", timestamp=datetime(2024, 1, 13))
        a4 = AuditLogModel(id="a4", comment_id="c5", action="approve", user_id="u2", reviewer_name="Bob Reviewer", timestamp=datetime(2024, 1, 14))
        # AI auto-approval log that must be excluded from human reviewers
        a5 = AuditLogModel(id="a5", comment_id="c1", action="approve", user_id=None, reviewer_name="AI Auto-Approval", timestamp=datetime(2024, 1, 10))
        session.add_all([a1, a2, a3, a4, a5])
        session.commit()

    return engine, service


def test_status_distribution_matches_kpi_totals(a13_db_and_service):
    """Verify sum of statuses equals KPI total comments, and include_rejected=False drops rejected."""
    _, service = a13_db_and_service

    # With include_rejected=True (default)
    kpis = service.get_global_kpis(project_id="proj_1", include_rejected=True)
    status_dist = service.get_status_distribution(project_id="proj_1", include_rejected=True)

    assert status_dist["Approved"] == 1
    assert status_dist["Rejected"] == 1
    assert status_dist["Pending"] == 1
    assert status_dist["Flagged"] == 1
    assert sum(status_dist.values()) == kpis.total_comments == 4

    # With include_rejected=False
    kpis_no_rej = service.get_global_kpis(project_id="proj_1", include_rejected=False)
    status_dist_no_rej = service.get_status_distribution(project_id="proj_1", include_rejected=False)

    assert status_dist_no_rej["Rejected"] == 0
    assert sum(status_dist_no_rej.values()) == kpis_no_rej.total_comments == 3


def test_confidence_distribution_respects_filters(a13_db_and_service):
    """Verify confidence buckets calculate correct counts and respect include_rejected."""
    _, service = a13_db_and_service

    # All comments for proj_1 (c1: 0.95, c2: 0.85, c3: 0.50, c4: 0.10)
    conf_dist = service.get_confidence_distribution(project_id="proj_1", include_rejected=True)
    buckets = {b.range_label: b.count for b in conf_dist}

    assert buckets["0.0-0.2"] == 1  # c4 (0.10)
    assert buckets["0.4-0.6"] == 1  # c3 (0.50)
    assert buckets["0.8-1.0"] == 2  # c1 (0.95), c2 (0.85)
    assert sum(buckets.values()) == 4

    # With include_rejected=False (c2 is excluded)
    conf_dist_no_rej = service.get_confidence_distribution(project_id="proj_1", include_rejected=False)
    buckets_no_rej = {b.range_label: b.count for b in conf_dist_no_rej}
    assert buckets_no_rej["0.8-1.0"] == 1  # c1 only
    assert sum(buckets_no_rej.values()) == 3


def test_reviewer_metrics_scoped_and_excludes_ai(a13_db_and_service):
    """Verify reviewer metrics derive from audit logs, scope to project, and exclude AI Auto-Approval."""
    _, service = a13_db_and_service

    # Proj 1: Alice reviewed c1 (approved) and c2 (rejected). Bob reviewed c4 (flagged).
    revs_p1 = service.get_reviewer_metrics(project_id="proj_1")
    names = {r.reviewer_name: r for r in revs_p1}

    assert "AI Auto-Approval" not in names
    assert "Alice Reviewer" in names
    assert names["Alice Reviewer"].comments_reviewed == 2
    assert names["Alice Reviewer"].approved == 1
    assert names["Alice Reviewer"].rejected == 1

    assert "Bob Reviewer" in names
    assert names["Bob Reviewer"].comments_reviewed == 1
    assert names["Bob Reviewer"].flagged == 1

    # Proj 2: Bob reviewed c5 (approved). Alice has none.
    revs_p2 = service.get_reviewer_metrics(project_id="proj_2")
    names_p2 = {r.reviewer_name: r for r in revs_p2}
    assert "Alice Reviewer" not in names_p2
    assert "Bob Reviewer" in names_p2
    assert names_p2["Bob Reviewer"].approved == 1


def test_project_analytics_full_reconciliation(a13_db_and_service):
    """Verify get_project_analytics builds a fully reconciled ProjectAnalyticsDTO."""
    _, service = a13_db_and_service

    pa = service.get_project_analytics(project_id="proj_1")
    assert pa is not None
    assert pa.project_id == "proj_1"
    assert pa.project_name == "Project 1"
    assert pa.kpi_summary.total_comments == 4
    assert sum(c.count for c in pa.category_distribution) == 4
    assert sum(b.count for b in pa.confidence_distribution) == 4
    assert sum(r.comments_reviewed for r in pa.reviewer_metrics) == 3


def test_analytics_page_renders_status_and_confidence_charts(qapp, a13_db_and_service):
    """Verify AnalyticsPage embeds status distribution and confidence distribution in the grid."""
    engine, service = a13_db_and_service

    class MockController:
        current_department_name = None
        current_batch_drawing_ids = []

        def get_all_projects(self):
            return [{"id": "proj_1", "name": "Project 1"}]

        def get_department_options(self):
            return {"departments": [], "has_unassigned": False}

        def get_category_options(self):
            return ["Technical", "Dimension"]

        def get_all_categories(self):
            return [{"name": "Technical"}, {"name": "Dimension"}]

        def get_min_comment_date(self):
            return datetime(2024, 1, 1)

        def get_drawing_options(self, **kwargs):
            return service.get_drawing_options(**kwargs)

        def get_dashboard_kpis(self, **kwargs):
            return service.get_global_kpis(**kwargs)

        def get_pareto_analysis(self, **kwargs):
            return service.get_pareto_analysis(**kwargs)

        def get_category_distribution(self, **kwargs):
            return service.get_category_distribution(**kwargs)

        def get_status_trend(self, **kwargs):
            return service.get_status_trend(**kwargs)

        def get_status_distribution(self, **kwargs):
            return service.get_status_distribution(**kwargs)

        def get_confidence_distribution(self, **kwargs):
            return service.get_confidence_distribution(**kwargs)

    ctrl = MockController()
    page = AnalyticsPage(controller=ctrl)

    # 5 charts in grid:
    # 0,0 (span 2,1): pareto
    # 0,1: timeline
    # 0,2: status donut
    # 1,1: category donut
    # 1,2: confidence bars
    assert page._grid.count() == 5
