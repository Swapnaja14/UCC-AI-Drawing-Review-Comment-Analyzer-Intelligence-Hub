import pytest
from datetime import datetime, timedelta, timezone
from src.infrastructure.storage.repository import DatabaseEngine
from src.infrastructure.storage.models import (
    Base, ProjectModel, DrawingModel, PageModel, CommentModel, UserModel
)
from src.services.analytics_service import AnalyticsService


def _setup_test_db(tmp_path):
    db_path = tmp_path / "test.db"
    db_engine = DatabaseEngine(db_path=db_path)
    service = AnalyticsService(db_engine)
    return db_engine, service


@pytest.fixture
def test_setup(tmp_path):
    db_engine, service = _setup_test_db(tmp_path)

    with db_engine.get_session() as session:
        # User — username is NOT NULL
        user = UserModel(id="u1", username="testuser", display_name="Test User")
        session.add(user)

        # Projects
        p1 = ProjectModel(id="p1", name="Proj 1")
        p2 = ProjectModel(id="p2", name="Proj 2")
        session.add_all([p1, p2])

        # Drawings — supply all NOT NULL columns
        _dwg = dict(file_path="/tmp/test.pdf", file_name="test.pdf",
                     file_size_bytes=1024, file_hash_sha256="abc123", total_pages=2)
        d1 = DrawingModel(id="d1", project_id="p1", **_dwg)
        d2 = DrawingModel(id="d2", project_id="p1", **{**_dwg, "file_hash_sha256": "def456"})
        d3 = DrawingModel(id="d3", project_id="p2", **{**_dwg, "file_hash_sha256": "ghi789"})
        session.add_all([d1, d2, d3])

        # Pages — supply NOT NULL columns
        session.add_all([
            PageModel(id="pg1", drawing_id="d1", page_number=1,
                      width_pt=612.0, height_pt=792.0, aspect_ratio=0.77),
            PageModel(id="pg2", drawing_id="d1", page_number=2,
                      width_pt=612.0, height_pt=792.0, aspect_ratio=0.77),
        ])

        # Comments — supply NOT NULL columns (page_number, raw_text)
        today = datetime.now(timezone.utc)
        _cmt = dict(page_number=1, raw_text="test comment")
        comments = [
            CommentModel(id="c1", drawing_id="d1", category_name="Piping/Process", confidence=0.9, status="Approved", is_verified_by_human=True, user_id="u1", created_at=today, **_cmt),
            CommentModel(id="c2", drawing_id="d1", category_name="Structural/Civil", confidence=0.5, status="Pending", is_verified_by_human=False, created_at=today, **_cmt),
            CommentModel(id="c3", drawing_id="d1", category_name="Piping/Process", confidence=0.95, status="Approved", is_verified_by_human=True, user_id="u1", created_at=today - timedelta(days=1), **_cmt),
            CommentModel(id="c4", drawing_id="d2", category_name="Safety/HSE", confidence=0.1, status="Rejected", is_verified_by_human=True, user_id="u1", created_at=today - timedelta(days=1), **_cmt),
            CommentModel(id="c5", drawing_id="d2", category_name="Uncategorized", confidence=0.4, status="Flagged", is_verified_by_human=False, created_at=today - timedelta(days=2), **_cmt),
            CommentModel(id="c6", drawing_id="d3", category_name="Structural/Civil", confidence=0.7, status="Approved", is_verified_by_human=False, created_at=today, **_cmt),
            CommentModel(id="c7", drawing_id="d3", category_name="Electrical/Instrumentation", confidence=0.8, status="Pending", is_verified_by_human=False, created_at=today, **_cmt),
            CommentModel(id="c8", drawing_id="d3", category_name="Dimensional/Tolerancing", confidence=0.99, status="Rejected", is_verified_by_human=True, user_id="u1", created_at=today, **_cmt),
            CommentModel(id="c9", drawing_id="d3", category_name="Safety/HSE", confidence=0.3, status="Pending", is_verified_by_human=False, created_at=today, **_cmt),
            CommentModel(id="c10", drawing_id="d3", category_name="General/Administrative", confidence=0.88, status="Flagged", is_verified_by_human=False, created_at=today, **_cmt),
        ]
        session.add_all(comments)
        session.commit()

    return service

def test_global_kpis_counts(test_setup):
    service = test_setup
    kpis = service.get_global_kpis()
    assert kpis.total_projects == 2
    assert kpis.total_drawings == 3
    assert kpis.total_pages == 2
    assert kpis.total_comments == 10
    assert kpis.approved_count == 3
    assert kpis.rejected_count == 2
    assert kpis.pending_count == 3
    assert kpis.flagged_count == 2

def test_category_distribution_percentages(test_setup):
    service = test_setup
    dist = service.get_category_distribution()
    assert sum(d.percentage for d in dist) == pytest.approx(100.0)
    assert len(dist) == 7 
    
def test_confidence_distribution_buckets(test_setup):
    service = test_setup
    buckets = service.get_confidence_distribution()
    assert len(buckets) == 5
    assert sum(b.count for b in buckets) == 10
    assert sum(b.percentage for b in buckets) == pytest.approx(100.0)

def test_pareto_analysis_sorted_descending(test_setup):
    service = test_setup
    pareto = service.get_pareto_analysis(top_n=3)
    assert len(pareto) == 3
    assert pareto[0].count >= pareto[1].count
    assert pareto[1].count >= pareto[2].count

def test_status_trend_returns_data(test_setup):
    service = test_setup
    trend = service.get_status_trend()
    assert len(trend) > 0
    total_points = sum(t.count for t in trend)
    assert total_points == 10

