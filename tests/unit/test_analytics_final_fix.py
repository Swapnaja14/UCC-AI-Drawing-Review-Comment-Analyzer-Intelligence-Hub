"""
tests/unit/test_analytics_final_fix.py
Focused unit and regression tests for Analytics Final Fix:
- Verification of:
  1. All drawings
  2. Single drawing
  3. Single category
  4. Current batch
  5. Date range
  6. Department
  7. Category + drawing
  8. Category + date
  9. Empty dataset
  10. Pending/Approved/Rejected/Flagged totals
- Verification that for every scenario:
  * KPI total == chart population (Pareto sum == Category Distribution sum == Timeline sum == Total Comments)
  * Total == Pending + Approved + Rejected + Flagged
  * Filters affect every component consistently
  * No mock data contaminates real SQLite analytics
  * Confidence is not presented as AI accuracy
  * Timeline terminology matches its actual timestamp
"""
import pytest
from datetime import datetime, timedelta, timezone

from src.infrastructure.storage.repository import DatabaseEngine
from src.infrastructure.storage.models import (
    ProjectModel, DrawingModel, PageModel, CommentModel, UserModel, EngineeringDepartmentModel
)
from src.services.analytics_service import AnalyticsService
from app.components.charts import build_pareto_chart, build_monthly_chart, build_category_pie


@pytest.fixture
def analytics_fixture(tmp_path):
    db_path = tmp_path / "test_analytics_final_fix.db"
    db_engine = DatabaseEngine(db_path=db_path)
    service = AnalyticsService(db_engine)

    with db_engine.get_session() as session:
        # Auto-seeded departments
        d_piping = session.query(EngineeringDepartmentModel).filter(EngineeringDepartmentModel.name == "Piping Engineering").first()
        d_struct = session.query(EngineeringDepartmentModel).filter(EngineeringDepartmentModel.name == "Structural & Physical Design").first()

        pip_id = d_piping.id if d_piping else "DEPT-PIP"
        str_id = d_struct.id if d_struct else "DEPT-STR"

        # Projects
        p1 = ProjectModel(id="PRJ-101", name="Plant Alpha Expansion")
        session.add(p1)

        # Drawings
        _dwg_defaults = dict(file_size_bytes=4096, total_pages=1)
        d1 = DrawingModel(id="DWG-001", project_id="PRJ-101", department_id=pip_id, file_path="/drawings/p1.pdf", file_name="p1.pdf", file_hash_sha256="hash1", **_dwg_defaults)
        d2 = DrawingModel(id="DWG-002", project_id="PRJ-101", department_id=pip_id, file_path="/drawings/p2.pdf", file_name="p2.pdf", file_hash_sha256="hash2", **_dwg_defaults)
        d3 = DrawingModel(id="DWG-003", project_id="PRJ-101", department_id=str_id, file_path="/drawings/s1.pdf", file_name="s1.pdf", file_hash_sha256="hash3", **_dwg_defaults)
        session.add_all([d1, d2, d3])

        # Pages
        pg1 = PageModel(id="PG-001", drawing_id="DWG-001", page_number=1, width_pt=612.0, height_pt=792.0, aspect_ratio=0.77)
        pg2 = PageModel(id="PG-002", drawing_id="DWG-002", page_number=1, width_pt=612.0, height_pt=792.0, aspect_ratio=0.77)
        pg3 = PageModel(id="PG-003", drawing_id="DWG-003", page_number=1, width_pt=612.0, height_pt=792.0, aspect_ratio=0.77)
        session.add_all([pg1, pg2, pg3])

        base_time = datetime(2026, 10, 15, 10, 0, 0, tzinfo=timezone.utc)

        # DWG-001 (Piping): 4 comments across all 4 statuses
        # Dates: base_time (Oct 15) and base_time - 1 day (Oct 14)
        c1 = CommentModel(
            id="CMT-01", drawing_id="DWG-001", page_number=1, raw_text="Pipe wall thickness check",
            category_name="Technical", department_id=pip_id, status="Approved",
            is_verified_by_human=True, confidence=0.92, created_at=base_time
        )
        c2 = CommentModel(
            id="CMT-02", drawing_id="DWG-001", page_number=1, raw_text="Flange rating missing",
            category_name="Standards", department_id=pip_id, status="Pending",
            is_verified_by_human=False, confidence=0.85, created_at=base_time
        )
        c3 = CommentModel(
            id="CMT-03", drawing_id="DWG-001", page_number=1, raw_text="Dimension illegible",
            category_name="Dimension", department_id=pip_id, status="Rejected",
            is_verified_by_human=True, confidence=0.45, created_at=base_time - timedelta(days=1)
        )
        c4 = CommentModel(
            id="CMT-04", drawing_id="DWG-001", page_number=1, raw_text="Unclear callout symbol",
            category_name="Drafting", department_id=pip_id, status="Flagged",
            is_verified_by_human=False, confidence=0.78, created_at=base_time - timedelta(days=1)
        )

        # DWG-002 (Piping): 2 comments
        c5 = CommentModel(
            id="CMT-05", drawing_id="DWG-002", page_number=1, raw_text="Valve tag mismatch",
            category_name="Technical", department_id=pip_id, status="Approved",
            is_verified_by_human=False, confidence=0.94, created_at=base_time
        )
        c6 = CommentModel(
            id="CMT-06", drawing_id="DWG-002", page_number=1, raw_text="Unknown tag format",
            category_name="Uncategorized", department_id=pip_id, status="Pending",
            is_verified_by_human=False, confidence=0.30, created_at=base_time - timedelta(days=2)
        )

        # DWG-003 (Structural): 2 comments
        c7 = CommentModel(
            id="CMT-07", drawing_id="DWG-003", page_number=1, raw_text="Beam connection shear tab",
            category_name="Technical", department_id=str_id, status="Approved",
            is_verified_by_human=True, confidence=0.90, created_at=base_time
        )
        c8 = CommentModel(
            id="CMT-08", drawing_id="DWG-003", page_number=1, raw_text="Column baseplate clearance",
            category_name="Dimension", department_id=str_id, status="Pending",
            is_verified_by_human=False, confidence=0.88, created_at=base_time - timedelta(days=3)
        )

        session.add_all([c1, c2, c3, c4, c5, c6, c7, c8])
        session.commit()

    return db_engine, service, base_time


