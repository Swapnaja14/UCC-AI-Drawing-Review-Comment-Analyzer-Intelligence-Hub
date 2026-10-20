# PostgreSQL Migration & Disaster Recovery Plan

**Document Path:** `docs/migration/postgresql_migration_and_recovery_plan.md`  
**Phase:** Phase 3 — Migration and Recovery Design (Planning Only)  
**Date:** 2026-10-12  
**Status:** Approved for Review (Planning Document Only — No DB Changes Made)  

---

## 1. Executive Summary & Foundational Baselines

This document defines an implementation-ready, repeatable, zero-data-loss migration and disaster recovery plan to transition the **UCC AI Drawing Review Intelligence** platform from local SQLite to a shared **PostgreSQL 18** database.

### Immutable Safety & Preservation Rules
1. **Source SQLite Database Invariance:**  
   `data/ucc_database.db` (SHA-256: `91221BBDB2382A9BBF93110835E1DF296881B1EB565EDEF1437C0A72C8F565C4`) is preserved at its current path indefinitely and treated strictly as a **read-only source**. It will never be deleted, renamed, truncated, or modified.
2. **Verified Backup Retention:**  
   `backups/sqlite_pre_migration/ucc_database_backup_20261012.db` (SHA-256: `E66517B42D216527584DCC14A55A28F9B51F463EEED298C949FE2C14EA119DA4`) remains safely stored in isolated storage alongside manifests `backup_manifest.json`, `phase1a_verification_report.json`, and `phase1b_reconciliation_report.json`.
3. **Confirmed Data Volume:**  
   12 tables, exactly **1,240 physical records** across all entities (verified in Phase 1B).
4. **Target Database Engine:**  
   PostgreSQL 18 x64 (local service `postgresql-x64-18` currently running on port 5432). Python driver `psycopg2` verified available.

---

## 2. Exhaustive Schema & Type Mapping Specification

Every SQLite table is mapped to PostgreSQL types using SQLAlchemy 2.x ORM standards. All client-generated string primary keys (`DWG-...`, `CMT-...`, `USR-...`) are preserved bit-for-bit without sequence modification.

### 2.1 Table-by-Table Schema Specification

#### 1. `engineering_departments` (Root Entity — 7 Rows)
- **Target Table:** `engineering_departments`
- **Columns:**
  - `id`: `VARCHAR(50)` `NOT NULL` `PRIMARY KEY` (e.g., `DEPT-ELEC-01`)
  - `name`: `VARCHAR(100)` `NOT NULL` `UNIQUE`
  - `description`: `TEXT` `NULL`
  - `is_active`: `BOOLEAN` `NOT NULL` `DEFAULT TRUE`
  - `created_at`: `TIMESTAMP WITH TIME ZONE` `NOT NULL` `DEFAULT CURRENT_TIMESTAMP`
- **Indexes:** `ix_engineering_departments_name` on `(name)`
- **Dependencies:** None (Parent table).

#### 2. `categories` (Root Taxonomy — 13 Rows)
- **Target Table:** `categories`
- **Columns:**
  - `id`: `VARCHAR(50)` `NOT NULL` `PRIMARY KEY` (e.g., `CAT-ELEC-01`)
  - `name`: `VARCHAR(100)` `NOT NULL`
  - `department_name`: `VARCHAR(100)` `NULL` (Universal categories have `NULL`)
  - `description`: `TEXT` `NULL`
  - `keywords`: `TEXT` `NULL` (Comma-separated keyword patterns)
  - `color_hex`: `VARCHAR(7)` `NULL` (e.g., `#FBBF24`)
  - `created_at`: `TIMESTAMP WITH TIME ZONE` `NOT NULL` `DEFAULT CURRENT_TIMESTAMP`
- **Indexes:** `ix_categories_name` on `(name)`, `ix_categories_department` on `(department_name)`
- **Dependencies:** None.

