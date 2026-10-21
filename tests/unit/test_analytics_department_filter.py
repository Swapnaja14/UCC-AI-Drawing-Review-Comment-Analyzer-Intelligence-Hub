"""
A2 — department filter semantics.

The department lives on the comment, not on the drawing. These tests pin that
single semantic across the KPIs, the drawing dropdown and the "Unassigned"
option, which used to be mapped to None and therefore silently meant "All".
"""
import pytest

from PySide6.QtWidgets import QApplication, QLabel

from src.infrastructure.storage.repository import DatabaseEngine
from src.infrastructure.storage.models import (
    ProjectModel, DrawingModel, PageModel, CommentModel, EngineeringDepartmentModel,
)
from src.services.analytics_service import AnalyticsService


@pytest.fixture
def env(tmp_path):
    db_engine = DatabaseEngine(db_path=tmp_path / "dept.db")
    with db_engine.get_session() as session:
        piping = session.query(EngineeringDepartmentModel).filter_by(name="Piping Engineering").first()
        struct = session.query(EngineeringDepartmentModel).filter_by(name="Structural & Physical Design").first()
        assert piping and struct, "DatabaseEngine must seed the official departments"

        session.add(ProjectModel(id="p1", name="Proj 1"))
        # dwg_pipe is filed under Piping but every comment on it is Structural.
        for did, dept_id in (("dwg_pipe", piping.id), ("dwg_struct", struct.id), ("dwg_none", None)):
            session.add(DrawingModel(
                id=did, project_id="p1", department_id=dept_id,
                file_path=f"/tmp/{did}.pdf", file_name=f"{did}.pdf",
                file_size_bytes=10, file_hash_sha256=did, total_pages=1,
            ))
            session.add(PageModel(
                id=f"pg_{did}", drawing_id=did, page_number=1,
                width_pt=612.0, height_pt=792.0, aspect_ratio=0.77,
            ))

        # (id, drawing, department id)
        for cid, did, dept_id in (
            ("a1", "dwg_pipe", struct.id),
            ("a2", "dwg_pipe", struct.id),
            ("b1", "dwg_struct", piping.id),
            ("c1", "dwg_none", None),
            ("c2", "dwg_none", None),
            ("d1", "dwg_struct", None),
        ):
            session.add(CommentModel(
                id=cid, drawing_id=did, department_id=dept_id, page_number=1,
                raw_text=f"note {cid}", category_name="Technical", status="Pending",
            ))
        session.commit()

    return db_engine, AnalyticsService(db_engine)


def test_unassigned_selects_null_department_not_everything(env):
    _, service = env
    kpis = service.get_global_kpis(department_name="Unassigned")
    assert kpis.total_comments == 3          # c1, c2, d1
    assert kpis.total_drawings == 2          # dwg_none, dwg_struct
    assert service.get_global_kpis().total_comments == 6


def test_department_filter_uses_the_comment_not_the_drawing(env):
    """dwg_pipe is filed under Piping but carries only Structural comments."""
    _, service = env

    piping = service.get_global_kpis(department_name="Piping Engineering")
    assert piping.total_comments == 1        # b1 only
    assert piping.total_drawings == 1        # dwg_struct, not dwg_pipe
    assert piping.total_pages == 1

    struct = service.get_global_kpis(department_name="Structural & Physical Design")
    assert struct.total_comments == 2        # a1, a2
    assert struct.total_drawings == 1        # dwg_pipe
    assert struct.total_pages == 1


def test_department_with_no_comments_is_empty_not_widened(env):
    _, service = env
    kpis = service.get_global_kpis(department_name="Electrical Engineering")
    assert kpis.total_comments == 0
    assert kpis.total_drawings == 0
    assert kpis.total_pages == 0
    assert kpis.total_projects == 0


def test_drawing_options_match_the_kpi_drawing_count(env):
    _, service = env
    for dept in ("Piping Engineering", "Structural & Physical Design", "Unassigned", None):
        options = service.get_drawing_options(department_name=dept)
        kpis = service.get_global_kpis(department_name=dept)
        assert len(options) == kpis.total_drawings, dept


def test_drawing_options_are_lightweight_and_department_scoped(env):
    _, service = env
    options = service.get_drawing_options(department_name="Structural & Physical Design")
    assert options == [{"id": "dwg_pipe", "file_name": "dwg_pipe.pdf", "comments_count": 2}]

    # Without a department filter, drawings that have no comments still appear.
    all_options = {o["id"]: o["comments_count"] for o in service.get_drawing_options()}
    assert all_options == {"dwg_none": 2, "dwg_pipe": 2, "dwg_struct": 2}


def test_drawing_options_respect_batch_and_project_scope(env):
    _, service = env
    assert service.get_drawing_options(drawing_ids=[]) == []
    assert [o["id"] for o in service.get_drawing_options(drawing_ids=["dwg_none"])] == ["dwg_none"]
    assert service.get_drawing_options(project_id="missing") == []


def test_department_options_reports_unassigned_availability(env):
    _, service = env
    options = service.get_department_options()
    assert options["has_unassigned"] is True
    assert "Piping Engineering" in options["departments"]
    assert "Unassigned" not in options["departments"]   # the UI adds it as a sentinel