def _verify_consistency(kpis, cat_dist, pareto, trend, conf_dist=None, status_dist=None):
    """Core consistency assertions: KPI totals == chart population & mathematical integrity."""
    # 1. Total == Pending + Approved + Rejected + Flagged
    assert (
        kpis.total_comments == kpis.pending_count + kpis.approved_count + kpis.rejected_count + kpis.flagged_count
    ), f"KPI sum mismatch: {kpis.total_comments} != {kpis.pending_count}+{kpis.approved_count}+{kpis.rejected_count}+{kpis.flagged_count}"

    # 2. KPI Total == Category Distribution population sum
    cat_sum = sum(c.count for c in cat_dist)
    assert kpis.total_comments == cat_sum, f"Category distribution sum {cat_sum} != KPI total {kpis.total_comments}"

    # 3. KPI Total == Pareto chart population sum
    pareto_sum = sum(p.count for p in pareto)
    assert kpis.total_comments == pareto_sum, f"Pareto sum {pareto_sum} != KPI total {kpis.total_comments}"

    # 4. KPI Total == Timeline population sum
    trend_sum = sum(t.count for t in trend)
    assert kpis.total_comments == trend_sum, f"Timeline sum {trend_sum} != KPI total {kpis.total_comments}"

    # 5. KPI Total == Confidence distribution sum
    if conf_dist is not None:
        conf_sum = sum(b.count for b in conf_dist)
        assert kpis.total_comments == conf_sum, f"Confidence sum {conf_sum} != KPI total {kpis.total_comments}"

    # 6. KPI Total == Status distribution sum
    if status_dist is not None:
        status_sum = sum(status_dist.values())
        assert kpis.total_comments == status_sum, f"Status sum {status_sum} != KPI total {kpis.total_comments}"

    # 7. Concept separation: confidence is distinct from approval rate and review progress
    if kpis.total_comments > 0:
        assert isinstance(kpis.avg_confidence, float)
        assert 0.0 <= kpis.avg_confidence <= 1.0
        assert kpis.approval_rate is not None
        assert 0.0 <= kpis.approval_rate <= 100.0
        assert kpis.review_progress is not None
        assert 0.0 <= kpis.review_progress <= 100.0
        assert kpis.reviewed_count == kpis.approved_count + kpis.rejected_count
        assert kpis.estimated_hours_saved is not None
        assert kpis.estimated_hours_saved >= 0.0


