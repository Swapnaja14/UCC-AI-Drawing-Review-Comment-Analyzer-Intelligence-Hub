"""
Unit test suite verifying DistilBERT Model Integration:
1. Model weights presence and memory loading
2. Guaranteeing the application does NOT silently use rule-based fallback
3. Complete pipeline execution: Input -> preprocessing -> tokenizer -> DistilBERT -> softmax -> classification DTO
4. Model name, architecture, source, parameter count, and categories
5. Model initialization & inference logging
6. Explicit fallback behavior when model is unavailable
7. Comparison of DistilBERT predictions vs. rule-engine predictions on representative samples
"""
import pytest
import logging
from pathlib import Path
import torch

from src.services.classification_service import ClassificationService
from src.services.text_cleaning_service import TextCleaningService
from src.ai.dataset_generator import CATEGORIES

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = PROJECT_ROOT / "models" / "distilbert_engineering_classifier"


def test_distilbert_weights_and_files_exist():
    """Verify that all DistilBERT model artifact files are present on disk."""
    assert MODEL_DIR.exists(), f"Model directory must exist at {MODEL_DIR}"
    
    weights_file = MODEL_DIR / "model.safetensors"
    config_file = MODEL_DIR / "config.json"
    tokenizer_file = MODEL_DIR / "tokenizer.json"
    meta_file = MODEL_DIR / "training_metadata.json"

    assert weights_file.exists(), "model.safetensors weights file must exist"
    assert weights_file.stat().st_size > 200 * 1024 * 1024, "Weights file should be > 200 MB (~268 MB)"
    assert config_file.exists(), "config.json must exist"
    assert tokenizer_file.exists(), "tokenizer.json must exist"
    assert meta_file.exists(), "training_metadata.json must exist"


def test_model_metadata_and_architecture():
    """Confirm model name, architecture, 13 categories, and parameter count."""
    service = ClassificationService(model_dir=MODEL_DIR)
    status = service.get_model_status()

    assert status["is_loaded"] is True
    assert status["architecture"] == "DistilBertForSequenceClassification"
    assert status["num_classes"] == 13
    assert status["total_parameters"] > 60_000_000
    assert status["weights_exist"] is True
    assert status["load_error"] is None
    
    for cat in CATEGORIES:
        assert cat in status["classes"]


def test_complete_pipeline_flow():
    """
    Verify complete classification pipeline:
    Input → Preprocessing → Tokenizer → DistilBERT → Softmax → Result DTO
    """
    # 1. Raw Input
    raw_input = "  [CRITICAL] Check flange weld on pipe line 174005-S12-04-P08 for ASME B16.5 compliance \n\t "

    # 2. Preprocessing / Cleaning
    cleaner = TextCleaningService()
    cleaned_dto = cleaner.clean_text(raw_input)
    cleaned_text = cleaned_dto.cleaned_text
    assert len(cleaned_text) > 0
    assert not cleaned_text.startswith(" ")

    # 3. Model & Tokenizer loading
    service = ClassificationService(model_dir=MODEL_DIR)
    assert service.ensure_loaded() is True
    assert service.is_model_loaded() is True

    # 4. Tokenizer step
    encoding = service._ai_tokenizer(
        cleaned_text,
        truncation=True,
        max_length=128,
        return_tensors="pt"
    ).to(service._ai_device)
    assert "input_ids" in encoding
    assert "attention_mask" in encoding
    assert encoding["input_ids"].shape[0] == 1

    # 5. DistilBERT forward pass
    with torch.no_grad():
        outputs = service._ai_model(**encoding)
        logits = outputs.logits
        assert logits.shape == (1, 13)

        probs = torch.softmax(logits, dim=1).cpu().squeeze(0).numpy()
        assert len(probs) == 13
        assert abs(sum(probs) - 1.0) < 1e-4

    # 6. Output DTO verification (Confirms application is actively using DistilBERT, NOT fallback)
    result = service.classify_comment(cleaned_text, comment_id="TEST-001")
    assert result.comment_id == "TEST-001"
    assert result.classification_method == "ai_model"
    assert result.fallback_used is False
    assert result.fallback_reason == ""
    assert result.primary_category.category_name in CATEGORIES
    assert 0.0 <= result.primary_category.confidence <= 1.0
    assert len(result.alternative_categories) == 12


def test_pure_ai_vs_pure_rules_methods():
    """Verify that pure AI and pure rule prediction methods work independently."""
    service = ClassificationService(model_dir=MODEL_DIR)
    sample_text = "Verify structural column W14x90 base plate thickness calculation"

    # Pure AI predictions (raw softmax, no keyword weighting)
    ai_preds = service.predict_ai_only(sample_text)
    assert len(ai_preds) == 13
    ai_confs = [p.confidence for p in ai_preds]
    assert abs(sum(ai_confs) - 1.0) < 0.02  # Softmax sum close to 1.0

    # Pure rule-based predictions
    rule_preds = service.predict_rules_only(sample_text)
    assert len(rule_preds) == 13
    calc_pred = next((p for p in rule_preds if p.category_name == "Calculation"), None)
    assert calc_pred is not None
    assert len(calc_pred.matched_keywords) > 0


