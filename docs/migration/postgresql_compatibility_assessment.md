# PostgreSQL Compatibility Assessment & Migration Architecture Plan

**Document Path:** `docs/migration/postgresql_compatibility_assessment.md`  
**Assessment Phase:** Phase 2 (Strict Read-Only Audit & Compatibility Planning)  
**Date:** 2026-10-12  
**Status:** Approved for Review (Assessment Only — No Database Alteration Undertaken)  

---

## 1. Executive Summary & Objective

This report delivers a comprehensive, read-only architectural and schema assessment of the **UCC AI Drawing Review Intelligence** application to prepare for migration from local SQLite storage to an office-wide, central PostgreSQL database.

### Core Environment Baseline
- **Original SQLite Source Database:** `data/ucc_database.db` (SHA-256: `91221BBDB2382A9BBF93110835E1DF296881B1EB565EDEF1437C0A72C8F565C4`) — **Preserved and untouched.**
- **Verified Offline Backup:** `backups/sqlite_pre_migration/ucc_database_backup_20261012.db` (SHA-256: `E66517B42D216527584DCC14A55A28F9B51F463EEED298C949FE2C14EA119DA4`) — **Preserved in isolated storage.**
- **Table Count:** 12 tables
- **Total Physical Row Count:** 1,240 rows (100% reconciled in Phase 1B).
- **Target PostgreSQL Engine:** PostgreSQL 18 x64 (Active Windows service `postgresql-x64-18` running on `localhost:5432`).
- **Python Driver:** `psycopg2` (v2.9.x) verified available in the application runtime environment.

### Safety Guarantee
**No PostgreSQL database has been created, initialized, populated, or connected to.** No application configuration, SQLAlchemy models, repositories, or source files were modified. The original SQLite database remains the sole, unmodified active database.

---

## 2. Current Architecture & Codebase Inspection

The application is structured as a desktop hybrid: a **PySide6** graphical user interface backed by modular domain services and SQLAlchemy 2.x ORM repositories.

### Key Architecture Components
1. **Configuration Management (`src/config/app_config.py`):**
   - Dataclass-based hierarchy (`AppConfig`, `DatabaseConfig`) loaded from `config/config.yaml`.
   - `DatabaseConfig` explicitly targets SQLite (`db_path: str = "data/ucc_database.db"`, `wal_mode: bool = True`, `pool_size: int = 5`).
2. **Database Engine & Connection Lifecycle (`src/infrastructure/storage/repository.py`):**
   - Managed by `DatabaseEngine` class (Lines 65–135).
   - Currently hardcoded to `sqlite:///{self.db_path}` with `connect_args={"check_same_thread": False}`.
   - Attaches SQLite connection event listeners for PRAGMAs (`journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`).
   - Implements an internal `_run_migrations()` method (Lines 135–204) that directly executes SQLite-specific `PRAGMA table_info(...)` and `ALTER TABLE ... ADD COLUMN ...` statements.
3. **ORM Model Definitions (`src/infrastructure/storage/models.py`):**
   - Declarative models inheriting from SQLAlchemy 2.x `DeclarativeBase`.
   - Models: `UserModel`, `EngineeringDepartmentModel`, `CategoryModel`, `ProjectModel`, `DrawingModel`, `PageModel`, `CommentModel`, `AuditLogModel`, `ExportLogModel`, `ProcessingRunModel`.
   - SQLite tables not explicitly mapped to ORM classes: `schema_migrations`, `comment_audit_log`.
4. **Desktop Packaging (`UCC_Drawing_Review_Intelligence.spec`):**
   - PyInstaller single-folder distribution bundle.
   - Bundles the local `data/` folder directly into the distribution, assuming SQLite file storage colocated with the executable.

---

## 3. Detailed SQLite-Specific Dependencies & Code Locations

Every direct SQLite dependency in the codebase has been identified and cataloged:

| # | File Path & Line Reference | SQLite-Specific Pattern | Impact on PostgreSQL Migration |
|---|---|---|---|
| 1 | `src/infrastructure/storage/repository.py:86-90` | `create_engine(f"sqlite:///{self.db_path}", connect_args={"check_same_thread": False})` | **Critical.** Cannot connect to PostgreSQL. Must support dynamic connection strings (`postgresql+psycopg2://...`). |
| 2 | `src/infrastructure/storage/repository.py:93-102` | SQLite PRAGMAs: `journal_mode=WAL; synchronous=NORMAL; cache_size=-64000; temp_store=MEMORY; foreign_keys=ON;` | **High.** PostgreSQL syntax error if executed. Must be isolated strictly to SQLite dialect connections. |
| 3 | `src/infrastructure/storage/repository.py:135-204` | Direct `PRAGMA table_info(...)` queries inside `_run_migrations()` | **High.** Will fail on PostgreSQL. Must be replaced with Alembic migrations or dialect-agnostic inspection. |
| 4 | `src/config/app_config.py:22-35` | `DatabaseConfig.db_path: str = "data/ucc_database.db"`, `wal_mode: bool = True` | **Medium.** Lacks fields for PostgreSQL host, port, dbname, user, password, and SSL mode. |
| 5 | `config/config.yaml:4-9` | Configuration block contains only `db_path`, `wal_mode`, `timeout_seconds`, `pool_size`. | **Medium.** Needs optional PostgreSQL connection parameter block. |
| 6 | `src/services/workflow_engine.py:921` | UI status string: `"Saving drawing records to SQLite database."` | **Low.** Cosmetic notification text. |
| 7 | `src/services/auth_service.py:58` | Docstring: `"Seeds default demo accounts into SQLite database if empty."` | **Low.** Informational only. |
| 8 | `UCC_Drawing_Review_Intelligence.spec:8` | PyInstaller datas bundles `('data', 'data')` containing local SQLite database | **High.** Desktop clients distributed to multiple PCs would package local SQLite copies instead of connecting to central database. |

---

## 4. Comprehensive Schema Compatibility Table (All 12 Tables)

All tables and columns use portable SQLAlchemy types. No SQLite-specific keywords (`AUTOINCREMENT`, `INSERT OR REPLACE`, `lastrowid`) are used in ORM operations.

| Table Name | Primary Key Style | Column Types & Constraints | Timestamp Format | Nullability & Relationships | PostgreSQL Compatibility Notes |
|---|---|---|---|---|---|
| `users` (9 rows) | String (`USR-...`) | `VARCHAR(50, 100, 150, 254, 255)`, `BOOLEAN` | `DATETIME` (`datetime.utcnow`) | `department_id` is nullable FK to `engineering_departments.id` | Fully compatible. `username` and `email` have unique indexes. Has PBKDF2 hash & salt. |
| `engineering_departments` (7 rows) | String (`DEPT-...`) | `VARCHAR(50, 100)`, `TEXT`, `BOOLEAN` | `DATETIME` (`datetime.utcnow`) | Root entity. No parent FKs. | Fully compatible. `name` has unique constraint. |
| `categories` (13 rows) | String (`CAT-...`) | `VARCHAR(50, 100, 7)`, `TEXT` | `DATETIME` (`datetime.utcnow`) | Universal categories have `department_name = NULL` | Fully compatible. `name` is indexed. |
| `projects` (0 rows) | String (`PRJ-...`) | `VARCHAR(50, 255, 100)`, `INTEGER`, `TEXT` | `DATETIME` (`datetime.utcnow`) | Container table. | Fully compatible. Currently 0 records in historical DB. |
| `drawings` (9 rows) | String (`DWG-...`) | `VARCHAR(50, 64, 255)`, `INTEGER`, `TEXT`, `BOOLEAN` | `DATETIME` (`datetime.utcnow`) | `project_id` (NULL), `department_id` (NULL for 3 legacy drawings) | Fully compatible. `file_path` stores disk paths. Foreign keys must be `SET NULL`. |
| `pages` (182 rows) | String (`PAGE-...`) | `VARCHAR(50)`, `INTEGER`, `FLOAT`, `BOOLEAN` | No timestamps | Strict `NOT NULL` FK to `drawings.id` (ON DELETE CASCADE) | Fully compatible. Page numbers 1..N. Dimensions in PDF points. |
| `comments` (560 rows) | String (`CMT-...`) | `VARCHAR(50, 100)`, `INTEGER`, `FLOAT`, `TEXT`, `BOOLEAN` | `DATETIME` (`created_at`, `updated_at`) | `drawing_id` (NOT NULL). `page_id`, `category_id`, `department_id`, `user_id` (Nullable FKs) | Fully compatible. 110 legacy comments have NULL `department_id`. Bounding box coordinates in Float. |
| `audit_logs` (449 rows) | String (`AUD-...`) | `VARCHAR(50, 150)`, `TEXT` | `DATETIME` (`timestamp`) | `comment_id` (NOT NULL FK). `user_id` (Nullable FK) | Fully compatible. Historical audit records reference comment IDs. |
| `export_history` (1 row) | String (`EXP-...`) | `VARCHAR(50, 100, 255)`, `INTEGER`, `TEXT` | `DATETIME` (`created_at`) | `drawing_id`, `project_id` (Nullable FKs) | Fully compatible. Excel export record. |
| `processing_runs` (1 row) | String (`RUN-...`) | `VARCHAR(50, 255)`, `FLOAT`, `TEXT` | `DATETIME` (`started_at`, `completed_at`, `created_at`, `updated_at`) | `drawing_id`, `project_id` (Nullable FKs) | Fully compatible. Status strings (`COMPLETED`, `QUEUED`, etc.). |
| `schema_migrations` (9 rows) | Integer (`id`) | `INTEGER` (PK), `VARCHAR(100)`, `DATETIME` | ISO-8601 with TZ (`+00:00`) | Standalone table. | Fully compatible. Tracks applied migration versions. |
| `comment_audit_log` (0 rows) | String | `VARCHAR(50)`, `TEXT`, `DATETIME` | `DATETIME` | Empty legacy table. | Fully compatible. |

