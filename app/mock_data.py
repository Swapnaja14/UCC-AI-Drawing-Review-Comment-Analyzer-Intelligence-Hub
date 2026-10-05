"""
Mock data for UCC AI Drawing Review Comment Analyzer.
Provides realistic engineering drawing comment datasets for all screens.
"""
from dataclasses import dataclass, field
from typing import List, Optional
import random

# ── Project records ──────────────────────────────────────────────────────────

@dataclass
class Project:
    id: str
    name: str
    drawings: int
    comments: int
    status: str          # "Active", "Complete", "On Hold"
    progress: int        # 0–100
    last_modified: str
    engineer: str

PROJECTS: List[Project] = [
    Project("PRJ-001", "UCC Site-4 Expansion",       48, 312, "Active",   78, "2026-07-28", "A. Mehta"),
    Project("PRJ-002", "Refinery Unit-7 Upgrade",    32, 197, "Active",   55, "2026-07-25", "S. Nair"),
    Project("PRJ-003", "Pipeline Corridor North",    61, 408, "Complete", 100, "2026-07-10", "R. Kapoor"),
    Project("PRJ-004", "Compressor Station Alpha",   19, 121, "On Hold",  33, "2026-07-05", "T. Patel"),
    Project("PRJ-005", "LNG Terminal Phase-2",       74, 523, "Active",   62, "2026-07-30", "V. Singh"),
    Project("PRJ-006", "Water Treatment Facility",   27, 184, "Complete", 100, "2026-06-20", "D. Rao"),
    Project("PRJ-007", "Offshore Platform Mod",      41, 291, "Active",   41, "2026-07-29", "J. Sharma"),
]

# ── KPI totals ────────────────────────────────────────────────────────────────

KPI = {
    "total_projects":   7,
    "drawings_processed": 302,
    "comments_detected":  2036,
    "accuracy":          91.4,
    "trend_projects":   "+2",
    "trend_drawings":  "+18",
    "trend_comments":  "+143",
    "trend_accuracy":  "+0.8",
}

# ── Comment / OCR records ─────────────────────────────────────────────────────

CATEGORIES = [
    "Technical",
    "Drafting",
    "Dimension",
    "Cosmetic",
    "Standards",
    "Coordination",
    "Documentation",
    "Revision",
    "Calculation",
    "Feasibility",
    "Material",
    "Notes",
    "BOM"
]
STATUSES   = ["Pending", "Approved", "Rejected", "Flagged"]

@dataclass
class Comment:
    id: str
    project_id: str
    drawing_no: str
    page: int
    ocr_text: str
    category: str
    confidence: float     # 0.0–1.0
    status: str
    bbox: tuple           # (x, y, w, h) normalised 0–1
    reviewer: Optional[str]
    timestamp: str
    ocr_confidence: Optional[float] = None
    classification_confidence: Optional[float] = None
    classification_method: str = "ai_model"
    fallback_used: bool = False