def test_model_unavailable_explicit_fallback():
    """
    Test behavior when the model weights/directory is unavailable:
    Must explicitly flag fallback_used=True, classification_method='rule_based_fallback',
    and provide fallback_reason.
    """
    non_existent_dir = PROJECT_ROOT / "models" / "non_existent_model_dir"
    service = ClassificationService(model_dir=non_existent_dir)

    status = service.get_model_status()
    assert status["is_loaded"] is False
    assert status["weights_exist"] is False

    result = service.classify_comment("Incorrect weld callout on stiffener plate", comment_id="FALLBACK-01")

    # Fallback must NOT be silent:
    assert result.classification_method == "rule_based_fallback"
    assert result.fallback_used is True
    assert "not found" in result.fallback_reason.lower()
    assert result.primary_category.category_name in ["Technical", "Drafting", "Material", "Standards"]
    assert result.primary_category.confidence > 0.50


def test_explicit_force_rule_based():
    """Test explicitly forcing rule-based classification."""
    service = ClassificationService(model_dir=MODEL_DIR)
    result = service.classify_comment(
        "Line overlap between dimension line and section cut",
        comment_id="RULE-01",
        force_method="rule_based"
    )

    assert result.classification_method == "rule_based"
    assert result.fallback_used is False
    assert result.primary_category.category_name in ["Drafting", "Dimension"]


def test_batch_classification_explicit_counts():
    """Verify batch classification provides detailed AI, fallback, and rule counts."""
    service = ClassificationService(model_dir=MODEL_DIR)
    comments = [
        {"id": "1", "text": "Beam size W12x45 undersized for moment connection"},
        {"id": "2", "text": "ISA-5.1 tag symbol incorrect on pressure transmitter"},
        {"id": "3", "text": "Clash with HVAC duct near column B-4"},
    ]

    batch_res = service.classify_batch(comments, drawing_id="DWG-TEST-BATCH")

    assert batch_res.total_classified == 3
    assert batch_res.ai_classified_count == 3
    assert batch_res.fallback_count == 0
    assert batch_res.rule_classified_count == 0
    for r in batch_res.results:
        assert r.classification_method == "ai_model"
        assert r.fallback_used is False


def test_side_by_side_comparison_all_13_categories():
    """
    Compare DistilBERT predictions vs. rule-engine predictions across representative
    samples for all 13 engineering categories.
    """
    service = ClassificationService(model_dir=MODEL_DIR)

    samples = {
        "Technical": "Incorrect weld callout: replace fillet weld with full penetration weld on moment connection",
        "Drafting": "Line overlap observed between section cut A-A and leader line bubble",
        "Dimension": "Missing dimension: overall height from top of concrete to centerline elevation",
        "Cosmetic": "Text overlapping and font style inconsistency in title notes",
        "Standards": "Codal issue: emergency exit sign does not meet NFPA 101 standard",
        "Coordination": "Interference detected: 4-inch sprinkler pipe clashes with electrical cable tray",
        "Documentation": "Sign-off block incomplete: checker signature and professional seal missing",
        "Revision": "Add Revision C delta triangle tag and cloud boundary around modified nozzle",
        "Calculation": "Calculation sheet missing: provide allowable stress and deflection calculation",
        "Feasibility": "Erection feasibility issue: torque wrench clearance insufficient for flange bolting",
        "Material": "Incorrect material grade: specify 316L stainless steel instead of carbon steel",
        "Notes": "Update mandatory general notes regarding PWHT and hydrotest pressure requirement",
        "BOM": "Quantity mismatch in bill of materials: BOM quantity does not match detail bubble count"
    }

    for expected_cat, text in samples.items():
        # Pure AI
        ai_preds = service.predict_ai_only(text)
        top_ai = ai_preds[0]
        assert top_ai.confidence > 0.0

        # Pure Rule
        rule_preds = service.predict_rules_only(text)
        top_rule = rule_preds[0]

        # Hybrid/Calibrated
        hybrid_res = service.classify_comment(text)

        assert hybrid_res.classification_method == "ai_model"
        assert hybrid_res.fallback_used is False
        assert hybrid_res.primary_category.category_name == expected_cat, (
            f"Expected {expected_cat}, got {hybrid_res.primary_category.category_name} for '{text}'"
        )


def test_pyinstaller_frozen_model_resolution(monkeypatch, tmp_path):
    """
    Verify that ClassificationService.resolve_model_path correctly locates
    models in frozen PyInstaller environments (both _MEIPASS and executable dir).
    """
    import sys

    # 1. Test custom path override
    custom_target = tmp_path / "custom_model"
    assert ClassificationService.resolve_model_path(custom_target) == custom_target

    # 2. Test one-file mode: sys.frozen = True and sys._MEIPASS exists
    meipass_dir = tmp_path / "_MEIPASS_mock"
    meipass_model = meipass_dir / "models" / "distilbert_engineering_classifier"
    meipass_model.mkdir(parents=True)
    (meipass_model / "model.safetensors").write_bytes(b"dummy_weights")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass_dir), raising=False)

    resolved = ClassificationService.resolve_model_path()
    assert resolved == meipass_model
    assert (resolved / "model.safetensors").exists()

    # 3. Test one-dir mode: sys.frozen = True, no _MEIPASS, model next to executable
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    exe_dir = tmp_path / "exe_dir_mock"
    exe_model = exe_dir / "models" / "distilbert_engineering_classifier"
    exe_model.mkdir(parents=True)
    (exe_model / "model.safetensors").write_bytes(b"dummy_weights")
    mock_exe = exe_dir / "app.exe"

    monkeypatch.setattr(sys, "executable", str(mock_exe))
    resolved_onedir = ClassificationService.resolve_model_path()
    assert resolved_onedir == exe_model
    assert (resolved_onedir / "model.safetensors").exists()
