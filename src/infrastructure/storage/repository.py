"""
src/infrastructure/storage/repository.py
SQLAlchemy 2.x session factory, engine initialisation, and repository classes.

Database file: data/ucc_database.db  (relative to the project root)
The data/ directory is created automatically if it does not exist.
No seed / mock data is inserted anywhere in this module.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker, selectinload

from src.core.dtos.pdf_dtos import PDFDocumentDTO
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.storage.models import (
    Base,
    CommentModel,
    DrawingModel,
    PageModel,
    ProjectModel,
    CategoryModel,
    EngineeringDepartmentModel,
    UserModel,
    AuditLogModel,
)

logger = get_logger("DatabaseRepository")

OFFICIAL_UCC_DEPARTMENTS = [
    "Electrical Engineering",
    "GPD",
    "Pipe Support Engineering",
    "Piping Engineering",
    "Plakon",
    "Structural & Physical Design",
    "System Engineering",
]

# ---------------------------------------------------------------------------
# Resolve the canonical database path once at import time.
# Works on Windows (pathlib handles separators) and Linux/macOS alike.
# ---------------------------------------------------------------------------

# __file__ is  …/src/infrastructure/storage/repository.py
# project root is four levels up
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
_DEFAULT_DB_PATH: Path = _PROJECT_ROOT / "data" / "ucc_database.db"


# ---------------------------------------------------------------------------
# DatabaseEngine — engine + session factory
# ---------------------------------------------------------------------------

class DatabaseEngine:
    """
    Manages the SQLite engine and SQLAlchemy session factory.

    Parameters
    ----------
    db_path:
        Absolute or relative path to the SQLite file.
        Defaults to  <project_root>/data/ucc_database.db.
    echo:
        Pass ``True`` to log all generated SQL (useful for debugging).
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        echo: bool = False,
    ) -> None:
        self.db_path: Path = Path(db_path).resolve() if db_path else _DEFAULT_DB_PATH

        # Create the data directory if it does not exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=echo,
            connect_args={"check_same_thread": False},
        )

        # Enable WAL mode, high-performance caching, and foreign-key enforcement
        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA cache_size=-64000;")  # 64MB RAM cache
            cursor.execute("PRAGMA temp_store=MEMORY;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

        self.SessionLocal: sessionmaker[Session] = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

        self._init_db()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_session(self) -> Session:
        """Return a new SQLAlchemy Session.  Caller is responsible for closing it."""
        return self.SessionLocal()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Create all tables declared in models.py (idempotent) and apply migrations."""
        Base.metadata.create_all(bind=self.engine)
        self._run_migrations()
        # Seed official UCC departments automatically if empty
        dept_repo = EngineeringDepartmentRepository(self)
        dept_repo.seed_default_departments()
        logger.info(f"SQLite database ready at: {self.db_path}")

    def _run_migrations(self) -> None:
        """Ensure newly added columns exist in existing SQLite databases and indexes are present."""
        try:
            with self.engine.begin() as conn:
                # Check columns in comments table
                result = conn.execute(text("PRAGMA table_info(comments);"))
                columns = [row[1] for row in result.fetchall()]
                if columns and "label" not in columns:
                    logger.info("Migrating database: adding 'label' column to 'comments' table")
                    conn.execute(text("ALTER TABLE comments ADD COLUMN label VARCHAR(50) DEFAULT 'comment_red';"))
                if columns and "department_id" not in columns:
                    logger.info("Migrating database: adding 'department_id' column to 'comments' table")
                    conn.execute(text("ALTER TABLE comments ADD COLUMN department_id VARCHAR(50);"))

                # Check columns in drawings table
                dwg_result = conn.execute(text("PRAGMA table_info(drawings);"))
                dwg_columns = [row[1] for row in dwg_result.fetchall()]
                if dwg_columns and "department_id" not in dwg_columns:
                    logger.info("Migrating database: adding 'department_id' column to 'drawings' table")
                    conn.execute(text("ALTER TABLE drawings ADD COLUMN department_id VARCHAR(50);"))

                # Ensure performance indexes exist for high-speed queries
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_comments_drawing_id ON comments(drawing_id);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_comments_dept_id ON comments(department_id);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_comments_status ON comments(status);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_comments_category ON comments(category_name);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_drawings_dept_id ON drawings(department_id);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_drawings_proj_id ON drawings(project_id);"))
        except Exception as exc:
            logger.warning(f"Database migration check failed: {exc}")


# ---------------------------------------------------------------------------
# DrawingRepository
# ---------------------------------------------------------------------------

class DrawingRepository:
    """Persistence operations for Drawing and Page records."""

    def __init__(self, db_engine: DatabaseEngine) -> None:
        self._db = db_engine

    def save_drawing_from_dto(
        self,
        dto: PDFDocumentDTO,
        project_id: Optional[str] = None,
        department_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Persist a PDFDocumentDTO as a DrawingModel + PageModel records.

        If a drawing with the same SHA-256 hash already exists, the
        ``uploaded_at`` timestamp is refreshed and the existing record is
        returned — no duplicate is inserted.

        Returns
        -------
        dict with keys: id, file_name, file_path, total_pages,
                        is_scanned, file_hash, department_id
        """
        with self._db.get_session() as session:
            existing = (
                session.query(DrawingModel)
                .filter(DrawingModel.file_hash_sha256 == dto.file_hash_sha256)
                .first()
            )
            if existing:
                existing.uploaded_at = datetime.now(timezone.utc)
                if department_id and not existing.department_id:
                    existing.department_id = department_id
                session.commit()
                logger.info(
                    f"Drawing already in DB (hash={dto.file_hash_sha256[:8]}, "
                    f"id={existing.id}) — timestamp refreshed, department_id={existing.department_id}."
                )
                return _drawing_to_dict(existing)

            drawing_id = f"DWG-{uuid.uuid4().hex[:8].upper()}"
            drawing = DrawingModel(
                id=drawing_id,
                project_id=project_id,
                department_id=department_id,
                file_path=str(dto.file_path),
                file_name=dto.file_name,
                file_size_bytes=dto.file_size_bytes,
                file_hash_sha256=dto.file_hash_sha256,
                total_pages=dto.total_pages,
                is_scanned=dto.is_scanned,
                title=getattr(dto, "title", None),
                author=getattr(dto, "author", None),
                uploaded_at=datetime.now(timezone.utc),
            )
            session.add(drawing)

            for page_dto in dto.pages:
                session.add(
                    PageModel(
                        id=f"PG-{uuid.uuid4().hex[:8].upper()}",
                        drawing_id=drawing_id,
                        page_number=page_dto.page_number,
                        width_pt=page_dto.width_pt,
                        height_pt=page_dto.height_pt,
                        aspect_ratio=page_dto.aspect_ratio,
                        has_native_text=page_dto.has_native_text,
                        text_character_count=page_dto.text_character_count,
                        orientation_deg=page_dto.orientation_deg,
                    )
                )

            session.commit()
            logger.info(
                f"Saved drawing '{dto.file_name}' -> id={drawing_id}, "
                f"department_id={department_id}, {dto.total_pages} page(s)."
            )
            return _drawing_to_dict(drawing)

    def get_recent_drawings(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the most recently uploaded drawings enriched with comment counts."""
        with self._db.get_session() as session:
            rows = (
                session.query(DrawingModel)
                .options(selectinload(DrawingModel.comments))
                .order_by(DrawingModel.uploaded_at.desc())
                .limit(limit)
                .all()
            )
            result = []
            for d in rows:
                d_dict = _drawing_to_dict(d)
                cmts = d.comments if hasattr(d, "comments") and d.comments else []
                d_dict["comments_count"] = len(cmts)
                d_dict["total_comments"] = len(cmts)
                if cmts:
                    conf_vals = [c.confidence for c in cmts if c.confidence is not None]
                    d_dict["avg_confidence"] = (sum(conf_vals) / len(conf_vals)) if conf_vals else 0.0
                    approved_or_rej = sum(1 for c in cmts if c.status in ("Approved", "Rejected"))
                    d_dict["progress"] = int(round((approved_or_rej / len(cmts)) * 100))
                    d_dict["status"] = "Reviewed" if approved_or_rej > 0 else "Analyzed"
                else:
                    d_dict["avg_confidence"] = 0.0
                    d_dict["progress"] = 0
                    d_dict["status"] = "Ready"
                result.append(d_dict)
            return result

    def get_drawing_by_id(self, drawing_id: str) -> Optional[Dict[str, Any]]:
        """Return a single drawing record by primary key, or None."""
        with self._db.get_session() as session:
            row = session.get(DrawingModel, drawing_id)
            return _drawing_to_dict(row) if row else None


# ---------------------------------------------------------------------------
# ProjectRepository
# ---------------------------------------------------------------------------

class ProjectRepository:
    """Persistence and query operations for Project records and KPI aggregates."""

    def __init__(self, db_engine: DatabaseEngine) -> None:
        self._db = db_engine

    def get_all_projects(self) -> List[Dict[str, Any]]:
        """Return all projects ordered by creation date (newest first) with aggregated drawing/comment counts."""
        with self._db.get_session() as session:
            total_projects_count = session.query(ProjectModel).count()
            rows = (
                session.query(ProjectModel)
                .order_by(ProjectModel.created_at.desc())
                .all()
            )
            result = []
            for p in rows:
                p_dict = _project_to_dict(p)
                # Count drawings belonging to this project (or unassigned for default project)
                if total_projects_count == 1 or p.name == "Default Project":
                    dwg_query = session.query(DrawingModel).filter(
                        (DrawingModel.project_id == p.id) | (DrawingModel.project_id.is_(None))
                    )
                else:
                    dwg_query = session.query(DrawingModel).filter(DrawingModel.project_id == p.id)

                dwgs = dwg_query.all()
                dwg_ids = [d.id for d in dwgs]
                dwg_count = len(dwgs)

                if dwg_ids:
                    comments = session.query(CommentModel).filter(CommentModel.drawing_id.in_(dwg_ids)).all()
                    comment_count = len(comments)
                    reviewed_count = sum(1 for c in comments if c.status in ("Approved", "Rejected"))
                    progress = int(round((reviewed_count / comment_count * 100))) if comment_count > 0 else (100 if dwg_count > 0 else 0)
                else:
                    comment_count = 0
                    progress = p.progress or 0

                p_dict["drawings"] = dwg_count
                p_dict["total_drawings"] = dwg_count
                p_dict["comments"] = comment_count
                p_dict["total_comments"] = comment_count
                p_dict["progress"] = progress
                p_dict["lead_engineer"] = p.lead_engineer or "Lead Reviewer"
                result.append(p_dict)
            return result

    def get_project_by_id(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Return a single project with enriched drawing and comment metrics, or None."""
        with self._db.get_session() as session:
            row = session.get(ProjectModel, project_id)
            if not row:
                return None
            p_dict = _project_to_dict(row)
            dwgs = session.query(DrawingModel).filter(DrawingModel.project_id == project_id).all()
            dwg_ids = [d.id for d in dwgs]
            dwg_count = len(dwgs)
            if dwg_ids:
                comments = session.query(CommentModel).filter(CommentModel.drawing_id.in_(dwg_ids)).all()
                comment_count = len(comments)
                reviewed_count = sum(1 for c in comments if c.status in ("Approved", "Rejected"))
                progress = int(round((reviewed_count / comment_count * 100))) if comment_count > 0 else 0
            else:
                comment_count = 0
                progress = row.progress or 0
            p_dict["drawings"] = dwg_count
            p_dict["total_drawings"] = dwg_count
            p_dict["comments"] = comment_count
            p_dict["total_comments"] = comment_count
            p_dict["progress"] = progress
            p_dict["lead_engineer"] = row.lead_engineer or "Lead Reviewer"
            return p_dict

    def create_project(
        self,
        name: str,
        description: Optional[str] = None,
        lead_engineer: Optional[str] = None,
        status: str = "Active",
    ) -> Dict[str, Any]:
        """Insert a new project and return its record."""
        with self._db.get_session() as session:
            project = ProjectModel(
                id=f"PRJ-{uuid.uuid4().hex[:8].upper()}",
                name=name,
                description=description,
                lead_engineer=lead_engineer,
                status=status,
                progress=0,
            )
            session.add(project)
            session.commit()
            logger.info(f"Created project '{name}' → id={project.id}")
            return _project_to_dict(project)

    def get_kpis(self) -> Dict[str, Any]:
        """
        Return live KPI counts from the database.
        No hardcoded fallback values — all figures come from real rows.
        """
        with self._db.get_session() as session:
            total_projects    = session.query(ProjectModel).count()
            drawings_processed = session.query(DrawingModel).count()
            comments_detected  = session.query(CommentModel).count()

            # Accuracy: ratio of human-verified approved comments to all comments
            approved = (
                session.query(CommentModel)
                .filter(
                    CommentModel.status == "Approved",
                    CommentModel.is_verified_by_human.is_(True),
                )
                .count()
            )
            accuracy = (
                round((approved / comments_detected) * 100, 1)
                if comments_detected > 0
                else None
            )

            return {
                "total_projects":    total_projects,
                "drawings_processed": drawings_processed,
                "comments_detected":  comments_detected,
                "accuracy":          accuracy,
            }


# ---------------------------------------------------------------------------
# CategoryRepository
# ---------------------------------------------------------------------------

class CategoryRepository:
    """CRUD for comment classification categories."""

    def __init__(self, db_engine: DatabaseEngine) -> None:
        self._db = db_engine

    def get_all_categories(self) -> List[Dict[str, Any]]:
        with self._db.get_session() as session:
            rows = session.query(CategoryModel).order_by(CategoryModel.name).all()
            return [
                {
                    "id":          c.id,
                    "name":        c.name,
                    "description": c.description,
                    "color_hex":   c.color_hex,
                }
                for c in rows
            ]

    def get_or_create_category(
        self,
        name: str,
        description: Optional[str] = None,
        color_hex: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return an existing category by name, or create it."""
        with self._db.get_session() as session:
            row = (
                session.query(CategoryModel)
                .filter(CategoryModel.name == name)
                .first()
            )
            if row:
                return {"id": row.id, "name": row.name}

            cat = CategoryModel(
                id=f"CAT-{uuid.uuid4().hex[:8].upper()}",
                name=name,
                description=description,
                color_hex=color_hex,
            )
            session.add(cat)
            session.commit()
            logger.info(f"Created category '{name}' → id={cat.id}")
            return {"id": cat.id, "name": cat.name}


# ---------------------------------------------------------------------------
# EngineeringDepartmentRepository
# ---------------------------------------------------------------------------

class EngineeringDepartmentRepository:
    """CRUD operations and seed logic for Engineering Department records."""

    def __init__(self, db_engine: DatabaseEngine) -> None:
        self._db = db_engine

    def get_all_departments(self) -> List[Dict[str, Any]]:
        """Return all active engineering departments ordered by name."""
        with self._db.get_session() as session:
            rows = (
                session.query(EngineeringDepartmentModel)
                .filter(EngineeringDepartmentModel.is_active.is_(True))
                .order_by(EngineeringDepartmentModel.name)
                .all()
            )
            return [
                {
                    "id": d.id,
                    "name": d.name,
                    "description": d.description,
                    "is_active": d.is_active,
                }
                for d in rows
            ]

    def get_or_create_department(
        self,
        name: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return an existing engineering department by name, or create it."""
        with self._db.get_session() as session:
            row = (
                session.query(EngineeringDepartmentModel)
                .filter(EngineeringDepartmentModel.name == name)
                .first()
            )
            if row:
                return {"id": row.id, "name": row.name}

            dept_id = f"DEPT-{uuid.uuid4().hex[:8].upper()}"
            dept = EngineeringDepartmentModel(
                id=dept_id,
                name=name,
                description=description,
                is_active=True,
            )
            session.add(dept)
            session.commit()
            logger.info(f"Created engineering department '{name}' → id={dept_id}")
            return {"id": dept.id, "name": dept.name}

    def seed_default_departments(self) -> None:
        """Seed the 7 official UCC engineering departments if not already present."""
        with self._db.get_session() as session:
            for dept_name in OFFICIAL_UCC_DEPARTMENTS:
                existing = (
                    session.query(EngineeringDepartmentModel)
                    .filter(EngineeringDepartmentModel.name == dept_name)
                    .first()
                )
                if not existing:
                    dept_id = f"DEPT-{uuid.uuid4().hex[:8].upper()}"
                    session.add(
                        EngineeringDepartmentModel(
                            id=dept_id,
                            name=dept_name,
                            description=f"Official UCC Department: {dept_name}",
                            is_active=True,
                        )
                    )
            session.commit()


# ---------------------------------------------------------------------------
# UserRepository
# ---------------------------------------------------------------------------

class UserRepository:
    """CRUD for user / reviewer records."""

    def __init__(self, db_engine: DatabaseEngine) -> None:
        self._db = db_engine

    def get_all_users(self) -> List[Dict[str, Any]]:
        with self._db.get_session() as session:
            rows = (
                session.query(UserModel)
                .filter(UserModel.is_active.is_(True))
                .order_by(UserModel.display_name)
                .all()
            )
            return [_user_to_dict(u) for u in rows]

    def get_or_create_user(
        self,
        username: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
        role: str = "Reviewer",
    ) -> Dict[str, Any]:
        """Return an existing user by username, or create them."""
        with self._db.get_session() as session:
            row = (
                session.query(UserModel)
                .filter(UserModel.username == username)
                .first()
            )
            if row:
                return _user_to_dict(row)

            user = UserModel(
                id=f"USR-{uuid.uuid4().hex[:8].upper()}",
                username=username,
                display_name=display_name or username,
                email=email,
                role=role,
            )
            session.add(user)
            session.commit()
            logger.info(f"Created user '{username}' → id={user.id}")
            return _user_to_dict(user)


# ---------------------------------------------------------------------------
# CommentRepository
# ---------------------------------------------------------------------------

class CommentRepository:
    """Persistence and query operations for Comment records."""

    def __init__(self, db_engine: DatabaseEngine) -> None:
        self._db = db_engine

    def save_comment(
        self,
        drawing_id: str,
        page_number: int,
        raw_text: str,
        bbox: tuple[float, float, float, float],
        confidence: float = 0.0,
        category_id: Optional[str] = None,
        category_name: Optional[str] = "Uncategorized",
        department_id: Optional[str] = None,
        page_id: Optional[str] = None,
        user_id: Optional[str] = None,
        cleaned_text: str = "",
        status: str = "Pending",
        label: str = "comment_red",
    ) -> Dict[str, Any]:
        """Persist a single extracted comment."""
        with self._db.get_session() as session:
            comment = CommentModel(
                id=f"CMT-{uuid.uuid4().hex[:8].upper()}",
                drawing_id=drawing_id,
                page_id=page_id,
                category_id=category_id,
                department_id=department_id,
                user_id=user_id,
                page_number=page_number,
                raw_text=raw_text,
                cleaned_text=cleaned_text,
                category_name=category_name,
                confidence=confidence,
                status=status,
                label=label,
                bbox_x0=bbox[0],
                bbox_y0=bbox[1],
                bbox_x1=bbox[2],
                bbox_y1=bbox[3],
            )
            session.add(comment)
            session.commit()
            return {"id": comment.id, "status": comment.status}

    def delete_comments_for_drawing(self, drawing_id: str) -> int:
        """Delete all existing comments for a drawing before re-processing."""
        with self._db.get_session() as session:
            count = session.query(CommentModel).filter(CommentModel.drawing_id == drawing_id).delete()
            session.commit()
            return count

    def get_comments_for_drawing(self, drawing_id: str) -> List[Dict[str, Any]]:
        with self._db.get_session() as session:
            rows = (
                session.query(CommentModel)
                .filter(CommentModel.drawing_id == drawing_id)
                .order_by(CommentModel.page_number, CommentModel.bbox_y0)
                .all()
            )
            return [_comment_to_dict(c) for c in rows]

    def get_comments_for_page(self, page_id: str) -> List[Dict[str, Any]]:
        with self._db.get_session() as session:
            rows = (
                session.query(CommentModel)
                .filter(CommentModel.page_id == page_id)
                .order_by(CommentModel.bbox_y0)
                .all()
            )
            return [_comment_to_dict(c) for c in rows]

    def get_all_comments(self) -> List[Dict[str, Any]]:
        with self._db.get_session() as session:
            rows = (
                session.query(CommentModel)
                .order_by(CommentModel.drawing_id, CommentModel.page_number, CommentModel.bbox_y0)
                .all()
            )
            return [_comment_to_dict(c) for c in rows]

    def get_comment_by_id(self, comment_id: str) -> Optional[Dict[str, Any]]:
        with self._db.get_session() as session:
            row = session.get(CommentModel, comment_id)
            return _comment_to_dict(row) if row else None

    def update_comment_status(
        self,
        comment_id: str,
        status: str,
        verified_by_human: bool = True,
    ) -> bool:
        """
        Update the status of a single comment.

        Parameters
        ----------
        comment_id:
            The CommentModel primary key ("CMT-XXXXXXXX").
        status:
            Must be one of: "Pending", "Approved", "Rejected", "Flagged".
            Using any other value will store an unrecognised status that
            UI components (StatusChip, StatusDelegate) will not render
            correctly.
        verified_by_human:
            Set True when a human reviewer explicitly approves or rejects.
            Defaults to True for review-screen actions.

        Returns
        -------
        bool
            True if the record was found and updated, False if not found.

        # INTEGRATION NOTE:
        # This method is called from AppController.update_comment_status().
        # UI screens must never call this repository method directly.
        # Status vocabulary: "Pending" | "Approved" | "Rejected" | "Flagged"
        """
        _VALID_STATUSES = {"Pending", "Approved", "Rejected", "Flagged"}
        if status not in _VALID_STATUSES:
            logger.warning(
                f"update_comment_status: '{status}' is not a recognised status. "
                f"Expected one of {_VALID_STATUSES}."
            )

        with self._db.get_session() as session:
            row = session.get(CommentModel, comment_id)
            if row is None:
                logger.warning(f"update_comment_status: comment '{comment_id}' not found.")
                return False
            row.status = status
            row.is_verified_by_human = verified_by_human
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
            logger.info(f"Comment '{comment_id}' status → '{status}', verified={verified_by_human}")
            return True

    def update_comment_text(self, comment_id: str, new_text: str) -> bool:
        """
        Update the raw OCR text of a single comment.

        Used when a human reviewer corrects an OCR extraction error in the
        review screen or OCR results screen.

        Parameters
        ----------
        comment_id:
            The CommentModel primary key ("CMT-XXXXXXXX").
        new_text:
            The corrected OCR text to store in raw_text.

        Returns
        -------
        bool
            True if the record was found and updated, False if not found.

        # INTEGRATION NOTE:
        # This method is called from AppController.update_comment_text().
        # UI screens must never call this repository method directly.
        """
        with self._db.get_session() as session:
            row = session.get(CommentModel, comment_id)
            if row is None:
                logger.warning(f"update_comment_text: comment '{comment_id}' not found.")
                return False
            row.raw_text = new_text
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
            logger.info(f"Comment '{comment_id}' raw_text updated ({len(new_text)} chars).")
            return True

    def get_category_counts(
        self, drawing_id: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Return comment counts grouped by category_name.

        Parameters
        ----------
        drawing_id:
            If provided, counts only comments for that drawing.
            If None, counts across all drawings in the database.

        Returns
        -------
        Dict[str, int]
            e.g. {"Dimensional": 42, "Structural": 18, ...}
            Returns an empty dict if no comments exist.

        # INTEGRATION NOTE:
        # Used by ClassificationPage (per-drawing counts) and AnalyticsPage
        # (all-drawing counts). Called through AppController.get_category_counts().
        # UI screens must never call this repository method directly.
        """
        with self._db.get_session() as session:
            query = session.query(
                CommentModel.category_name,
                # Use SQLAlchemy func.count for portability across DB backends
                __import__("sqlalchemy").func.count(CommentModel.id).label("cnt"),
            )
            if drawing_id is not None:
                query = query.filter(CommentModel.drawing_id == drawing_id)
            rows = query.group_by(CommentModel.category_name).all()
            return {
                (row.category_name or "Uncategorized"): row.cnt
                for row in rows
            }

    def get_department_category_counts(
        self, drawing_id: Optional[str] = None
    ) -> Dict[tuple[str, str], int]:
        """
        Return comment counts grouped by (department_name, category_name) for Pareto charts.
        """
        with self._db.get_session() as session:
            query = session.query(
                EngineeringDepartmentModel.name.label("dept_name"),
                CommentModel.category_name,
                __import__("sqlalchemy").func.count(CommentModel.id).label("cnt"),
            ).outerjoin(
                EngineeringDepartmentModel,
                CommentModel.department_id == EngineeringDepartmentModel.id,
            )
            if drawing_id is not None:
                query = query.filter(CommentModel.drawing_id == drawing_id)
            rows = query.group_by(
                EngineeringDepartmentModel.name, CommentModel.category_name
            ).all()
            return {
                (
                    row.dept_name or "Unassigned",
                    row.category_name or "Uncategorized",
                ): row.cnt
                for row in rows
            }


# ---------------------------------------------------------------------------
# AuditLogRepository
# ---------------------------------------------------------------------------

class AuditLogRepository:
    """Persistence and query operations for Comment Audit Logs."""

    def __init__(self, db_engine: DatabaseEngine) -> None:
        self._db = db_engine

    def create_audit_entry(
        self,
        comment_id: str,
        action: str,
        reviewer_id: Optional[str] = None,
        reviewer_name: Optional[str] = None,
        old_value: Optional[str] = "",
        new_value: Optional[str] = "",
        notes: Optional[str] = "",
        timestamp: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Record an immutable audit log entry for a comment modification."""
        with self._db.get_session() as session:
            # Safely check if reviewer_id is a valid user_id in the users table
            valid_user_id = None
            if reviewer_id and reviewer_id != "system":
                user_match = session.get(UserModel, reviewer_id)
                if user_match:
                    valid_user_id = reviewer_id
                    if not reviewer_name:
                        reviewer_name = user_match.display_name or user_match.username

            entry = AuditLogModel(
                id=f"AUD-{uuid.uuid4().hex[:8].upper()}",
                comment_id=comment_id,
                action=action,
                user_id=valid_user_id,
                reviewer_name=reviewer_name or reviewer_id or "system",
                old_value=old_value or "",
                new_value=new_value or "",
                notes=notes or "",
                timestamp=timestamp or datetime.now(timezone.utc),
            )
            session.add(entry)
            session.commit()
            return _audit_log_to_dict(entry)

    def get_audit_logs_for_comment(self, comment_id: str) -> List[Dict[str, Any]]:
        """Return all historical audit log entries for a specific comment (newest first)."""
        with self._db.get_session() as session:
            rows = (
                session.query(AuditLogModel)
                .filter(AuditLogModel.comment_id == comment_id)
                .order_by(AuditLogModel.timestamp.desc())
                .all()
            )
            return [_audit_log_to_dict(r) for r in rows]

    def get_recent_audit_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent audit logs across all comments."""
        with self._db.get_session() as session:
            rows = (
                session.query(AuditLogModel)
                .order_by(AuditLogModel.timestamp.desc())
                .limit(limit)
                .all()
            )
            return [_audit_log_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Private serialisation helpers
# ---------------------------------------------------------------------------

def _drawing_to_dict(d: DrawingModel) -> Dict[str, Any]:
    return {
        "id":              d.id,
        "file_name":       d.file_name,
        "file_path":       d.file_path,
        "total_pages":     d.total_pages,
        "is_scanned":      d.is_scanned,
        "file_hash":       d.file_hash_sha256,
        "project_id":      d.project_id,
        "department_id":   d.department_id,
        "department_name": d.department_rel.name if d.department_rel else "Unassigned",
        "uploaded_at":     (
            d.uploaded_at.strftime("%Y-%m-%d %H:%M:%S")
            if d.uploaded_at else ""
        ),
    }


def _project_to_dict(p: ProjectModel) -> Dict[str, Any]:
    return {
        "id":            p.id,
        "name":          p.name,
        "description":   p.description,
        "status":        p.status,
        "progress":      p.progress,
        "lead_engineer": p.lead_engineer,
        "created_at":    (
            p.created_at.strftime("%Y-%m-%d %H:%M:%S")
            if p.created_at else ""
        ),
        "updated_at":    (
            p.updated_at.strftime("%Y-%m-%d %H:%M:%S")
            if p.updated_at else ""
        ),
    }


def _user_to_dict(u: UserModel) -> Dict[str, Any]:
    return {
        "id":           u.id,
        "username":     u.username,
        "display_name": u.display_name,
        "email":        u.email,
        "role":         u.role,
        "is_active":    u.is_active,
    }


def _comment_to_dict(c: CommentModel) -> Dict[str, Any]:
    return {
        "id":                   c.id,
        "drawing_id":           c.drawing_id,
        "page_id":              c.page_id,
        "page_number":          c.page_number,
        "raw_text":             c.raw_text,
        "cleaned_text":         c.cleaned_text,
        "category_id":          c.category_id,
        "category_name":        c.category_name,
        "department_id":        c.department_id,
        "department_name":      c.department_name,
        "user_id":              c.user_id,
        "confidence":           c.confidence,
        "status":               c.status,
        "label":                getattr(c, "label", "comment_red") or "comment_red",
        "bbox":                 (c.bbox_x0, c.bbox_y0, c.bbox_x1, c.bbox_y1),
        "is_verified_by_human": c.is_verified_by_human,
        "created_at":           (
            c.created_at.strftime("%Y-%m-%d %H:%M:%S")
            if c.created_at else ""
        ),
    }


def _audit_log_to_dict(a: AuditLogModel) -> Dict[str, Any]:
    return {
        "id":            a.id,
        "comment_id":    a.comment_id,
        "action":        a.action,
        "user_id":       a.user_id,
        "reviewer_id":   a.user_id or a.reviewer_name or "system",
        "reviewer_name": a.reviewer_name or a.user_id or "system",
        "old_value":     a.old_value or "",
        "new_value":     a.new_value or "",
        "notes":         a.notes or "",
        "timestamp":     (
            a.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            if a.timestamp else ""
        ),
        "created_at":    (
            a.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            if a.timestamp else ""
        ),
    }
