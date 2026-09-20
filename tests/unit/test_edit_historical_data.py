"""
test_edit_historical_data.py — Focused unit tests for Feature 6:
Editing and saving historical data with audit history in SQLite.
"""

import pytest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.infrastructure.storage.repository import (
    DatabaseEngine,
    CommentRepository,
    AuditLogRepository,
    ProjectRepository,
)
from src.infrastructure.storage.models import Base, DrawingModel
from app.controllers.app_controller import AppController


@pytest.fixture
def temp_db(tmp_path: Path):
    db_file = tmp_path / "test_historical_edit.db"
    engine = DatabaseEngine(db_path=db_file)
    Base.metadata.create_all(engine.engine)

    proj_repo = ProjectRepository(engine)
    proj = proj_repo.create_project(name="Historical Test Project")
    proj_id = proj["id"]

    # Create drawing record with required non-null fields
    dwg_id = f"DWG-{uuid.uuid4().hex[:8].upper()}"
    with engine.get_session() as session:
        session.add(
            DrawingModel(
                id=dwg_id,
                project_id=proj_id,
                file_name="dwg_historical.pdf",
                file_path=str(tmp_path / "dwg_historical.pdf"),
                file_size_bytes=1024,
                file_hash_sha256="hash_dwg_historical_12345",
                total_pages=1,
                is_scanned=False,
                uploaded_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    yield engine, proj_id, dwg_id, db_file


def test_1_edit_historical_classification_and_audit(temp_db):
    engine, proj_id, dwg_id, db_file = temp_db
    cmt_repo = CommentRepository(engine)
    audit_repo = AuditLogRepository(engine)

    # 1. Create initial historical comment (processed on 20 Sep 2026)
    c_res = cmt_repo.save_comment(
        drawing_id=dwg_id,
        page_number=1,
        raw_text="Check pipe thickness value 5.2mm",
        category_name="Documentation",
        status="Pending",
        bbox=(10.0, 10.0, 100.0, 50.0),
    )
    cmt_id = c_res["id"]
    initial_raw = "Check pipe thickness value 5.2mm"

    # 2. Reviewer edits classification on 25 Sep 2026 to "Design Error"
    ok = cmt_repo.update_comment_category(
        cmt_id,
        new_category="Design Error",
        changed_by_user_id="reviewer_senior",
    )
    assert ok is True

    # 3. Reload from database using a NEW DatabaseEngine (simulating app restart)
    new_engine = DatabaseEngine(db_path=db_file)
    new_cmt_repo = CommentRepository(new_engine)
    new_audit_repo = AuditLogRepository(new_engine)

    reloaded_comment = new_cmt_repo.get_comment_by_id(cmt_id)

    # 4. Verify new classification value
    assert reloaded_comment["category_name"] == "Design Error"
    assert reloaded_comment["is_verified_by_human"] is True

    # 7. Verify raw OCR text remains completely unchanged
    assert reloaded_comment["raw_text"] == initial_raw

    # 5. & 6. Verify audit record in audit_logs table
    logs = new_audit_repo.get_audit_logs_for_comment(cmt_id)
    assert len(logs) >= 1
    cat_log = next(log for log in logs if log["action"] == "edit_category")
    assert cat_log["old_value"] == "Documentation"
    assert cat_log["new_value"] == "Design Error"
    assert cat_log["reviewer_name"] == "reviewer_senior"


def test_2_edit_comment_text_preserves_raw_text(temp_db):
    engine, proj_id, dwg_id, db_file = temp_db
    cmt_repo = CommentRepository(engine)

    raw_ocr = "valve leak test pressure 150 psi"
    c_res = cmt_repo.save_comment(
        drawing_id=dwg_id,
        page_number=1,
        raw_text=raw_ocr,
        category_name="Dimensional",
        bbox=(0.0, 0.0, 10.0, 10.0),
    )
    cmt_id = c_res["id"]

    # Reviewer corrects OCR typo in text
    corrected_text = "Valve leak test pressure 150 PSI (Verified)"
    cmt_repo.update_comment_text(
        cmt_id,
        new_text=corrected_text,
        changed_by_user_id="reviewer_lead",
    )

    # Reload from fresh DB instance
    new_engine = DatabaseEngine(db_path=db_file)
    new_cmt_repo = CommentRepository(new_engine)
    new_audit_repo = AuditLogRepository(new_engine)

    reloaded = new_cmt_repo.get_comment_by_id(cmt_id)

    # Raw OCR remains untouched
    assert reloaded["raw_text"] == raw_ocr

    # Cleaned text holds corrected value
    assert reloaded["cleaned_text"] == corrected_text

    # Audit record check
    logs = new_audit_repo.get_audit_logs_for_comment(cmt_id)
    text_log = next(log for log in logs if log["action"] == "edit_text")
    assert text_log["old_value"] == raw_ocr
    assert text_log["new_value"] == corrected_text
    assert text_log["reviewer_name"] == "reviewer_lead"


def test_3_app_controller_historical_edits_survive_restart(temp_db):
    engine, proj_id, dwg_id, db_file = temp_db
    cmt_repo = CommentRepository(engine)

    c_res = cmt_repo.save_comment(
        drawing_id=dwg_id,
        page_number=2,
        raw_text="No grounding connection found",
        category_name="Safety",
        status="Pending",
        bbox=(5.0, 5.0, 20.0, 20.0),
    )
    cmt_id = c_res["id"]

    # Controller updates status, category, department, and reviewer
    controller = AppController(db_engine=engine)
    controller.update_comment_category(cmt_id, "Electrical", changed_by_user_id="eng_user")
    controller.update_comment_status(cmt_id, "Approved", verified_by_human=True, changed_by_user_id="eng_user")
    controller.update_comment_department(cmt_id, "Electrical Engineering", changed_by_user_id="eng_user")
    controller.update_comment_reviewer(cmt_id, "USR-ELEC-99", changed_by_user_id="eng_user")

    # Restart app with fresh engine
    restart_engine = DatabaseEngine(db_path=db_file)
    restart_controller = AppController(db_engine=restart_engine)

    reloaded_raw = restart_controller.comment_repo.get_comment_by_id(cmt_id)
    normalised = restart_controller.normalise_comment(reloaded_raw)

    assert normalised["category"] == "Electrical"
    assert normalised["status"] == "Approved"
    assert normalised["department"] == "Electrical Engineering"
    assert normalised["reviewer"] == "USR-ELEC-99"
    assert normalised["raw_text"] == "No grounding connection found"

    audit_trail = restart_controller.get_audit_trail(cmt_id)
    assert len(audit_trail) >= 4
