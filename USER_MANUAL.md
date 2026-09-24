# UCC AI Drawing Review Comment Analyzer
## User Manual - Version 1.0.0

**Prepared by:** Varad / UCC Engineering
**Phase:** Phase 13 - Deployment and Documentation
**Date:** September 2026

---

## 1. System Overview

The UCC AI Drawing Review Comment Analyzer is an enterprise desktop application
that automates extraction, classification, and human review of engineering drawing
review comments. It processes PDF engineering drawings through a hybrid AI pipeline.

| Component | Technology |
|---|---|
| Desktop UI | PySide6 (Qt 6.x for Python) |
| OCR Engine | Hybrid: Tesseract + Microsoft TrOCR |
| Classifier | DistilBERT 13-class engineering category model |
| PDF Rendering | PyMuPDF (fitz) |
| Database | SQLite 3 via SQLAlchemy ORM |
| Platform | Windows 10 / 11 desktop |

Core Capabilities:
- Detect multi-color annotation boxes on engineering drawings via computer vision
- Extract comment text via hybrid OCR (handwritten and printed text)
- Classify comments into 13 engineering categories
- Enable engineer-driven human review, approval, rejection, and flagging
- Export structured datasets as CSV, Excel, JSON, or PDF reports
- Analytics dashboards for project-level comment trend tracking

---

## 2. System Requirements & Installation

Prerequisites:
- Python 3.11+ (3.12 recommended)
- Windows 10/11 64-bit
- 8 GB RAM minimum (16 GB recommended)
- 1280x768 display minimum (1920x1080 recommended)

Installation:
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt

---

## 3. Launching the Application

    python main.py

Opens with a 2.2-second animated splash screen, then shows the Dashboard
in the pure white enterprise light theme.

---

## 4. Application Layout

Sidebar (240px): Navigation menu, backend status indicator, version label
Top Bar (72px): Screen breadcrumb, global search, theme toggle, user profile
Status Bar: Currently loaded drawing info, backend connection, Python/PySide6 version

---

## 5. Core Workflows

### 5.1 Dashboard
4 KPI cards: Total Projects, Drawings Processed, Comments Detected, OCR Accuracy.
3 Analytics charts: Category Pareto bar, Category Distribution donut, Comment Trend line.
Recent Projects table, Recent Drawings table, Recent Activity feed, Processing Status bars.

### 5.2 Upload Drawing
1. Drag and drop a PDF into the drop zone OR click Browse PDF File.
2. Uploaded file appears in a horizontal preview card with name, size, READY badge.
3. Click Start AI Processing Workflow to run the full AI pipeline.
4. On completion click View PDF Drawing to go to PDF Viewer.

### 5.3 PDF Viewer
Toolbar: Zoom in/out, Fit Page, Rotate, Annotations toggle, Prev/Next sheet, Page field.
Right Panel: Scrollable metadata (file size, pages, format, title, author, digest, regions).
Bottom: Thumbnail strip for fast page navigation.

### 5.4 Comment Highlight Viewer
Left: Drawing canvas with color-coded bounding boxes over detected comments.
Right: Filter chips (All | Pending | Approved | Flagged | Technical) + comment list.
Comment cards: ID, OCR text, Category badge, Status chip, Confidence %.
Canvas controls: + Zoom In | - Zoom Out | Fit View

### 5.5 OCR Results
Editable table: Comment ID, Text (inline-editable), Confidence bar, Status.
Search bar filters by text; Status dropdown filters by review status.
Clean Text button: runs text cleaning service with correction diff dialog.

### 5.6 Classification
DistilBERT 13-class results table with category, confidence score, and logits.
Re-classify button re-runs classification on the current drawing.

### 5.7 Human Review
Left: Drawing canvas showing current comment bounding box highlighted.
Right Panel:
  - Comment progress bar (e.g. Comment 3 of 71)
  - Comment ID and drawing reference
  - OCR DETECTED TEXT read-only field (editable via Edit Text button)
  - ENGINEERING CATEGORY dropdown + category badge
  - DETECTION CONFIDENCE progress bar + percentage label
  - CURRENT REVIEW STATUS chip
  - Audit History collapsible panel with timestamps

