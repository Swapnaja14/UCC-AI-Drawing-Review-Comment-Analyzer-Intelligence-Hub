"""
test_category_management.py — Unit tests for CategoryRepository, dynamic category management,
comment category updates, and SettingsPage category editor integration.
"""
from pathlib import Path
import pytest

from src.infrastructure.storage.repository import (
    DatabaseEngine,
    CategoryRepository,
    CommentRepository,
    AuditLogRepository,
)
from src.infrastructure.storage.models import (
    CommentModel,
    DrawingModel,
)
from app.controllers.app_controller import AppController
from PySide6.QtCore import Qt


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseEngine:
    db_file = tmp_path / "test_cat.db"
    engine = DatabaseEngine(f"sqlite:///{db_file.as_posix()}")
    return engine


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_category_repository_seeding_and_crud(test_db: DatabaseEngine):
    repo = CategoryRepository(test_db)
    
    # 1. Seeding
    repo.seed_default_categories()
    cats = repo.get_all_categories()
    assert len(cats) == 13
    names = [c["name"] for c in cats]
    assert "Technical" in names
    assert "Dimension" in names

    # 2. Add custom category
    created = repo.get_or_create_category("Piping & Instrumentation", "P&ID checks", "#FF5733")
    assert created["name"] == "Piping & Instrumentation"
    
    all_cats = repo.get_all_categories()
    assert len(all_cats) == 14

    # 3. Delete category
    deleted = repo.delete_category("Piping & Instrumentation")
    assert deleted is True
    assert len(repo.get_all_categories()) == 13

    # 4. Delete non-existent returns False
    assert repo.delete_category("NonExistentCat") is False


def test_update_comment_category_and_audit_trail(test_db: DatabaseEngine):
    cat_repo = CategoryRepository(test_db)
    cat_repo.seed_default_categories()

    comment_repo = CommentRepository(test_db)

    # Insert a dummy drawing and comment
    with test_db.get_session() as session:
        dwg = DrawingModel(
            id="DWG-CAT-1",
            file_name="test.pdf",
            file_path="test.pdf",
            file_size_bytes=100,
            file_hash_sha256="hash1",
            total_pages=1,
        )
        session.add(dwg)
        session.flush()

        cmt = CommentModel(
            id="CMT-TEST-1",
            drawing_id="DWG-CAT-1",
            page_number=1,
            raw_text="Check flange clearance",
            cleaned_text="Check flange clearance",
            category_name="Dimension",
            confidence=0.85,
            status="Pending",
            bbox_x0=0.1,
            bbox_y0=0.1,
            bbox_x1=0.3,
            bbox_y1=0.3,
        )
        session.add(cmt)
        session.commit()

    # Update category
    ok = comment_repo.update_comment_category("CMT-TEST-1", "Technical", changed_by_user_id="reviewer_1")
    assert ok is True

    # Verify updated fields in DB
    with test_db.get_session() as session:
        updated = session.get(CommentModel, "CMT-TEST-1")
        assert updated.category_name == "Technical"
        assert updated.is_verified_by_human is True

        # Verify audit log entry
        audit_repo = AuditLogRepository(test_db)
        audit_logs = audit_repo.get_audit_trail("CMT-TEST-1")
        assert len(audit_logs) >= 1
        cat_log = next(a for a in audit_logs if a["action"] == "edit_category")
        assert cat_log["old_value"] == "Dimension"
        assert cat_log["new_value"] == "Technical"
        assert cat_log["reviewer_name"] == "reviewer_1"


def test_app_controller_category_methods(test_db: DatabaseEngine):
    controller = AppController(db_engine=test_db)
    controller.category_repo.seed_default_categories()

    initial_cats = controller.get_all_categories()
    assert len(initial_cats) == 13

    # Add category via controller
    controller.add_category("Instrumentation")
    cats_after_add = controller.get_all_categories()
    assert len(cats_after_add) == 14
    assert any(c["name"] == "Instrumentation" for c in cats_after_add)

    # Delete category via controller
    del_ok = controller.delete_category("Instrumentation")
    assert del_ok is True
    assert len(controller.get_all_categories()) == 13


