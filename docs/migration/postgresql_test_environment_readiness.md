# PostgreSQL Test Environment Readiness & Pre-Implementation Plan

**Document Path:** `docs/migration/postgresql_test_environment_readiness.md`  
**Phase:** Phase 4 — PostgreSQL Test Environment Readiness (Assessment & Pre-Implementation Planning Only)  
**Date:** 2026-10-12  
**Status:** Complete — Ready for Review (No Database Created or Modified)  

---

## 1. Executive Summary & Strict Safety Invariance

This report details the concrete readiness assessment of the local Windows PostgreSQL 18 environment, defines an isolated testing strategy, hardens the rollback methodology, and formalizes the verified foreign-key dependency tree across all 12 tables.

### Immutable Safety Confirmations
- **Source SQLite Database:** `data/ucc_database.db` (SHA-256: `91221BBDB2382A9BBF93110835E1DF296881B1EB565EDEF1437C0A72C8F565C4`) remains untouched, unmoved, and preserved at its exact path indefinitely.
- **Offline Backup Snapshot:** `backups/sqlite_pre_migration/ucc_database_backup_20261012.db` (SHA-256: `E66517B42D216527584DCC14A55A28F9B51F463EEED298C949FE2C14EA119DA4`) remains safely preserved in isolated storage.
- **Target PostgreSQL State:** **Zero PostgreSQL databases were created, dropped, initialized, populated, or modified during this assessment.**
- **Application Code & Config:** Unaltered. Active database remains SQLite.

---

## 2. Task 1: PostgreSQL Environment Readiness Inspection

An inspection of the local Windows environment was executed using read-only diagnostic commands:

### 2.1 Service & Engine Details
- **Windows Service Name:** `postgresql-x64-18`
- **Service Display Name:** `postgresql-x64-18 - PostgreSQL Server 18`
- **Current Status:** `Running` (Startup type: `Automatic`)
- **Listening Endpoint:** `localhost:5432`
- **Engine Connection Check (`pg_isready.exe`):**  
  Output: `:5432 - accepting connections` (Exit code: 0). The engine is online and accepting connections.

### 2.2 Client Tools & Version Inspection
- **Installation Root:** `C:\Program Files\PostgreSQL\18`
- **Binary Directory:** `C:\Program Files\PostgreSQL\18\bin`
- **Available Binaries Verified:**
  - `psql.exe` (Version: `psql (PostgreSQL) 18.3`)
  - `pg_dump.exe`
  - `pg_restore.exe`
  - `pg_isready.exe`
  - `createdb.exe` / `dropdb.exe`
- *(Note: PostgreSQL bin directory is not currently in the global system PATH; any future automated scripts should reference binaries via the absolute installation path or configure the session environment appropriately).*

### 2.3 Python Runtime & Driver Inspection
- **Active Python Executable:** `C:\Program Files\Python313\python.exe`
- **Python Version:** `3.13.3 (tags/v3.13.3:6280bb5, Apr 8 2025, 14:47:33) [MSC v.1943 64 bit (AMD64)]`
- **Installed PostgreSQL Driver:** `psycopg2`
  - Version: `2.9.11 (dt dec pq3 ext lo64)`
  - Status: Built and linked against `libpq3` with 64-bit architecture. Verified functional for SQLAlchemy dialect `postgresql+psycopg2://`.

### 2.4 Credentials & Secrets Handling
- No passwords, usernames, or secrets were queried, logged, or printed.
- Future connection scripts will consume credentials strictly via environment variables (e.g. `UCC_PG_TEST_PASSWORD`, `UCC_PG_TEST_USER`) or prompt interactively rather than hardcoding credentials into source files or configuration repositories.

---

## 3. Task 2: Isolated Test Target Definition & Governance

To ensure zero risk to existing systems, a dedicated, isolated test database target is defined:

### 3.1 Proposed Test Target Parameters
- **Proposed Test Database Name:** `ucc_test_db`
- **Dedicated Test Role / User:** `ucc_test_user`
- **Connection Endpoint:** `localhost:5432/ucc_test_db`
- **Dialect URL:** `postgresql+psycopg2://ucc_test_user:<password>@localhost:5432/ucc_test_db`

### 3.2 Pre-Creation Validation & Conflict Prevention Policy
Before any creation command is run in future implementation phases:
1. **Pre-Flight Conflict Query:** Run `SELECT datname FROM pg_database WHERE datname = 'ucc_test_db';` via administrative connection. If the database exists, the tool **must abort immediately** rather than overwriting or dropping.
2. **Access Scoping:** The test user will be granted permissions **only** on `ucc_test_db`. No privileges will be granted on default administrative databases (`postgres`, `template1`).
3. **Automated Teardown / Cleanup Policy:**
   - The test target will be created exclusively for Phase 5 rehearsal/testing.
   - Once reconciliation tests and regression tests pass, the test database can be dropped or retained as a staging benchmark according to explicit user instruction.

