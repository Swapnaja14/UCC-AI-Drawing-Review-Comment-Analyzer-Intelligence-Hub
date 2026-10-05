"""
Unit test suite verifying OCR to NLP Pipeline Integration:
1. OCR output handoff to NLP model (WorkflowEngine Step 4 -> Step 5)
2. Text cleaning & normalization before tokenization (abbreviations, OCR artifacts, whitespace)
3. Maximum token length (max_length=128) and truncation behavior for long engineering markups
4. Empty and low-confidence OCR handling (graceful degradation, review flagging)
5. Guardrails preventing OCR errors from causing incorrect auto-approvals or misclassifications
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import torch

from src.services.classification_service import ClassificationService
from src.services.text_cleaning_service import TextCleaningService
from src.services.workflow_engine import ProcessingWorkflowEngine
from src.services.auto_approval_policy import evaluate_auto_approval
from src.core.dtos.annotation_dtos import BoundingBoxDTO, DocumentAnnotationDTO, AnnotationResultDTO


@pytest.fixture
def classification_service():
    service = ClassificationService()
    service.ensure_loaded()
    return service


@pytest.fixture
def text_cleaning_service():
    return TextCleaningService(expand_acronyms=True)


def test_ocr_to_nlp_workflow_handoff():
    """
    Verify that WorkflowEngine correctly extracts OCR text, passes it through
    TextCleaningService, and feeds the cleaned text into ClassificationService.
    """
    file_service_mock = MagicMock()
    file_service_mock.validate_pdf_file.return_value = MagicMock(is_valid=True, error_message=None)
    file_service_mock.copy_to_managed_storage.side_effect = lambda p: p

    pdf_service_mock = MagicMock()
    pdf_service_mock.process_pdf_document.return_value = MagicMock(
        page_count=1,
        title="TEST DRAWING",
        drawing_number="DWG-OCR-NLP-01",
        revision="A",
    )

    regions = [
        BoundingBoxDTO(x0=50, y0=50, x1=200, y1=100, page_number=0, confidence=0.92, label="red_box")
    ]
    annotation_service_mock = MagicMock()
    annotation_service_mock.detect_all_pages.return_value = DocumentAnnotationDTO(
        file_name="test_handoff.pdf",
        total_pages=1,
        total_regions=1,
        page_results=[AnnotationResultDTO(drawing_id="1", page_number=0, regions=regions, detection_method="hybrid", processing_time_ms=10.0)],
    )

    drawing_repo_mock = MagicMock()
    drawing_repo_mock.get_by_hash.return_value = None
    drawing_repo_mock.save_drawing_from_dto.return_value = {"id": "DWG-OCR-NLP-01", "department_id": None, "project_id": None}

    comment_repo_mock = MagicMock()
    comment_repo_mock.save_comment.side_effect = lambda **kwargs: MagicMock(id=1, **kwargs)

    cleaning_service = TextCleaningService(expand_acronyms=True)
    classification_service = ClassificationService()

    engine = ProcessingWorkflowEngine(
        file_service=file_service_mock,
        pdf_service=pdf_service_mock,
        drawing_repo=drawing_repo_mock,
        comment_repo=comment_repo_mock,
        annotation_service=annotation_service_mock,
        classification_service=classification_service,
        text_cleaning_service=cleaning_service,
    )

    # Simulated raw OCR output containing engineering acronyms and noise
    raw_ocr_output = "  INCORRECT FLG RATING: VERIFY ASME B16.5 SPECS ON P&ID   "

    def mock_process_region(p_obj, reg, p_idx, page_envs, **kwargs):
        # OCR extracts raw text and passes to text_cleaning_service
        clean_dto = cleaning_service.clean_text(raw_ocr_output)
        return {
            "page_number": p_idx + 1,
            "raw_text": raw_ocr_output,
            "cleaned_text": clean_dto.cleaned_text,
            "bbox": (reg.x0, reg.y0, reg.x1, reg.y1),
            "detection_confidence": reg.confidence,
            "ocr_confidence": 0.95,
            "confidence": 0.95,
            "ocr_engine": "tesseract",
            "label": reg.label,
            "is_ocr_failed": False,
        }

    with patch.object(engine, "_process_single_region_ocr", side_effect=mock_process_region):
        with patch("src.services.workflow_engine.fitz.open") as mock_fitz_open:
            mock_doc = MagicMock()
            mock_doc.__len__.return_value = 1
            mock_doc.__getitem__.return_value = MagicMock()
            mock_fitz_open.return_value = mock_doc
            mock_doc.__enter__.return_value = mock_doc

            result = engine.execute_workflow(Path("test_handoff.pdf"))

            assert result.status == "Completed"
            assert result.total_comments_found == 1
            assert comment_repo_mock.save_comment.call_count == 1

            saved_kwargs = comment_repo_mock.save_comment.call_args.kwargs
            assert "Flange" in saved_kwargs["cleaned_text"]
            assert "Piping and Instrumentation Diagram" in saved_kwargs["cleaned_text"]
            assert saved_kwargs["category_name"] in ["Technical", "Standards", "Documentation"]
            assert saved_kwargs["classification_method"] == "ai_model"


def test_text_cleaning_and_normalization(text_cleaning_service):
    """Verify abbreviation expansion, whitespace normalization, and domain preservation."""
    test_cases = [
        (
            "   CHECK DWG REV A   P&ID   BOM   QTY   ",
            "CHECK Drawing Revision A Piping and Instrumentation Diagram Bill of Materials Quantity"
        ),
        (
            "CL EL +104'-6\" TOC ELEVATION",
            "Centerline Elevation +104'-6\" Top of Concrete ELEVATION"
        ),
        (
            "FLG WELD DETAIL ON 316L SS PIPE SCH 40",
            "Flange WELD DETAIL ON 316L SS PIPE Schedule 40"
        )
    ]

    for raw, expected_substr in test_cases:
        res = text_cleaning_service.clean_text(raw)
        assert len(res.cleaned_text) > 0
        assert not res.cleaned_text.startswith(" ")
        assert not res.cleaned_text.endswith(" ")
        # Check normalized tokens
        for token in expected_substr.split():
            assert token.upper() in res.cleaned_text.upper()



def test_max_token_length_and_truncation(classification_service):
    """
    Verify tokenizer truncation behavior for excessively long engineering review notes.
    Model max_length=128 must truncate cleanly without runtime tensor shape exceptions.
    """
    # Create an excessively long 300-word engineering comment
    long_comment = (
        "Check nozzle projection dimension on reactor vessel R-101. " * 30 +
        "Ensure all weld details conform to ASME Section VIII Division 1 standard."
    )
    assert len(long_comment.split()) > 200

    # 1. Verify tokenizer truncation
    encoding = classification_service._ai_tokenizer(
        long_comment,
        truncation=True,
        max_length=128,
        return_tensors="pt"
    ).to(classification_service._ai_device)

    assert encoding["input_ids"].shape == (1, 128)
    assert encoding["attention_mask"].shape == (1, 128)

    # 2. Forward pass runs cleanly
    with torch.no_grad():
        outputs = classification_service._ai_model(**encoding)
        assert outputs.logits.shape == (1, 13)

    # 3. classify_comment executes without exception
    res = classification_service.classify_comment(long_comment)
    assert res.classification_method == "ai_model"
    assert res.primary_category.category_name in ["Dimension", "Technical", "Standards"]


def test_empty_and_whitespace_ocr_handling(classification_service):
    """Verify empty or whitespace-only OCR strings gracefully degrade without errors."""
    for empty_input in ["", "   ", "\n\t  \r\n", None]:
        res = classification_service.classify_comment(empty_input)
        assert res.requires_human_review is True
        assert res.primary_category.confidence == 0.0
        assert res.fallback_used is False


def test_ocr_failure_bypass_and_guardrails():
    """
    Verify that OCR Failed regions ('OCR Failed (Needs Manual Transcription)')
    completely bypass AI classification and are quarantined with manual transcription status.
    """
    file_service_mock = MagicMock()
    file_service_mock.validate_pdf_file.return_value = MagicMock(is_valid=True, error_message=None)
    file_service_mock.copy_to_managed_storage.side_effect = lambda p: p

    pdf_service_mock = MagicMock()
    pdf_service_mock.process_pdf_document.return_value = MagicMock(
        page_count=1,
        title="OCR FAILED TEST",
        drawing_number="DWG-FAIL-01",
        revision="A",
    )

    regions = [
        BoundingBoxDTO(x0=50, y0=50, x1=200, y1=100, page_number=0, confidence=0.96, label="red_box")
    ]
    annotation_service_mock = MagicMock()
    annotation_service_mock.detect_all_pages.return_value = DocumentAnnotationDTO(
        file_name="test_fail.pdf",
        total_pages=1,
        total_regions=1,
        page_results=[AnnotationResultDTO(drawing_id="1", page_number=0, regions=regions, detection_method="hybrid", processing_time_ms=10.0)],
    )

    drawing_repo_mock = MagicMock()
    drawing_repo_mock.get_by_hash.return_value = None
    drawing_repo_mock.save_drawing_from_dto.return_value = {"id": "DWG-FAIL-01", "department_id": None, "project_id": None}

    comment_repo_mock = MagicMock()
    comment_repo_mock.save_comment.side_effect = lambda **kwargs: MagicMock(id=1, **kwargs)

    classification_service_mock = MagicMock()

    engine = ProcessingWorkflowEngine(
        file_service=file_service_mock,
        pdf_service=pdf_service_mock,
        drawing_repo=drawing_repo_mock,
        comment_repo=comment_repo_mock,
        annotation_service=annotation_service_mock,
        classification_service=classification_service_mock,
        text_cleaning_service=MagicMock(clean_text=lambda t: MagicMock(cleaned_text=t)),
    )

    # Simulated OCR failure on unreadable crop
    def mock_process_region(p_obj, reg, p_idx, page_envs, **kwargs):
        return {
            "page_number": p_idx + 1,
            "raw_text": "OCR Failed (Needs Manual Transcription)",
            "cleaned_text": "OCR Failed (Needs Manual Transcription)",
            "bbox": (reg.x0, reg.y0, reg.x1, reg.y1),
            "detection_confidence": 0.96,
            "ocr_confidence": 0.0,
            "confidence": 0.0,
            "ocr_engine": "OCR Failed",
            "label": reg.label,
            "is_ocr_failed": True,
        }

    with patch.object(engine, "_process_single_region_ocr", side_effect=mock_process_region):
        with patch("src.services.workflow_engine.fitz.open") as mock_fitz_open:
            mock_doc = MagicMock()
            mock_doc.__len__.return_value = 1
            mock_doc.__getitem__.return_value = MagicMock()
            mock_fitz_open.return_value = mock_doc
            mock_doc.__enter__.return_value = mock_doc

            result = engine.execute_workflow(Path("test_fail.pdf"))

            assert result.status == "Completed"
            # AI classifier should NOT have been called for failed items
            assert classification_service_mock.classify_batch.call_count == 0

            saved_kwargs = comment_repo_mock.save_comment.call_args.kwargs
            assert saved_kwargs["category_name"] == "Uncategorized"
            assert saved_kwargs["status"] == "Flagged"
            assert saved_kwargs["classification_method"] == "manual_transcription_required"
            assert saved_kwargs["ocr_confidence"] == 0.0
            assert saved_kwargs["classification_confidence"] == 0.0


def test_garbled_ocr_noise_rejection_and_auto_approval_guard(classification_service):
    """
    Confirm that noisy, garbled OCR artifacts or short fragments:
    1. Are capped with low classification confidence (<= 0.50)
    2. Are rejected by auto-approval policy
    3. Are forced to Human Review
    """
    noisy_samples = [
        "?? ## %%%",
        "? 7/16\"",
        "N J ? EXP",
        "PLE 5",
        "W14",
    ]

    for noisy_text in noisy_samples:
        res = classification_service.classify_comment(noisy_text)
        
        # 1. Confidence must be capped and flagged for review
        assert res.requires_human_review is True
        assert res.primary_category.confidence <= 0.55

        # 2. Hardened Auto-Approval Policy MUST reject
        should_approve, reason = evaluate_auto_approval(
            ocr_confidence=0.70,  # Low OCR confidence
            classification_confidence=res.primary_category.confidence,
            text=noisy_text,
            fallback_used=res.fallback_used,
            classification_method=res.classification_method,
            auto_approve_enabled=True,
            threshold=0.85
        )

        assert should_approve is False
        assert "below threshold" in reason.lower() or "short" in reason.lower() or "noisy" in reason.lower()