#### 3. `users` (Accounts & Security — 9 Rows)
- **Target Table:** `users`
- **Columns:**
  - `id`: `VARCHAR(50)` `NOT NULL` `PRIMARY KEY` (e.g., `USR-ADMIN`, `USR-ELEC`)
  - `username`: `VARCHAR(100)` `NOT NULL` `UNIQUE`
  - `display_name`: `VARCHAR(150)` `NULL`
  - `email`: `VARCHAR(254)` `NULL` `UNIQUE`
  - `role`: `VARCHAR(50)` `NOT NULL` `DEFAULT 'Reviewer'`
  - `department_id`: `VARCHAR(50)` `NULL` `REFERENCES engineering_departments(id) ON DELETE SET NULL`
  - `is_active`: `BOOLEAN` `NOT NULL` `DEFAULT TRUE`
  - `password_hash`: `VARCHAR(255)` `NULL` (Preserved PBKDF2 hash)
  - `salt`: `VARCHAR(64)` `NULL` (Preserved cryptographic salt)
  - `last_login`: `TIMESTAMP WITH TIME ZONE` `NULL`
  - `created_at`: `TIMESTAMP WITH TIME ZONE` `NOT NULL` `DEFAULT CURRENT_TIMESTAMP`
- **Indexes:** `ix_users_username` on `(username)`, `ix_users_department_id` on `(department_id)`
- **Dependencies:** `engineering_departments`.

#### 4. `projects` (Container Entity — 0 Rows)
- **Target Table:** `projects`
- **Columns:**
  - `id`: `VARCHAR(50)` `NOT NULL` `PRIMARY KEY` (e.g., `PRJ-XXXXXXXX`)
  - `name`: `VARCHAR(255)` `NOT NULL`
  - `description`: `TEXT` `NULL`
  - `status`: `VARCHAR(50)` `NOT NULL` `DEFAULT 'Active'`
  - `progress`: `INTEGER` `NOT NULL` `DEFAULT 0`
  - `lead_engineer`: `VARCHAR(100)` `NULL`
  - `created_at`: `TIMESTAMP WITH TIME ZONE` `NOT NULL` `DEFAULT CURRENT_TIMESTAMP`
  - `updated_at`: `TIMESTAMP WITH TIME ZONE` `NOT NULL` `DEFAULT CURRENT_TIMESTAMP`
- **Indexes:** `ix_projects_status` on `(status)`
- **Dependencies:** None. Note: Table currently has 0 rows; DDL will be created clean.

#### 5. `drawings` (Engineering Drawing Files — 9 Rows)
- **Target Table:** `drawings`
- **Columns:**
  - `id`: `VARCHAR(50)` `NOT NULL` `PRIMARY KEY` (e.g., `DWG-XXXXXXXX`)
  - `project_id`: `VARCHAR(50)` `NULL` `REFERENCES projects(id) ON DELETE SET NULL`
  - `department_id`: `VARCHAR(50)` `NULL` `REFERENCES engineering_departments(id) ON DELETE SET NULL`
  - `file_path`: `TEXT` `NOT NULL` (Physical path on disk or network storage)
  - `file_name`: `VARCHAR(255)` `NOT NULL`
  - `file_size_bytes`: `BIGINT` `NOT NULL` (Cast SQLite Integer to BIGINT for large PDF safety)
  - `file_hash_sha256`: `VARCHAR(64)` `NOT NULL`
  - `total_pages`: `INTEGER` `NOT NULL`
  - `is_scanned`: `BOOLEAN` `NOT NULL` `DEFAULT FALSE`
  - `title`: `VARCHAR(255)` `NULL`
  - `author`: `VARCHAR(255)` `NULL`
  - `drawing_number`: `VARCHAR(100)` `NULL`
  - `creation_date`: `VARCHAR(100)` `NULL`
  - `modification_date`: `VARCHAR(100)` `NULL`
  - `ocr_status`: `VARCHAR(50)` `NULL`
  - `uploaded_at`: `TIMESTAMP WITH TIME ZONE` `NOT NULL` `DEFAULT CURRENT_TIMESTAMP`
- **Indexes:** `ix_drawings_file_hash` on `(file_hash_sha256)`, `ix_drawings_project_id` on `(project_id)`, `ix_drawings_department_id` on `(department_id)`
- **Dependencies:** `projects`, `engineering_departments`.

