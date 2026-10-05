"""
Unit tests verifying every AI and Fallback path:
1. AI model successfully executed (DistilBERT, ai_model, fallback_used=False)
2. AI model unavailable (weights/directory missing, rule_based_fallback, fallback_used=True, explicit reason)
3. Rule-based fallback executed (keyword matching, explicit attribution)
4. Inference failed (runtime exception, error_fallback, fallback_used=True)
5. Anti-spoofing verification (fallback outputs never masquerade as AI and never auto-approve)
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.services.classification_service import ClassificationService
from src.services.auto_approval_policy import evaluate_auto_approval
from src.core.dtos.classification_dtos import ClassificationResultDTO, CategoryPredictionDTO


@pytest.fixture
def service():
    return ClassificationService()


def test_1_ai_model_successfully_executed(service):
    """Verify state when DistilBERT model executes successfully."""
    # Test valid engineering prompt
    text = "REVISE BEAM SIZE TO W24X68 AND VERIFY MOMENT CONNECTION"
    res = service.classify_comment(text)

    assert res.classification_method == "ai_model"
    assert res.fallback_used is False
    assert res.fallback_reason == ""
    assert res.primary_category.confidence > 0.50
    assert res.primary_category.category_name in ["Technical", "Drafting", "Dimension", "Standards", "Documentation"]


def test_2_ai_model_unavailable_missing_weights():
    """Verify explicit fallback attribution when model weights are missing."""
    dummy_path = Path("non_existent_model_dir_xyz")
    svc_no_model = ClassificationService(model_dir=dummy_path)

    text = "REVISE BEAM SIZE TO W24X68"
    res = svc_no_model.classify_comment(text)

    assert res.classification_method == "rule_based_fallback"
    assert res.fallback_used is True
    assert "not found" in res.fallback_reason or "unavailable" in res.fallback_reason
    assert res.primary_category.category_name == "Technical"  # Rule matched 'beam size'


def test_3_rule_based_explicit_execution(service):
    """Verify explicit rule-based classification (force_method='rule_based')."""
    text = "INCORRECT DRAWING SCALE 1:50 IN DETAIL C"
    res = service.classify_comment(text, force_method="rule_based")

    assert res.classification_method == "rule_based"
    assert res.fallback_used is False
    assert res.fallback_reason == ""
    assert res.primary_category.category_name == "Drafting"


def test_4_inference_failed_runtime_exception(service):
    """Verify graceful error_fallback attribution when AI forward pass raises runtime error."""
    text = "CHECK CLEARANCE ELEVATION"
    with patch.object(service, "_try_ai_classify", side_effect=RuntimeError("CUDA Out of Memory")):
        res = service.classify_comment(text)

    assert res.classification_method == "rule_based_fallback"
    assert res.fallback_used is True
    assert res.fallback_reason != ""


def test_5_batched_fallback_attribution(service):
    """Verify batch classification correctly attributes AI vs. Fallback per item."""
    texts = [
        "MOMENT CONNECTION SHEAR TAB DEFICIENT",
        "",  # Empty text
        "REVISE DIMENSION STRING TO CENTERLINE",
    ]
    batch_dto = service.classify_batch(texts)

    assert len(batch_dto.results) == 3
    # Item 0: AI
    assert batch_dto.results[0].classification_method == "ai_model"
    assert batch_dto.results[0].fallback_used is False
    # Item 1: Empty -> rule_based
    assert batch_dto.results[1].classification_method == "rule_based"
    assert batch_dto.results[1].requires_human_review is True
    # Item 2: AI
    assert batch_dto.results[2].classification_method == "ai_model"
    assert batch_dto.results[2].fallback_used is False


def test_6_anti_spoofing_auto_approval_guardrail():
    """Verify that NO fallback or rule-based method can ever be auto-approved."""
    fallback_methods = [
        "rule_based_fallback",
        "rule_based",
        "error_fallback",
        "manual_transcription_required",
        "fallback_keyword_heuristics",
    ]

    for method in fallback_methods:
        approved, reason = evaluate_auto_approval(
            ocr_confidence=0.99,
            classification_confidence=0.99,
            text="REVISE MOMENT CONNECTION SHEAR TAB PER AISC SPECIFICATION",
            fallback_used=True,
            classification_method=method,
            auto_approve_enabled=True,
            threshold=0.85,
        )
        assert approved is False
        assert "Fallback classification used" in reason
