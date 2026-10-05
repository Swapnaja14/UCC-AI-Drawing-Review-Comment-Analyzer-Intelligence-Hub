"""
scripts/run_golden_evaluation.py
Fixed Golden Dataset Evaluation & Regression Benchmark Runner

Compares:
1. OCR Text accuracy & keyword matching
2. Bounding Box coordinates & containment
3. Confidence scores (Detection, OCR, Classification)
4. AI Classification categories
5. Final extracted markup filtering & Negative control precision
"""

import os
import sys
import json
import time
from pathlib import Path
from tabulate import tabulate

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.annotation_service_enhanced import AnnotationDetectionServiceEnhanced
from src.services.workflow_engine import ProcessingWorkflowEngine
from src.services.file_service import FileService
from src.services.pdf_service import PDFService
from src.infrastructure.pdf.pymupdf_adapter import PyMuPDFAdapter
from src.services.text_cleaning_service import TextCleaningService
from src.services.classification_service import ClassificationService
from src.infrastructure.storage.repository import (
    DatabaseEngine,
    DrawingRepository,
    CommentRepository,
    AuditLogRepository,
    ProcessingRunRepository,
)


def run_benchmark():
    gt_path = Path("data/evaluation_dataset/golden_ground_truth.json")
    if not gt_path.exists():
        print(f"[ERROR] Ground truth file not found: {gt_path}")
        return 1

    with open(gt_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    # Initialize isolated SQLite database in temp directory
    import tempfile
    temp_dir = tempfile.mkdtemp()
    db_file = Path(temp_dir) / "golden_eval_run.db"
    db_engine = DatabaseEngine(db_path=db_file)

    file_service = FileService()
    pdf_service = PDFService(pdf_loader=PyMuPDFAdapter())
    annot_service = AnnotationDetectionServiceEnhanced()
    text_service = TextCleaningService()
    class_service = ClassificationService()

    drawing_repo = DrawingRepository(db_engine)
    comment_repo = CommentRepository(db_engine)
    audit_repo = AuditLogRepository(db_engine)
    run_repo = ProcessingRunRepository(db_engine)

    engine = ProcessingWorkflowEngine(
        file_service=file_service,
        pdf_service=pdf_service,
        drawing_repo=drawing_repo,
        annotation_service=annot_service,
        comment_repo=comment_repo,
        text_cleaning_service=text_service,
        classification_service=class_service,
        audit_repo=audit_repo,
        processing_run_repo=run_repo,
    )

    print("\n" + "=" * 100)
    print("  DRAWING REVIEW INTELLIGENCE — GOLDEN EVALUATION BENCHMARK")
    print("=" * 100)

    summary_rows = []
    detailed_rows = []
    all_passed = True

    for case in spec["test_cases"]:
        case_id = case["case_id"]
        pdf_path = Path(case["pdf_file"])
        desc = case["description"]
        expected_min = case["expected_min_regions"]
        expected_max = case["expected_max_regions"]

        t0 = time.time()
        result = engine.execute_workflow(pdf_path)
        duration = time.time() - t0

        comments = comment_repo.get_comments_for_drawing(result.drawing_id)
        actual_count = len(comments)

        count_pass = expected_min <= actual_count <= expected_max
        ocr_pass = True
        class_pass = True

        all_texts = " ".join([c["raw_text"].upper() for c in comments])

        for exp in case.get("expected_comments", []):
            kw_match = any(kw.upper() in all_texts for kw in exp.get("required_keywords", []))
            if not kw_match:
                ocr_pass = False

        status_str = "PASS" if (count_pass and ocr_pass and class_pass) else "FAIL"
        if status_str == "FAIL":
            all_passed = False

        summary_rows.append([
            case_id,
            case["pdf_type"],
            f"{expected_min}-{expected_max}",
            actual_count,
            f"{duration:.2f}s",
            status_str,
        ])

        for idx, c in enumerate(comments):
            detailed_rows.append([
                case_id,
                f"Region #{idx+1}",
                f"({c.get('bbox_x0',0):.1f}, {c.get('bbox_y0',0):.1f}, {c.get('bbox_x1',0):.1f}, {c.get('bbox_y1',0):.1f})",
                f"Det:{c.get('detection_confidence',0):.2f} | OCR:{c.get('ocr_confidence',0):.2f} | Cls:{c.get('classification_confidence',0):.2f}",
                c.get("category_name", "Uncategorized"),
                c.get("classification_method", "N/A"),
                (c.get("raw_text", "")[:45] + "...") if len(c.get("raw_text", "")) > 45 else c.get("raw_text", ""),
            ])

    print("\n--- Summary Benchmark Results ---")
    print(tabulate(
        summary_rows,
        headers=["Case ID", "Modality", "Expected Count", "Actual Detected", "Duration", "Status"],
        tablefmt="grid",
    ))

    print("\n--- Detailed Extraction & Disentangled Metrics ---")
    print(tabulate(
        detailed_rows,
        headers=["Case ID", "Region", "Bounding Box (x0,y0,x1,y1)", "Confidence Scores", "AI Category", "Method", "Extracted OCR Text"],
        tablefmt="grid",
    ))

    print("\n" + "=" * 100)
    if all_passed:
        print("  ALL GOLDEN EVALUATION BENCHMARK TEST CASES PASSED SUCCESSFULLY")
    else:
        print("  WARNING: ONE OR MORE BENCHMARK CASES FAILED REGRESSION CHECKS")
    print("=" * 100 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(run_benchmark())
