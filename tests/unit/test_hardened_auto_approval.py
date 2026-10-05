"""
Unit tests for Issue #6: Hardened Auto-Approval Policy and Enforcement.

Verifies:
1. Requiring both ocr_confidence >= threshold AND classification_confidence >= threshold.
2. Rejecting auto-approval for short/noisy text (<= 3 words, pure symbols/noise).
3. Preventing rule-based or fallback classifications from auto-approving.
4. Respecting feature configuration toggle and custom thresholds.
5. End-to-end integration with WorkflowEngine and VerificationService.
"""
import pytest
from src.services.auto_approval_policy import evaluate_auto_approval
from src.infrastructure.storage.repository import DatabaseEngine, CommentRepository, DrawingRepository, AuditLogRepository
from src.services.verification_service import VerificationService


def test_auto_approval_requires_both_ocr_and_classification_above_threshold():
    """Verify that both confidences must independently meet or exceed the threshold."""
    valid_text = "VERIFY CLEARANCE AT COLUMN BASE PLATE"
    
    # 1. OCR high, Classification below threshold
    ok, reason = evaluate_auto_approval(
        ocr_confidence=0.95,
        classification_confidence=0.80,
        text=valid_text,
        fallback_used=False,
        classification_method="ai_model",
        threshold=0.85,
    )
    assert not ok
    assert "Classification confidence" in reason

    # 2. Classification high, OCR below threshold
    ok, reason = evaluate_auto_approval(
        ocr_confidence=0.80,
        classification_confidence=0.95,
        text=valid_text,
        fallback_used=False,
        classification_method="ai_model",
        threshold=0.85,
    )
    assert not ok
    assert "OCR confidence" in reason

    # 3. Both below threshold
    ok, reason = evaluate_auto_approval(
        ocr_confidence=0.84,
        classification_confidence=0.84,
        text=valid_text,
        fallback_used=False,
        classification_method="ai_model",
        threshold=0.85,
    )
    assert not ok

    # 4. Exactly at threshold
    ok, reason = evaluate_auto_approval(
        ocr_confidence=0.85,
        classification_confidence=0.85,
        text=valid_text,
        fallback_used=False,
        classification_method="ai_model",
        threshold=0.85,
    )
    assert ok
    assert "AI model" in reason

    # 5. Well above threshold
    ok, reason = evaluate_auto_approval(
        ocr_confidence=0.94,
        classification_confidence=0.91,
        text=valid_text,
        fallback_used=False,
        classification_method="ai_model",
        threshold=0.85,
    )
    assert ok


def test_auto_approval_rejects_short_text():
    """Verify that comments with <= 3 words are rejected regardless of confidence."""
    # 1 word
    ok, reason = evaluate_auto_approval(
        ocr_confidence=0.98,
        classification_confidence=0.98,
        text="PIPE",
        fallback_used=False,
        classification_method="ai_model",
    )
    assert not ok
    assert "Text too short" in reason

    # 2 words
    ok, reason = evaluate_auto_approval(
        ocr_confidence=0.98,
        classification_confidence=0.98,
        text="SEE DETAIL",
        fallback_used=False,
        classification_method="ai_model",
    )
    assert not ok
    assert "Text too short" in reason

    # 3 words
    ok, reason = evaluate_auto_approval(
        ocr_confidence=0.98,
        classification_confidence=0.98,
        text="REVISE PER SPEC",
        fallback_used=False,
        classification_method="ai_model",
    )
    assert not ok
    assert "Text too short" in reason

    # 4 words (valid length)
    ok, reason = evaluate_auto_approval(
        ocr_confidence=0.98,
        classification_confidence=0.98,
        text="REVISE PER SPECIFICATION SHEET",
        fallback_used=False,
        classification_method="ai_model",
    )
    assert ok


def test_auto_approval_rejects_noisy_text():
    """Verify that noisy, empty, or purely symbolic text is rejected."""
    # Empty string
    ok, reason = evaluate_auto_approval(
        ocr_confidence=0.99,
        classification_confidence=0.99,
        text="",
        fallback_used=False,
        classification_method="ai_model",
    )
    assert not ok

    # Only whitespace
    ok, reason = evaluate_auto_approval(
        ocr_confidence=0.99,
        classification_confidence=0.99,
        text="   \n\t  ",
        fallback_used=False,
        classification_method="ai_model",
    )
    assert not ok

    # Pure symbols / punctuation
    ok, reason = evaluate_auto_approval(
        ocr_confidence=0.99,
        classification_confidence=0.99,
        text="--- ... ### ***",
        fallback_used=False,
        classification_method="ai_model",
    )
    assert not ok
    assert "Text too short" in reason or "noisy" in reason