def test_department_scoped_categories_and_suggestions(test_db: DatabaseEngine):
    controller = AppController(db_engine=test_db)
    controller.category_repo.seed_default_categories()

    # 1. Add category scoped to Piping Engineering
    controller.add_category("Flange Rating Mismatch", department_name="Piping Engineering")

    # 2. Verify it shows up in Piping Engineering
    piping_cats = controller.get_categories_for_department("Piping Engineering")
    piping_cat_names = [c["name"] for c in piping_cats]
    assert "Flange Rating Mismatch" in piping_cat_names

    # 3. Verify it does NOT show up in Electrical Engineering
    elec_cats = controller.get_categories_for_department("Electrical Engineering")
    elec_cat_names = [c["name"] for c in elec_cats]
    assert "Flange Rating Mismatch" not in elec_cat_names

    # 4. Check suggestions for Piping Engineering
    suggestions = controller.get_category_suggestions("Piping Engineering")
    assert len(suggestions) > 0
    # Custom added category should be among suggestions or discipline defaults
    assert any("Flange" in s or "Piping" in s for s in suggestions)

    # 5. Delete department category
    deleted = controller.delete_category("Flange Rating Mismatch", department_name="Piping Engineering")
    assert deleted is True
    piping_cats_after = controller.get_categories_for_department("Piping Engineering")
    assert "Flange Rating Mismatch" not in [c["name"] for c in piping_cats_after]


def test_export_page_and_review_screen_category_ui(test_db: DatabaseEngine, qapp):
    from app.screens.export_screen import ExportPage
    from app.screens.review_screen import HumanReviewPage

    controller = AppController(db_engine=test_db)
    controller.category_repo.seed_default_categories()

    # Create ExportPage with controller
    export_page = ExportPage(controller=controller)
    assert hasattr(export_page, "_dept_combo")
    assert hasattr(export_page, "_scope_grp")
    assert hasattr(export_page, "_export_btn")
    # Verify category editor is cleanly removed from ExportPage
    assert not hasattr(export_page, "_cats_grid")
    assert not hasattr(export_page, "_new_cat_keywords_input")

    # Test review screen instantiation and quick-add
    review_page = HumanReviewPage(controller=controller)
    assert hasattr(review_page, "_cat_combo")
    assert hasattr(review_page, "_quick_add_cat_btn")


def test_category_keywords_storage_and_preconfigured_suggestions(test_db: DatabaseEngine):
    repo = CategoryRepository(test_db)
    repo.seed_default_categories()

    # Test preconfigured suggestion keywords lookup
    kw = repo.get_suggestion_keywords("Flange Rating Mismatch")
    assert "class 150" in kw
    assert "flange rating" in kw

    # Test adding category with keywords
    cat = repo.get_or_create_category(
        name="Nozzle Orientation",
        department_name="Piping Engineering",
        keywords="nozzle orientation, azimuth, nozzle clocking"
    )
    assert cat["name"] == "Nozzle Orientation"
    assert cat["keywords"] == "nozzle orientation, azimuth, nozzle clocking"

    # Query back
    dept_cats = repo.get_categories_for_department("Piping Engineering")
    matching = next(c for c in dept_cats if c["name"] == "Nozzle Orientation")
    assert matching["keywords"] == "nozzle orientation, azimuth, nozzle clocking"


