"""
tests/unit/test_dialect_audit.py
Tests for B3: Dialect-agnostic queries across SQLite and PostgreSQL.
Audits queries for GROUP BY expressions, boolean handling (.is_(True/False)),
case statements, string normalization (coalesce, trim, upper, lower), and false() conditions.
"""
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from sqlalchemy import text

from src.infrastructure.storage.repository import DatabaseEngine
from src.infrastructure.storage.models import (
    Base,
    CommentModel,
    DrawingModel,
    PageModel,
    ProjectModel,
    CategoryModel,
    EngineeringDepartmentModel,
    UserModel,
    AuditLogModel,
    VALID_COMMENT_STATUSES,
)
from src.services.analytics_service import AnalyticsService, _category_clean, _status_clean


def _setup_test_db(engine: DatabaseEngine):
    """Populate test database with varied data testing dialect edge cases."""
    Base.metadata.drop_all(bind=engine.engine)
    Base.metadata.create_all(bind=engine.engine)

    with engine.get_session() as session:
        dept = EngineeringDepartmentModel(id="DEPT-1", name="Piping Engineering")
        proj = ProjectModel(id="PROJ-1", name="Test Project")
        cat1 = CategoryModel(id="CAT-1", name="Dimension", color_hex="#3E9BFF")
        cat2 = CategoryModel(id="CAT-2", name="Welding", color_hex="#10B981")
        user = UserModel(id="user-1", username="alice", display_name="Alice Smith", role="Reviewer")
        session.add_all([dept, proj, cat1, cat2, user])
        session.flush()

        dwg = DrawingModel(
            id="DWG-1",
            project_id=proj.id,
            department_id=dept.id,
            file_path="/path/test.pdf",
            file_name="test.pdf",
            file_size_bytes=1000,
            file_hash_sha256="hash123",
            total_pages=1,
        )
        session.add(dwg)
        session.flush()

        # Add comments with varied casing, whitespace, and statuses to test GROUP BY and case()
        now = datetime.now(timezone.utc)
        comments = [
            CommentModel(
                id="C-1",
                drawing_id=dwg.id,
                department_id=dept.id,
                page_number=1,
                raw_text="Dimension check required",
                category_name="Dimension",
                initial_category="dimension",
                confidence=0.95,
                classification_confidence=0.95,
                classification_method="ai_model",
                fallback_used=False,
                status="Approved",
                is_verified_by_human=True,
                created_at=now,
            ),
            CommentModel(
                id="C-2",
                drawing_id=dwg.id,
                department_id=dept.id,
                page_number=1,
                raw_text="Dimension incorrect",
                category_name="  dimension  ",  # Trimming test
                initial_category="Dimension",
                confidence=0.75,
                classification_confidence=0.75,
                classification_method="ai_model",
                fallback_used=False,
                status="Rejected",
                is_verified_by_human=True,
                created_at=now - timedelta(days=1),
            ),
            CommentModel(
                id="C-3",
                drawing_id=dwg.id,
                department_id=dept.id,
                page_number=1,
                raw_text="Unclear symbol",
                category_name=None,  # Null category -> Uncategorized
                confidence=0.50,
                classification_confidence=0.50,
                classification_method="rule_fallback",
                fallback_used=True,
                status="Flagged",
                ocr_engine="OCR Failed",
                is_verified_by_human=False,
                created_at=now - timedelta(days=2),
            ),
            CommentModel(
                id="C-4",
                drawing_id=dwg.id,
                department_id=dept.id,
                page_number=1,
                raw_text="Welding symbol missing",
                category_name="Welding",
                confidence=0.85,
                classification_confidence=0.85,
                classification_method="ai_model",
                fallback_used=False,
                status="Pending",
                is_verified_by_human=False,
                created_at=now,
            ),
        ]
        session.add_all(comments)

        audit = AuditLogModel(
            id="AUD-1",
            comment_id="C-1",
            action="approve",
            user_id="user-1",
            reviewer_name="Alice Smith",
            timestamp=now,
        )
        session.add(audit)
        session.commit()


@pytest.fixture(params=["sqlite", "postgresql"])
def dialect_engine(request, tmp_path):
    """Fixture providing database engines for both SQLite and PostgreSQL backends."""
    backend = request.param
    if backend == "sqlite":
        db_path = tmp_path / "dialect_test.db"
        engine = DatabaseEngine(db_path=db_path)
        _setup_test_db(engine)
        yield engine
    elif backend == "postgresql":
        pg_url = os.environ.get("UCC_POSTGRES_TEST_URL")
        if not pg_url:
            pytest.skip("UCC_POSTGRES_TEST_URL not set; skipping live PostgreSQL dialect test")
        engine = DatabaseEngine(url=pg_url)
        _setup_test_db(engine)
        yield engine


def test_dialect_global_kpis_query(dialect_engine):
    """Verify that get_global_kpis runs without error and computes correct aggregates."""
    service = AnalyticsService(dialect_engine)
    kpis = service.get_global_kpis()

    assert kpis.total_comments == 4
    assert kpis.approved_count == 1
    assert kpis.rejected_count == 1
    assert kpis.pending_count == 1
    assert kpis.flagged_count == 1
    assert kpis.human_reviewed_count == 2
    assert kpis.flagged_ocr_failed_count == 1


def test_dialect_category_distribution_group_by(dialect_engine):
    """Verify GROUP BY on normalized category expressions works correctly."""
    service = AnalyticsService(dialect_engine)
    dist = service.get_category_distribution()

    # Dimension and "  dimension  " should merge into "Dimension"
    names = {d.category_name for d in dist}
    assert "Dimension" in names
    dim_dto = next(d for d in dist if d.category_name == "Dimension")
    assert dim_dto.count == 2


def test_dialect_reviewer_metrics_group_by(dialect_engine):
    """Verify AuditLogModel aggregation with COALESCE and LOWER works cleanly."""
    service = AnalyticsService(dialect_engine)
    reviewers = service.get_reviewer_metrics()

    assert len(reviewers) >= 1
    alice = next(r for r in reviewers if r.reviewer_name == "Alice Smith")
    assert alice.approved == 1
    assert alice.comments_reviewed == 1


def test_dialect_false_condition_queries(dialect_engine):
    """Verify false() conditions return empty results rather than syntax errors."""
    service = AnalyticsService(dialect_engine)
    # Passing empty drawing_ids triggers the false() branch
    kpis = service.get_global_kpis(drawing_ids=[])
    assert kpis.total_comments == 0
