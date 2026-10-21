"""
A13b: reviewer attribution through VerificationService -> CommentRepository.

VerificationService.approve/reject/flag called update_comment_status without the
acting user, so every audit row was written as reviewer_name="reviewer" with a
NULL user_id. _log_audit then matched that row as already persisted and tried to
attach the reviewer's notes through an ORM model it never imported, raising a
NameError that the surrounding try/except swallowed - so notes were lost too.
"""
import pytest

from src.infrastructure.storage.models import CommentModel, DrawingModel, UserModel
from src.infrastructure.storage.repository import (
    AuditLogRepository,
    CommentRepository,
    DatabaseEngine,
)
from src.services.verification_service import VerificationService


@pytest.fixture
def env(tmp_path):
    db_engine = DatabaseEngine(db_path=tmp_path / "attribution.db")
    with db_engine.get_session() as session:
        session.add(UserModel(
            id="u-lead", username="jdoe", display_name="Jane Doe",
        ))
        session.add(DrawingModel(
            id="d1", file_path="/tmp/test.pdf", file_name="test.pdf",
            file_size_bytes=1024, file_hash_sha256="abc123", total_pages=1,
        ))
        session.add(CommentModel(
            id="c1", drawing_id="d1", page_number=1,
            raw_text="check beam clearance", status="Pending",
        ))
        session.commit()

    comment_repo = CommentRepository(db_engine)
    audit_repo = AuditLogRepository(db_engine)
    service = VerificationService(comment_repo, audit_repo)
    return db_engine, service, audit_repo


def _audit_rows(db_engine, comment_id="c1"):
    from src.infrastructure.storage.models import AuditLogModel
    with db_engine.get_session() as session:
        return (
            session.query(AuditLogModel)
            .filter(AuditLogModel.comment_id == comment_id)
            .all()
        )


def test_approve_attributes_the_acting_user(env):
    db_engine, service, _ = env
    assert service.approve_comment("c1", "u-lead", notes="Looks correct") is True

    rows = _audit_rows(db_engine)
    assert len(rows) == 1
    assert rows[0].action == "approve"
    assert rows[0].user_id == "u-lead"
    assert rows[0].reviewer_name == "Jane Doe"


def test_reviewer_notes_are_attached_not_lost(env):
    db_engine, service, _ = env
    service.reject_comment("c1", "u-lead", notes="Superseded by rev C")

    rows = _audit_rows(db_engine)
    assert len(rows) == 1
    assert rows[0].notes == "Superseded by rev C"


@pytest.mark.parametrize(
    "method,expected_action,expected_status",
    [
        ("approve_comment", "approve", "Approved"),
        ("reject_comment", "reject", "Rejected"),
        ("flag_comment", "flag", "Flagged"),
    ],
)
def test_each_action_writes_exactly_one_attributed_row(
    env, method, expected_action, expected_status
):
    db_engine, service, _ = env
    assert getattr(service, method)("c1", "u-lead", notes="note") is True

    rows = _audit_rows(db_engine)
    assert len(rows) == 1
    assert rows[0].action == expected_action
    assert rows[0].new_value == expected_status
    assert rows[0].user_id == "u-lead"


def test_unknown_reviewer_id_is_recorded_verbatim_not_anonymised(env):
    db_engine, service, _ = env
    service.approve_comment("c1", "external-contractor", notes="")

    rows = _audit_rows(db_engine)
    assert rows[0].user_id is None
    assert rows[0].reviewer_name == "external-contractor"


def test_missing_reviewer_falls_back_to_placeholder(env):
    db_engine, service, _ = env
    service.approve_comment("c1", "", notes="")

    rows = _audit_rows(db_engine)
    assert rows[0].user_id is None
    assert rows[0].reviewer_name == "reviewer"


def test_audit_rows_are_exposed_through_the_service(env):
    _, service, _ = env
    service.flag_comment("c1", "u-lead", notes="needs senior review")

    history = service.get_audit_log("c1")
    assert len(history) == 1
    assert history[0].action == "flag"
    assert history[0].notes == "needs senior review"