def test_classification_with_custom_category_and_revision_matching(test_db: DatabaseEngine):
    from src.services.classification_service import ClassificationService

    cat_repo = CategoryRepository(test_db)
    cat_repo.seed_default_categories()

    # Add custom category with keywords for Piping Engineering
    cat_repo.get_or_create_category(
        name="Tie-in Flange Spec",
        department_name="Piping Engineering",
        keywords="flange rating, class 150, class 300, tie-in flange"
    )

    classifier = ClassificationService(category_repo=cat_repo)

    # 1. Custom category classification with matched keywords
    res_custom = classifier.classify_comment(
        "Verify tie-in flange rating conforms to class 150 specification",
        department_name="Piping Engineering"
    )
    assert res_custom.primary_category.category_name == "Tie-in Flange Spec"
    assert res_custom.primary_category.confidence >= 0.70
    assert any("class 150" in kw or "flange" in kw for kw in res_custom.primary_category.matched_keywords)

    # 2. Scoped check: For Electrical Engineering, this custom category should NOT be active
    res_elec = classifier.classify_comment(
        "Verify tie-in flange rating conforms to class 150 specification",
        department_name="Electrical Engineering"
    )
    assert res_elec.primary_category.category_name != "Tie-in Flange Spec"

    # 3. Specific user case: "Remove all Revision B flags throughout this drawing"
    # Previously defaulted to Technical — now accurately classifies as Revision!
    res_rev = classifier.classify_comment("Remove all Revision B flags throughout this drawing")
    assert res_rev.primary_category.category_name == "Revision"
    assert res_rev.primary_category.confidence >= 0.65


def test_settings_page_category_scope_and_keywords(test_db: DatabaseEngine, qapp, monkeypatch):
    from app.screens.settings_screen import SettingsPage
    from PySide6.QtWidgets import QMessageBox

    # Mock QMessageBox to auto-confirm
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    controller = AppController(db_engine=test_db)
    controller.category_repo.seed_default_categories()

    page = SettingsPage(controller=controller)
    assert hasattr(page, "_new_cat_name")
    assert hasattr(page, "_new_cat_dept")
    assert hasattr(page, "_new_cat_keywords")
    assert hasattr(page, "_filter_dept_combo")

    # 1. Add department-scoped category via Settings
    page._new_cat_name.setText("Cable Tray Clash")
    # Find and select Electrical Engineering
    idx = page._new_cat_dept.findText("Electrical Engineering", Qt.MatchFlag.MatchContains)
    assert idx != -1
    page._new_cat_dept.setCurrentIndex(idx)
    page._new_cat_keywords.setText("cable tray, tray clash, cable ladder")
    page._on_add_category()

    # Verify saved to DB
    elec_cats = controller.get_categories_for_department("Electrical Engineering")
    tray_cat = next((c for c in elec_cats if c["name"] == "Cable Tray Clash"), None)
    assert tray_cat is not None
    assert tray_cat["department_name"] == "Electrical Engineering"
    assert "tray clash" in tray_cat["keywords"]

    # 2. Add Universal / All Departments category via Settings
    page._new_cat_name.setText("General Standard Deviation")
    page._new_cat_dept.setCurrentIndex(0)  # All Departments (Universal)
    page._new_cat_keywords.setText("spec deviation, standard deviation")
    page._on_add_category()

    all_cats = controller.get_all_categories()
    dev_cat = next((c for c in all_cats if c["name"] == "General Standard Deviation"), None)
    assert dev_cat is not None
    assert dev_cat["department_name"] is None

    # 3. Test filtering categories in list widget
    page._filter_dept_combo.setCurrentText("Electrical Engineering")
    page._refresh_categories()
    items_text = [page._cat_list.item(i).text() for i in range(page._cat_list.count())]
    assert any("Cable Tray Clash" in t for t in items_text)

    # 4. Test deleting category via Settings
    # Select Cable Tray Clash
    for i in range(page._cat_list.count()):
        if "Cable Tray Clash" in page._cat_list.item(i).text():
            page._cat_list.setCurrentRow(i)
            break
    page._on_delete_category()

    elec_cats_after_del = controller.get_categories_for_department("Electrical Engineering")
    assert not any(c["name"] == "Cable Tray Clash" for c in elec_cats_after_del)


