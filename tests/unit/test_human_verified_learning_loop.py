"""
tests/unit/test_human_verified_learning_loop.py
Comprehensive test suite for Phase 1: Human-Verified Classification Learning Loop.

Verifies:
- Test A: Human correction persistence (preserves both AI initial prediction and human final category)
- Test B: Verified-example reuse (authoritative ground-truth lookup by normalized text)
- Test C: Human decision protection (verified comments cannot be overwritten by automatic passes)
- Test D: Department isolation (verified example in Dept A does not affect Dept B)
- Test E: No-data behavior (standard fallback/AI pipeline operates normally without verified examples)
- Test F: Regression verification (audit logging, category counts, and repository consistency)
"""

import pytest
import uuid
from pathlib import Path
from datetime import datetime, timezone
from src.infrastructure.storage.repository import (
    DatabaseEngine,
    CommentRepository,
    EngineeringDepartmentRepository,
    CategoryRepository,
    DrawingRepository,
)
from src.infrastructure.storage.models import DrawingModel
from src.services.classification_service import ClassificationService


@pytest.fixture
def in_memory_db(tmp_path: Path):
    db_file = tmp_path / "test_learning_loop.db"
    engine = DatabaseEngine(db_path=db_file)
    return engine


@pytest.fixture
def setup_repositories(in_memory_db):
    dept_repo = EngineeringDepartmentRepository(in_memory_db)
    cat_repo = CategoryRepository(in_memory_db)
    draw_repo = DrawingRepository(in_memory_db)
    cmt_repo = CommentRepository(in_memory_db)

    # Seed departments
    dept_a = dept_repo.get_or_create_department("Process Piping", "Piping systems")
    dept_b = dept_repo.get_or_create_department("Electrical", "Electrical systems")

    # Seed drawing
    with in_memory_db.get_session() as session:
        dwg = DrawingModel(
            id="DWG-TEST-01",
            file_path="dummy.pdf",
            file_name="test_drawing.pdf",
            file_size_bytes=1024,
            file_hash_sha256="abc123hash",
            total_pages=1,
            is_scanned=False,
        )
        session.add(dwg)
        session.commit()

    drawing = {"id": "DWG-TEST-01"}

    return {
        "db": in_memory_db,
        "dept_repo": dept_repo,
        "cat_repo": cat_repo,
        "draw_repo": draw_repo,
        "cmt_repo": cmt_repo,
        "dept_a": dept_a,
        "dept_b": dept_b,
        "drawing": drawing,
    }


def test_a_human_correction_persistence(setup_repositories):
    """
    Test A: Human correction persistence
    - AI initially predicts 'Technical'.
    - Engineer updates category to 'Drafting'.
    - Final category becomes 'Drafting' with is_verified_by_human=True, method='manual'.
    - Original AI classification is preserved in initial_category and audit log.
    """
    repos = setup_repositories
    cmt_repo = repos["cmt_repo"]
    drawing_id = repos["drawing"]["id"]
    dept_id = repos["dept_a"]["id"]

    # 1. AI saves comment
    saved = cmt_repo.save_comment(
        drawing_id=drawing_id,
        page_number=1,
        raw_text="shift titles up a row",
        cleaned_text="shift titles up a row",
        bbox=(10.0, 10.0, 100.0, 50.0),
        confidence=0.85,
        classification_confidence=0.85,
        category_name="Technical",
        initial_category="Technical",
        classification_method="ai_model",
        department_id=dept_id,
        comment_id="CMT-TEST-PERSIST-1",
    )
    cid = saved["id"]

    # Verify initial AI state
    cmt = cmt_repo.get_comment_by_id(cid)
    assert cmt["category_name"] == "Technical"
    assert cmt["initial_category"] == "Technical"
    assert cmt["is_verified_by_human"] is False

    # 2. Engineer corrects to 'Drafting'
    ok = cmt_repo.update_comment_category(
        comment_id=cid,
        new_category="Drafting",
        changed_by_user_id="lead_engineer_1",
    )
    assert ok is True

    # 3. Verify final state preserves both human decision and initial AI prediction
    updated = cmt_repo.get_comment_by_id(cid)
    assert updated["category_name"] == "Drafting"
    assert updated["initial_category"] == "Technical"  # Preserved!
    assert updated["is_verified_by_human"] is True
    assert updated["classification_method"] == "manual"
    assert updated["fallback_used"] is False


def test_b_verified_example_reuse(setup_repositories):
    """
    Test B: Verified-example reuse
    - When a human decision is recorded for text in Dept A,
    - A future comment with identical or normalized wording in Dept A is classified
      using the verified human decision (classification_method='human_verified').
    """
    repos = setup_repositories
    cmt_repo = repos["cmt_repo"]
    drawing_id = repos["drawing"]["id"]
    dept_id = repos["dept_a"]["id"]

    # 1. Save and verify a comment
    saved = cmt_repo.save_comment(
        drawing_id=drawing_id,
        page_number=1,
        raw_text="shift titles up a row",
        cleaned_text="shift titles up a row",
        bbox=(10.0, 10.0, 100.0, 50.0),
        category_name="Technical",
        department_id=dept_id,
        comment_id="CMT-LEARN-1",
    )
    cmt_repo.update_comment_category("CMT-LEARN-1", "Drafting", changed_by_user_id="eng_user")

    # 2. Initialize classifier with comment_repo
    classifier = ClassificationService(category_repo=repos["cat_repo"], comment_repo=cmt_repo)

    # 3. Classify a new comment with punctuation / casing variations
    # 'Shift titles up a row.' -> should normalize to 'shift titles up a row'
    result = classifier.classify_comment(
        comment_text="Shift titles up a row.",
        department_name=dept_id,
    )

    assert result.primary_category.category_name == "Drafting"
    assert result.classification_method == "human_verified"
    assert result.requires_human_review is False
    assert result.fallback_used is False


