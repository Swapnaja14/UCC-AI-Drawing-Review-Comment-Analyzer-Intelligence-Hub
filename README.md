# 📐 UCC AI Drawing Review Comment Analyzer & Intelligence Hub

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![GUI](https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt6-41CD52?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![AI](https://img.shields.io/badge/NLP-DistilBERT%20Transformer-FF6F00?logo=huggingface&logoColor=white)](https://huggingface.co/)
[![Vision](https://img.shields.io/badge/Vision-OpenCV%20%2B%20PyMuPDF%20%2B%20Tesseract-5C3EE8?logo=opencv&logoColor=white)](https://opencv.org/)
[![Database](https://img.shields.io/badge/Database-PostgreSQL%20%2F%20SQLite-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Tests](https://img.shields.io/badge/Tests-400%2B%20Passed-brightgreen?logo=pytest&logoColor=white)](tests/)
[![Commits](https://img.shields.io/badge/Commits-134-blue?logo=git&logoColor=white)](.git)
[![Version](https://img.shields.io/badge/Version-1.0.0-informational)](VERSION)

> **An enterprise-grade, AI-powered desktop intelligence platform for engineering drawing review workflows.**
> Automatically detects colored reviewer markups and revision clouds, extracts technical annotations via hybrid vector/raster OCR, classifies comments into engineering disciplines using a fine-tuned DistilBERT transformer, facilitates human verification with immutable audit trails, and exports multi-tab department Error Tracker workbooks — all stored in **PostgreSQL** or **SQLite**.

---

## 📑 Table of Contents

- [🌟 Overview](#-overview)
- [⚡ Key Innovations & Performance](#-key-innovations--performance)
- [🚀 Key Features](#-key-features)
- [🏗 System & Processing Pipeline Architecture](#-system--processing-pipeline-architecture)
- [🏢 Supported Engineering Disciplines](#-supported-engineering-disciplines)
- [🖥 Application Screens & Capabilities](#-application-screens--capabilities)
- [🛠 Getting Started](#-getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Database Setup](#database-setup)
  - [Running the Application](#running-the-application)
  - [Running the Installer (.exe)](#running-the-installer-exe)
- [📂 Project Structure](#-project-structure)
- [🧪 Testing & Quality Assurance](#-testing--quality-assurance)
- [⚙️ Configuration Reference](#️-configuration-reference)
- [🗄 PostgreSQL Migration Guide](#-postgresql-migration-guide)
- [📊 Analytics & Reporting](#-analytics--reporting)
- [🤝 Contributing & Development](#-contributing--development)
- [📜 License](#-license)

---

## 🌟 Overview

Engineering drawing reviews for heavy industrial projects (P&IDs, Isometrics, Structural Layouts, GA Drawings, Single Line Diagrams) generate hundreds of colored redlines, comments, and revision clouds across large-format PDF sheets.  
Manually transcribing, categorizing, and routing these comments to individual engineering departments is time-consuming, prone to omissions, and leads to expensive rework cycles.

**UCC Analyzer** solves this by automating the full end-to-end review lifecycle:

1. **Detects** colored reviewer markups (Red, Blue, Green, Cyan, Magenta) and revision clouds with sub-pixel contour approximation.
2. **Extracts** comment text via a high-precision hybrid pipeline combining native PDF vector character intersection with Tesseract OCR fallback.
3. **Classifies** comments into domain taxonomies using a custom fine-tuned **DistilBERT** transformer model with 13 engineering discipline labels.
4. **Validates & Manages** comments through an interactive desktop UI with zoomable PDF canvases, bounding-box overlays, and human review workflows.
5. **Exports** structured, multi-sheet Excel Error Trackers organized by engineering department.
6. **Persists** everything in **PostgreSQL** (primary) or **SQLite WAL** (fallback) with full Alembic migration history.

---

## ⚡ Key Innovations & Performance

| Capability | Previous Standard | UCC Analyzer Platform |
| :--- | :--- | :--- |
| **Markup Detection** | High-overhead raster scanning at 300 DPI (~12 s/page) | **72-DPI SIMD Vector Pre-filtering + High-Res Contour Box** (~2.8 s/page — **4.2× faster**) |
| **Cloud Enclosure** | Misses hollow clouds or partial loops | **Convex Hull & Contour Closure Analysis** with text-envelope capture |
| **Text Extraction** | Slow OCR on the entire page | **Hybrid Spatial Extraction**: vector-native first; raster OCR on bounded ROI only |
| **Classification** | Keyword lookup / manual tagging | **Fine-Tuned DistilBERT Transformer** + regex rule-based fallback |
| **Human-in-the-Loop** | Uncontrolled Excel updates | **Immutable Audit Trails** tracking reviewer, timestamp, and text diffs |
| **Department Tracking** | Manual copy-paste into separate files | **Automated Multi-Tab Excel Workbook** with data-validation dropdowns |
| **Database Backend** | SQLite-only | **PostgreSQL-first** with automated Alembic migration & SQLite fallback |
| **Analytics** | Static totals | **Live Pareto, trend bucketing, confidence KPIs, reviewer attribution** |

---

## 🚀 Key Features

### 🔍 1. Precision Colored Annotation & Cloud Detection
- **Adaptive HSV Segmentation**: Multi-band color thresholds isolate Red, Blue, Green, Cyan, and Magenta annotations while suppressing black technical line-art.
- **Revision Cloud Enclosure Engine**: Detects hollow, scalloped, and solid revision clouds using contour approximation; captures all text bounded within the cloud geometry.
- **Title Block & Stamp Suppression**: Automatically excludes engineering title blocks, revision tables, and approval stamps in sheet margins.
- **DPI-Aware Acceleration**: 72-DPI SIMD multi-threaded acceleration for 4.2× faster page processing.
- **Black Handwriting Support**: Optional detection mode for hand-annotated scanned drawings.

### 📝 2. Hybrid OCR & Text Extraction Engine
- **Vector Spatial Extraction**: Queries native PDF character blocks using sub-pixel bounding-box intersection via PyMuPDF.
- **Raster Fallback (Tesseract)**: Routes scanned drawings and rasterized markups through an image pre-processing pipeline (contrast normalization, adaptive binarization, CLAHE, de-skewing, micro-upscaling).
- **Dynamic PSM Fallback**: Auto-switches Tesseract page-segmentation modes (PSM 6 → PSM 11) when confidence falls below threshold.
- **Parallel Region OCR**: Up to 4 worker threads simultaneously process annotation bounding regions.
- **Engineering Text Cleaning**: Expands standard abbreviations (`TYP` → `Typical`, `SCH` → `Schedule`, `W/` → `With`), eliminates OCR noise, and normalizes technical notations.

### 🤖 3. Fine-Tuned DistilBERT Engineering Classifier
- **Transformer NLP Architecture**: Custom fine-tuned `distilbert_engineering_classifier` with batched PyTorch tensor inference.
- **13 Discipline Taxonomies**: Accurately categorizes into *Technical, Drafting, Dimension, Coordination, Standards, Materials, Calculation, Revision, Feasibility, BOM, Notes, Queries*, and more.
- **Hybrid Fallback**: Instantaneous regex rule-based classification ensures 100% uptime even in resource-constrained environments.
- **PyInstaller-Aware Model Resolution**: Automatically locates model weights in both development (`src/`) and frozen executable (one-file `_MEIPASS` + one-dir) environments.

### 📥 4. Single & Batch/ZIP Workflow Ingestion
- **Dual Upload Modes**: Individual multi-page engineering drawing sheets or entire ZIP archives / multi-file batches.
- **Department Auto-Binding**: Automatic discipline categorization; FK-safe department resolution prevents constraint violations even for admin (unscoped) users.
- **Real-Time Progress ETA**: Determinate progress tracking with step-by-step pipeline indicators and elapsed/estimated remaining time.

### 🖥 5. Context-Aware PDF & Markup Viewer
- **Auto-Collapsing Sidebar**: In Single File mode the sidebar collapses for a full-width canvas; in Batch/ZIP mode it auto-expands displaying `BATCH DRAWINGS (N)`.
- **Interactive Markup Overlays**: Bounding-box overlays on detected colored markups, revision clouds, and OCR regions.
- **Zoom & Navigation**: Fit-to-width, fit-to-page, zoom slider, page rotation, thumbnail filmstrip.

### 📊 6. Real-Time Dashboard & Advanced Analytics
- **Live KPI Tiles**: Total projects, drawings processed, comments detected, OCR confidence, review progress, and auto-approval rate.
- **Pareto 80/20 Analysis**: Category-level Pareto bars with cumulative percentage line against the full population.
- **Trend Bucketing**: Daily / weekly / monthly auto-selection based on filtered date range; zero-filled, UTC → local timezone conversion.
- **Reviewer Attribution Metrics**: Per-reviewer comment counts, verification rates, and batch-scoped statistics.
- **Filter Suite**: Department, category, drawing, date range, current-batch, include-rejected — all debounced (150 ms) and summarized in a live filter badge.
- **Status Distribution Donut**: Visual breakdown of Pending / Approved / Rejected / Flagged comments.
- **Theme Integration**: Charts automatically rebuild on dark/light theme switch via `ThemeManager.theme_changed`.

### 📑 7. Multi-Tab Excel Error Tracker Generation
- **Department Tab Segregation**: Master workbook + dedicated tabs for each of the 7 engineering disciplines.
- **Conditional Formatting**: Freeze panes, auto-fit columns, colored severity headers, Excel data-validation dropdowns.
- **Scope Filters**: Export by project, department, drawing, date range, or the current batch only.

### 🔒 8. Human Review & Immutable Audit Trail
- **Verification Workflow**: Four standard statuses — `Pending`, `Approved`, `Rejected`, `Flagged`.
- **Audit Log Repository**: Records reviewer identity, action timestamp, old/new text diffs, and reviewer notes — stored in both PostgreSQL and SQLite.
- **Auto-Approval Policy**: Comments above the configurable high-confidence threshold (default 80%) are flagged for auto-approval; a separate policy engine enforces business rules.

### 🗄 9. Dual-Database Architecture (PostgreSQL + SQLite)
- **PostgreSQL-First**: Production deployments connect to a PostgreSQL server; connection URL is resolved from `UCC_DATABASE_URL` environment variable or `config/config.yaml`.
- **SQLite Fallback**: Zero-config development mode using WAL-mode SQLite.
- **Alembic Migrations**: Schema versioned via Alembic; `alembic upgrade head` applies all migrations to either backend.
- **One-Click Migration**: `scripts/migrate_sqlite_to_postgres.py --execute` copies all historical data from SQLite to PostgreSQL with FK-ordered inserts and quarantine tracking.
- **Reconciliation Tool**: `scripts/reconcile_databases.py` generates a markdown report confirming row-level parity between backends.

---

## 🏗 System & Processing Pipeline Architecture

```mermaid
flowchart TD
    A["📄 Upload Engineering Drawing PDF / ZIP Batch"] --> B["⚙️ Workflow Engine Coordinator"]
    B --> C["🎨 SIMD Color Masking & Cloud Contour Detection"]
    C --> D["📐 Title Block & Corner Envelope Suppression"]
    D --> E["🔎 Hybrid OCR: PyMuPDF Vector + Tesseract Raster"]
    E --> F["🧹 Technical Spell Correction & Abbreviation Expansion"]
    F --> G["🤖 DistilBERT AI Classification & Confidence Scoring"]
    G --> H[("💾 PostgreSQL / SQLite — Alembic Migrations")]
    H --> I["🖥️ PySide6 Desktop UI — Live Sync"]
    I --> J["🔍 Context-Aware PDF Viewer with Batch Navigation"]
    I --> K["✏️ Human Review & Audit Trail"]
    I --> L["📊 Pareto, Trend & Reviewer Analytics"]
    I --> M["📑 Multi-Sheet Excel Error Tracker Export"]
```

---

## 🏢 Supported Engineering Disciplines

| Department | Key Responsibilities | Typical Drawing Types |
| :--- | :--- | :--- |
| **Electrical Engineering** | Single-line diagrams, cable schedules, tray routing | SLD, Wiring Schematics, Electrical Layouts |
| **GPD (General Plant Design)** | Plant layout, overall plot plans, equipment location | Plot Plans, General Arrangement (GA) |
| **Pipe Support Engineering** | Pipe hanger details, secondary steel supports | Pipe Support Details, Load Schedules |
| **Piping Engineering** | Process lines, P&IDs, piping isometrics, tie-ins | P&ID, Piping Isometrics, Spool Sheets |
| **Plakon** | Equipment placement, modular skids, platform design | Skid Layouts, Equipment GA |
| **Structural & Physical Design** | Structural steel, foundation details, concrete work | Structural Framing, Foundation Plans |
| **System Engineering** | Instrumentation, logic diagrams, loop sheets | Logic Diagrams, Loop Schematics |

---

## 🖥 Application Screens & Capabilities

| Screen | Key Features |
| :--- | :--- |
| **📊 Dashboard** | Live KPI tiles, recent drawings table, projects overview, engine status monitors, auto-refresh on navigation. |
| **📥 Upload Drawing** | Single & Batch/ZIP modes, department binding (FK-safe), interactive recent-files picker, real-time ETA timer, ZIP slip protection. |
| **📄 PDF Viewer** | Hardware-accelerated rendering, context-aware auto-collapsing sidebar, batch-scoped navigation, manual toolbar toggle. |
| **🔍 Comment Viewer** | Bounding-box overlays, zoom +/−, fit-width/fit-page, page rotation, inspector drawer for comment metadata. |
| **📑 OCR Results** | Full transcript table, confidence scores, search filters, inline text editing. |
| **🏷️ Classification** | ML prediction review, discipline badges with color coding, category reassignment. |
| **✅ Human Review** | Approve / Reject / Flag with mandatory notes; immutable audit log; reviewer attribution. |
| **📈 Analytics** | Pareto chart, trend timeline, category pie, status donut, confidence distribution, reviewer metrics — all filter-aware. |
| **📤 Export** | Multi-tab Excel Error Tracker; CSV / JSON alternatives; scope by project, department, batch, or date. |
| **⚙️ Settings** | Dark/Light theme, database path configuration, system diagnostics, OCR engine selection. |
| **🔐 Login** | Role-based access: Admin (cross-department) vs. Department User (scoped). |

---

## 🛠 Getting Started

### Prerequisites

| Dependency | Version | Notes |
| :--- | :--- | :--- |
| **Python** | 3.10 / 3.11 / 3.12 | Python 3.11 recommended |
| **PostgreSQL** | 14+ | Optional — SQLite used if not configured |
| **Tesseract OCR** | 5.x | Required only for scanned/raster PDFs |
| **Git** | Any | For cloning the repository |

**Install Tesseract:**
- **Windows**: [UB-Mannheim Installer](https://github.com/UB-Mannheim/tesseract/wiki) — ensure `tesseract` is in `PATH`
- **Ubuntu/Debian**: `sudo apt-get install tesseract-ocr`
- **macOS**: `brew install tesseract`

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/YourOrg/UCC-AI-Drawing-Review-Comment-Analyzer-Intelligence-Hub.git
cd UCC-AI-Drawing-Review-Comment-Analyzer-Intelligence-Hub

# 2. Create and activate a virtual environment
python -m venv venv

# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Linux / macOS
source venv/bin/activate

# 3. Install all dependencies
pip install -r requirements.txt
```

### Database Setup

#### Option A — PostgreSQL (Production / Recommended)

```bash
# Create the database (run as postgres superuser)
createdb ucc_database

# Set connection environment variables (Windows PowerShell — persistent)
[System.Environment]::SetEnvironmentVariable("UCC_DATABASE_URL", "postgresql+psycopg://postgres:YourPassword@localhost:5432/ucc_database", "User")
[System.Environment]::SetEnvironmentVariable("UCC_DATABASE_BACKEND", "postgresql", "User")

# Apply schema migrations
alembic upgrade head

# (Optional) Migrate existing SQLite data to PostgreSQL
python scripts/migrate_sqlite_to_postgres.py --execute

# (Optional) Verify data parity between backends
python scripts/reconcile_databases.py
```

#### Option B — SQLite (Zero-Config Development)

No additional setup required. The application creates `data/ucc_database.db` automatically on first launch.

### Running the Application

```bash
python main.py
```

### Running the Installer (.exe)

If you have a pre-built Windows executable (built via PyInstaller):

```
dist/
└── UCC_Drawing_Review_Intelligence/
    └── UCC_Drawing_Review_Intelligence.exe   ← Double-click to launch
```

> **Note**: The `.exe` bundle does **not** include PostgreSQL. You must have PostgreSQL running and set `UCC_DATABASE_URL` as a Windows User environment variable before launching the executable. SQLite works out of the box.

To build the executable yourself:
```powershell
pyinstaller --clean UCC_Drawing_Review_Intelligence.spec
```

---

## 📂 Project Structure

```
UCC-AI-Drawing-Review-Comment-Analyzer-Intelligence-Hub/
│
├── app/                                # PySide6 Desktop GUI Layer (41 files)
│   ├── components/                     # Reusable UI widgets
│   │   ├── charts.py                   # QtCharts: Pareto, timeline, pie, donut
│   │   ├── kpi_card.py                 # Animated KPI metric tiles
│   │   ├── pdf_canvas.py               # Hardware-accelerated PDF renderer
│   │   ├── pdf_toolbar.py              # Zoom, fit, rotate controls
│   │   ├── sidebar.py                  # Collapsible navigation panel
│   │   └── ...                         # chips, overlays, comment_table, etc.
│   ├── controllers/
│   │   └── app_controller.py           # Central AppController (QObject)
│   ├── screens/                        # Main application views
│   │   ├── analytics_screen.py         # Full analytics dashboard
│   │   ├── dashboard_screen.py         # Live activity overview
│   │   ├── upload_screen.py            # Single & Batch/ZIP ingestion
│   │   ├── login_screen.py             # Role-based authentication
│   │   ├── review_screen.py            # Human verification workflow
│   │   ├── export_screen.py            # Error Tracker export
│   │   └── ...                         # pdf_viewer, comment_viewer, settings, etc.
│   ├── theme.py                        # Dark / Light ThemeManager
│   └── main_window.py                  # Application shell & navigation
│
├── src/                                # Core Domain & Infrastructure (42 files)
│   ├── ai/
│   │   ├── dataset_generator.py        # Synthetic training data generation
│   │   ├── train_distilbert.py         # Fine-tuning training script
│   │   └── evaluate_classifier.py      # Evaluation & metrics report
│   ├── config/
│   │   └── app_config.py               # Typed config dataclasses + env/registry resolution
│   ├── core/
│   │   ├── dtos/                       # Data Transfer Objects (analytics, auth, comments, …)
│   │   └── exceptions/                 # Domain-specific exceptions
│   ├── infrastructure/
│   │   ├── logging/logger.py           # Centralized structured logger
│   │   ├── pdf/pymupdf_adapter.py      # PyMuPDF page rendering adapter
│   │   └── storage/
│   │       ├── models.py               # SQLAlchemy ORM models (10 tables)
│   │       └── repository.py           # DatabaseEngine + all repositories
│   └── services/                       # Business Logic Layer
│       ├── analytics_service.py        # KPI aggregations, Pareto, trend, reviewer metrics
│       ├── annotation_service_enhanced.py  # 72-DPI SIMD color segmentation & cloud detection
│       ├── classification_service.py   # DistilBERT transformer + regex fallback
│       ├── export_service.py           # Multi-sheet Excel Error Tracker builder
│       ├── hybrid_ocr_service.py       # PyMuPDF vector + Tesseract raster pipeline
│       ├── text_cleaning_service.py    # Abbreviation expansion & spell correction
│       ├── verification_service.py     # Human review & reviewer attribution
│       └── workflow_engine.py          # Multi-step pipeline coordinator
│
├── models/
│   └── distilbert_engineering_classifier/
│       ├── config.json                 # Model architecture config
│       ├── tokenizer.json              # Vocabulary & tokenizer rules
│       ├── tokenizer_config.json       # Tokenizer settings
│       ├── training_metadata.json      # Training hyperparameters & metrics
│       └── model.safetensors           # Fine-tuned weights (~268 MB, tracked via LFS)
│
├── alembic/                            # Database migration history
│   ├── env.py                          # Alembic environment (PostgreSQL + SQLite aware)
│   └── versions/
│       └── 4998d6d8ee26_baseline_from_models.py  # Baseline schema migration
│
├── scripts/                            # Developer & ops utilities
│   ├── migrate_sqlite_to_postgres.py   # One-shot SQLite → PostgreSQL migration
│   ├── reconcile_databases.py          # Cross-backend parity verification
│   ├── run_golden_evaluation.py        # Golden dataset evaluation runner
│   └── ...                             # Additional demo, test, and verification scripts
│
├── tests/
│   ├── unit/                           # 69 unit test files — 400+ test cases
│   │   ├── test_analytics_service.py
│   │   ├── test_annotation_service.py
│   │   ├── test_batch_zip_workflow.py
│   │   ├── test_classification_service.py
│   │   ├── test_database_config_and_backend.py
│   │   ├── test_drawing_department_fk.py
│   │   ├── test_export_service.py
│   │   ├── test_workflow_engine.py
│   │   └── ...
│   └── integration/
│       └── test_golden_evaluation_benchmark.py
│
├── config/
│   └── config.yaml                     # Runtime configuration (all settings)
├── data/                               # Database files & uploaded drawings
├── dataset/                            # Classification training datasets
├── docs/                               # Architecture & migration documentation
├── exports/                            # Generated Excel Error Trackers
├── main.py                             # Application entry point
├── requirements.txt                    # Python package dependencies
├── UCC_Drawing_Review_Intelligence.spec  # PyInstaller build specification
├── alembic.ini                         # Alembic CLI configuration
└── README.md                           # This document
```

---

## 🧪 Testing & Quality Assurance

The codebase is backed by a comprehensive unit test suite with **400+ test cases across 69 test files**, covering:

| Test Domain | Files | What's Covered |
| :--- | :--- | :--- |
| Analytics Service | 7 files | KPI aggregations, Pareto, trend bucketing, reviewer metrics, filters |
| OCR & Preprocessing | 6 files | Color segmentation, Tesseract pipeline, PSM fallback, micro-upscaling |
| Classification | 4 files | DistilBERT inference, rule fallback, confidence scoring |
| Database & Config | 5 files | PostgreSQL/SQLite backends, Alembic, FK constraints, config loading |
| Batch & Upload Workflows | 3 files | ZIP ingestion, department binding, progress tracking |
| Export & Audit | 4 files | Excel generation, audit log integrity, reviewer attribution |
| UI Logic | 8 files | Visibility rules, context-aware sidebar, filter state |
| Migrations | 2 files | SQLite → PostgreSQL migration, reconciliation parity |

**Run the full test suite:**
```bash
# Fast run — excludes Tesseract/distilbert environment tests
python -m pytest tests/unit/ \
  --ignore=tests/unit/test_distilbert_verification.py \
  --ignore=tests/unit/test_ocr_nlp_pipeline_integration.py \
  -q

# Expected result: 400+ passed, 18 skipped (Tesseract not in PATH)
```

> **Note on 18 Tesseract failures**: Tests in `test_tesseract_ocr_verification.py`, `test_preprocessing_verification.py`, and related files require Tesseract installed in `PATH`. These are environmental and are not application defects.

---

## ⚙️ Configuration Reference

All settings live in [`config/config.yaml`](config/config.yaml). **Environment variables always take precedence.**

### Database

| Environment Variable | `config.yaml` Key | Default | Description |
| :--- | :--- | :--- | :--- |
| `UCC_DATABASE_URL` | `database.url` | *(SQLite path)* | Full connection URL (PostgreSQL or SQLite) |
| `UCC_DATABASE_BACKEND` | `database.backend` | `sqlite` | `postgresql` or `sqlite` |
| `UCC_DATABASE_DB_PATH` | `database.db_path` | `data/ucc_database.db` | SQLite file path |

### OCR

| Environment Variable | `config.yaml` Key | Default | Description |
| :--- | :--- | :--- | :--- |
| `UCC_OCR_ENGINE` | `ocr.engine` | `auto` | `auto`, `tesseract`, `trocr`, or `hybrid` |
| `UCC_OCR_CONFIDENCE_THRESHOLD` | `ocr.confidence_threshold` | `0.50` | Minimum confidence for text acceptance |
| `UCC_OCR_TESSERACT_PSM` | `ocr.tesseract_psm` | `6` | Primary Tesseract page-segmentation mode |
| `UCC_OCR_FALLBACK_PSM` | `ocr.fallback_psm` | `11` | Fallback PSM when primary confidence is low |

### AI Classification

| Environment Variable | `config.yaml` Key | Default | Description |
| :--- | :--- | :--- | :--- |
| `UCC_AI_CLASSIFIER_TYPE` | `ai.classifier_type` | `hybrid_nlp` | `hybrid_nlp`, `distilbert`, or `rule_fallback` |
| `UCC_AI_AUTO_APPROVE_THRESHOLD` | `ai.auto_approve_threshold` | `0.80` | Confidence threshold for auto-approval |
| `UCC_AI_LOW_CONFIDENCE_THRESHOLD` | `ai.low_confidence_threshold` | `0.60` | Low-confidence band boundary |

### PDF Processing

| `config.yaml` Key | Default | Description |
| :--- | :--- | :--- |
| `pdf.display_dpi` | `150` | DPI for viewport rendering |
| `pdf.ocr_dpi` | `300` | DPI for raster OCR fallback |
| `pdf.max_file_size_mb` | `500` | Maximum upload file size |

### UI

| `config.yaml` Key | Default | Description |
| :--- | :--- | :--- |
| `ui.theme` | `dark` | `dark` or `light` |
| `ui.rows_per_page` | `25` | Rows per page in tables |
| `ui.window_maximized` | `true` | Start maximized |

---

## 🗄 PostgreSQL Migration Guide

The application ships with complete migration tooling. The following steps migrate a live SQLite deployment to PostgreSQL:

```bash
# Step 1: Create the target database
psql -U postgres -c "CREATE DATABASE ucc_database;"

# Step 2: Configure connection (PowerShell — sets Windows User env vars)
[System.Environment]::SetEnvironmentVariable(
    "UCC_DATABASE_URL",
    "postgresql+psycopg://postgres:YourPassword@localhost:5432/ucc_database",
    "User"
)
[System.Environment]::SetEnvironmentVariable("UCC_DATABASE_BACKEND", "postgresql", "User")

# Step 3: Apply Alembic baseline schema (creates all 10 tables with FKs and indexes)
alembic upgrade head

# Step 4: Migrate historical SQLite data (dry-run first)
python scripts/migrate_sqlite_to_postgres.py --dry-run
python scripts/migrate_sqlite_to_postgres.py --execute

# Step 5: Verify 100% data parity
python scripts/reconcile_databases.py
```

The reconciliation tool generates [`docs/migration/reconciliation_report.md`](docs/migration/reconciliation_report.md) with row counts, comment distributions, and KPI comparisons across both backends.

**PostgreSQL compatibility notes:**
- All timestamp columns use `TIMESTAMP WITH TIME ZONE` (`DateTime(timezone=True)`) stored as UTC.
- Boolean comparisons use `column.is_(True/False)` instead of `== True` for dialect safety.
- `GROUP BY` clauses reference model columns directly (not SQLAlchemy-computed aliases) to avoid `GroupingError` on PostgreSQL.

---

## 📊 Analytics & Reporting

The **Analytics screen** provides a full filter-driven intelligence dashboard:

```
┌─────────────────────────────────────────────────────────────┐
│  FILTER BAR                                                 │
│  Department ▼  Category ▼  Drawing ▼  Batch □  Rejected ☑  │
│  Extracted from: [2024-01-01] to: [Today]   [Refresh]      │
│  Showing 1,247 comments — Dept: Piping, excl. rejected      │
├────────────────────────────┬────────────────────────────────┤
│  Pareto Chart              │  Timeline (daily/weekly/monthly)│
│  (full distribution,       │  (auto-bucketed, zero-filled,  │
│   selected highlighted)    │   UTC → local timezone)        │
├────────────────────────────┼────────────────────────────────┤
│  Category Pie              │  Status Distribution Donut     │
│  (exploded slice on filter)│  Pending / Approved / Rejected │
├────────────────────────────┴────────────────────────────────┤
│  KPI CARDS                                                  │
│  Total  │  Approved  │  Avg Confidence  │  Auto-Approve %  │
│  Comments│  Rate      │  (AI model only) │  (≥ 0.80 conf)  │
└─────────────────────────────────────────────────────────────┘
```

**Trend bucketing rules:**
- ≤ 31 days in range → **Daily** buckets (`YYYY-MM-DD`)
- ≤ 26 weeks → **Weekly** buckets (`YYYY-Www`)
- Larger range → **Monthly** buckets (`YYYY-MM`)

---

## 🤝 Contributing & Development

Contributions are welcome! Follow these steps:

1. Fork the repository and create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Implement changes following PEP 8 guidelines with full type annotations.
3. Run the unit test suite and ensure no regressions:
   ```bash
   python -m pytest tests/unit/ --ignore=tests/unit/test_distilbert_verification.py --ignore=tests/unit/test_ocr_nlp_pipeline_integration.py -q
   ```
4. Commit with semantic messages:
   ```bash
   git commit -m "feat(analytics): add retention trend chart"
   ```
5. Push and open a Pull Request against `main`.

### Development Architecture Notes

- **AppController** (`app/controllers/app_controller.py`) is the single bridge between the GUI layer and all backend services. UI screens should never import services directly.
- **DatabaseEngine** (`src/infrastructure/storage/repository.py`) transparently supports both PostgreSQL and SQLite via SQLAlchemy 2.0 unified API.
- **Config resolution order**: `UCC_DATABASE_URL` env var > Windows Registry (`HKCU\Environment`) > `config/config.yaml` > dataclass defaults.
- **PyInstaller**: The spec file at `UCC_Drawing_Review_Intelligence.spec` packages `config/`, `models/`, `alembic/`, and `data/` alongside the application binaries. Build with `pyinstaller --clean UCC_Drawing_Review_Intelligence.spec`.

---

## 📜 License

This project is developed for **UCC Engineering Drawing Intelligence** workflows.  
Distributed under the **MIT License**.

---

<div align="center">

**UCC AI Drawing Review Comment Analyzer & Intelligence Hub**  
*Built with PySide6 · DistilBERT · PyMuPDF · OpenCV · PostgreSQL · SQLAlchemy · Alembic*

| Metric | Value |
|:---|:---|
| Python Source Files | 185 |
| Unit Test Files | 69 |
| Test Cases | 400+ |
| Git Commits | 134 |
| Database Tables | 10 |
| Engineering Departments | 7 |
| AI Taxonomy Labels | 13 |
| Processing Speed | ~2.8 s/page |

</div>
