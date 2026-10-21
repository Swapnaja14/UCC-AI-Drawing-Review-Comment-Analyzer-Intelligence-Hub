"""
A3 — Pareto correctness.

The cumulative line used to be computed over the truncated top-N slice, so it
always hit 100% on the last visible bar, and it was drawn on the count axis
after being rescaled — there was no percentage axis at all. These tests pin the
full-population denominator, the stable ordering, the leftover-bucket placement,
tail grouping that still reconciles, and the chart's dual axes.
"""
import pytest

from PySide6.QtWidgets import QApplication
from PySide6.QtCharts import QValueAxis, QBarCategoryAxis, QBarSeries

from src.infrastructure.storage.repository import DatabaseEngine
from src.infrastructure.storage.models import ProjectModel, DrawingModel, CommentModel
from src.core.dtos.analytics_dtos import CategoryDistributionDTO
from src.services.analytics_service import AnalyticsService
from app.components.charts import build_pareto_chart


#: name -> number of comments. Uncategorized deliberately has the most.
COUNTS = {"Uncategorized": 6, "Technical": 5, "Dimension": 3, "Drafting": 3, "Standards": 1}
TOTAL = sum(COUNTS.values())   # 18


@pytest.fixture
def service(tmp_path):
    db_engine = DatabaseEngine(db_path=tmp_path / "pareto.db")
    with db_engine.get_session() as session:
        session.add(ProjectModel(id="p1", name="Proj 1"))
        session.add(DrawingModel(
            id="d1", project_id="p1", file_path="/tmp/d1.pdf", file_name="d1.pdf",
            file_size_bytes=10, file_hash_sha256="d1", total_pages=1,
        ))
        n = 0
        for name, count in COUNTS.items():
            for _ in range(count):
                n += 1
                session.add(CommentModel(
                    id=f"c{n}", drawing_id="d1", page_number=1, raw_text=f"note {n}",
                    category_name=(None if name == "Uncategorized" else name),
                    status="Pending",
                ))
        session.commit()
    return AnalyticsService(db_engine)


def test_cumulative_is_measured_against_the_full_total(service):
    pareto = service.get_pareto_analysis(top_n=3)
    assert [p.category_name for p in pareto] == ["Technical", "Dimension", "Drafting"]
    assert [p.count for p in pareto] == [5, 3, 3]

    # 5, 8 and 11 of 18 — not of 11, which is all the visible bars add up to.
    assert pareto[0].cumulative_percentage == pytest.approx(5 / TOTAL * 100)
    assert pareto[1].cumulative_percentage == pytest.approx(8 / TOTAL * 100)
    assert pareto[2].cumulative_percentage == pytest.approx(11 / TOTAL * 100)
    assert pareto[-1].cumulative_percentage < 100.0
    assert [p.cumulative_count for p in pareto] == [5, 8, 11]


def test_ordering_is_stable_and_leftovers_come_last(service):
    pareto = service.get_pareto_analysis(top_n=50)
    names = [p.category_name for p in pareto]

    # Uncategorized has the highest count but is a leftover, so it is drawn last.
    assert names[-1] == "Uncategorized"
    # Equal counts break ties on the name, ascending.
    assert names.index("Dimension") < names.index("Drafting")
    assert names == ["Technical", "Dimension", "Drafting", "Standards", "Uncategorized"]
    assert pareto[-1].cumulative_percentage == pytest.approx(100.0)


def test_grouped_tail_reconciles_with_the_population(service):
    grouped = service.get_pareto_analysis(top_n=3, group_tail=True)
    assert [g.category_name for g in grouped] == ["Technical", "Dimension", "Drafting", "Other"]
    assert sum(g.count for g in grouped) == TOTAL
    assert grouped[-1].count == 7            # Standards 1 + Uncategorized 6
    assert grouped[-1].cumulative_percentage == pytest.approx(100.0)