def test_department_options_without_unassigned_rows(tmp_path):
    db_engine = DatabaseEngine(db_path=tmp_path / "dept2.db")
    with db_engine.get_session() as session:
        piping = session.query(EngineeringDepartmentModel).filter_by(name="Piping Engineering").first()
        session.add(ProjectModel(id="p1", name="Proj 1"))
        session.add(DrawingModel(
            id="d1", project_id="p1", file_path="/tmp/d1.pdf", file_name="d1.pdf",
            file_size_bytes=10, file_hash_sha256="d1", total_pages=1,
        ))
        session.add(CommentModel(
            id="c1", drawing_id="d1", department_id=piping.id, page_number=1,
            raw_text="note", category_name="Technical", status="Pending",
        ))
        session.commit()

    assert AnalyticsService(db_engine).get_department_options()["has_unassigned"] is False


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _build_page(qapp, env):
    from app.screens.analytics_screen import AnalyticsPage

    _, service = env

    class MockController:
        current_department_name = None
        current_batch_drawing_ids = []

        def get_all_projects(self):
            return [{"id": "p1", "name": "Proj 1"}]

        def get_department_options(self):
            return service.get_department_options()

        def get_all_categories(self):
            return [{"name": "Technical"}]

        def get_drawing_options(self, project_id=None, department_name=None, drawing_ids=None):
            return service.get_drawing_options(
                project_id=project_id, department_name=department_name, drawing_ids=drawing_ids
            )

        def get_dashboard_kpis(self, **kwargs):
            return service.get_global_kpis(**kwargs)

        def get_pareto_analysis(self, **kwargs):
            return service.get_pareto_analysis(**kwargs)

        def get_category_distribution(self, **kwargs):
            return service.get_category_distribution(**kwargs)

        def get_status_trend(self, **kwargs):
            return service.get_status_trend(**kwargs)

    return AnalyticsPage(controller=MockController()), service


def test_ui_offers_unassigned_and_passes_it_through(qapp, env):
    from app.screens.analytics_screen import UNASSIGNED_DEPARTMENT

    page, service = _build_page(qapp, env)
    idx = page._dept_cb.findText(UNASSIGNED_DEPARTMENT)
    assert idx >= 0, "Unassigned must be offered while such rows exist"

    page._dept_cb.setCurrentIndex(idx)
    assert page._get_active_filters()["department_name"] == UNASSIGNED_DEPARTMENT
    assert page._kpi_cards[0].findChild(QLabel, "KpiValue").text() == "3"

    drawing_ids = [page._dwg_cb.itemData(i) for i in range(page._dwg_cb.count())]
    assert drawing_ids == ["", "dwg_none", "dwg_struct"]


def test_ui_does_not_offer_unassigned_without_rows(qapp, tmp_path):
    from app.screens.analytics_screen import AnalyticsPage, UNASSIGNED_DEPARTMENT

    db_engine = DatabaseEngine(db_path=tmp_path / "dept3.db")
    with db_engine.get_session() as session:
        piping = session.query(EngineeringDepartmentModel).filter_by(name="Piping Engineering").first()
        session.add(ProjectModel(id="p1", name="Proj 1"))
        session.add(DrawingModel(
            id="d1", project_id="p1", file_path="/tmp/d1.pdf", file_name="d1.pdf",
            file_size_bytes=10, file_hash_sha256="d1", total_pages=1,
        ))
        session.add(CommentModel(
            id="c1", drawing_id="d1", department_id=piping.id, page_number=1,
            raw_text="note", category_name="Technical", status="Pending",
        ))
        session.commit()
    service = AnalyticsService(db_engine)

    class MockController:
        current_department_name = None
        current_batch_drawing_ids = []

        def get_all_projects(self):
            return []

        def get_department_options(self):
            return service.get_department_options()

        def get_all_categories(self):
            return [{"name": "Technical"}]

        def get_drawing_options(self, project_id=None, department_name=None, drawing_ids=None):
            return service.get_drawing_options(
                project_id=project_id, department_name=department_name, drawing_ids=drawing_ids
            )

        def get_dashboard_kpis(self, **kwargs):
            return service.get_global_kpis(**kwargs)

        def get_pareto_analysis(self, **kwargs):
            return service.get_pareto_analysis(**kwargs)

        def get_category_distribution(self, **kwargs):
            return service.get_category_distribution(**kwargs)

        def get_status_trend(self, **kwargs):
            return service.get_status_trend(**kwargs)

    page = AnalyticsPage(controller=MockController())
    assert page._dept_cb.findText(UNASSIGNED_DEPARTMENT) < 0


def test_ui_department_selection_narrows_the_drawing_list(qapp, env):
    page, _ = _build_page(qapp, env)

    idx = page._dept_cb.findText("Piping Engineering")
    page._dept_cb.setCurrentIndex(idx)

    drawing_ids = [page._dwg_cb.itemData(i) for i in range(page._dwg_cb.count())]
    assert drawing_ids == ["", "dwg_struct"]
    assert page._kpi_cards[0].findChild(QLabel, "KpiValue").text() == "1"
