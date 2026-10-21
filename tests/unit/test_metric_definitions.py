"""
A12 — metric definitions.

Covers the three concepts that must stay separate on screen and the supporting
counts: review progress, AI confidence, category agreement, the Flagged
manual/OCR-failed split, human-reviewed rows, config-driven confidence bands,
the include-rejected population flag, and the stable Dashboard card.
"""
import pytest

import src.config as config_module
from src.config.app_config import AppConfig
from src.infrastructure.storage.repository import DatabaseEngine
from src.infrastructure.storage.models import (
    ProjectModel, DrawingModel, CommentModel, OCR_FAILED_ENGINE,
)
from src.services.analytics_service import AnalyticsService, get_confidence_thresholds


#: (id, status, verified, ocr_engine, method, fallback, cls_conf, conf, category, initial)
ROWS = [
    ("c1", "Approved", True,  "Tesseract OCR",  "ai_model",   False, 0.90, 0.90, "Technical",     "Technical"),
    ("c2", "Approved", False, "Tesseract OCR",  "ai_model",   False, 0.70, 0.70, "Technical",     "Drafting"),
    ("c3", "Rejected", True,  "Tesseract OCR",  "ai_model",   True,  0.20, 0.20, "Dimension",     "Technical"),
    ("c4", "Flagged",  False, OCR_FAILED_ENGINE, "rule_based", False, 0.00, 0.00, "Uncategorized", None),
    ("c5", "Flagged",  True,  "Tesseract OCR",  "ai_model",   False, 0.50, 0.50, "Technical",     "Technical"),
    ("c6", "Pending",  False, "Tesseract OCR",  "ai_model",   False, 0.99, 0.99, "Drafting",      "Drafting"),
    ("c7", "Rejected", False, "Tesseract OCR",  "ai_model",   False, 0.40, 0.40, "Standards",     None),
    ("c8", "Pending",  True,  "Tesseract OCR",  "ai_model",   False, 0.60, 0.60, "Technical",     "Technical"),
]


def _seed(tmp_path, high=0.80, low=0.60):
    """Build a throwaway DB plus a config singleton with known thresholds."""
    cfg = AppConfig()
    cfg.ai.auto_approve_threshold = high
    cfg.ai.low_confidence_threshold = low
    config_module.set_config(cfg)

    db_engine = DatabaseEngine(db_path=tmp_path / "metrics.db")
    with db_engine.get_session() as session:
        session.add(ProjectModel(id="p1", name="Proj 1"))
        session.add(DrawingModel(
            id="d1", project_id="p1", file_path="/tmp/d1.pdf", file_name="d1.pdf",
            file_size_bytes=1024, file_hash_sha256="abc", total_pages=1,
        ))
        for (cid, status, verified, engine, method, fallback,
             cls_conf, conf, category, initial) in ROWS:
            session.add(CommentModel(
                id=cid, drawing_id="d1", page_number=1, raw_text=f"text {cid}",
                status=status, is_verified_by_human=verified, ocr_engine=engine,
                classification_method=method, fallback_used=fallback,
                classification_confidence=cls_conf, confidence=conf,
                category_name=category, initial_category=initial,
            ))
        session.commit()
    return AnalyticsService(db_engine)


@pytest.fixture
def service(tmp_path):
    original = config_module._ACTIVE_CONFIG
    try:
        yield _seed(tmp_path)
    finally:
        config_module._ACTIVE_CONFIG = original


def test_review_progress_counts_decided_rows_only(service):
    """(Approved + Rejected) / total — auto-approvals in, Flagged and Pending out."""
    kpis = service.get_global_kpis()
    assert kpis.total_comments == 8
    assert kpis.reviewed_count == 4          # c1, c2, c3, c7
    assert kpis.review_progress == pytest.approx(50.0)


def test_status_counts_are_exhaustive(service):
    kpis = service.get_global_kpis()
    assert (kpis.approved_count, kpis.rejected_count,
            kpis.pending_count, kpis.flagged_count) == (2, 2, 2, 2)
    assert kpis.approved_count + kpis.rejected_count + kpis.pending_count + kpis.flagged_count \
        == kpis.total_comments


def test_flagged_split_separates_ocr_failures_from_manual_flags(service):
    kpis = service.get_global_kpis()
    assert kpis.flagged_ocr_failed_count == 1     # c4
    assert kpis.flagged_manual_count == 1         # c5
    assert kpis.flagged_manual_count + kpis.flagged_ocr_failed_count == kpis.flagged_count


def test_human_reviewed_requires_a_decided_status(service):
    """c8 is human-verified but still Pending, so it must not count as reviewed."""
    kpis = service.get_global_kpis()
    assert kpis.human_reviewed_count == 3         # c1, c3, c5
    assert kpis.auto_approved_count == 1          # c2
    assert kpis.human_verified_approval_rate == pytest.approx(12.5)


