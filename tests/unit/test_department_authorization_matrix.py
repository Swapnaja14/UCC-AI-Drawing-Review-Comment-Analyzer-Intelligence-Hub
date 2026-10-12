"""
tests/unit/test_department_authorization_matrix.py

Isolated regression test suite verifying backend-enforced department-level
authorization and the interim NULL-department policy on comment and drawing mutations.

Coverage:
1. Same-department comment modification succeeds.
2. Cross-department comment modification is denied and prevented.
3. Department-scoped user cannot modify unassigned drawing comments.
4. Administrative role (Lead Engineer / Admin) override on unassigned drawing comments.
5. Unscoped non-admin user (NULL dept, role='User') is denied.
6. Missing identity or invalid comment/drawing is safely denied.
7. Drawing-level reprocessing authorization (same-dept allowed, cross-dept denied, unassigned rules).
8. Comprehensive mutation prevention across text, category, department, and reviewer updates.
9. GUI signal compatibility (processing_error_signal emitted with clear reason).
10. Audit logging failure resilience (audit error does not permit an unauthorized mutation).
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.infrastructure.storage.models import (
    Base,
    CommentModel,
    DrawingModel,
    PageModel,
    UserModel,
    AuditLogModel,
)
from src.infrastructure.storage.repository import (
    DatabaseEngine,
    EngineeringDepartmentRepository,
)
from src.core.dtos.auth_dtos import UserDTO, SessionTokenDTO
from app.controllers.app_controller import AppController


@pytest.fixture
def test_setup(tmp_path: Path):
    """
    Sets up an isolated, temporary SQLite database with test departments,
    drawings, comments, and users for authorization testing.
    """
    db_file = tmp_path / "test_auth_matrix.db"
    db_engine = DatabaseEngine(db_path=db_file)

    dept_repo = EngineeringDepartmentRepository(db_engine)
    depts = {d["name"]: d["id"] for d in dept_repo.get_all_departments()}
    dept_elec = depts["Electrical Engineering"]
    dept_pipe = depts["Piping Engineering"]

    with db_engine.get_session() as session:
        # 1. Seed Drawings
        dwg_elec = DrawingModel(
            id="DWG-ELEC-100",
            department_id=dept_elec,
            file_path=str(tmp_path / "elec.pdf"),
            file_name="elec.pdf",
            file_size_bytes=1024,
            file_hash_sha256="hash_elec",
            total_pages=1,
            is_scanned=False,
            uploaded_at=datetime.now(timezone.utc),
        )
        dwg_pipe = DrawingModel(
            id="DWG-PIPE-200",
            department_id=dept_pipe,
            file_path=str(tmp_path / "pipe.pdf"),
            file_name="pipe.pdf",
            file_size_bytes=1024,
            file_hash_sha256="hash_pipe",
            total_pages=1,
            is_scanned=False,
            uploaded_at=datetime.now(timezone.utc),
        )
        dwg_unassigned = DrawingModel(
            id="DWG-UNASSIGNED-300",
            department_id=None,  # Legacy unassigned drawing
            file_path=str(tmp_path / "unassigned.pdf"),
            file_name="unassigned.pdf",
            file_size_bytes=1024,
            file_hash_sha256="hash_unassigned",
            total_pages=1,
            is_scanned=False,
            uploaded_at=datetime.now(timezone.utc),
        )
        session.add_all([dwg_elec, dwg_pipe, dwg_unassigned])
        session.flush()

        # Create dummy PDF files so exists() checks pass for reprocess tests
        (tmp_path / "elec.pdf").write_bytes(b"%PDF-1.4 dummy")
        (tmp_path / "pipe.pdf").write_bytes(b"%PDF-1.4 dummy")
        (tmp_path / "unassigned.pdf").write_bytes(b"%PDF-1.4 dummy")

        # 2. Seed Pages
        p_elec = PageModel(id="PAGE-ELEC", drawing_id=dwg_elec.id, page_number=1, width_pt=595.0, height_pt=842.0, aspect_ratio=0.7)
        p_pipe = PageModel(id="PAGE-PIPE", drawing_id=dwg_pipe.id, page_number=1, width_pt=595.0, height_pt=842.0, aspect_ratio=0.7)
        p_unassigned = PageModel(id="PAGE-UNASSIGNED", drawing_id=dwg_unassigned.id, page_number=1, width_pt=595.0, height_pt=842.0, aspect_ratio=0.7)
        session.add_all([p_elec, p_pipe, p_unassigned])
        session.flush()

        # 3. Seed Comments
        c_elec = CommentModel(
            id="CMT-ELEC-01",
            drawing_id=dwg_elec.id,
            page_id=p_elec.id,
            page_number=1,
            raw_text="Check 480V MCC cable tray clearance",
            cleaned_text="Check 480V MCC cable tray clearance",
            category_name="Electrical",
            status="Pending",
            created_at=datetime.now(timezone.utc),
        )
        c_pipe = CommentModel(
            id="CMT-PIPE-02",
            drawing_id=dwg_pipe.id,
            page_id=p_pipe.id,
            page_number=1,
            raw_text="Revise steam header pipe schedule to SCH 80",
            cleaned_text="Revise steam header pipe schedule to SCH 80",
            category_name="Piping",
            status="Pending",
            created_at=datetime.now(timezone.utc),
        )
        c_unassigned = CommentModel(
            id="CMT-UNASSIGNED-03",
            drawing_id=dwg_unassigned.id,
            page_id=p_unassigned.id,
            page_number=1,
            raw_text="Legacy note without department assignment",
            cleaned_text="Legacy note without department assignment",
            category_name="General",
            status="Pending",
            created_at=datetime.now(timezone.utc),
        )
        session.add_all([c_elec, c_pipe, c_unassigned])
        session.commit()

    # Users
    user_elec = UserDTO(
        user_id="USR-ELEC",
        username="elec_reviewer",
        email="elec@ucc.com",
        role="Reviewer",
        department_id=dept_elec,
        department_name="Electrical Engineering",
    )
    user_pipe = UserDTO(
        user_id="USR-PIPE",
        username="pipe_reviewer",
        email="pipe@ucc.com",
        role="Reviewer",
        department_id=dept_pipe,
        department_name="Piping Engineering",
    )
    user_admin = UserDTO(
        user_id="USR-ADMIN",
        username="admin_lead",
        email="admin@ucc.com",
        role="Lead Engineer",
        department_id=None,
        department_name=None,
    )
    user_unscoped_non_admin = UserDTO(
        user_id="USR-GUEST",
        username="guest_user",
        email="guest@ucc.com",
        role="User",
        department_id=None,
        department_name=None,
    )

    controller = AppController(db_engine=db_engine)

    return {
        "engine": db_engine,
        "controller": controller,
        "users": {
            "elec": user_elec,
            "pipe": user_pipe,
            "admin": user_admin,
            "unscoped": user_unscoped_non_admin,
        },
        "comments": {
            "elec": "CMT-ELEC-01",
            "pipe": "CMT-PIPE-02",
            "unassigned": "CMT-UNASSIGNED-03",
        },
        "drawings": {
            "elec": "DWG-ELEC-100",
            "pipe": "DWG-PIPE-200",
            "unassigned": "DWG-UNASSIGNED-300",
        },
    }


def _set_active_user(controller: AppController, user: UserDTO):
    """Helper to mock active session on controller."""
    controller._current_session = SessionTokenDTO(
        token="test_token",
        user=user,
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_1_same_department_mutation_succeeds(test_setup):
    """Test 1: Electrical reviewer can successfully modify electrical comment status."""
    ctrl = test_setup["controller"]
    _set_active_user(ctrl, test_setup["users"]["elec"])

    comment_id = test_setup["comments"]["elec"]
    success = ctrl.update_comment_status(comment_id, "Approved")

    assert success is True
    # Verify persisted in DB
    cmt = ctrl.comment_repo.get_comment_by_id(comment_id)
    assert cmt["status"] == "Approved"


def test_2_cross_department_mutation_denied(test_setup):
    """Test 2: Electrical reviewer attempting to modify Piping comment is denied."""
    ctrl = test_setup["controller"]
    _set_active_user(ctrl, test_setup["users"]["elec"])

    error_signals = []
    ctrl.processing_error_signal.connect(lambda msg: error_signals.append(msg))

    pipe_comment_id = test_setup["comments"]["pipe"]
    success = ctrl.update_comment_status(pipe_comment_id, "Rejected")

    assert success is False
    # DB status must remain unchanged
    cmt = ctrl.comment_repo.get_comment_by_id(pipe_comment_id)
    assert cmt["status"] == "Pending"

    # Verify signal emitted
    assert len(error_signals) == 1
    assert "Permission Denied: Cross-department comment modification denied" in error_signals[0]

    # Verify denied attempt was recorded in audit logs
    audits = ctrl.audit_repo.get_audit_logs_for_comment(pipe_comment_id)
    assert any(a["action"] == "auth_denied" for a in audits)


def test_3_department_user_cannot_modify_unassigned_drawing_comment(test_setup):
    """Test 3: Department-scoped user cannot modify comments on unassigned drawings."""
    ctrl = test_setup["controller"]
    _set_active_user(ctrl, test_setup["users"]["elec"])

    unassigned_cmt_id = test_setup["comments"]["unassigned"]
    success = ctrl.update_comment_status(unassigned_cmt_id, "Flagged")

    assert success is False
    cmt = ctrl.comment_repo.get_comment_by_id(unassigned_cmt_id)
    assert cmt["status"] == "Pending"

    # Audit log check
    audits = ctrl.audit_repo.get_audit_logs_for_comment(unassigned_cmt_id)
    assert any(a["action"] == "auth_denied" and "unassigned drawings" in a["notes"] for a in audits)


def test_4_lead_engineer_can_modify_unassigned_drawing_comment(test_setup):
    """Test 4: Authorized Lead Engineer can modify unassigned drawing comment with administrative audit note."""
    ctrl = test_setup["controller"]
    _set_active_user(ctrl, test_setup["users"]["admin"])

    unassigned_cmt_id = test_setup["comments"]["unassigned"]
    success = ctrl.update_comment_status(unassigned_cmt_id, "Approved")

    assert success is True
    cmt = ctrl.comment_repo.get_comment_by_id(unassigned_cmt_id)
    assert cmt["status"] == "Approved"

    # Verify audit note captures administrative override
    audits = ctrl.audit_repo.get_audit_logs_for_comment(unassigned_cmt_id)
    assert any("Administrative override on unassigned drawing" in (a.get("notes") or "") for a in audits)


def test_5_unscoped_non_admin_user_denied(test_setup):
    """Test 5: An unscoped user with role='User' (no department) is denied all mutations."""
    ctrl = test_setup["controller"]
    _set_active_user(ctrl, test_setup["users"]["unscoped"])

    elec_cmt_id = test_setup["comments"]["elec"]
    success = ctrl.update_comment_status(elec_cmt_id, "Approved")
    assert success is False

    unassigned_cmt_id = test_setup["comments"]["unassigned"]
    success2 = ctrl.update_comment_status(unassigned_cmt_id, "Approved")
    assert success2 is False


def test_6_missing_or_invalid_identity_denied_safely(test_setup):
    """Test 6: Mutation without active user or with non-existent IDs fails safely."""
    ctrl = test_setup["controller"]
    ctrl._current_session = None  # No user logged in

    success = ctrl.update_comment_status("CMT-ELEC-01", "Approved")
    assert success is False

    # Log in admin, but use bogus comment ID
    _set_active_user(ctrl, test_setup["users"]["admin"])
    success_bogus = ctrl.update_comment_status("CMT-NONEXISTENT-999", "Approved")
    assert success_bogus is False


def test_7_reprocess_drawing_authorization(test_setup):
    """Test 7: Drawing-level reprocess authorization rules."""
    ctrl = test_setup["controller"]
    ctrl.start_processing_workflow = MagicMock()

    # Case A: Same department reprocess allowed
    _set_active_user(ctrl, test_setup["users"]["elec"])
    res_same = ctrl.reprocess_drawing(test_setup["drawings"]["elec"])
    assert res_same is True
    assert ctrl.start_processing_workflow.called

    ctrl.start_processing_workflow.reset_mock()

    # Case B: Cross department reprocess denied
    res_cross = ctrl.reprocess_drawing(test_setup["drawings"]["pipe"])
    assert res_cross is False
    assert not ctrl.start_processing_workflow.called

    # Case C: Unassigned drawing reprocess denied for department user
    res_unassigned_user = ctrl.reprocess_drawing(test_setup["drawings"]["unassigned"])
    assert res_unassigned_user is False
    assert not ctrl.start_processing_workflow.called

    # Case D: Lead Engineer reprocess on unassigned drawing allowed
    _set_active_user(ctrl, test_setup["users"]["admin"])
    res_unassigned_admin = ctrl.reprocess_drawing(test_setup["drawings"]["unassigned"])
    assert res_unassigned_admin is True
    assert ctrl.start_processing_workflow.called


def test_8_mutation_prevention_on_text_category_department_reviewer(test_setup):
    """Test 8: Unauthorized users cannot modify text, category, department, or reviewer."""
    ctrl = test_setup["controller"]
    _set_active_user(ctrl, test_setup["users"]["elec"])  # Electrical reviewer

    pipe_comment_id = test_setup["comments"]["pipe"]  # Piping comment

    # 1. Update text denied
    res_text = ctrl.update_comment_text(pipe_comment_id, "HACKED TEXT")
    assert res_text is False

    # 2. Update category denied
    res_cat = ctrl.update_comment_category(pipe_comment_id, "HackedCategory")
    assert res_cat is False

    # 3. Update department denied
    res_dept = ctrl.update_comment_department(pipe_comment_id, "DEPT-ELEC-01")
    assert res_dept is False

    # 4. Update reviewer denied
    res_rev = ctrl.update_comment_reviewer(pipe_comment_id, "HackedReviewer")
    assert res_rev is False

    # Verify original values remain unchanged in database
    cmt = ctrl.comment_repo.get_comment_by_id(pipe_comment_id)
    assert cmt["cleaned_text"] == "Revise steam header pipe schedule to SCH 80"
    assert cmt["category_name"] == "Piping"


def test_9_gui_compatibility_signals_emitted(test_setup):
    """Test 9: Verify processing_error_signal is emitted on denial for GUI toast display."""
    ctrl = test_setup["controller"]
    _set_active_user(ctrl, test_setup["users"]["elec"])

    received_errors = []
    ctrl.processing_error_signal.connect(lambda msg: received_errors.append(msg))

    ctrl.update_comment_text(test_setup["comments"]["pipe"], "Unauthorized update")
    assert len(received_errors) == 1
    assert "Permission Denied: Cross-department comment modification denied" in received_errors[0]


def test_10_audit_logging_failure_does_not_permit_denied_mutation(test_setup, monkeypatch):
    """Test 10: Even if audit repository raises an exception, unauthorized mutation remains denied."""
    ctrl = test_setup["controller"]
    _set_active_user(ctrl, test_setup["users"]["elec"])

    pipe_comment_id = test_setup["comments"]["pipe"]

    # Sabotage audit repository
    def _exploding_audit(*args, **kwargs):
        raise RuntimeError("Audit database disk I/O failure")

    monkeypatch.setattr(ctrl.audit_repo, "create_audit_entry", _exploding_audit)

    # Mutation must still be denied
    success = ctrl.update_comment_status(pipe_comment_id, "Approved")
    assert success is False

    cmt = ctrl.comment_repo.get_comment_by_id(pipe_comment_id)
    assert cmt["status"] == "Pending"
