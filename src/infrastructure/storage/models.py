"""
src/infrastructure/storage/models.py
SQLAlchemy 2.x ORM Models for the UCC Analyzer SQLite database.

Tables:
    users        — reviewer/engineer accounts
    categories   — comment classification categories
    projects     — engineering projects
    drawings     — uploaded PDF drawing files (metadata only, no binary data)
    pages        — individual pages extracted from drawings
    comments     — review comments extracted from pages
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    ForeignKey, Text, Index
)
from sqlalchemy.orm import DeclarativeBase, relationship


# ---------------------------------------------------------------------------
# Declarative base (SQLAlchemy 2.x style)
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------

class UserModel(Base):
    """Engineers and reviewers who create or approve comments."""

    __tablename__ = "users"

    id           = Column(String(50),  primary_key=True)
    username     = Column(String(100), nullable=False, unique=True)
    display_name = Column(String(150), nullable=True)
    email        = Column(String(254), nullable=True, unique=True)
    role         = Column(String(50),  nullable=False, default="Reviewer")
    # e.g. "Reviewer", "Lead Engineer", "Admin"
    is_active    = Column(Boolean,     nullable=False, default=True)
    created_at   = Column(DateTime,    nullable=False, default=datetime.utcnow)

    # Authentication fields (used by AuthService for PBKDF2 sign-in)
    password_hash = Column(String(255), nullable=True)
    salt          = Column(String(64),  nullable=True)
    last_login    = Column(DateTime,    nullable=True)

    # Relationships
    comments = relationship(
        "CommentModel",
        back_populates="user",
        foreign_keys="CommentModel.user_id",
    )

    __table_args__ = (
        Index("ix_users_username", "username"),
    )


# ---------------------------------------------------------------------------
# engineering_departments
# ---------------------------------------------------------------------------

class EngineeringDepartmentModel(Base):
    """Engineering departments taxonomy for error tracker metrics and Pareto charts."""

    __tablename__ = "engineering_departments"

    id          = Column(String(50),  primary_key=True)
    name        = Column(String(100), nullable=False, unique=True)
    description = Column(Text,        nullable=True)
    is_active   = Column(Boolean,     nullable=False, default=True)
    created_at  = Column(DateTime,    nullable=False, default=datetime.utcnow)

    # Relationships
    drawings = relationship("DrawingModel", back_populates="department_rel")
    comments = relationship("CommentModel", back_populates="department_rel")

    __table_args__ = (
        Index("ix_engineering_departments_name", "name"),
    )


# ---------------------------------------------------------------------------
# categories
# ---------------------------------------------------------------------------

class CategoryModel(Base):
    """Taxonomy of comment classification categories."""

    __tablename__ = "categories"

    id          = Column(String(50),  primary_key=True)
    name        = Column(String(100), nullable=False, unique=True)
    description = Column(Text,        nullable=True)
    color_hex   = Column(String(7),   nullable=True)   # e.g. "#FBBF24"
    created_at  = Column(DateTime,    nullable=False, default=datetime.utcnow)

    # Relationships
    comments = relationship("CommentModel", back_populates="category_rel")

    __table_args__ = (
        Index("ix_categories_name", "name"),
    )


# ---------------------------------------------------------------------------
# projects
# ---------------------------------------------------------------------------

class ProjectModel(Base):
    """Top-level engineering project containers."""

    __tablename__ = "projects"

    id            = Column(String(50),  primary_key=True)
    name          = Column(String(255), nullable=False)
    description   = Column(Text,        nullable=True)
    status        = Column(String(50),  nullable=False, default="Active")
    # "Active" | "Complete" | "On Hold"
    progress      = Column(Integer,     nullable=False, default=0)   # 0-100
    lead_engineer = Column(String(100), nullable=True)
    created_at    = Column(DateTime,    nullable=False, default=datetime.utcnow)
    updated_at    = Column(DateTime,    nullable=False,
                           default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    drawings = relationship(
        "DrawingModel",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_projects_status", "status"),
    )


# ---------------------------------------------------------------------------
# drawings
# ---------------------------------------------------------------------------

class DrawingModel(Base):
    """
    Metadata for an uploaded PDF drawing.
    Binary PDF content is NEVER stored here — only file path and hashes.
    """

    __tablename__ = "drawings"

    id                = Column(String(50),  primary_key=True)
    project_id        = Column(String(50),
                               ForeignKey("projects.id", ondelete="SET NULL"),
                               nullable=True)
    department_id     = Column(String(50),
                               ForeignKey("engineering_departments.id", ondelete="SET NULL"),
                               nullable=True)
    file_path         = Column(Text,        nullable=False)
    file_name         = Column(String(255), nullable=False)
    file_size_bytes   = Column(Integer,     nullable=False)
    file_hash_sha256  = Column(String(64),  nullable=False)
    total_pages       = Column(Integer,     nullable=False)
    is_scanned        = Column(Boolean,     nullable=False, default=False)
    title             = Column(String(255), nullable=True)
    author            = Column(String(255), nullable=True)
    uploaded_at       = Column(DateTime,    nullable=False, default=datetime.utcnow)

    # Relationships
    project        = relationship("ProjectModel", back_populates="drawings")
    department_rel = relationship("EngineeringDepartmentModel", back_populates="drawings",
                                  foreign_keys=[department_id])
    pages          = relationship(
        "PageModel",
        back_populates="drawing",
        cascade="all, delete-orphan",
    )
    comments       = relationship(
        "CommentModel",
        back_populates="drawing",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # Fast duplicate-detection by hash
        Index("ix_drawings_file_hash", "file_hash_sha256"),
        Index("ix_drawings_project_id", "project_id"),
        Index("ix_drawings_department_id", "department_id"),
    )


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------

class PageModel(Base):
    """Metadata for a single page within a drawing PDF."""

    __tablename__ = "pages"

    id                   = Column(String(50), primary_key=True)
    drawing_id           = Column(String(50),
                                  ForeignKey("drawings.id", ondelete="CASCADE"),
                                  nullable=False)
    page_number          = Column(Integer,    nullable=False)
    width_pt             = Column(Float,      nullable=False)
    height_pt            = Column(Float,      nullable=False)
    aspect_ratio         = Column(Float,      nullable=False)
    has_native_text      = Column(Boolean,    nullable=False, default=False)
    text_character_count = Column(Integer,    nullable=False, default=0)
    orientation_deg      = Column(Integer,    nullable=False, default=0)

    # Relationships
    drawing  = relationship("DrawingModel", back_populates="pages")
    comments = relationship(
        "CommentModel",
        back_populates="page",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_pages_drawing_id", "drawing_id"),
    )


# ---------------------------------------------------------------------------
# comments
# ---------------------------------------------------------------------------

class CommentModel(Base):
    """
    A review comment extracted from a drawing page.

    Relationships:
        page           — the page the comment was extracted from
        drawing        — denormalised short-cut for direct drawing queries
        category_rel   — classification category
        department_rel — engineering department taxonomy
        user           — reviewer who last actioned the comment (nullable)
    """

    __tablename__ = "comments"

    id                   = Column(String(50), primary_key=True)
    drawing_id           = Column(String(50),
                                  ForeignKey("drawings.id", ondelete="CASCADE"),
                                  nullable=False)
    page_id              = Column(String(50),
                                  ForeignKey("pages.id", ondelete="SET NULL"),
                                  nullable=True)
    category_id          = Column(String(50),
                                  ForeignKey("categories.id", ondelete="SET NULL"),
                                  nullable=True)
    department_id        = Column(String(50),
                                  ForeignKey("engineering_departments.id", ondelete="SET NULL"),
                                  nullable=True)
    user_id              = Column(String(50),
                                  ForeignKey("users.id", ondelete="SET NULL"),
                                  nullable=True)
    page_number          = Column(Integer,    nullable=False)
    raw_text             = Column(Text,       nullable=False)
    cleaned_text         = Column(Text,       nullable=True, default="")
    category_name        = Column(String(100),nullable=True, default="Uncategorized")
    # Denormalised label for fast reads; canonical FK is category_id
    confidence           = Column(Float,      nullable=False, default=0.0)
    status               = Column(String(50), nullable=False, default="Pending")
    # "Pending" | "Approved" | "Rejected" | "Flagged"
    bbox_x0              = Column(Float,      nullable=False, default=0.0)
    bbox_y0              = Column(Float,      nullable=False, default=0.0)
    bbox_x1              = Column(Float,      nullable=False, default=0.0)
    bbox_y1              = Column(Float,      nullable=False, default=0.0)
    label                = Column(String(50), nullable=True, default="comment_red")
    is_verified_by_human = Column(Boolean,    nullable=False, default=False)
    created_at           = Column(DateTime,   nullable=False, default=datetime.utcnow)
    updated_at           = Column(DateTime,   nullable=False,
                                  default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    drawing        = relationship("DrawingModel",              back_populates="comments",
                                  foreign_keys=[drawing_id])
    page           = relationship("PageModel",                 back_populates="comments",
                                  foreign_keys=[page_id])
    category_rel   = relationship("CategoryModel",             back_populates="comments",
                                  foreign_keys=[category_id])
    department_rel = relationship("EngineeringDepartmentModel", back_populates="comments",
                                  foreign_keys=[department_id])
    user           = relationship("UserModel",                 back_populates="comments",
                                  foreign_keys=[user_id])
    audit_logs     = relationship("AuditLogModel",             back_populates="comment",
                                  cascade="all, delete-orphan")

    @property
    def department_name(self) -> str:
        """Dynamically return the engineering department name, defaulting to 'Unassigned'."""
        if self.department_rel and self.department_rel.name:
            return self.department_rel.name
        return "Unassigned"

    __table_args__ = (
        Index("ix_comments_drawing_id",     "drawing_id"),
        Index("ix_comments_status",         "status"),
        Index("ix_comments_category_id",    "category_id"),
        Index("ix_comments_department_id",  "department_id"),
        Index("ix_comments_user_id",        "user_id"),
    )


# ---------------------------------------------------------------------------
# audit_logs
# ---------------------------------------------------------------------------

class AuditLogModel(Base):
    """
    Immutable audit log entry recording human review and modification actions
    on comments (e.g. approve, reject, flag, edit text/category).
    """

    __tablename__ = "audit_logs"

    id            = Column(String(50),  primary_key=True)
    comment_id    = Column(String(50),
                           ForeignKey("comments.id", ondelete="CASCADE"),
                           nullable=False)
    action        = Column(String(50),  nullable=False)
    # e.g. "approve", "reject", "flag", "edit_text", "edit_category", "bulk_approve"
    user_id       = Column(String(50),
                           ForeignKey("users.id", ondelete="SET NULL"),
                           nullable=True)
    reviewer_name = Column(String(150), nullable=True)
    old_value     = Column(Text,        nullable=True)
    new_value     = Column(Text,        nullable=True)
    notes         = Column(Text,        nullable=True)
    timestamp     = Column(DateTime,    nullable=False, default=datetime.utcnow)

    # Relationships
    comment = relationship("CommentModel", back_populates="audit_logs", foreign_keys=[comment_id])
    user    = relationship("UserModel", foreign_keys=[user_id])

    __table_args__ = (
        Index("ix_audit_logs_comment_id", "comment_id"),
        Index("ix_audit_logs_timestamp",  "timestamp"),
        Index("ix_audit_logs_user_id",    "user_id"),
    )