def test_ai_confidence_only_covers_model_scored_rows(service):
    """fallback_used rows and non-ai_model rows are excluded from the average."""
    kpis = service.get_global_kpis()
    assert kpis.ai_confidence_sample_size == 6    # all but c3 (fallback) and c4 (rule_based)
    expected = (0.90 + 0.70 + 0.50 + 0.99 + 0.40 + 0.60) / 6
    assert kpis.ai_confidence_avg == pytest.approx(expected)


def test_category_agreement_population_and_value(service):
    """
    Only human-verified, decided rows with a recorded initial category count:
    c1 (match), c3 (mismatch), c5 (match). c2 is auto-approved, c8 is Pending,
    c4/c7 have no initial category.
    """
    kpis = service.get_global_kpis()
    assert kpis.category_agreement_sample_size == 3
    assert kpis.category_agreement_pct == pytest.approx(200.0 / 3)


def test_category_agreement_is_none_without_a_population(service):
    kpis = service.get_global_kpis(category_name="Cosmetic")
    assert kpis.total_comments == 0
    assert kpis.category_agreement_pct is None
    assert kpis.ai_confidence_avg is None


def test_confidence_bands_come_from_config(service):
    kpis = service.get_global_kpis()
    assert kpis.high_confidence_threshold == pytest.approx(0.80)
    assert kpis.low_confidence_threshold == pytest.approx(0.60)
    assert kpis.high_confidence_pct == pytest.approx(25.0)   # c1, c6
    assert kpis.low_confidence_pct == pytest.approx(50.0)    # c3, c4, c5, c7


def test_confidence_bands_follow_config_changes(tmp_path):
    original = config_module._ACTIVE_CONFIG
    try:
        svc = _seed(tmp_path, high=0.90, low=0.50)
        assert get_confidence_thresholds() == pytest.approx((0.90, 0.50))
        kpis = svc.get_global_kpis()
        assert kpis.high_confidence_threshold == pytest.approx(0.90)
        assert kpis.low_confidence_threshold == pytest.approx(0.50)
        assert kpis.high_confidence_pct == pytest.approx(25.0)   # c1, c6
        assert kpis.low_confidence_pct == pytest.approx(37.5)    # c3, c4, c7
    finally:
        config_module._ACTIVE_CONFIG = original


def test_include_rejected_default_on_and_flag_echoed(service):
    kpis = service.get_global_kpis()
    assert kpis.include_rejected is True
    assert kpis.rejected_count == 2


def test_include_rejected_off_drops_rejected_from_every_count(service):
    kpis = service.get_global_kpis(include_rejected=False)
    assert kpis.include_rejected is False
    assert kpis.total_comments == 6
    assert kpis.rejected_count == 0
    assert kpis.approved_count + kpis.rejected_count + kpis.pending_count + kpis.flagged_count \
        == kpis.total_comments
    assert kpis.review_progress == pytest.approx(2 / 6 * 100)


def test_no_metric_is_named_accuracy(service):
    kpis = service.get_global_kpis()
    for banned in ("accuracy", "accuracy_rate", "estimated_hours_saved", "hours_saved"):
        assert not hasattr(kpis, banned)


def test_dashboard_card_label_is_stable(service):
    """
    The Dashboard card must keep one label and one definition: it used to show
    "Approval Rate" and silently fall back to "Avg Confidence" when that was 0.
    """
    from app.screens.dashboard_screen import DashboardPage

    _, _, _, metric_str, metric_lbl, trend = DashboardPage._get_kpi_values(
        _KpiStub(service, {})
    )
    assert metric_lbl == "Review Progress"
    assert metric_str == "50.0%"
    assert trend == "4/8 reviewed"

    # Empty population: still Review Progress, never a different metric.
    _, _, _, metric_str, metric_lbl, trend = DashboardPage._get_kpi_values(
        _KpiStub(service, {"category_name": "Cosmetic"})
    )
    assert metric_lbl == "Review Progress"
    assert metric_str == "0.0%"
    assert trend == "Nothing to review yet"


def test_dashboard_card_survives_a_missing_controller():
    from app.screens.dashboard_screen import DashboardPage

    _, _, _, metric_str, metric_lbl, trend = DashboardPage._get_kpi_values(
        _KpiStub(None, {})
    )
    assert metric_lbl == "Review Progress"
    assert metric_str == "—"
    assert trend == "Ready"


class _KpiStub:
    """Bare object exposing only what ``DashboardPage._get_kpi_values`` reads."""

    def __init__(self, service, kwargs):
        self._controller = _ServiceController(service, kwargs) if service else None


class _ServiceController:
    def __init__(self, service, kwargs):
        self._service = service
        self._kwargs = kwargs

    def get_dashboard_kpis(self, **kwargs):
        return self._service.get_global_kpis(**self._kwargs)