def test_empty_database_returns_zeros(tmp_path):
    _, service = _setup_test_db(tmp_path)
    kpis = service.get_global_kpis()
    assert kpis.total_projects == 0
    assert kpis.total_drawings == 0
    assert kpis.total_comments == 0
    assert kpis.human_verified_approval_rate is None

def test_human_verified_approval_rate(test_setup):
    service = test_setup
    kpis = service.get_global_kpis()
    # c1 and c3 are Approved AND is_verified_by_human -> 2 of 10 comments.
    assert kpis.human_verified_approval_rate == pytest.approx(20.0)


def test_department_pareto_analysis(tmp_path):
    from src.infrastructure.storage.models import EngineeringDepartmentModel
    db_engine, service = _setup_test_db(tmp_path)

    with db_engine.get_session() as session:
        dept_elec = session.query(EngineeringDepartmentModel).filter_by(name="Electrical Engineering").first()
        dept_pipe = session.query(EngineeringDepartmentModel).filter_by(name="Piping Engineering").first()

        _dwg = dict(file_path="/tmp/test.pdf", file_name="test.pdf", file_size_bytes=1024, file_hash_sha256="abc123", total_pages=1)
        d1 = DrawingModel(id="d1", **_dwg)
        session.add(d1)

        c1 = CommentModel(id="c1", drawing_id="d1", page_number=1, raw_text="t1", category_name="Wiring", department_id=dept_elec.id)
        c2 = CommentModel(id="c2", drawing_id="d1", page_number=1, raw_text="t2", category_name="Wiring", department_id=dept_elec.id)
        c3 = CommentModel(id="c3", drawing_id="d1", page_number=1, raw_text="t3", category_name="Clearance", department_id=dept_pipe.id)
        session.add_all([c1, c2, c3])
        session.commit()

    pareto_elec = service.get_pareto_analysis(department_name="Electrical Engineering")
    assert len(pareto_elec) == 1
    assert pareto_elec[0].category_name == "Wiring"
    assert pareto_elec[0].count == 2

    pareto_pipe = service.get_pareto_analysis(department_name="Piping Engineering")
    assert len(pareto_pipe) == 1
    assert pareto_pipe[0].category_name == "Clearance"
    assert pareto_pipe[0].count == 1




def test_include_rejected_toggle(test_setup):
    service = test_setup
    # With include_rejected=True (default)
    kpi_all = service.get_global_kpis(include_rejected=True)
    assert kpi_all.total_comments == 10
    assert kpi_all.rejected_count == 2
    assert kpi_all.include_rejected is True

    # With include_rejected=False
    kpi_no_rej = service.get_global_kpis(include_rejected=False)
    assert kpi_no_rej.total_comments == 8
    assert kpi_no_rej.rejected_count == 0
    assert kpi_no_rej.include_rejected is False

    # Category distribution
    cat_all = service.get_category_distribution(include_rejected=True)
    assert sum(d.count for d in cat_all) == 10

    cat_no_rej = service.get_category_distribution(include_rejected=False)
    assert sum(d.count for d in cat_no_rej) == 8

    # Pareto analysis
    pareto_all = service.get_pareto_analysis(include_rejected=True)
    assert sum(d.count for d in pareto_all) == 10

    pareto_no_rej = service.get_pareto_analysis(include_rejected=False)
    assert sum(d.count for d in pareto_no_rej) == 8


def test_bucket_trend_data_daily_span_and_zero_fill():
    from src.services.analytics_service import bucket_trend_data
    # 5 dates across Jan 1 to Jan 5 (span <= 31 days)
    # Notice: no dates on Jan 3 -> must be zero-filled!
    d1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    d2 = datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
    d4 = datetime(2026, 1, 4, 15, 0, 0, tzinfo=timezone.utc)
    d5 = datetime(2026, 1, 5, 8, 0, 0, tzinfo=timezone.utc)
    
    result = bucket_trend_data([d1, d2, d4, d5])
    # Expect 5 daily buckets (Jan 1 through Jan 5)
    assert len(result) == 5
    labels = [r.period_label for r in result]
    # Verify continuous days
    assert labels[0].endswith('-01')
    assert labels[1].endswith('-02')
    assert labels[2].endswith('-03')
    assert labels[3].endswith('-04')
    assert labels[4].endswith('-05')
    # Jan 3 should have count 0 (zero-filled)
    assert result[2].count == 0
    assert result[0].count == 1
    assert result[1].count == 1
    assert result[3].count == 1
    assert result[4].count == 1


def test_bucket_trend_data_weekly_span():
    from src.services.analytics_service import bucket_trend_data
    # Dates 60 days apart (span between 32 and 182 days -> weekly buckets)
    d1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    d2 = datetime(2026, 3, 2, 10, 0, 0, tzinfo=timezone.utc)
    result = bucket_trend_data([d1, d2])
    assert len(result) >= 8  # ~9 weeks
    assert all('-W' in r.period_label for r in result)


def test_bucket_trend_data_monthly_span():
    from src.services.analytics_service import bucket_trend_data
    # Dates 300 days apart (> 26 weeks -> monthly buckets)
    d1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    d2 = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
    result = bucket_trend_data([d1, d2])
    assert len(result) == 10  # Jan through Oct (10 months, continuous)
    assert result[0].period_label == '2026-01'
    assert result[-1].period_label == '2026-10'
    # Empty months between Jan and Oct are zero-filled
    assert result[1].count == 0  # Feb
    assert result[0].count == 1  # Jan
    assert result[-1].count == 1  # Oct


def test_get_min_comment_date(test_setup):
    service = test_setup
    min_date = service.get_min_comment_date()
    assert min_date is not None
    assert isinstance(min_date, datetime)