### Key Schema Insights
1. **Primary Keys:** Every core business entity uses client-generated prefixed strings (`DWG-XXXXXXXX`, `CMT-XXXXXXXX`, etc.). **There is zero reliance on SQLite `rowid` or autoincrementing integers.** This eliminates primary key re-sequencing risks during migration.
2. **Timestamps:** Timestamps in SQLite are stored as naive text representations of UTC (`2026-09-13 09:21:33.175122`). In PostgreSQL, these will map directly to `TIMESTAMP WITHOUT TIME ZONE` or timezone-aware UTC timestamps.
3. **Boolean Handling:** Handled cleanly by SQLAlchemy's `Boolean` type (maps to `BOOLEAN` in PostgreSQL, whereas SQLite represented them as 0/1 integers).

---

## 5. Repository, Transaction & Concurrency Compatibility

### 1. Connection Pooling & Lifecycle
- **Current SQLite Behavior:** Uses a single local connection or NullPool with file-level locking.
- **PostgreSQL Requirement:** Shared office server requires connection pooling (`QueuePool`). Pool parameters (`pool_size=10`, `max_overflow=20`, `pool_recycle=1800`, `pool_pre_ping=True`) are necessary to prevent stale connections across office PCs.

### 2. Transaction Isolation & Locking
- **Current SQLite Behavior:** In WAL mode, SQLite allows multiple readers but restricts writes to a single concurrent writer across the entire file.
- **PostgreSQL Requirement:** PostgreSQL provides row-level MVCC (Multi-Version Concurrency Control) at `READ COMMITTED` isolation level.
- **Concurrent Edit Protection:** In a multi-user environment where two engineers review the same drawing:
  - Optimistic concurrency control (e.g., checking `updated_at` or version counter before comment modification) is recommended to prevent lost updates.
  - Transactions must use standard explicit commit/rollback blocks (`with session.begin(): ...`).

### 3. Insertion Order & Foreign Key Constraints
- In PostgreSQL, deferred foreign keys or strict topological insertion order is enforced:
  1. `engineering_departments`
  2. `categories`
  3. `users`
  4. `projects`
  5. `drawings`
  6. `pages`
  7. `comments`
  8. `audit_logs`
  9. `processing_runs`
  10. `export_history`

---

## 6. Shared Multi-PC Architecture Requirements (<100 Users)

To achieve the intended office deployment:
```
[Office PC 1 (PySide6 Client)]  ──┐
[Office PC 2 (PySide6 Client)]  ──┼──> [Central FastAPI Backend Service] ──> [PostgreSQL 18 Database]
[Office PC N (PySide6 Client)]  ──┘       └──> [Central Shared File Storage] (PDFs & Excel Exports)
```

### 1. Separation of Concerns (Heavy Processing vs. Central Storage)
- **PDF/OCR Processing Remains Local:** Local desktop clients continue executing PyMuPDF, OpenCV color markup detection, and Tesseract OCR locally on the engineer's machine. This offloads compute from the central server.
- **Central Data Submission:** Once comments and bounding boxes are extracted, the structured DTOs are sent to the central backend and committed to PostgreSQL.

