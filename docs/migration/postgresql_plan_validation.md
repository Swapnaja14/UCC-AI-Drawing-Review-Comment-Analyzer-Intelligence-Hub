# PostgreSQL Migration Plan Safety Validation Report

**Document Path:** `docs/migration/postgresql_plan_validation.md`  
**Phase:** Phase 3A — Migration Plan Safety Validation (Planning & Inspection Only)  
**Date:** 2026-10-12  
**Status:** Complete — Validation Findings & Architectural Hardening  

---

## 1. Executive Summary & Review Scope

This validation report critically reviews the Phase 3 design document ([`docs/migration/postgresql_migration_and_recovery_plan.md`](file:///c:/UCC_project/drawing-review-intelligence/docs/migration/postgresql_migration_and_recovery_plan.md)) against active application code, historical data patterns in `data/ucc_database.db`, and multi-user operational constraints.

### Absolute Safety Invariance
- **Source Database:** `data/ucc_database.db` (SHA-256: `91221BBDB2382A9BBF93110835E1DF296881B1EB565EDEF1437C0A72C8F565C4`) remains untouched and preserved at its exact path.
- **Verified Offline Backup:** `backups/sqlite_pre_migration/ucc_database_backup_20261012.db` (SHA-256: `E66517B42D216527584DCC14A55A28F9B51F463EEED298C949FE2C14EA119DA4`) remains untouched in isolated storage.
- **Target PostgreSQL Instance:** Local service `postgresql-x64-18` is running, but **no target database has been created, populated, or modified**.
- **Application Code & Config:** 100% unaltered. Application continues running on SQLite.

---

## 2. Task 1: Historical Timestamp Semantics & Code Verification

A strict inspection of active source code was conducted across all files creating and updating timestamps:
- `src/infrastructure/storage/models.py` (Lines 47, 87, 113, 140, 183, 296, 355, 390, 418, 424)
- `src/infrastructure/storage/repository.py` (Lines 253, 285, 1119, 1138, 1169, 1179, 1218, 1264, 1325, 1449, 1519, 1597, 1646)
- `src/services/verification_service.py` (Lines 32, 233, 235, 239)
- `src/services/workflow_engine.py` (Lines 629, 641, 1024, 1051)
- `src/services/auth_service.py` (Lines 86, 161, 210, 233)
- `src/services/export_service.py` (Line 1151)

### Concrete Findings & Verified Facts

1. **ORM Defaults Use `datetime.utcnow`:**
   In `src/infrastructure/storage/models.py`, all default column timestamps are defined as:
   `default=datetime.utcnow` (e.g., `UserModel.created_at`, `DrawingModel.uploaded_at`, `CommentModel.created_at`, `AuditLogModel.timestamp`).
   *(Note: Python's `datetime.utcnow()` generates naive datetime objects representing UTC time without attached timezone metadata).*
2. **Repository Write Methods Use Explicit `datetime.now(timezone.utc)`:**
   In `src/infrastructure/storage/repository.py`, runtime updates explicitly call `datetime.now(timezone.utc)`:
   - `DrawingRepository.save_drawing_from_dto`: `uploaded_at = datetime.now(timezone.utc)`
   - `CommentRepository.update_comment_*`: `row.updated_at = datetime.now(timezone.utc)`
   - `AuditLogRepository.create_audit_entry`: `timestamp = timestamp or datetime.now(timezone.utc)`
   - `ProcessingRunRepository.create_run_entry`: `started_at = started_at or datetime.now(timezone.utc)`
3. **The `VerificationService` Discrepancy:**
   In `src/services/verification_service.py` (Line 32), an in-memory method calls `now_dt = datetime.now()` (local time). However, when persisted to the database via `AuditLogRepository.create_audit_entry()` (Line 1449), the repository overrides or defaults naive timestamps to `datetime.now(timezone.utc)`.
4. **Historical SQLite Timestamp Examination:**
   Inspection of actual records in `data/ucc_database.db`:
   - `comments.created_at`: range `2026-09-13 09:21:33.175122` to `2026-10-01 03:51:09.036821`
   - `drawings.uploaded_at`: range `2026-09-13 09:21:33.165594` to `2026-10-01 03:32:16.251639`
   - `audit_logs.timestamp`: range `2026-09-15 14:34:04.343132` to `2026-10-01 03:51:08.431487`
   - `schema_migrations.applied_at`: explicit ISO UTC format (`2026-09-27T11:08:31.977997+00:00`)
   - Correlation check: Audit log `AUD-4B08C2C8` timestamp is `2026-10-01 03:51:08.431487` while comment `CMT-01724C-P2-02` `updated_at` is `2026-10-01 03:51:09.036821` (0.6 seconds apart). Both reflect UTC execution.

### Safe Timestamp Preservation Strategy (No Automatic Conversions)
- **Documented Uncertainty:** While historical code overwhelmingly intended UTC (`datetime.utcnow` and `datetime.now(timezone.utc)`), SQLite stored them as naive strings (`VARCHAR` / naive text) without timezone offsets. Converting them with an assumed local offset would distort chronological ordering.
- **Rule:** Store historical timestamps in PostgreSQL as **`TIMESTAMP WITHOUT TIME ZONE`** (or interpret them strictly as UTC without shifting the stored wall-clock hours/minutes/seconds). Under no circumstances will a timezone offset (e.g. +05:30) be applied to alter the historical date-time digits.

---

## 3. Task 2: Robust Rollback & Disaster Recovery Strategy

The Phase 3 proposal suggested an instantaneous configuration-toggle rollback. This validation report identifies a critical gap in that proposal: **If PostgreSQL accepts new user edits after cutover, simply reverting `config.yaml` to SQLite would abandon those post-cutover writes.**

A comprehensive, realistic rollback protocol is established below:

```
[Phase A: Pre-Cutover Verification & Rehearsal Stage]
  ├── Rehearse migration into separate `ucc_migration_rehearsal_db` on PostgreSQL.
  ├── Run 100% automated row, PK, and text hash reconciliation.
  └── Rehearsal MUST succeed before scheduling production cutover.

[Phase B: Maintenance / Cutover Window]
  ├── Schedule an explicit maintenance window (app closed on all user PCs).
  ├── Enforce SQLite Read-Only Lock: Set OS-level read-only permissions on `data/ucc_database.db`.
  │   └── Prevents simultaneous split-brain writes to SQLite and PostgreSQL.
  ├── Final delta extraction from SQLite -> Production PostgreSQL (`ucc_production_db`).
  ├── Post-import reconciliation check (1,240 rows + checksum assertions).
  └── Smoke test PySide6 client against `ucc_production_db`.

[Phase C: Cutover Acceptance Decision]
  ├── Human reviewer inspects reconciliation results and signs off.
  └── If accepted -> Remove maintenance mode and launch application.

[Phase D: Post-Cutover Rollback Contingency (Handling Post-Cutover Writes)]
  ├── If severe issue occurs within 24-48 hours of cutover:
  │   ├── 1. Put application into read-only maintenance mode.
  │   ├── 2. Query PostgreSQL for records created/modified after cutover timestamp:
  │   │      `SELECT * FROM comments WHERE updated_at > cutover_timestamp;`
  │   │      `SELECT * FROM audit_logs WHERE timestamp > cutover_timestamp;`
  │   ├── 3. Export all post-cutover writes to a structured delta bundle (`delta_export.json`).
  │   ├── 4. Backport delta records into `data/ucc_database.db` using isolated replay script.
  │   ├── 5. Re-enable SQLite mode in `config/config.yaml`.
  │   └── 6. Verify zero loss of post-cutover annotations or audit trails.
```

### Safety Rules
1. **No Data Discard:** Never discard post-cutover user contributions during a rollback.
2. **Never Delete SQLite Database:** `data/ucc_database.db` remains intact at all times.
3. **No Split-Brain:** Only one database engine may accept writes at any time.

---

## 4. Task 3: Multi-User Architecture Evolution

To prevent security vulnerabilities and architectural confusion, the platform evolution is strictly demarcated into three tiers:

```
[Tier 1: Migration Verification & Local Compatibility Testing]
  └── Purpose: Validate SQLAlchemy models, queries, and driver on local PostgreSQL service.
  └── Scope: Antigravity IDE & local automated test suite (`pytest`) on developer PC.
  └── Security: Local test credentials only. No network exposure.

[Tier 2: Direct-Connection Trusted LAN Architecture (Interim / High Risk)]
  └── Evaluation: Desktop PySide6 clients connect directly via `postgresql+psycopg2://user:pass@server:5432/ucc_db`.
  └── Security Flaw: 
      - Hardcoding or distributing PostgreSQL connection strings to 50+ PCs exposes full database credentials.
      - Any user on the LAN could connect directly with `psql`/DBeaver and bypass application authorization.
      - Network dropouts cause unhandled socket disconnects in client UI.
  └── Verdict: Acceptable ONLY as a temporary, controlled staging test; NOT acceptable for final production.

[Tier 3: Intended Shared-Office Architecture (Target Production)]
  └── Structure:
      [Office PCs: PySide6 GUI Client]
             │  (Local PyMuPDF rasterization & local Tesseract OCR compute)
             │  (HTTP / WebSocket JSON payload — No DB credentials on client)
             ▼
      [Central Server: Lightweight FastAPI Application Service]
             │  (Server-side PBKDF2 authentication & department authorization)
             │  (Connection pooling, optimistic concurrency, and transaction control)
             ▼
      [Authoritative Shared PostgreSQL 18 Database]
             ▲
      [Central Shared File Storage] (UNC Network Share: `\\server\ucc_storage\`)
```

### Shared Storage & Concurrency Details
1. **Central File Storage:** Move `drawings.file_path` from local paths (e.g. `C:\Users\satyajeet virkar22\...`) to a central network share (e.g., `\\server\ucc_data\drawings\`). All clients reference identical network paths.
2. **Concurrency Control:** Implement optimistic locking via `updated_at` check on `comments`. If Reviewer B attempts to approve a comment already modified by Reviewer A, the server rejects with a concurrency conflict warning (`HTTP 409 Conflict`) rather than overwriting.
3. **Idempotency & Resilience:** All mutation APIs require unique transaction/operation IDs to safely handle network retries without creating duplicate audit log entries.

---

## 5. Task 4: Schema, Foreign-Key Dependencies & Reconciliation Requirements

### 1. Complete Topological Dependency Order (All 12 Tables)
Foreign-key insertion order must follow this strict sequence:
1. `engineering_departments` (0 dependencies)
2. `categories` (0 dependencies)
3. `users` (Depends on `engineering_departments` via `department_id`)
4. `projects` (0 dependencies)
5. `drawings` (Depends on `projects` and `engineering_departments`)
6. `pages` (Depends on `drawings` via `drawing_id` ON DELETE CASCADE)
7. `comments` (Depends on `drawings`, `pages`, `categories`, `engineering_departments`, `users`)
8. `audit_logs` (Depends on `comments` and `users`)
9. `processing_runs` (Depends on `projects` and `drawings`)
10. `export_history` (Depends on `projects` and `drawings`)
11. `schema_migrations` (0 dependencies — tracks applied versions)
12. `comment_audit_log` (0 dependencies — empty legacy mirror table)

### 2. Entity Preservation Guarantees
- **Nullable Legacy Departments:** 110 legacy comments have `comments.department_id IS NULL` and 3 drawings have `drawings.department_id IS NULL`. PostgreSQL schema must retain `nullable=True` and foreign keys must have `ON DELETE SET NULL`.
- **Text Fidelity:** `raw_text` (unaltered OCR text) and `cleaned_text` (human/rule-cleaned text) must be inserted with UTF-8 encoding without truncation.
- **Bounding Boxes:** `bbox_x0`, `bbox_y0`, `bbox_x1`, `bbox_y1` must be preserved as `DOUBLE PRECISION` float values without rounding.

### 3. Comprehensive Reconciliation Suite (Beyond Row Counts)
Row count equality ($1,240 == 1,240$) is a necessary condition, but **not sufficient**. The automated reconciliation suite must assert:
1. **Row Counts:** All 12 tables match exactly.
2. **Primary Key Symmetric Difference:** `set(sqlite_pks) ^ set(pg_pks) == set()` for all tables.
3. **Text Hash Assertion:** Compute SHA-256 of concatenated `id + raw_text + cleaned_text` across all 560 comments in SQLite vs PostgreSQL. Checksums must match bitwise.
4. **Relational Integrity:** Zero orphan rows (`PRAGMA foreign_key_check` and PostgreSQL join assertions).
5. **Physical Asset Hash Verification:** All 9 PDF files in `drawings.file_path` must exist on disk and match `drawings.file_hash_sha256`.

---

## 6. Pre-Implementation Acceptance Criteria

Before any code changes, target database creation, or migration scripts are executed in Phase 4:

- [ ] **Criterion 1:** SQLite source database `data/ucc_database.db` and backup `backups/sqlite_pre_migration/ucc_database_backup_20261012.db` confirmed untouched.
- [ ] **Criterion 2:** Timestamp preservation policy accepted: Timestamps stored as `TIMESTAMP WITHOUT TIME ZONE` in PostgreSQL to preserve exact historical digits without timezone shifts.
- [ ] **Criterion 3:** Rehearsal test database specified: Target migration tested against isolated database `ucc_test_db` before any production cutover.
- [ ] **Criterion 4:** Post-cutover delta export procedure confirmed for rollback safety.
- [ ] **Criterion 5:** Central file storage path strategy approved.
- [ ] **Criterion 6:** Formal approval from user/architect received.

---

## 7. Safety & Invariance Confirmations

- **Source Database Modified?** NO (`data/ucc_database.db` SHA-256 verified identical).
- **Existing Backup Modified?** NO (`ucc_database_backup_20261012.db` SHA-256 verified identical).
- **PostgreSQL Database Created or Altered?** NO.
- **Application Configuration Modified?** NO.
- **Application Code Modified?** NO.
- **Git Status:** Working tree clean on branch `main`.

**Phase 3A is complete. This validation report resolves the design risks and awaits your explicit approval before Phase 4 implementation.**