_raw_comments = [
    ("C-0001","PRJ-001","UCC-E-101",1,"INCORRECT MEMBER SIZE: UPGRADE W12X45 TO W14X68 FOR SPAN LOAD","Technical",0.97,"Approved",(0.12,0.23,0.28,0.04),"A. Mehta","2026-07-28 09:14"),
    ("C-0002","PRJ-001","UCC-E-101",1,"TITLE BLOCK INCOMPLETE: PROJECT NUMBER AND DWG REVISION MISSING","Documentation",0.88,"Approved",(0.55,0.40,0.22,0.03),"A. Mehta","2026-07-28 09:18"),
    ("C-0003","PRJ-001","UCC-E-102",2,"WRONG WELD CALLOUT: REPLACE FILLET WELD WITH MOMENT CONNECTION","Technical",0.76,"Pending",(0.08,0.61,0.30,0.04),None,"2026-07-28 10:02"),
    ("C-0004","PRJ-001","UCC-E-103",1,"INCORRECT MATERIAL SPECIFIED: LINE REQUIRES SS316L INSTEAD OF CS","Material",0.92,"Approved",(0.42,0.18,0.25,0.03),"A. Mehta","2026-07-28 10:45"),
    ("C-0005","PRJ-001","UCC-E-104",3,"CLASH WITH ELECTRICAL: CONDUIT BANK ROUTES THROUGH VALVE ENVELOPE","Coordination",0.65,"Flagged",(0.20,0.55,0.35,0.04),None,"2026-07-28 11:23"),
    ("C-0006","PRJ-001","UCC-E-104",3,"REVISION CLOUD MISSING AROUND MODIFIED NOZZLE CONNECTION AT GRID 4","Revision",0.83,"Pending",(0.60,0.70,0.20,0.03),None,"2026-07-28 11:25"),
    ("C-0007","PRJ-002","RU7-P-201",1,"BOM QUANTITY MISMATCH: DRAWING SHOWS 4 BRACKETS BUT BOM LISTS 2","BOM",0.91,"Approved",(0.15,0.30,0.28,0.04),"S. Nair","2026-07-25 14:10"),
    ("C-0008","PRJ-002","RU7-P-201",2,"INCORRECT DIMENSION: OVERALL LENGTH 4500MM BUT SUM OF PARTS IS 4620MM","Dimension",0.94,"Approved",(0.50,0.45,0.24,0.03),"S. Nair","2026-07-25 14:22"),
    ("C-0009","PRJ-002","RU7-P-202",1,"CODAL ISSUE: STAIR HANDRAIL HEIGHT 900MM DOES NOT MEET OSHA MIN 42IN","Standards",0.58,"Flagged",(0.08,0.72,0.32,0.04),None,"2026-07-25 15:05"),
    ("C-0010","PRJ-002","RU7-P-203",4,"LINE OVERLAP OBSERVED BETWEEN DIMENSION LINE AND CENTERLINE","Drafting",0.79,"Pending",(0.35,0.28,0.30,0.04),None,"2026-07-25 15:40"),
    ("C-0011","PRJ-003","PL-N-301",1,"DESIGN INCONSISTENCY: PRESSURE DROP CALCULATION DOES NOT MATCH P&ID","Calculation",0.96,"Approved",(0.10,0.20,0.35,0.04),"R. Kapoor","2026-07-10 08:55"),
    ("C-0012","PRJ-003","PL-N-301",2,"MAINTENANCE ACCESSIBILITY: INSUFFICIENT CLEARANCE TO PULL TUBE BUNDLE","Feasibility",0.89,"Approved",(0.48,0.55,0.28,0.03),"R. Kapoor","2026-07-10 09:10"),
    ("C-0013","PRJ-003","PL-N-302",1,"UPDATE GENERAL NOTE 4: FIELD VERIFICATION OF FOUNDATION IS MANDATORY","Notes",0.72,"Rejected",(0.18,0.65,0.26,0.04),"R. Kapoor","2026-07-10 09:45"),
    ("C-0014","PRJ-004","CS-A-401",1,"TYPO ERROR IN TITLE: 'STRUCTRAL' SHOULD BE 'STRUCTURAL'","Cosmetic",0.85,"Pending",(0.30,0.35,0.22,0.03),None,"2026-07-05 11:00"),
    ("C-0015","PRJ-005","LNG-T-501",1,"GASKET MATERIAL SPECIFIED IS INCOMPATIBLE: CHANGE TO SPIRAL WOUND","Material",0.98,"Approved",(0.05,0.15,0.40,0.04),"V. Singh","2026-07-30 10:20"),
    ("C-0016","PRJ-005","LNG-T-502",3,"CLASH WITH PIPING: 6 INCH LINE CONFLICTS WITH CABLE TRAY AT GRID B","Coordination",0.87,"Pending",(0.55,0.60,0.28,0.04),None,"2026-07-30 11:05"),
    ("C-0017","PRJ-005","LNG-T-503",2,"MISSING DIMENSION FROM COLUMN GRID TO PUMP CENTERLINE","Dimension",0.93,"Approved",(0.22,0.40,0.32,0.04),"V. Singh","2026-07-30 11:50"),
    ("C-0018","PRJ-006","WT-F-601",1,"INCORRECT PART NUMBER IN BOM: CATALOG NUMBER DOES NOT MATCH VENDOR","BOM",0.70,"Flagged",(0.40,0.50,0.28,0.03),None,"2026-06-20 14:30"),
    ("C-0019","PRJ-007","OP-M-701",1,"MISSING HIDDEN LINE FOR UNDERGROUND CONDUIT DUCT ON PLAN VIEW","Drafting",0.81,"Pending",(0.12,0.42,0.35,0.04),None,"2026-07-29 09:00"),
    ("C-0020","PRJ-007","OP-M-702",2,"REVISION TABLE NOT UPDATED: ADD REV B DESCRIPTION INCORPORATED COMMENTS","Revision",0.88,"Approved",(0.50,0.30,0.25,0.03),"J. Sharma","2026-07-29 09:30"),
]