### 2. Shared File Storage (Resolving Local Absolute Paths)
- **Identified Defect:** Currently, `drawings.file_path` contains local machine absolute paths (e.g., `C:\Users\satyajeet virkar22\OneDrive\Desktop\...`).
- **PostgreSQL Solution:** A centralized network file share (UNC path `\\server\ucc_storage\drawings\` or backend object/REST streaming endpoint) is required so that any PC in the office can retrieve and view drawing PDFs and Excel exports.

### 3. Credential Security
- **No Direct PostgreSQL Credentials on Clients:** Desktop PySide6 applications must **not** connect directly to PostgreSQL with administrative credentials over the LAN.
- The central backend API handles database authentication, roles, and department-level authorization (as implemented in Priority 1).

---

## 7. Risk Assessment Matrix

| Risk Level | Risk Description | Root Cause | Mitigation Strategy |
|---|---|---|---|
| **CRITICAL** | Hardcoded Absolute Local File Paths | `drawings.file_path` and `export_history.file_path` store local user paths | Implement relative URI storage or central SMB/REST storage handler so all clients access files reliably. |
| **HIGH** | SQLite PRAGMAs & `_run_migrations` execution | Direct PRAGMA execution in `DatabaseEngine` | Wrap connection setup in dialect check (`if engine.dialect.name == "sqlite": ...`). Adopt Alembic for PostgreSQL DDL. |
| **HIGH** | Connection Dropping on Office LAN | Office network interruptions cause stale connection errors | Configure SQLAlchemy with `pool_pre_ping=True`, `pool_recycle=1800`, and automatic reconnect logic. |
| **MEDIUM** | Timestamp Microsecond & Timezone Discrepancies | SQLite stores naive strings; PostgreSQL expects structured timestamps | Normalize all incoming and migrated timestamps to ISO-8601 UTC before bulk insert. |
| **LOW** | Boolean Type Casts | SQLite stores 0/1; PostgreSQL uses native `BOOLEAN` | SQLAlchemy ORM automatically handles the translation seamlessly. |

---

## 8. Phased Implementation Roadmap

### Phase 3 — Dual-Dialect `DatabaseEngine` Abstraction
- Enhance `DatabaseEngine` in `src/infrastructure/storage/repository.py` to support both `sqlite:///` and `postgresql+psycopg2://` URLs.
- Gate SQLite PRAGMAs behind dialect detection.
- Add PostgreSQL connection pool parameters (`pool_pre_ping=True`).
- Add database configuration options to `DatabaseConfig` in `src/config/app_config.py`.

### Phase 4 — Target PostgreSQL Schema Creation & Repeatable Migration Script
- Create isolated target PostgreSQL database (e.g., `ucc_drawing_intelligence`).
- Generate clean DDL schema using SQLAlchemy `Base.metadata.create_all()`.
- Develop an idempotent, repeatable data migration pipeline (`scripts/migrate_sqlite_to_postgres.py`):
  - Read from `data/ucc_database.db` strictly in read-only mode (`sqlite3:file:...?mode=ro`).
  - Batch insert records into PostgreSQL in dependency order.
  - Automatically verify primary keys, foreign keys, and row counts.

### Phase 5 — Multi-Entity Data Reconciliation
- Execute automated reconciliation comparing SQLite vs. PostgreSQL:
  - Exact row count matches (1,240 total rows).
  - Primary key set comparisons.
  - Comment text integrity (raw OCR vs. edited text).
  - Audit trail linkages and user accounts.

### Phase 6 — Test Suite Execution Against PostgreSQL
- Execute existing test suite (`pytest tests/unit/`) using a temporary PostgreSQL test database.
- Verify 0 regressions across authentication, department authorization, review, and export.

### Phase 7 — Approval-Gated Cutover
- Present comprehensive migration and reconciliation report.
- Await user review and explicit approval.
- Switch `config.yaml` to point to PostgreSQL, leaving `data/ucc_database.db` permanently preserved.

---

## 9. Rollback & Preservation Protocol

1. **Original SQLite Database Invariance:**
   - `data/ucc_database.db` is never modified, renamed, or deleted.
   - If PostgreSQL cutover encounters any issue, reverting `config.yaml` to `db_path: data/ucc_database.db` immediately restores 100% operational state within seconds.
2. **Offline Backup Safety:**
   - The verified offline backup at `backups/sqlite_pre_migration/ucc_database_backup_20261012.db` remains isolated and untouched.

---

## 10. Confirmation of Safety Constraints

- **Source Database Modified?** NO. `data/ucc_database.db` checksum remains `91221BBDB2382A9BBF93110835E1DF296881B1EB565EDEF1437C0A72C8F565C4`.
- **Backup Modified?** NO. `ucc_database_backup_20261012.db` checksum remains `E66517B42D216527584DCC14A55A28F9B51F463EEED298C949FE2C14EA119DA4`.
- **PostgreSQL Database Created or Altered?** NO.
- **Application Configuration Changed?** NO.
- **Dependencies or Packages Installed?** NO.
- **Working Tree Clean?** Yes, Git working tree on `main` is unmodified.