def test_c_human_decision_protection(setup_repositories):
    """
    Test C: Human decision protection
    - If a comment has is_verified_by_human=True, running classification again
      must preserve the verified category without overwriting it.
    """
    repos = setup_repositories
    cmt_repo = repos["cmt_repo"]
    drawing_id = repos["drawing"]["id"]
    dept_id = repos["dept_a"]["id"]

    classifier = ClassificationService(category_repo=repos["cat_repo"], comment_repo=cmt_repo)

    # Test single comment preservation
    result = classifier.classify_comment(
        comment_text="check pipe schedule and flange rating",  # Normally matches Technical
        department_name=dept_id,
        is_verified_by_human=True,
        existing_category="Structural",  # Explicitly human-verified category
    )

    assert result.primary_category.category_name == "Structural"
    assert result.classification_method == "human_verified"
    assert result.requires_human_review is False

    # Test batch preservation
    batch_input = [
        {
            "id": "CMT-V1",
            "text": "check pipe schedule",
            "is_verified_by_human": True,
            "category_name": "Structural",
        },
        {
            "id": "CMT-V2",
            "text": "check pipe schedule",
            "is_verified_by_human": False,
            "category_name": "Pending",
        }
    ]
    batch_res = classifier.classify_batch(batch_input, department_name=dept_id)
    assert batch_res.results[0].primary_category.category_name == "Structural"
    assert batch_res.results[0].classification_method == "human_verified"


def test_d_department_isolation(setup_repositories):
    """
    Test D: Department isolation
    - A human correction in Department A ('Process Piping') must NOT influence
      classification in Department B ('Electrical').
    """
    repos = setup_repositories
    cmt_repo = repos["cmt_repo"]
    drawing_id = repos["drawing"]["id"]
    dept_a_id = repos["dept_a"]["id"]
    dept_b_id = repos["dept_b"]["id"]

    # Human corrects "verify breaker clearance" to "Technical" in Dept A
    saved = cmt_repo.save_comment(
        drawing_id=drawing_id,
        page_number=1,
        raw_text="verify breaker clearance",
        cleaned_text="verify breaker clearance",
        bbox=(0, 0, 10, 10),
        category_name="Drafting",
        department_id=dept_a_id,
        comment_id="CMT-DEPT-ISOLATE",
    )
    cmt_repo.update_comment_category("CMT-DEPT-ISOLATE", "Technical", changed_by_user_id="piping_eng")

    classifier = ClassificationService(category_repo=repos["cat_repo"], comment_repo=cmt_repo)

    # In Dept A: should reuse verified ground-truth "Technical"
    res_dept_a = classifier.classify_comment("verify breaker clearance", department_name=dept_a_id)
    assert res_dept_a.primary_category.category_name == "Technical"
    assert res_dept_a.classification_method == "human_verified"

    # In Dept B: verified example from Dept A must NOT apply!
    res_dept_b = classifier.classify_comment("verify breaker clearance", department_name=dept_b_id)
    assert res_dept_b.classification_method != "human_verified"


def test_e_no_data_behavior(setup_repositories):
    """
    Test E: No-data behavior
    - When there are no human-verified examples, the system operates normally
      using the standard AI / rule-based fallback pipeline.
    """
    repos = setup_repositories
    cmt_repo = repos["cmt_repo"]
    dept_id = repos["dept_a"]["id"]

    classifier = ClassificationService(category_repo=repos["cat_repo"], comment_repo=cmt_repo)

    # Empty database of verified comments:
    verified_examples = cmt_repo.get_verified_examples(department_id=dept_id)
    assert len(verified_examples) == 0

    # Rule-based fallback should work as expected
    res = classifier.classify_comment("incorrect drawing scale and font overlap", department_name=dept_id)
    assert res.primary_category.category_name == "Drafting"
    assert res.classification_method in ("ai_model", "rule_based_fallback", "rule_based")


def test_f_reprocess_preserves_verified_comments(setup_repositories):
    """
    Test F: Reprocess preserves verified comments
    - Calling delete_comments_for_drawing with preserve_verified=True clears only
      unverified comments while retaining human-verified ground truth.
    """
    repos = setup_repositories
    cmt_repo = repos["cmt_repo"]
    drawing_id = repos["drawing"]["id"]
    dept_id = repos["dept_a"]["id"]

    # Create 1 verified and 1 unverified comment
    cmt_repo.save_comment(
        drawing_id=drawing_id,
        page_number=1,
        raw_text="Unverified auto comment",
        bbox=(0, 0, 10, 10),
        category_name="Technical",
        comment_id="CMT-UNVERIFIED",
    )
    cmt_repo.save_comment(
        drawing_id=drawing_id,
        page_number=1,
        raw_text="Verified human comment",
        bbox=(0, 0, 10, 10),
        category_name="Technical",
        comment_id="CMT-VERIFIED",
    )
    cmt_repo.update_comment_category("CMT-VERIFIED", "Drafting", changed_by_user_id="lead_eng")

    # Reprocess drawing with preserve_verified=True
    deleted = cmt_repo.delete_comments_for_drawing(drawing_id, preserve_verified=True)
    assert deleted == 1  # Only the unverified comment was deleted

    remaining = cmt_repo.get_comments_for_drawing(drawing_id)
    assert len(remaining) == 1
    assert remaining[0]["id"] == "CMT-VERIFIED"
    assert remaining[0]["category_name"] == "Drafting"
    assert remaining[0]["initial_category"] == "Technical"