#### 6. `pages` (Extracted Drawing Pages — 182 Rows)
- **Target Table:** `pages`
- **Columns:**
  - `id`: `VARCHAR(50)` `NOT NULL` `PRIMARY KEY` (e.g., `PAGE-XXXXXXXX`)
  - `drawing_id`: `VARCHAR(50)` `NOT NULL` `REFERENCES drawings(id) ON DELETE CASCADE`
  - `page_number`: `INTEGER` `NOT NULL`
  - `width_pt`: `DOUBLE PRECISION` `NOT NULL`
  - `height_pt`: `DOUBLE PRECISION` `NOT NULL`
  - `aspect_ratio`: `DOUBLE PRECISION` `NOT NULL`
  - `has_native_text`: `BOOLEAN` `NOT NULL` `DEFAULT FALSE`
  - `text_character_count`: `INTEGER` `NOT NULL` `DEFAULT 0`
  - `orientation_deg`: `INTEGER` `NOT NULL` `DEFAULT 0`
- **Indexes:** `ix_pages_drawing_id` on `(drawing_id)`
- **Dependencies:** `drawings`.

#### 7. `comments` (Core Extracted Review Comments — 560 Rows)
- **Target Table:** `comments`
- **Columns:**
  - `id`: `VARCHAR(50)` `NOT NULL` `PRIMARY KEY` (e.g., `CMT-XXXXXXXX`)
  - `drawing_id`: `VARCHAR(50)` `NOT NULL` `REFERENCES drawings(id) ON DELETE CASCADE`
  - `page_id`: `VARCHAR(50)` `NULL` `REFERENCES pages(id) ON DELETE SET NULL`
  - `category_id`: `VARCHAR(50)` `NULL` `REFERENCES categories(id) ON DELETE SET NULL`
  - `department_id`: `VARCHAR(50)` `NULL` `REFERENCES engineering_departments(id) ON DELETE SET NULL`
  - `user_id`: `VARCHAR(50)` `NULL` `REFERENCES users(id) ON DELETE SET NULL`
  - `page_number`: `INTEGER` `NOT NULL`
  - `raw_text`: `TEXT` `NOT NULL` (Exact unedited OCR extraction text)
  - `cleaned_text`: `TEXT` `NULL` (Human-edited or cleaned text)
  - `category_name`: `VARCHAR(100)` `NULL` `DEFAULT 'Uncategorized'`
  - `confidence`: `DOUBLE PRECISION` `NOT NULL` `DEFAULT 0.0`
  - `detection_confidence`: `DOUBLE PRECISION` `NOT NULL` `DEFAULT 0.0`
  - `ocr_confidence`: `DOUBLE PRECISION` `NOT NULL` `DEFAULT 0.0`
  - `classification_confidence`: `DOUBLE PRECISION` `NOT NULL` `DEFAULT 0.0`
  - `classification_method`: `VARCHAR(50)` `NULL` `DEFAULT 'ai_model'`
  - `fallback_used`: `BOOLEAN` `NOT NULL` `DEFAULT FALSE`
  - `ocr_engine`: `VARCHAR(50)` `NULL` `DEFAULT 'Tesseract OCR'`
  - `status`: `VARCHAR(50)` `NOT NULL` `DEFAULT 'Pending'`
  - `bbox_x0`: `DOUBLE PRECISION` `NOT NULL` `DEFAULT 0.0`
  - `bbox_y0`: `DOUBLE PRECISION` `NOT NULL` `DEFAULT 0.0`
  - `bbox_x1`: `DOUBLE PRECISION` `NOT NULL` `DEFAULT 0.0`
  - `bbox_y1`: `DOUBLE PRECISION` `NOT NULL` `DEFAULT 0.0`
  - `label`: `VARCHAR(50)` `NULL` `DEFAULT 'comment_red'`
  - `is_verified_by_human`: `BOOLEAN` `NOT NULL` `DEFAULT FALSE`
  - `department_name`: `VARCHAR(100)` `NULL`
  - `created_at`: `TIMESTAMP WITH TIME ZONE` `NOT NULL` `DEFAULT CURRENT_TIMESTAMP`
  - `updated_at`: `TIMESTAMP WITH TIME ZONE` `NOT NULL` `DEFAULT CURRENT_TIMESTAMP`
- **Indexes:** `ix_comments_drawing_id`, `ix_comments_status`, `ix_comments_category_id`, `ix_comments_department_id`, `ix_comments_user_id`
- **Dependencies:** `drawings`, `pages`, `categories`, `engineering_departments`, `users`.