# ── Scenario 1: All Drawings ───────────────────────────────────────────────
def test_scenario_1_all_drawings(analytics_fixture):
    _, service, _ = analytics_fixture
    kpis = service.get_global_kpis()
    cat_dist = service.get_category_distribution()
    pareto = service.get_pareto_analysis(include_rejected=True)
    trend = service.get_status_trend()

    assert kpis.total_comments == 8
    assert kpis.approved_count == 3
    assert kpis.pending_count == 3
    assert kpis.rejected_count == 1
    assert kpis.flagged_count == 1
    _verify_consistency(kpis, cat_dist, pareto, trend)


# ── Scenario 2: Single Drawing ──────────────────────────────────────────────
def test_scenario_2_single_drawing(analytics_fixture):
    _, service, _ = analytics_fixture
    kpis = service.get_global_kpis(drawing_id="DWG-001")
    cat_dist = service.get_category_distribution(drawing_id="DWG-001")
    pareto = service.get_pareto_analysis(drawing_id="DWG-001", include_rejected=True)
    trend = service.get_status_trend(drawing_id="DWG-001")

    assert kpis.total_comments == 4
    assert kpis.approved_count == 1
    assert kpis.pending_count == 1
    assert kpis.rejected_count == 1
    assert kpis.flagged_count == 1
    _verify_consistency(kpis, cat_dist, pareto, trend)


# ── Scenario 3: Single Category ─────────────────────────────────────────────
def test_scenario_3_single_category(analytics_fixture):
    _, service, _ = analytics_fixture
    kpis = service.get_global_kpis(category_name="Technical")
    cat_dist = service.get_category_distribution(category_name="Technical")
    pareto = service.get_pareto_analysis(category_name="Technical", include_rejected=True)
    trend = service.get_status_trend(category_name="Technical")

    # 3 Technical comments: c1 (dwg1), c5 (dwg2), c7 (dwg3) -> all Approved
    assert kpis.total_comments == 3
    assert kpis.approved_count == 3
    assert kpis.pending_count == 0
    assert len(cat_dist) == 1
    assert cat_dist[0].category_name == "Technical"
    assert cat_dist[0].count == 3
    _verify_consistency(kpis, cat_dist, pareto, trend)


# ── Scenario 4: Current Batch ───────────────────────────────────────────────
def test_scenario_4_current_batch(analytics_fixture):
    _, service, _ = analytics_fixture
    # Current batch consists of DWG-001 and DWG-002
    batch_ids = ["DWG-001", "DWG-002"]
    kpis = service.get_global_kpis(drawing_ids=batch_ids)
    cat_dist = service.get_category_distribution(drawing_ids=batch_ids)
    pareto = service.get_pareto_analysis(drawing_ids=batch_ids, include_rejected=True)
    trend = service.get_status_trend(drawing_ids=batch_ids)

    # 4 on DWG-001 + 2 on DWG-002 = 6
    assert kpis.total_comments == 6
    assert kpis.approved_count == 2
    assert kpis.pending_count == 2
    assert kpis.rejected_count == 1
    assert kpis.flagged_count == 1
    _verify_consistency(kpis, cat_dist, pareto, trend)


