"""
CLI script to test the complete backend pipeline end-to-end without the UI.
Run this script to verify the services work correctly.
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.infrastructure.storage.repository import DatabaseEngine
from src.services.text_cleaning_service import TextCleaningService
from src.services.classification_service import ClassificationService
from src.services.verification_service import VerificationService
from src.services.export_service import ExportService
from src.services.analytics_service import AnalyticsService
from src.core.dtos.export_dtos import ExportConfigDTO

def main():
    print("Initializing Backend Services...\n")
    
    db_engine = DatabaseEngine()
    
    # Initialize all our new services
    cleaner = TextCleaningService()
    classifier = ClassificationService()
    
    # Pass repository to services that need it
    from src.infrastructure.storage.repository import CommentRepository, ProjectRepository
    comment_repo = CommentRepository(db_engine)
    project_repo = ProjectRepository(db_engine)
    
    export_svc = ExportService(comment_repo, project_repo)
    analytics_svc = AnalyticsService(db_engine)
    
    print("Services initialized successfully.\n")
    
    # 1. Test Text Cleaning
    print("1. Testing Text Cleaning Service")
    raw_text = "chk P&ID for valve    tol. !!!"
    print(f"   Raw Text: '{raw_text}'")
    cleaned = cleaner.clean_text(raw_text)
    print(f"   Cleaned Text: '{cleaned.cleaned_text}'")
    print(f"   Corrections Applied: {[c.original + '->' + c.corrected for c in cleaned.corrections]}\n")
    
    # 2. Test AI Classification
    print("2. Testing Classification Service")
    test_comments = [
        "Check valve flange alignment on P&ID",
        "Cable tray routing near panel is too close",
        "Emergency shutdown valve missing",
        "Tolerance on diameter exceeds limit by 2mm"
    ]
    
    for text in test_comments:
        result = classifier.classify_comment(text)
        confidence = f"{result.primary_category.confidence*100:.1f}%"
        print(f"   [{confidence}] {result.primary_category.category_name} <- '{text}'")
    print()
    
    # 3. Test Analytics Engine
    print("3. Testing Analytics Service")
    kpis = analytics_svc.get_global_kpis()
    print(f"   Total Projects: {kpis.total_projects}")
    print(f"   Total Drawings: {kpis.total_drawings}")
    print(f"   Total Comments: {kpis.total_comments}")
    if kpis.human_verified_approval_rate is not None:
        print(f"   Human-Verified Approval Rate: {kpis.human_verified_approval_rate:.1f}%")
    else:
        print("   Human-Verified Approval Rate: N/A (No comments verified yet)")
    print(f"   Review Progress: {kpis.review_progress or 0.0:.1f}%")
    if kpis.ai_confidence_avg is not None:
        print(f"   Avg AI Confidence (n={kpis.ai_confidence_sample_size}): {kpis.ai_confidence_avg:.2f}\n")
    else:
        print("   Avg AI Confidence: N/A (no ai_model-classified rows)\n")
        
    # 4. Test Excel Export
    print("4. Testing Export Service")
    export_path = Path(__file__).resolve().parent / "test_export.xlsx"
    config = ExportConfigDTO(
        output_path=export_path,
        format="xlsx",
        include_summary_sheet=True
    )
    
    try:
        result = export_svc.export_drawing_comments(config)
        print(f"   Export Success: {result.success}")
        print(f"   File saved to: {result.output_path}")
        print(f"   Total rows exported: {result.total_rows}")
    except ImportError:
        print("   Skipped Excel export because 'openpyxl' is not installed.")
        print("   Run: pip install openpyxl")
    except Exception as e:
        print(f"   Export failed: {e}")
        
    print("\nBackend pipeline test complete!")

if __name__ == "__main__":
    main()