COMMENTS: List[Comment] = []
for _raw_rec in _raw_comments:
    _c = Comment(*_raw_rec)
    _c.ocr_confidence = _c.confidence
    _c.classification_confidence = _c.confidence
    if _c.id in ("C-0005", "C-0009", "C-0018"):
        _c.classification_method = "rule_based_fallback"
        _c.fallback_used = True
    elif _c.id in ("C-0006", "C-0010"):
        _c.classification_method = "rule_based"
        _c.fallback_used = False
    elif _c.id in ("C-0013", "C-0020"):
        _c.classification_method = "manual"
        _c.fallback_used = False
    else:
        _c.classification_method = "ai_model"
        _c.fallback_used = False
    COMMENTS.append(_c)

# ── Activity feed ─────────────────────────────────────────────────────────────

ACTIVITIES = [
    {"icon": "fa5s.check-circle",  "color": "#4ADE80", "text": "Comment C-0017 approved",            "time": "2 min ago"},
    {"icon": "fa5s.upload",        "color": "#3E9BFF", "text": "Drawing LNG-T-503 uploaded",          "time": "8 min ago"},
    {"icon": "fa5s.flag",          "color": "#FBBF24", "text": "Comment C-0016 flagged for review",   "time": "15 min ago"},
    {"icon": "fa5s.times-circle",  "color": "#F87171", "text": "Comment C-0013 rejected",             "time": "1 hr ago"},
    {"icon": "fa5s.robot",         "color": "#8B9CFF", "text": "OCR completed: OP-M-702",             "time": "1 hr ago"},
    {"icon": "fa5s.file-export",   "color": "#3E9BFF", "text": "Report exported: PRJ-003",            "time": "3 hr ago"},
    {"icon": "fa5s.user-check",    "color": "#4ADE80", "text": "Review session started: PRJ-005",     "time": "4 hr ago"},
]

# ── Processing jobs ───────────────────────────────────────────────────────────

JOBS = [
    {"name": "LNG-T-501 OCR",          "progress": 100, "status": "Approved"},
    {"name": "OP-M-701 Classification", "progress":  72, "status": "Pending"},
    {"name": "RU7-P-203 OCR",           "progress":  45, "status": "Pending"},
    {"name": "CS-A-401 Upload",         "progress":  10, "status": "Pending"},
]

# ── Analytics data ────────────────────────────────────────────────────────────

MONTHLY_COUNTS = {
    "months":   ["Jan","Feb","Mar","Apr","May","Jun","Jul"],
    "comments": [120,  180,  145,  210,  195,  280,  312],
    "approved": [ 98,  152,  118,  180,  161,  243,  278],
}

CATEGORY_COUNTS = {
    "Technical":     342,
    "Dimension":     285,
    "Drafting":      230,
    "Coordination":  195,
    "Standards":     180,
    "BOM":           165,
    "Material":      150,
    "Revision":      140,
    "Calculation":   115,
    "Notes":         105,
    "Documentation":  90,
    "Feasibility":    85,
    "Cosmetic":       65,
}

PARETO_DATA = {
    "categories": ["Technical", "Dimension", "Drafting", "Coordination", "Standards", "BOM", "Material", "Revision", "Calculation", "Notes", "Documentation", "Feasibility", "Cosmetic"],
    "counts":     [342, 285, 230, 195, 180, 165, 150, 140, 115, 105, 90, 85, 65],
    "cumulative": [15.9, 29.2, 39.9, 49.0, 57.4, 65.1, 72.1, 78.6, 83.9, 88.8, 93.0, 97.0, 100.0],
}

# ── Export history ────────────────────────────────────────────────────────────

EXPORT_HISTORY = [
    {"name":"PRJ-003_Report_2026-07-10.xlsx","format":"Excel","date":"2026-07-10","size":"1.2 MB"},
    {"name":"PRJ-001_Comments_2026-07-28.csv","format":"CSV",  "date":"2026-07-28","size":"84 KB"},
    {"name":"PRJ-005_Summary_2026-07-30.pdf", "format":"PDF",  "date":"2026-07-30","size":"3.4 MB"},
    {"name":"PRJ-002_Report_2026-07-25.xlsx", "format":"Excel","date":"2026-07-25","size":"987 KB"},
]