---

## 4. Task 3: Safe Migration Tool Component Boundaries

The future migration implementation will be decoupled into independent, single-responsibility modules:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   MIGRATION TOOL ARCHITECTURE                           │
└────────────────────────────────────────────────────────────────────────┘

 [1. Source Extractor: `src_extractor.py`]
      └── Connects STRICTLY via SQLite read-only URI:
          `file:data/ucc_database.db?mode=ro`
      └── Enforces assertion: If connection is not read-only, ABORT immediately.
      └── Extracts records in dependency batches.
      
 [2. Schema Provisioner: `pg_schema_builder.py`]
      └── Connects ONLY to target specified by command-line flag `--target-db`.
      └── Asserts target DB name contains `_test_` or requires explicit `--allow-production` flag.
      └── Generates SQLAlchemy 2.x DDL schema cleanly.
      
 [3. Transactional Importer: `transactional_loader.py`]
      └── Wraps all 1,240 entity inserts in a SINGLE atomic PostgreSQL transaction.
      └── If any constraint, type, or foreign-key error occurs:
          Executes `ROLLBACK;` -> Leaves target empty; SQLite unaffected.
          
 [4. Multi-Entity Reconciler: `reconciliation_suite.py`]
      └── Performs row count, primary key symmetric difference, and text hash checks.
      └── Produces signed JSON reconciliation manifest.
      
 [5. Physical File Asserter: `file_integrity_checker.py`]
      └── Traverses all 9 drawing PDF file paths.
      └── Verifies file existence on disk and asserts SHA-256 equals `drawings.file_hash_sha256`.
      └── Verifies export Excel file existence on disk.
```

---

## 5. Task 4: Hardened Rollback & Cutover Design (Beyond Timestamps)

Relying solely on timestamps (`updated_at > cutover_time`) is vulnerable to clock skew, NTP sync issues, and unrecorded deletions. A hardened, tested cutover and rollback protocol is defined below:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      CUTOVER & ROLLBACK TIMELINE                        │
└─────────────────────────────────────────────────────────────────────────┘

 1. MAINTENANCE WINDOW (PREVENTING SPLIT-BRAIN)
    ├── Stop PySide6 desktop app instances on all office PCs.
    ├── Apply OS-level Read-Only attribute on `data/ucc_database.db`:
    │   `Set-ItemProperty data/ucc_database.db -Name IsReadOnly -Value $true`
    └── SQLite cannot accept writes. Split-brain is physically impossible.

 2. ATOMIC PRE-CUTOVER SNAPSHOTS
    ├── Final extraction of SQLite records -> Production PostgreSQL.
    ├── Reconcile 1,240 records (must match 100%).
    └── Create an immediate baseline PostgreSQL dump:
        `pg_dump -Fc -f backups/post_cutover_baseline.dump ucc_production_db`

 3. OPERATION MONITORING (POST-CUTOVER)
    ├── Enable PostgreSQL Audit Triggers or Change Data Capture (CDC):
    │   Every `INSERT`, `UPDATE`, `DELETE` on `comments`, `drawings`, `audit_logs`
    │   records the table name, row PK, old row JSON, new row JSON, and sequential sequence ID.

 4. CONTINGENCY ROLLBACK WORKFLOW (IF POST-CUTOVER WRITES OCCUR)
    ├── If rollback is required after 1-2 days of production use:
    │   ├── Step A: Put application into maintenance mode.
    │   ├── Step B: Extract all changes from the CDC capture log into `rollback_delta.json`.
    │   │           - Inserts: Add new comments to SQLite.
    │   │           - Updates: Update status/text in SQLite.
    │   │           - Deletes: Delete rows in SQLite.
    │   ├── Step C: Remove Read-Only attribute from `data/ucc_database.db`.
    │   ├── Step D: Replay `rollback_delta.json` into SQLite in a single transaction.
    │   ├── Step E: Revert `config/config.yaml` to point to SQLite.
    │   └── Step F: Re-verify integrity of SQLite database.
    └── Result: Rollback completed WITHOUT discarding post-cutover engineer reviews!
```

---

## 6. Task 5: Verified Dependency Tree & Table Topological Order

Using active SQLAlchemy ORM definitions in `src/infrastructure/storage/models.py` and SQLite schema constraints, the foreign-key relationships across all 12 tables were traced:

```
[Level 0: Independent Root Tables (No Foreign Keys)]
  ├── engineering_departments (7 rows)
  ├── categories              (13 rows)
  ├── projects                (0 rows)
  ├── schema_migrations       (9 rows - Applied version log)
  └── comment_audit_log       (0 rows - Legacy mirror)

[Level 1: First-Tier Dependents]
  ├── users (9 rows)
  │     └── FK: department_id -> engineering_departments.id (nullable=True, ON DELETE SET NULL)
  │
  └── drawings (9 rows)
        ├── FK: department_id -> engineering_departments.id (nullable=True, ON DELETE SET NULL)
        └── FK: project_id    -> projects.id                (nullable=True, ON DELETE SET NULL)

[Level 2: Second-Tier Dependents]
  ├── pages (182 rows)
  │     └── FK: drawing_id -> drawings.id (nullable=False, ON DELETE CASCADE)
  │
  ├── export_history (1 row)
  │     ├── FK: drawing_id -> drawings.id (nullable=True, ON DELETE SET NULL)
  │     └── FK: project_id -> projects.id (nullable=True, ON DELETE SET NULL)
  │
  └── processing_runs (1 row)
        ├── FK: drawing_id -> drawings.id (nullable=True, ON DELETE SET NULL)
        └── FK: project_id -> projects.id (nullable=True, ON DELETE SET NULL)

[Level 3: Core Comments Entity]
  └── comments (560 rows)
        ├── FK: drawing_id    -> drawings.id                (nullable=False, ON DELETE CASCADE)
        ├── FK: page_id       -> pages.id                   (nullable=True,  ON DELETE SET NULL)
        ├── FK: category_id   -> categories.id              (nullable=True,  ON DELETE SET NULL)
        ├── FK: department_id -> engineering_departments.id (nullable=True,  ON DELETE SET NULL)
        └── FK: user_id       -> users.id                   (nullable=True,  ON DELETE SET NULL)

[Level 4: Dependent Audit Entity]
  └── audit_logs (449 rows)
        ├── FK: comment_id -> comments.id (nullable=False, ON DELETE CASCADE)
        └── FK: user_id    -> users.id    (nullable=True,  ON DELETE SET NULL)
```

### Verified Insertion Sequence (Guaranteed Zero FK Violation)
1. `engineering_departments` (7 rows)
2. `categories` (13 rows)
3. `projects` (0 rows)
4. `schema_migrations` (9 rows)
5. `comment_audit_log` (0 rows)
6. `users` (9 rows)
7. `drawings` (9 rows)
8. `pages` (182 rows)
9. `export_history` (1 row)
10. `processing_runs` (1 row)
11. `comments` (560 rows)
12. `audit_logs` (449 rows)
**Total Records Inserted:** Exactly **1,240 rows**.

---

## 7. Proposed Future Phase 5 Commands (For Approval — Not Executed)

When explicitly approved to begin Phase 5 (Mock Migration into Isolated Test Database), the following sequence will be executed:

```powershell
# 1. Pre-flight check: verify 'ucc_test_db' does not already exist
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -c "SELECT datname FROM pg_database WHERE datname='ucc_test_db';"

# 2. Create isolated test database
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -c "CREATE DATABASE ucc_test_db;"

# 3. Provision SQLAlchemy ORM DDL into 'ucc_test_db'
python scripts/provision_test_schema.py --target-db "ucc_test_db"

# 4. Execute read-only extraction and transactional import
python scripts/migrate_sqlite_to_postgres.py --source "data/ucc_database.db" --target-db "ucc_test_db"

# 5. Run full automated reconciliation suite
python scripts/reconcile_sqlite_postgres.py --source "data/ucc_database.db" --target-db "ucc_test_db"

# 6. Execute pytest suite against 'ucc_test_db'
$env:UCC_DATABASE_TEST_URL = "postgresql+psycopg2://postgres:password@localhost:5432/ucc_test_db"
pytest tests/unit/
```

---

## 8. Safety & Invariance Confirmations

- **Source Database Modified?** NO (`data/ucc_database.db` SHA-256 verified identical).
- **Existing Offline Backup Modified?** NO (`ucc_database_backup_20261012.db` SHA-256 verified identical).
- **PostgreSQL Database Created or Altered?** NO.
- **Application Configuration Modified?** NO.
- **Application Code Modified?** NO.
- **Git Status:** Working tree clean on branch `main`.

**Phase 4 is complete. The test environment readiness plan and dependency order are validated and awaiting your review before any future implementation.**