#### 8. `audit_logs` (Historical Review Audit Trail — 449 Rows)
- **Target Table:** `audit_logs`
- **Columns:**
  - `id`: `VARCHAR(50)` `NOT NULL` `PRIMARY KEY` (e.g., `AUD-XXXXXXXX`)
  - `comment_id`: `VARCHAR(50)` `NOT NULL` `REFERENCES comments(id) ON DELETE CASCADE`
  - `action`: `VARCHAR(50)` `NOT NULL` (e.g., `approve`, `reject`, `flag`, `edit_text`)
  - `user_id`: `VARCHAR(50)` `NULL` `REFERENCES users(id) ON DELETE SET NULL`
  - `reviewer_name`: `VARCHAR(150)` `NULL`
  - `old_value`: `TEXT` `NULL`
  - `new_value`: `TEXT` `NULL`
  - `notes`: `TEXT` `NULL`
  - `timestamp`: `TIMESTAMP WITH TIME ZONE` `NOT NULL` `DEFAULT CURRENT_TIMESTAMP`
- **Indexes:** `ix_audit_logs_comment_id`, `ix_audit_logs_user_id`, `ix_audit_logs_timestamp`
- **Dependencies:** `comments`, `users`.

#### 9. `export_history` (Excel Audit Log — 1 Row)
- **Target Table:** `export_history`
- **Columns:**
  - `id`: `VARCHAR(50)` `NOT NULL` `PRIMARY KEY` (e.g., `EXP-XXXXXXXX`)
  - `file_name`: `VARCHAR(255)` `NOT NULL`
  - `file_path`: `TEXT` `NOT NULL`
  - `format`: `VARCHAR(50)` `NOT NULL` (`Excel`)
  - `scope`: `VARCHAR(50)` `NOT NULL`
  - `drawing_id`: `VARCHAR(50)` `NULL` `REFERENCES drawings(id) ON DELETE SET NULL`
  - `project_id`: `VARCHAR(50)` `NULL` `REFERENCES projects(id) ON DELETE SET NULL`
  - `department_name`: `VARCHAR(100)` `NULL`
  - `total_rows`: `INTEGER` `NOT NULL` `DEFAULT 0`
  - `file_size_bytes`: `BIGINT` `NOT NULL` `DEFAULT 0`
  - `status`: `VARCHAR(50)` `NOT NULL` `DEFAULT 'Success'`
  - `created_at`: `TIMESTAMP WITH TIME ZONE` `NOT NULL` `DEFAULT CURRENT_TIMESTAMP`
- **Indexes:** `ix_export_history_created_at`, `ix_export_history_project_id`, `ix_export_history_drawing_id`
- **Dependencies:** `drawings`, `projects`.

#### 10. `processing_runs` (Pipeline Execution History — 1 Row)
- **Target Table:** `processing_runs`
- **Columns:**
  - `id`: `VARCHAR(50)` `NOT NULL` `PRIMARY KEY` (e.g., `RUN-XXXXXXXX`)
  - `project_id`: `VARCHAR(50)` `NULL` `REFERENCES projects(id) ON DELETE SET NULL`
  - `drawing_id`: `VARCHAR(50)` `NULL` `REFERENCES drawings(id) ON DELETE SET NULL`
  - `original_filename`: `VARCHAR(255)` `NOT NULL`
  - `started_at`: `TIMESTAMP WITH TIME ZONE` `NOT NULL` `DEFAULT CURRENT_TIMESTAMP`
  - `completed_at`: `TIMESTAMP WITH TIME ZONE` `NULL`
  - `duration_seconds`: `DOUBLE PRECISION` `NOT NULL` `DEFAULT 0.0`
  - `status`: `VARCHAR(50)` `NOT NULL` `DEFAULT 'QUEUED'`
  - `error_message`: `TEXT` `NULL`
  - `telemetry_json`: `TEXT` `NULL`
  - `created_at`: `TIMESTAMP WITH TIME ZONE` `NOT NULL` `DEFAULT CURRENT_TIMESTAMP`
  - `updated_at`: `TIMESTAMP WITH TIME ZONE` `NOT NULL` `DEFAULT CURRENT_TIMESTAMP`
- **Indexes:** `ix_processing_runs_status`, `ix_processing_runs_created_at`, `ix_processing_runs_drawing_id`, `ix_processing_runs_project_id`
- **Dependencies:** `drawings`, `projects`.