Action Buttons:
  Row 1: < Prev | Edit Text | Next >
  Row 2: X Reject (red) | Flag (amber) | Approve Comment (green)

Keyboard shortcuts: A=Approve, R=Reject, F=Flag, Left/Right=Prev/Next

### 5.8 Analytics
Filter bar: Project, Category, Date Range. Apply Filter button.
4 KPI summary cards + responsive chart grid.

### 5.9 Export
Step 1: Select format card (CSV, Excel, JSON, PDF Report).
Step 2: Set scope (Project, Drawing, Category, Status, Date Range).
Step 3: Click Generate Export. Animated progress bar runs the export job.
Export history table lists all past exports with filename, format, date.

### 5.10 Settings
Theme selection, OCR engine configuration, Export directory,
Database path, Logging level.

---

## 6. Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| A | Approve current comment (Human Review) |
| R | Reject current comment |
| F | Flag current comment |
| Left / Right Arrow | Navigate Previous / Next comment |
| Ctrl+F | Focus global search bar |
| Ctrl+O | Open file browser (Upload screen) |
| Ctrl+E | Navigate to Export screen |
| Ctrl+D | Navigate to Dashboard |
| + / - | Zoom in / out (PDF Viewer, Comment Viewer) |
| Esc | Close active dialog |

---

## 7. UI Theme Switching

Default: Pure white enterprise Light Mode.
Switch to Dark: Click the Moon/Dark button in the top bar.
Switch back: Click the Sun/Light button.
All screens, charts, panels, badges, and buttons update instantly.

---

## 8. Troubleshooting & Diagnostics

Cannot start:
    python --version          # Must be 3.11+
    python -c "from PySide6.QtWidgets import QApplication; print('PySide6 OK')"

SQLite error: Delete data/ucc_database.db and restart. It auto-recreates.
PDF fails to load: Check the PDF is not password-protected. Verify PyMuPDF is installed.
OCR returns empty text: Verify Tesseract is on PATH (tesseract --version).
Backend indicator red: Check data/ directory is writable, then restart.

---

## 9. Testing & Verification Guide (Phase 12)

Phase 12 UI Testing Checklist:
  All 10 screen imports                PASS
  Backend DB initialization            PASS
  Offscreen GUI navigation (0-9)       PASS
  Light mode theme application         PASS
  Dark mode toggle                     PASS
  Export format card selection         PASS
  Comment Viewer filter chips          PASS
  Human Review approval flow           PASS
  PDF Viewer zoom controls             PASS
  Drop zone drag styling               PASS
  Text truncation check                PASS
  High DPI rendering (125%)            PASS

Automated verification:
    python -c "import app.theme, app.main_window, app.screens.dashboard_screen, app.screens.upload_screen, app.screens.pdf_viewer_screen, app.screens.comment_viewer_screen, app.screens.review_screen, app.screens.analytics_screen, app.screens.export_screen, app.screens.ocr_results_screen, app.screens.classification_screen, app.screens.settings_screen; print('ALL SCREENS PASS')"

---

## 10. System Architecture Summary

    main.py                   Entry point, theme, splash
    app/
      theme.py                Light/Dark tokens + QSS engine
      main_window.py          Shell: sidebar + topbar + stacked pages
      components/
        sidebar.py            240px navigation sidebar
        topbar.py             72px header
        chips.py              StatusChip + CategoryBadge (light/dark)
        kpi_card.py           KPI metric card
        charts.py             QtCharts: Pareto, Donut, Trend
        pdf_toolbar.py        54px PDF toolbar
        metadata_panel.py     Scrollable metadata panel
      screens/
        dashboard_screen.py
        upload_screen.py
        pdf_viewer_screen.py
        comment_viewer_screen.py
        ocr_results_screen.py
        classification_screen.py
        review_screen.py
        analytics_screen.py
        export_screen.py
        settings_screen.py
      controllers/
        app_controller.py     Single controller for all backend operations
    src/
      core/                   DTOs, interfaces, domain models
      services/               OCR, Classification, Export services
      repositories/           SQLAlchemy database repositories
      workers/                Background thread workers
    data/
      ucc_database.db         SQLite database (auto-created on first run)

---
Prepared as part of Phase 13 - Deployment and Documentation.
UCC AI Drawing Review Comment Analyzer v1.0.0