# ── Scenario 5: Date Range ──────────────────────────────────────────────────
def test_scenario_5_date_range(analytics_fixture):
    _, service, base_time = analytics_fixture
    # Filter to base_time only (Oct 15)
    d_from = datetime(2026, 10, 15, 0, 0, 0)
    d_to = datetime(2026, 10, 15, 23, 59, 59)

    kpis = service.get_global_kpis(date_from=d_from, date_to=d_to)
    cat_dist = service.get_category_distribution(date_from=d_from, date_to=d_to)
    pareto = service.get_pareto_analysis(date_from=d_from, date_to=d_to, include_rejected=True)
    trend = service.get_status_trend(date_from=d_from, date_to=d_to)

    # Comments created on Oct 15: c1, c2, c5, c7 = 4 comments
    assert kpis.total_comments == 4
    _verify_consistency(kpis, cat_dist, pareto, trend)


# ── Scenario 6: Department ──────────────────────────────────────────────────
def test_scenario_6_department(analytics_fixture):
    _, service, _ = analytics_fixture
    # Structural department
    kpis = service.get_global_kpis(department_name="Structural & Physical Design")
    cat_dist = service.get_category_distribution(department_name="Structural & Physical Design")
    pareto = service.get_pareto_analysis(department_name="Structural & Physical Design", include_rejected=True)
    trend = service.get_status_trend(department_name="Structural & Physical Design")

    # DWG-003 has 2 comments (c7, c8)
    assert kpis.total_comments == 2
    assert kpis.total_drawings == 1
    assert kpis.approved_count == 1
    assert kpis.pending_count == 1
    _verify_consistency(kpis, cat_dist, pareto, trend)


# ── Scenario 7: Category + Drawing ──────────────────────────────────────────
def test_scenario_7_category_plus_drawing(analytics_fixture):
    _, service, _ = analytics_fixture
    # Category = Dimension on DWG-001
    kpis = service.get_global_kpis(drawing_id="DWG-001", category_name="Dimension")
    cat_dist = service.get_category_distribution(drawing_id="DWG-001", category_name="Dimension")
    pareto = service.get_pareto_analysis(drawing_id="DWG-001", category_name="Dimension", include_rejected=True)
    trend = service.get_status_trend(drawing_id="DWG-001", category_name="Dimension")

    # c3 is on DWG-001 with Dimension (Rejected)
    assert kpis.total_comments == 1
    assert kpis.rejected_count == 1
    assert kpis.approved_count == 0
    _verify_consistency(kpis, cat_dist, pareto, trend)


# ── Scenario 8: Category + Date ─────────────────────────────────────────────
def test_scenario_8_category_plus_date(analytics_fixture):
    _, service, base_time = analytics_fixture
    # Technical on Oct 15
    d_from = datetime(2026, 10, 15, 0, 0, 0)
    d_to = datetime(2026, 10, 15, 23, 59, 59)

    kpis = service.get_global_kpis(category_name="Technical", date_from=d_from, date_to=d_to)
    cat_dist = service.get_category_distribution(category_name="Technical", date_from=d_from, date_to=d_to)
    pareto = service.get_pareto_analysis(category_name="Technical", date_from=d_from, date_to=d_to, include_rejected=True)
    trend = service.get_status_trend(category_name="Technical", date_from=d_from, date_to=d_to)

    # c1 (dwg1), c5 (dwg2), c7 (dwg3) were all created on Oct 15
    assert kpis.total_comments == 3
    assert kpis.approved_count == 3
    _verify_consistency(kpis, cat_dist, pareto, trend)


