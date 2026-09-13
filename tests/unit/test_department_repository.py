import pytest
import sqlite3
from pathlib import Path
from src.infrastructure.storage.models import DrawingModel
from src.infrastructure.storage.repository import (
    DatabaseEngine,
    EngineeringDepartmentRepository,
    CommentRepository,
    OFFICIAL_UCC_DEPARTMENTS,
)

def test_department_repository_seeds_official_ucc_departments(tmp_path):
    db_file = tmp_path / "test_dept.db"
    db_engine = DatabaseEngine(db_path=db_file)
    dept_repo = EngineeringDepartmentRepository(db_engine)

    depts = dept_repo.get_all_departments()
    dept_names = [d["name"] for d in depts]

    assert len(depts) >= 7
    for official_dept in OFFICIAL_UCC_DEPARTMENTS:
        assert official_dept in dept_names

def test_get_or_create_custom_department(tmp_path):
    db_file = tmp_path / "test_custom_dept.db"
    db_engine = DatabaseEngine(db_path=db_file)
    dept_repo = EngineeringDepartmentRepository(db_engine)

    new_dept = dept_repo.get_or_create_department(
        name="Instrumentation & Control",
        description="Future expansion department"
    )

    assert new_dept["name"] == "Instrumentation & Control"
    assert new_dept["id"].startswith("DEPT-")

    all_depts = dept_repo.get_all_departments()
    all_names = [d["name"] for d in all_depts]
    assert "Instrumentation & Control" in all_names

def test_sqlite_migration_adds_department_id_to_existing_db(tmp_path):
    db_file = tmp_path / "old_schema.db"
    
    # Create an old SQLite database without department_id column
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE comments (
            id VARCHAR(50) PRIMARY KEY,
            drawing_id VARCHAR(50) NOT NULL,
            page_number INTEGER NOT NULL,
            raw_text TEXT NOT NULL,
            cleaned_text TEXT,
            category_name VARCHAR(100),
            confidence FLOAT,
            status VARCHAR(50),
            bbox_x0 FLOAT, bbox_y0 FLOAT, bbox_x1 FLOAT, bbox_y1 FLOAT,
            label VARCHAR(50),
            is_verified_by_human BOOLEAN,
            created_at DATETIME, updated_at DATETIME
        );
    """)
    conn.commit()
    conn.close()

    # Initialise DatabaseEngine on the old database — _run_migrations should add department_id column seamlessly
    db_engine = DatabaseEngine(db_path=db_file)

    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(comments);")
    cols = [row[1] for row in cursor.fetchall()]
    conn.close()

    assert "department_id" in cols

def test_comment_department_resolution_and_unassigned_fallback(tmp_path):
    db_file = tmp_path / "test_comment_dept.db"
    db_engine = DatabaseEngine(db_path=db_file)
    dept_repo = EngineeringDepartmentRepository(db_engine)
    comment_repo = CommentRepository(db_engine)

    # 0. Create a parent drawing record to satisfy Foreign Key constraint
    with db_engine.get_session() as session:
        session.add(
            DrawingModel(
                id="DWG-TEST01",
                file_path="C:/test/dwg.pdf",
                file_name="dwg.pdf",
                file_size_bytes=1024,
                file_hash_sha256="abc123hash",
                total_pages=1,
            )
        )
        session.commit()

    # 1. Fetch created department
    piping = dept_repo.get_or_create_department("Piping Engineering")

    # 2. Save comment with department_id
    c1 = comment_repo.save_comment(
        drawing_id="DWG-TEST01",
        page_number=1,
        raw_text="Nozzle dimension incorrect",
        bbox=(10.0, 10.0, 100.0, 100.0),
        category_name="Dimensional",
        department_id=piping["id"],
    )

    # 3. Save comment without department_id (unassigned)
    c2 = comment_repo.save_comment(
        drawing_id="DWG-TEST01",
        page_number=1,
        raw_text="General note illegible",
        bbox=(20.0, 20.0, 120.0, 120.0),
        category_name="Documentation",
        department_id=None,
    )

    comments = comment_repo.get_comments_for_drawing("DWG-TEST01")
    assert len(comments) == 2

    # Check c1 department resolution
    comm1 = next(c for c in comments if c["id"] == c1["id"])
    assert comm1["department_name"] == "Piping Engineering"

    # Check c2 unassigned fallback
    comm2 = next(c for c in comments if c["id"] == c2["id"])
    assert comm2["department_name"] == "Unassigned"

def test_get_department_category_counts_pareto_query(tmp_path):
    db_file = tmp_path / "test_pareto_counts.db"
    db_engine = DatabaseEngine(db_path=db_file)
    dept_repo = EngineeringDepartmentRepository(db_engine)
    comment_repo = CommentRepository(db_engine)

    # Create parent drawing records
    with db_engine.get_session() as session:
        session.add(DrawingModel(id="DWG-P01", file_path="p.pdf", file_name="p.pdf", file_size_bytes=100, file_hash_sha256="h1", total_pages=1))
        session.add(DrawingModel(id="DWG-E01", file_path="e.pdf", file_name="e.pdf", file_size_bytes=100, file_hash_sha256="h2", total_pages=1))
        session.commit()

    piping = dept_repo.get_or_create_department("Piping Engineering")
    electrical = dept_repo.get_or_create_department("Electrical Engineering")

    comment_repo.save_comment(
        drawing_id="DWG-P01", page_number=1, raw_text="Flange size error",
        bbox=(0.0, 0.0, 1.0, 1.0), category_name="Dimensional", department_id=piping["id"]
    )
    comment_repo.save_comment(
        drawing_id="DWG-P01", page_number=1, raw_text="Pipe clearance error",
        bbox=(0.0, 0.0, 1.0, 1.0), category_name="Dimensional", department_id=piping["id"]
    )
    comment_repo.save_comment(
        drawing_id="DWG-E01", page_number=1, raw_text="Single line diagram error",
        bbox=(0.0, 0.0, 1.0, 1.0), category_name="Technical", department_id=electrical["id"]
    )

    counts = comment_repo.get_department_category_counts()

    assert counts.get(("Piping Engineering", "Dimensional")) == 2
    assert counts.get(("Electrical Engineering", "Technical")) == 1