#### 11. `schema_migrations` (Applied Migration Log — 9 Rows)
- **Target Table:** `schema_migrations`
- **Columns:**
  - `id`: `INTEGER` `PRIMARY KEY` (Preserved sequence ID 1..9)
  - `version`: `VARCHAR(100)` `NOT NULL`
  - `applied_at`: `TIMESTAMP WITH TIME ZONE` `NOT NULL`
- **Dependencies:** None.

#### 12. `comment_audit_log` (Legacy Table — 0 Rows)
- **Target Table:** `comment_audit_log`
- Created as an empty legacy schema mirror with identical types for 100% table-level fidelity.

---

## 3. Timestamp & Timezone Resolution Strategy

### Concrete Strategy
- SQLite values are naive strings recorded in UTC: `2026-09-13 09:21:33.175122`.
- `schema_migrations` values are ISO-8601 strings with explicit UTC: `2026-09-27T11:08:31.977997+00:00`.
- **Transformation Rule:** All incoming SQLite timestamp strings are parsed using Python's `datetime.fromisoformat()` and explicitly tagged with `timezone.utc` before inserting into PostgreSQL `TIMESTAMP WITH TIME ZONE` columns. This prevents any server-local timezone shift or daylight-saving distortion.

---

## 4. Repeatable, Transactional Migration Execution

The migration script (`scripts/migrate_sqlite_to_postgres.py`) will adhere to strict operational guidelines:

```
[Start Migration Process]
       │
       ▼
[Verify Pre-conditions]
  ├── Verify source DB checksum against Phase 1 manifest (Must match!)
  ├── Check PostgreSQL connection & database existence
  └── Confirm destination database is empty (0 rows in all tables)
       │
       ▼
[Open Source Database in Read-Only Mode]
  └── Connect with URI: `file:data/ucc_database.db?mode=ro`
       │
       ▼
[Begin PostgreSQL Atomic Transaction]
  │
  ├── 1. Insert `engineering_departments` (7 rows)
  ├── 2. Insert `categories` (13 rows)
  ├── 3. Insert `users` (9 rows)
  ├── 4. Insert `projects` (0 rows)
  ├── 5. Insert `drawings` (9 rows)
  ├── 6. Insert `pages` (182 rows)
  ├── 7. Insert `comments` (560 rows)
  ├── 8. Insert `audit_logs` (449 rows)
  ├── 9. Insert `processing_runs` (1 row)
  ├── 10. Insert `export_history` (1 row)
  ├── 11. Insert `schema_migrations` (9 rows)
  └── 12. Create `comment_audit_log` (0 rows)
       │
       ▼
[Run In-Transaction Verification]
  ├── Are total inserted rows == 1,240?
  ├── Are all primary key sets identical?
  └── Did any constraint violation occur?
       │
       ├───> [IF FAILED] ──> ROLLBACK TRANSACTION (PostgreSQL clean, SQLite untouched)
       │
       ▼ [IF SUCCESS]
[COMMIT TRANSACTION]
       │
       ▼
[Execute Automated Post-Migration Reconciliation (Phase 4)]
```

### Safety & Idempotency Rules
- **Non-Destructive Reruns:** If rerun, the migration script checks whether target tables already contain data. It will **refuse to run** against a non-empty target unless an explicit `--clean-target` flag is supplied.
- **Zero SQLite Modification:** Under no circumstances will the script execute `UPDATE`, `DELETE`, `DROP`, or `INSERT` against SQLite.

---

## 5. Automated Multi-Entity Reconciliation Plan

Reconciliation will verify semantic and relational equivalence beyond simple row counts:

1. **Table Row Counts:** Verify that all 12 tables have identical counts totaling 1,240 rows.
2. **Primary Key Set Equality:** Extract the complete set of primary keys for every table from both databases and verify `set(sqlite_keys) ^ set(pg_keys) == set()`.
3. **Foreign Key Integrity:** Execute PostgreSQL join assertions across `comments -> drawings`, `comments -> pages`, `comments -> categories`, `comments -> engineering_departments`, and `audit_logs -> comments`.
4. **Text Integrity Spot-Check:** Compute and compare SHA-256 digests of concatenated `raw_text` and `cleaned_text` fields across all 560 comments between SQLite and PostgreSQL.
5. **Physical Asset Verification:**
   - Verify that all 9 PDF drawings referenced in `drawings.file_path` exist and their file checksums match `drawings.file_hash_sha256`.
   - Verify that the historical export file referenced in `export_history.file_path` exists on disk.