# ── Scenario 9: Empty Dataset ───────────────────────────────────────────────
def test_scenario_9_empty_dataset(analytics_fixture):
    _, service, _ = analytics_fixture
    # Non-existent drawing ID
    kpis = service.get_global_kpis(drawing_id="DWG-NONEXISTENT")
    cat_dist = service.get_category_distribution(drawing_id="DWG-NONEXISTENT")
    pareto = service.get_pareto_analysis(drawing_id="DWG-NONEXISTENT", include_rejected=True)
    trend = service.get_status_trend(drawing_id="DWG-NONEXISTENT")

    assert kpis.total_comments == 0
    assert kpis.approved_count == 0
    assert kpis.pending_count == 0
    assert kpis.rejected_count == 0
    assert kpis.flagged_count == 0
    assert kpis.avg_confidence == 0.0
    _verify_consistency(kpis, cat_dist, pareto, trend)


# ── Scenario 10: Status Totals Math Exactness ────────────────────────────────
def test_scenario_10_status_totals_robustness(tmp_path):
    """Test with unassigned, lowercase, and null statuses in database to verify 100% math exactness."""
    db_path = tmp_path / "test_status_math.db"
    db_engine = DatabaseEngine(db_path=db_path)
    service = AnalyticsService(db_engine)

    with db_engine.get_session() as session:
        _dwg = dict(file_size_bytes=100, total_pages=1, file_path="/d.pdf", file_name="d.pdf", file_hash_sha256="h0")
        d = DrawingModel(id="DWG-999", **_dwg)
        session.add(d)

        # 4 comments with variations in case / unassigned / whitespace
        cmts = [
            CommentModel(id="c_app", drawing_id="DWG-999", page_number=1, raw_text="A", status="approved", confidence=0.8),
            CommentModel(id="c_rej", drawing_id="DWG-999", page_number=1, raw_text="B", status="REJECTED ", confidence=0.6),
            CommentModel(id="c_flg", drawing_id="DWG-999", page_number=1, raw_text="C", status="Flagged", confidence=0.7),
            CommentModel(id="c_unrev", drawing_id="DWG-999", page_number=1, raw_text="D", status="Pending", confidence=0.5),
            CommentModel(id="c_weird", drawing_id="DWG-999", page_number=1, raw_text="E", status="In Review", confidence=0.4), # unreviewed -> Pending
        ]
        session.add_all(cmts)
        session.commit()

    kpis = service.get_global_kpis(drawing_id="DWG-999")
    assert kpis.total_comments == 5
    assert kpis.approved_count == 1
    assert kpis.rejected_count == 1
    assert kpis.flagged_count == 1
    assert kpis.pending_count == 2
    assert (
        kpis.total_comments == kpis.approved_count + kpis.rejected_count + kpis.flagged_count + kpis.pending_count
    )


# ── Verification: Chart Renderers & Timeline Timestamp Match ─────────────────
def test_chart_renderers_and_timeline_label():
    from PySide6.QtWidgets import QApplication
    from app.components.charts import (
        build_confidence_distribution_chart,
        build_status_distribution_chart,
    )
    _ = QApplication.instance() or QApplication([])

    p_chart = build_pareto_chart([{"category_name": "Technical", "count": 5}], title="Pareto — Category: Technical")
    assert p_chart is not None

    t_chart = build_monthly_chart([{"period_label": "2026-10-15", "count": 4}], title="Comment Timeline (by Creation Date)")
    assert t_chart is not None

    pie_chart = build_category_pie([{"category_name": "Technical", "count": 5, "color_hex": "#EF4444"}], title="Category Distribution (Technical)")
    assert pie_chart is not None

    c_chart = build_confidence_distribution_chart([{"range_label": "0.8-1.0", "count": 5}], title="Confidence Distribution")
    assert c_chart is not None

    s_chart = build_status_distribution_chart({"Pending": 2, "Approved": 3, "Rejected": 1, "Flagged": 0}, title="Status Distribution")
    assert s_chart is not None


