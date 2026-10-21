"""
A1 — Current Batch filter behaviour.

The Batch dropdown used to drop the "Current Batch" entry whenever the session
had no drawings, which silently moved the user back to "All Uploads / Batches"
and widened the population from zero rows to the whole database. These tests
pin the option in place, the grammar of its label, the zero-row filter it
produces, and the empty state shown instead of blank charts.
"""
import pytest

from PySide6.QtWidgets import QApplication, QLabel

from src.infrastructure.storage.repository import DatabaseEngine
from src.infrastructure.storage.models import ProjectModel, DrawingModel, CommentModel
from src.services.analytics_service import AnalyticsService
from app.screens.analytics_screen import (
    AnalyticsPage, CURRENT_BATCH, EMPTY_BATCH_MESSAGE, batch_option_label,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(qapp, tmp_path):
    db_engine = DatabaseEngine(db_path=tmp_path / "batch.db")
    with db_engine.get_session() as session:
        session.add(ProjectModel(id="p1", name="Proj 1"))
        for did in ("d1", "d2"):
            session.add(DrawingModel(
                id=did, project_id="p1", file_path=f"/tmp/{did}.pdf",
                file_name=f"{did}.pdf", file_size_bytes=10, file_hash_sha256=did,
                total_pages=1,
            ))
        for i, did in enumerate(("d1", "d2"), start=1):
            session.add(CommentModel(
                id=f"c{i}", drawing_id=did, page_number=1, raw_text=f"note {i}",
                category_name="Technical", status="Pending",
            ))
        session.commit()

    service = AnalyticsService(db_engine)

    class MockController:
        current_department_name = None
        current_batch_drawing_ids = ["d1"]

        def __init__(self):
            self.kpi_calls = []

        def get_all_projects(self):
            return [{"id": "p1", "name": "Proj 1"}]

        def get_all_departments(self):
            return [{"id": "DEPT-1", "name": "Piping Engineering"}]

        def get_all_categories(self):
            return [{"name": "Technical"}]

        def get_all_drawings(self, project_id=None, department_id=None):
            return [{"id": "d1", "file_name": "d1.pdf"},
                    {"id": "d2", "file_name": "d2.pdf"}]

        def get_batch_drawings(self):
            return [d for d in self.get_all_drawings()
                    if d["id"] in self.current_batch_drawing_ids]

        def get_dashboard_kpis(self, **kwargs):
            self.kpi_calls.append(kwargs)
            return service.get_global_kpis(**kwargs)

        def get_pareto_analysis(self, **kwargs):
            return service.get_pareto_analysis(**kwargs)

        def get_category_distribution(self, **kwargs):
            return service.get_category_distribution(**kwargs)

        def get_status_trend(self, **kwargs):
            return service.get_status_trend(**kwargs)

    controller = MockController()
    return AnalyticsPage(controller=controller), controller


def _select_current_batch(pg):
    idx = pg._batch_cb.findData(CURRENT_BATCH)
    assert idx >= 0, "Current Batch option must always be offered"
    pg._batch_cb.setCurrentIndex(idx)


def _kpi_total(pg) -> str:
    return pg._kpi_cards[0].findChild(QLabel, "KpiValue").text()


def test_batch_label_grammar():
    assert batch_option_label(1) == "⚡ Current Batch (1 Drawing)"
    assert batch_option_label(2) == "⚡ Current Batch (2 Drawings)"
    assert batch_option_label(0) == "⚡ Current Batch (0 Drawings)"


def test_current_batch_option_exists_with_a_non_empty_batch(page):
    pg, _ = page
    assert pg._batch_cb.findData(CURRENT_BATCH) >= 0
    assert pg._batch_cb.itemText(pg._batch_cb.findData(CURRENT_BATCH)) == batch_option_label(1)


def test_current_batch_option_survives_an_empty_batch(page):
    """The entry must not disappear — that is what used to reset the user to All."""
    pg, ctrl = page
    _select_current_batch(pg)
    ctrl.current_batch_drawing_ids = []
    pg.reload_data()

    assert pg._batch_cb.findData(CURRENT_BATCH) >= 0
    assert pg._batch_cb.currentData() == CURRENT_BATCH
    assert pg._batch_cb.currentText() == batch_option_label(0)


def test_empty_batch_filters_to_zero_rows(page):
    pg, ctrl = page
    _select_current_batch(pg)
    ctrl.current_batch_drawing_ids = []
    ctrl.kpi_calls.clear()
    pg.reload_data()

    filters = pg._get_active_filters()
    assert filters["is_current_batch"] is True
    assert filters["drawing_ids"] == []

    assert ctrl.kpi_calls, "KPI cards must still be built from a query"
    assert ctrl.kpi_calls[-1]["drawing_ids"] == []
    assert _kpi_total(pg) == "0"


def test_empty_batch_shows_explicit_empty_state(page):
    pg, ctrl = page
    _select_current_batch(pg)
    ctrl.current_batch_drawing_ids = []
    pg.reload_data()

    labels = [lbl.text() for lbl in pg.findChildren(QLabel)]
    assert EMPTY_BATCH_MESSAGE in labels


def test_non_empty_batch_does_not_show_the_empty_state(page):
    pg, ctrl = page
    _select_current_batch(pg)
    pg.reload_data()

    labels = [lbl.text() for lbl in pg.findChildren(QLabel)]
    assert EMPTY_BATCH_MESSAGE not in labels
    assert _kpi_total(pg) == "1"   # only the batched drawing d1


def test_selection_is_sticky_across_a_batch_that_refills(page):
    pg, ctrl = page
    _select_current_batch(pg)
    ctrl.current_batch_drawing_ids = []
    pg.reload_data()
    ctrl.current_batch_drawing_ids = ["d1", "d2"]
    pg.reload_data()

    assert pg._batch_cb.currentData() == CURRENT_BATCH
    assert pg._batch_cb.currentText() == batch_option_label(2)
    assert _kpi_total(pg) == "2"


def test_switching_away_from_current_batch_widens_deliberately(page):
    pg, ctrl = page
    _select_current_batch(pg)
    ctrl.current_batch_drawing_ids = []
    pg.reload_data()

    pg._batch_cb.setCurrentIndex(pg._batch_cb.findData(""))
    assert pg._get_active_filters()["drawing_ids"] is None
    assert _kpi_total(pg) == "2"