def test_ungrouped_tail_does_not_invent_an_other_bucket(service):
    truncated = service.get_pareto_analysis(top_n=3, group_tail=False)
    assert "Other" not in [t.category_name for t in truncated]
    assert sum(t.count for t in truncated) < TOTAL


def test_empty_population_has_no_cumulative(service):
    assert service.get_pareto_analysis(drawing_ids=[]) == []
    empty = service.get_pareto_analysis(category_name="Cosmetic")
    assert empty == []


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _items():
    running = 0
    out = []
    for name, count in (("Technical", 5), ("Dimension", 3), ("Drafting", 3),
                        ("Standards", 1), ("Uncategorized", 6)):
        running += count
        out.append(CategoryDistributionDTO(
            category_name=name, count=count,
            percentage=count / TOTAL * 100.0, color_hex="#3E9BFF",
            cumulative_count=running, cumulative_percentage=running / TOTAL * 100.0,
        ))
    return out


def test_chart_has_a_dedicated_percentage_axis(qapp):
    view = build_pareto_chart(_items()[:3], title="Pareto", total=TOTAL)
    chart = view.chart()

    pct_axes = [a for a in chart.axes()
                if isinstance(a, QValueAxis) and a.titleText() == "Cumulative %"]
    count_axes = [a for a in chart.axes()
                  if isinstance(a, QValueAxis) and a.titleText() == "Comments"]
    assert len(pct_axes) == 1 and len(count_axes) == 1
    assert (pct_axes[0].min(), pct_axes[0].max()) == (0, 100)

    cat_axes = [a for a in chart.axes() if isinstance(a, QBarCategoryAxis)]
    assert len(cat_axes) == 1 and cat_axes[0].titleText() == "Category"


def test_cumulative_line_uses_the_percentage_axis_only(qapp):
    view = build_pareto_chart(_items()[:3], title="Pareto", total=TOTAL)
    chart = view.chart()

    line = next(s for s in chart.series() if s.name() == "Cumulative %")
    bars = next(s for s in chart.series() if isinstance(s, QBarSeries))
    pct_axis = next(a for a in chart.axes()
                    if isinstance(a, QValueAxis) and a.titleText() == "Cumulative %")
    count_axis = next(a for a in chart.axes()
                      if isinstance(a, QValueAxis) and a.titleText() == "Comments")

    assert pct_axis in line.attachedAxes()
    assert count_axis not in line.attachedAxes()
    assert count_axis in bars.attachedAxes()
    assert pct_axis not in bars.attachedAxes()

    # Raw percentages, no rescaling onto the count axis.
    assert line.at(0).y() == pytest.approx(5 / TOTAL * 100)
    assert line.at(2).y() == pytest.approx(11 / TOTAL * 100)


def test_chart_legend_visible_and_reference_line_drawn(qapp):
    view = build_pareto_chart(_items()[:3], title="Pareto", total=TOTAL)
    chart = view.chart()
    assert chart.legend().isVisible()
    ref = next(s for s in chart.series() if s.name() == "80% reference")
    assert ref.at(0).y() == pytest.approx(80.0)

    without_view = build_pareto_chart(_items()[:3], title="Pareto", total=TOTAL,
                                      reference_line=None)
    assert all(s.name() != "80% reference" for s in without_view.chart().series())


def test_chart_falls_back_to_visible_counts_without_a_total(qapp):
    """Plain counts still produce a cumulative line that ends at 100%."""
    plain = [CategoryDistributionDTO(category_name="A", count=1, percentage=50.0),
             CategoryDistributionDTO(category_name="B", count=1, percentage=50.0)]
    view = build_pareto_chart(plain, title="Pareto")
    line = next(s for s in view.chart().series() if s.name() == "Cumulative %")
    assert line.at(1).y() == pytest.approx(100.0)


def test_chart_handles_empty_input(qapp):
    view = build_pareto_chart([], title="Pareto")
    axis = next(a for a in view.chart().axes() if isinstance(a, QBarCategoryAxis))
    assert axis.categories() == ["No Data"]