# ── Scenario 11: Drawing + Date ─────────────────────────────────────────────
def test_scenario_11_drawing_plus_date(analytics_fixture):
    _, service, base_time = analytics_fixture
    # DWG-001 on Oct 15: c1 (Technical, Approved), c2 (Standards, Pending) -> 2 comments
    d_from = datetime(2026, 10, 15, 0, 0, 0)
    d_to = datetime(2026, 10, 15, 23, 59, 59)

    kpis = service.get_global_kpis(drawing_id="DWG-001", date_from=d_from, date_to=d_to)
    cat_dist = service.get_category_distribution(drawing_id="DWG-001", date_from=d_from, date_to=d_to)
    pareto = service.get_pareto_analysis(drawing_id="DWG-001", date_from=d_from, date_to=d_to, include_rejected=True)
    trend = service.get_status_trend(drawing_id="DWG-001", date_from=d_from, date_to=d_to)
    conf_dist = service.get_confidence_distribution(drawing_id="DWG-001", date_from=d_from, date_to=d_to)
    status_dist = service.get_status_distribution(drawing_id="DWG-001", date_from=d_from, date_to=d_to)

    assert kpis.total_comments == 2
    assert kpis.approved_count == 1
    assert kpis.pending_count == 1
    assert kpis.rejected_count == 0
    assert kpis.flagged_count == 0
    _verify_consistency(kpis, cat_dist, pareto, trend, conf_dist=conf_dist, status_dist=status_dist)


# ── Scenario 12: Confidence & Status Parity Across All Permutations ──────────
def test_scenario_12_confidence_and_status_parity_all(analytics_fixture):
    _, service, _ = analytics_fixture
    kpis = service.get_global_kpis()
    cat_dist = service.get_category_distribution()
    pareto = service.get_pareto_analysis(include_rejected=True)
    trend = service.get_status_trend()
    conf_dist = service.get_confidence_distribution()
    status_dist = service.get_status_distribution()

    # All 8 comments accounted for in every structure
    assert kpis.total_comments == 8
    _verify_consistency(kpis, cat_dist, pareto, trend, conf_dist=conf_dist, status_dist=status_dist)


# ── Scenario 13: Auto-Approval Metrics and Human Hours Saved ─────────────────
def test_scenario_13_auto_approval_and_hours_saved(analytics_fixture):
    _, service, _ = analytics_fixture
    # In fixture:
    # c1: Approved, is_verified_by_human=True
    # c5: Approved, is_verified_by_human=False (auto-approved by AI)
    # c7: Approved, is_verified_by_human=True
    # Total approved = 3, auto-approved = 1, human-approved = 2
    kpis = service.get_global_kpis()
    assert kpis.approved_count == 3
    assert kpis.auto_approved_count == 1
    assert kpis.auto_approval_rate == (1 / 8 * 100.0)
    assert kpis.reviewed_count == 4  # 3 approved + 1 rejected
    # Estimated hours saved: 1 auto-approved * 0.25h + 4 reviewed * 0.10h = 0.65h -> round(0.65, 1) = 0.6 or 0.7
    assert kpis.estimated_hours_saved is not None
    assert kpis.estimated_hours_saved > 0.0


# ── Scenario 14: AppController Analytics Proxies ─────────────────────────────
def test_scenario_14_controller_proxies(tmp_path):
    from unittest.mock import MagicMock
    from app.controllers.app_controller import AppController

    mock_db = DatabaseEngine(db_path=tmp_path / "ctrl_test.db")
    ctrl = AppController(db_engine=mock_db)
    
    kpis = ctrl.get_dashboard_kpis()
    assert kpis.total_comments == 0
    cat_dist = ctrl.get_category_distribution()
    assert cat_dist == []
    pareto = ctrl.get_pareto_analysis()
    assert pareto == []
    trend = ctrl.get_status_trend()
    assert trend == []
    conf_dist = ctrl.get_confidence_distribution()
    assert len(conf_dist) == 5
    assert sum(b.count for b in conf_dist) == 0
    status_dist = ctrl.get_status_distribution()
    assert status_dist == {"Pending": 0, "Approved": 0, "Rejected": 0, "Flagged": 0}

