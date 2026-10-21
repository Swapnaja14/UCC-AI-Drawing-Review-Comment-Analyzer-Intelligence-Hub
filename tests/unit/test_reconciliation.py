"""
tests/unit/test_reconciliation.py
Unit tests for B5: Verification and reconciliation tool.
Tests parity checks, metric diff detection, and report generation.
"""
from pathlib import Path
import pytest
from sqlalchemy import func

from scripts.reconcile_databases import DatabaseReconciler
from src.infrastructure.storage.repository import DatabaseEngine
from src.infrastructure.storage.models import (
    Base,
    CommentModel,
    DrawingModel,
    EngineeringDepartmentModel,
)


def test_database_reconciler_parity(tmp_path):
    """Verify reconciler confirms 100% parity on identical source and target."""
    db_source = tmp_path / "source.db"
    db_target = tmp_path / "target.db"

    src_engine = DatabaseEngine(db_path=db_source)
    tgt_engine = DatabaseEngine(db_path=db_target)

    # Insert identical records
    for eng in (src_engine, tgt_engine):
        with eng.get_session() as sess:
            dept = EngineeringDepartmentModel(id="DEPT-1", name="Piping")
            dwg = DrawingModel(
                id="DWG-1",
                file_path="/test.pdf",
                file_name="test.pdf",
                file_size_bytes=100,
                file_hash_sha256="hash",
                total_pages=1,
            )
            cmt = CommentModel(
                id="C-1",
                drawing_id=dwg.id,
                page_number=1,
                raw_text="Test",
                category_name="Technical",
                status="Approved",
                confidence=0.9,
                is_verified_by_human=True,
            )
            sess.add_all([dept, dwg, cmt])
            sess.commit()

    reconciler = DatabaseReconciler(src_engine, tgt_engine)
    table_counts = reconciler.reconcile_table_counts()
    comment_metrics = reconciler.reconcile_comment_metrics()
    analytics_parity = reconciler.reconcile_analytics_services()

    # Verify table counts match
    dept_stat = next(tc for tc in table_counts if tc["table"] == "engineering_departments")
    assert dept_stat["match"] is True
    assert dept_stat["diff"] == 0

    # Verify comment metrics match
    assert comment_metrics["confidence_sum"]["match"] is True
    assert comment_metrics["status"]["match"] is True
    assert comment_metrics["category"]["match"] is True

    # Verify analytics parity
    assert analytics_parity["kpis_match"] is True
    assert analytics_parity["category_pie_match"] is True

    # Verify report generation
    report_file = tmp_path / "report.md"
    reconciler.generate_markdown_report(report_file, table_counts, comment_metrics, analytics_parity)
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "✅ MATCH" in content
    assert "✅ 100% PARITY" in content