---

## 6. Disaster Recovery & Rollback Procedures

### Scenario A: Migration Script Failure / Crash
- **Symptom:** Python exception, network interruption, or database error during migration execution.
- **Recovery:** PostgreSQL transaction automatically aborts (rolls back). The target database remains empty. SQLite was in read-only mode and is unaffected.

### Scenario B: Data Discrepancy Detected During Reconciliation
- **Symptom:** Mismatched row count, missing foreign key, or corrupted text detected by reconciliation.
- **Recovery:**
  1. Truncate target PostgreSQL database tables in reverse dependency order.
  2. Inspect migration error logs.
  3. Source SQLite database remains untouched and operational.

### Scenario C: Post-Cutover Rollback
- **Symptom:** Unexpected application issue encountered in production after cutover.
- **Instant Rollback:**
  1. Change `config/config.yaml` to revert `database.db_path: data/ucc_database.db`.
  2. Revert `DatabaseEngine` active driver to SQLite.
  3. Total rollback time: **under 30 seconds**.
  4. The original SQLite database is immediately active with 100% of historical data intact.

---

## 7. Testing & Verification Roadmap (Pre-Cutover Gates)

```
[Gate 1: Isolated PostgreSQL Test DB Setup]
  └── Create dedicated test database: `ucc_test_db`.
  └── Validate schema generation via SQLAlchemy 2.x DDL.

[Gate 2: Mock Migration & Full Reconciliation Run]
  └── Run `migrate_sqlite_to_postgres.py` into `ucc_test_db`.
  └── Execute automated reconciliation suite (must pass with 0 discrepancies).

[Gate 3: Application Regression Testing Against PostgreSQL]
  └── Run full pytest regression suite (`pytest tests/unit/`) using PostgreSQL test engine.
  └── Verify 254+ tests pass, including:
      - Department authorization matrix
      - Multi-drawing workflows
      - Classification & OCR confidence handling
      - Export operations

[Gate 4: Multi-User Concurrency & Transaction Stress Test]
  └── Simulate 10 concurrent reviewer threads updating comment statuses and text.
  └── Verify row-level MVCC locking, absence of deadlocks, and audit log integrity.

[Gate 5: Central Shared Storage Verification]
  └── Verify that PDF drawing paths and Excel export files are accessible via network shares.

[Gate 6: Human Approval & Production Cutover]
  └── Present Phase 4 Reconciliation & Test Report to project lead.
  └── Await explicit written approval before updating production configuration.
```

---

## 8. Staged Path Toward Shared-Office Architecture (<100 Users)

To achieve the desired multi-PC office architecture without over-engineering:

### Stage 1: Central Database Cutover (Current Plan)
- Dedicated PostgreSQL 18 server installed on office server machine.
- PySide6 desktop clients on office PCs connect to central PostgreSQL via SQLAlchemy connection pooling (`pool_pre_ping=True`, `pool_size=10`).
- Local machines continue executing OCR/PyMuPDF processing locally.

### Stage 2: Central Shared Storage Migration
- Relocate drawing storage from local machine paths to an office UNC share (`\\server\ucc_storage\drawings\`) or central file directory.
- Update `FileService.copy_to_managed_storage()` to save files to the central share.

### Stage 3: Central API & Real-Time Sync (Future Iteration)
- Introduce a lightweight FastAPI service on the office server.
- Desktop PySide6 clients communicate with the API via REST.
- Server-side WebSocket broadcast notifies open desktop review screens when a drawing comment is updated by another engineer.

---

## 9. Deliverables & Safety Confirmations

- **Deliverable Path:** [`docs/migration/postgresql_migration_and_recovery_plan.md`](file:///c:/UCC_project/drawing-review-intelligence/docs/migration/postgresql_migration_and_recovery_plan.md)
- **Source Database Modified?** NO. `data/ucc_database.db` remains untouched.
- **Backup Modified?** NO. `ucc_database_backup_20261012.db` remains untouched.
- **PostgreSQL Database Created or Altered?** NO.
- **Application Configuration Modified?** NO.
- **Git Status:** Working tree clean on branch `main` (untracked files in `docs/migration/`, `backups/`, and `scripts/`).

**Phase 3 is complete. The implementation-ready plan is documented and waiting for your review and approval before any execution begins.**
