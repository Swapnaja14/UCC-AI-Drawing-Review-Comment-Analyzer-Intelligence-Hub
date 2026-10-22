# PostgreSQL Migration Verification & Reconciliation Report

**Generated:** 2026-10-22 16:35:35 UTC
**Source Engine:** `sqlite` (sqlite:///D:/Collage/SEMESTER V/industry/UCC-AI-Drawing-Review-Comment-Analyzer-Intelligence-Hub/data/ucc_database_working_copy.db)
**Target Engine:** `postgresql` (postgresql+psycopg://postgres:Varad%40210@localhost:5432/ucc_database)

## 1. Table Row Count Reconciliation

| Table | Source Rows | Target Rows | Difference | Status |
| :--- | :--- | :--- | :--- | :--- |
| `engineering_departments` | 7 | 7 | 0 | ✅ MATCH |
| `categories` | 13 | 13 | 0 | ✅ MATCH |
| `users` | 3 | 3 | 0 | ✅ MATCH |
| `projects` | 0 | 0 | 0 | ✅ MATCH |
| `drawings` | 4 | 4 | 0 | ✅ MATCH |
| `pages` | 4 | 4 | 0 | ✅ MATCH |
| `comments` | 8 | 8 | 0 | ✅ MATCH |
| `audit_logs` | 6 | 6 | 0 | ✅ MATCH |
| `processing_runs` | 4 | 4 | 0 | ✅ MATCH |
| `export_history` | 0 | 0 | 0 | ✅ MATCH |

## 2. Comment Aggregate & Metric Verification

| Metric | Source Value | Target Value | Match |
| :--- | :--- | :--- | :--- |
| **SUM(confidence)** | `8.0` | `8.0` | ✅ MATCH |
| **Earliest comment (local)** | `2026-10-21 18:41:51.383511` | `2026-10-21 18:41:51.383511` | ✅ MATCH |
| **Latest comment (local)** | `2026-10-21 18:42:11.654548` | `2026-10-21 18:42:11.654548` | ✅ MATCH |
| **Status Distribution** | `{'Approved': 6, 'Pending': 2}` | `{'Approved': 6, 'Pending': 2}` | ✅ MATCH |
| **Category Distribution** | `{'Calculation': 2, 'Technical': 6}` | `{'Calculation': 2, 'Technical': 6}` | ✅ MATCH |

## 3. Analytics Service Query Parity (Tolerance < 0.001%)

| Analytics Service API | Result | Parity |
| :--- | :--- | :--- |
| `get_global_kpis()` | Source: {'total': 8, 'approved': 6, 'rejected': 0, 'pending': 2, 'flagged': 0, 'avg_confidence': 1.0} <br> Target: {'total': 8, 'approved': 6, 'rejected': 0, 'pending': 2, 'flagged': 0, 'avg_confidence': 1.0} | ✅ 100% PARITY |
| `get_category_distribution()` | Distribution matches across all taxonomy and normalized groups | ✅ 100% PARITY |
| `get_pareto_analysis()` | Cumulative percentages and sort order match exactly | ✅ 100% PARITY |
| `get_status_trend()` | Bucket boundaries, zero-fill, and UTC->Local bucket labels match | ✅ 100% PARITY |

## 4. Integrity and Safety Guarantees
- `data/ucc_database.db` was accessed exclusively via read-only connections and was NOT modified.
- Foreign key cascades and dependencies followed strict migration order.
- Timestamp handling preserves UTC point-in-time accuracy while supporting local bucketing.

## 5. Live PostgreSQL Execution Instructions
To execute data migration and reconciliation against live PostgreSQL once credentials are provided:
```bash
# 1. Set environment variable (or pass --target)
export UCC_DATABASE_URL="postgresql+psycopg://<user>:<password>@localhost:5432/<dbname>"

# 2. Run data migration in execute mode
python scripts/migrate_sqlite_to_postgres.py --execute

# 3. Run reconciliation and regenerate this report
python scripts/reconcile_databases.py --target "$UCC_DATABASE_URL"
```
