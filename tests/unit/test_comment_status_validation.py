"""
A14: CommentRepository.update_comment_status must reject unknown statuses.

Previously it logged a warning and wrote the value anyway, which let a typo or a
stale UI vocabulary land in comments.status and silently break every aggregate
that groups by status (Pending + Approved + Rejected + Flagged == total).
"""
import pytest

from src.infrastructure.storage.models import (
    VALID_COMMENT_STATUSES,
    CommentModel,
    DrawingModel,
)
from src.infrastructure.storage.repository import CommentRepository, DatabaseEngine


@pytest.fixture
def comment_repo(tmp_path):
    db_engine = DatabaseEngine(db_path=tmp_path / "status_validation.db")
    with db_engine.get_session() as session:
        session.add(DrawingModel(
            id="d1",
            file_path="/tmp/test.pdf",
            file_name="test.pdf",
            file_size_bytes=1024,
            file_hash_sha256="abc123",
            total_pages=1,
        ))
        session.add(CommentModel(
            id="c1",
            drawing_id="d1",
            page_number=1,
            raw_text="check beam clearance",
            status="Pending",
        ))
        session.commit()
    return CommentRepository(db_engine)


@pytest.mark.parametrize("status", sorted(VALID_COMMENT_STATUSES))
def test_valid_statuses_are_written(comment_repo, status):
    assert comment_repo.update_comment_status("c1", status) is True
    assert comment_repo.get_comment_by_id("c1")["status"] == status


@pytest.mark.parametrize(
    "status",
    ["approved", "APPROVED", "Approve", "Done", "Escalated", "", None],
)
def test_unknown_statuses_are_rejected_without_writing(comment_repo, status):
    assert comment_repo.update_comment_status("c1", status) is False
    assert comment_repo.get_comment_by_id("c1")["status"] == "Pending"


def test_rejected_status_writes_no_audit_row(comment_repo):
    from src.infrastructure.storage.models import AuditLogModel

    comment_repo.update_comment_status("c1", "NotAStatus")
    with comment_repo._db.get_session() as session:
        assert session.query(AuditLogModel).count() == 0


def test_valid_transition_records_audit_row(comment_repo):
    from src.infrastructure.storage.models import AuditLogModel

    comment_repo.update_comment_status("c1", "Approved", changed_by_user_id="u-42")
    with comment_repo._db.get_session() as session:
        row = session.query(AuditLogModel).one()
    assert row.action == "approve"
    assert row.old_value == "Pending"
    assert row.new_value == "Approved"
    assert row.reviewer_name == "u-42"