def test_auto_approval_prevents_fallback_classifications():
    """Verify that rule-based or fallback classifications NEVER auto-approve."""
    valid_text = "CHECK WALL THICKNESS AND EXPANSION JOINTS"

    # fallback_used = True
    ok, reason = evaluate_auto_approval(
        ocr_confidence=0.99,
        classification_confidence=0.99,
        text=valid_text,
        fallback_used=True,
        classification_method="rule_based_fallback",
    )
    assert not ok
    assert "Fallback classification used" in reason

    # classification_method = "rule_based"
    ok, reason = evaluate_auto_approval(
        ocr_confidence=0.99,
        classification_confidence=0.99,
        text=valid_text,
        fallback_used=False,
        classification_method="rule_based",
    )
    assert not ok
    assert "Fallback classification used" in reason

    # classification_method = "error_fallback"
    ok, reason = evaluate_auto_approval(
        ocr_confidence=0.99,
        classification_confidence=0.99,
        text=valid_text,
        fallback_used=False,
        classification_method="error_fallback",
    )
    assert not ok
    assert "Fallback classification used" in reason


def test_auto_approval_respects_configuration_flag():
    """Verify that auto_approve_enabled=False prevents auto-approval."""
    valid_text = "CHECK WALL THICKNESS AND EXPANSION JOINTS"
    ok, reason = evaluate_auto_approval(
        ocr_confidence=0.95,
        classification_confidence=0.95,
        text=valid_text,
        fallback_used=False,
        classification_method="ai_model",
        auto_approve_enabled=False,
    )
    assert not ok
    assert "disabled" in reason


def test_verification_service_hardened_bulk_approve(tmp_path):
    """Verify VerificationService with hardened=True applies the hardened policy."""
    db_file = tmp_path / "test_hardened.db"
    db_engine = DatabaseEngine(db_file)
    from src.infrastructure.storage.models import DrawingModel
    with db_engine.get_session() as session:
        dwg = DrawingModel(
            id="DWG-HARD-001",
            file_path="dummy.pdf",
            file_name="dummy.pdf",
            file_size_bytes=100,
            file_hash_sha256="abc12345",
            total_pages=1,
        )
        session.add(dwg)
        session.commit()

    repo = CommentRepository(db_engine)

    # 1. Eligible comment: high OCR, high Cat, 5 words, genuine AI
    repo.save_comment(
        drawing_id="DWG-HARD-001",
        page_number=1,
        raw_text="CHECK WALL THICKNESS AND CLEARANCE",
        bbox=(0.1, 0.1, 0.5, 0.5),
        confidence=0.92,
        ocr_confidence=0.92,
        classification_confidence=0.90,
        classification_method="ai_model",
        fallback_used=False,
        status="Pending",
        comment_id="CMT-ELIGIBLE",
    )

    # 2. Ineligible: short text (2 words)
    repo.save_comment(
        drawing_id="DWG-HARD-001",
        page_number=1,
        raw_text="SEE NOTE",
        bbox=(0.2, 0.2, 0.4, 0.4),
        confidence=0.95,
        ocr_confidence=0.95,
        classification_confidence=0.95,
        classification_method="ai_model",
        fallback_used=False,
        status="Pending",
        comment_id="CMT-SHORT",
    )

    # 3. Ineligible: fallback used
    repo.save_comment(
        drawing_id="DWG-HARD-001",
        page_number=1,
        raw_text="VERIFY BEAM SPAN AND LOADING",
        bbox=(0.3, 0.3, 0.6, 0.6),
        confidence=0.95,
        ocr_confidence=0.95,
        classification_confidence=0.95,
        classification_method="rule_based_fallback",
        fallback_used=True,
        status="Pending",
        comment_id="CMT-FALLBACK",
    )

    # 4. Ineligible: low classification confidence
    repo.save_comment(
        drawing_id="DWG-HARD-001",
        page_number=1,
        raw_text="VERIFY BEAM SPAN AND LOADING",
        bbox=(0.4, 0.4, 0.7, 0.7),
        confidence=0.88,
        ocr_confidence=0.95,
        classification_confidence=0.72,
        classification_method="ai_model",
        fallback_used=False,
        status="Pending",
        comment_id="CMT-LOWCAT",
    )

    service = VerificationService(repo)
    res = service.approve_all_high_confidence("DWG-HARD-001", threshold=0.85, hardened=True)

    # Exactly 1 out of 4 should be approved!
    assert res.total_processed == 1
    assert res.successful == 1
    assert res.skipped == 3

    c_eligible = repo.get_comment_by_id("CMT-ELIGIBLE")
    assert c_eligible["status"] == "Approved"

    c_short = repo.get_comment_by_id("CMT-SHORT")
    assert c_short["status"] == "Pending"

    c_fallback = repo.get_comment_by_id("CMT-FALLBACK")
    assert c_fallback["status"] == "Pending"

    c_lowcat = repo.get_comment_by_id("CMT-LOWCAT")
    assert c_lowcat["status"] == "Pending"
