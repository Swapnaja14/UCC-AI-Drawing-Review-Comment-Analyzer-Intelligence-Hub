"""
app/controllers/app_controller.py
Application Controller & Thread-Safe Background Workers for Desktop UI.

Orchestrates Auth, PDF Operations, File Service, and Processing Workflow Engine,
while also acting as the single access point between the PySide6 UI layer and all
backend services and database repositories.

ARCHITECTURE NOTE:
AppController is the single access point between the PySide6 UI layer and all
backend services and database repositories. UI screens must NEVER instantiate
repositories or services directly.

Data flow:
    UI Screen → AppController → Service / Repository → SQLAlchemy → SQLite

The controller owns two important state properties after a PDF is loaded:
    current_document   → PDFDocumentDTO  (PDF metadata, page dimensions)
    current_drawing_id → str             (DrawingModel.id, e.g. "DWG-XXXXXXXX")

INTEGRATION WARNING:
    PDF filename (current_document.file_name) is NOT the database drawing ID.
    current_document.file_name = "UCC-E-101.pdf"  (bare filename)
    current_drawing_id          = "DWG-3F7A1C2B"  (DB primary key)
    Always use current_drawing_id when associating comments with a drawing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, QThread, Signal

from src.services.pdf_service import PDFService
from src.services.auth_service import AuthService
from src.services.file_service import FileService
from src.services.workflow_engine import ProcessingWorkflowEngine
from src.infrastructure.pdf.pymupdf_adapter import PyMuPDFAdapter
from src.infrastructure.storage.repository import (
    DatabaseEngine,
    DrawingRepository,
    ProjectRepository,
    CommentRepository,
    AuditLogRepository,
    EngineeringDepartmentRepository,
    CategoryRepository
)
from src.core.dtos.pdf_dtos import PDFDocumentDTO, RenderedPageDTO
from src.core.dtos.auth_dtos import UserDTO, SessionTokenDTO
from src.core.dtos.workflow_dtos import WorkflowStepDTO, WorkflowResultDTO, FileValidationResultDTO
from src.core.dtos.export_dtos import ExportConfigDTO

# Import new backend services
from src.services.analytics_service import AnalyticsService
from src.services.export_service import ExportService
from src.services.verification_service import VerificationService
from src.services.text_cleaning_service import TextCleaningService
from src.services.classification_service import ClassificationService
from src.services.annotation_service_enhanced import AnnotationDetectionServiceEnhanced
from src.core.exceptions.auth_exceptions import InvalidCredentialsError
from src.infrastructure.logging.logger import get_logger
from src.config import get_config

logger = get_logger("AppController")


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class WorkflowWorker(QThread):
    """Background QThread executing full multi-step drawing processing pipeline without freezing UI."""

    step_signal      = Signal(object)   # Emits WorkflowStepDTO
    completed_signal = Signal(object)   # Emits WorkflowResultDTO
    error_signal     = Signal(str)      # Emits error string

    def __init__(
        self,
        workflow_engine: ProcessingWorkflowEngine,
        file_path: Path,
        department_id: Optional[str] = None,
    ):
        super().__init__()
        self.workflow_engine = workflow_engine
        self.file_path       = file_path
        self.department_id   = department_id

    def run(self):
        try:
            def on_progress(step_snapshot: WorkflowStepDTO):
                self.step_signal.emit(step_snapshot)

            result = self.workflow_engine.execute_workflow(
                self.file_path,
                progress_callback=on_progress,
                department_id=self.department_id,
            )
            self.completed_signal.emit(result)
        except Exception as e:
            logger.error(f"Error in WorkflowWorker: {e}")
            self.error_signal.emit(str(e))


class PDFLoadWorker(QThread):
    """Worker thread: loads a PDF document and saves drawing metadata to DB.

    Emits success_signal(PDFDocumentDTO, drawing_id: str) on completion so
    AppController can store current_drawing_id without blocking the UI thread.

    INTEGRATION NOTE:
    The drawing_id emitted here is the DrawingModel.id primary key returned by
    DrawingRepository.save_drawing_from_dto(). It is NOT the PDF filename.
    AppController stores this as _current_drawing_id for use by all downstream
    comment operations.
    """

    # Emits (doc_dto, drawing_id) — drawing_id may be "" on DB save failure
    success_signal = Signal(object, str)
    error_signal   = Signal(str)

    def __init__(
        self,
        pdf_service: PDFService,
        drawing_repo: DrawingRepository,
        file_path: Path,
    ) -> None:
        super().__init__()
        self.pdf_service  = pdf_service
        self.drawing_repo = drawing_repo
        self.file_path    = file_path

    def run(self) -> None:
        try:
            doc_dto = self.pdf_service.process_pdf_document(self.file_path)

            drawing_id = ""
            try:
                result     = self.drawing_repo.save_drawing_from_dto(doc_dto)
                drawing_id = result.get("id", "")
            except Exception as exc:
                logger.warning(f"Database save warning: {exc}")

            self.success_signal.emit(doc_dto, drawing_id)

        except Exception as exc:
            logger.error(f"Error in PDFLoadWorker: {exc}")
            self.error_signal.emit(str(exc))


class PDFRenderWorker(QThread):
    """Worker thread for high-DPI page rendering without blocking GUI."""

    rendered_signal = Signal(object)   # RenderedPageDTO
    error_signal    = Signal(str)

    def __init__(
        self,
        pdf_service: PDFService,
        file_path: Path,
        page_number: int,
        dpi: int = 300,
    ) -> None:
        super().__init__()
        self.pdf_service = pdf_service
        self.file_path   = file_path
        self.page_number = page_number
        self.dpi         = dpi

    def run(self) -> None:
        try:
            rendered_dto = self.pdf_service.get_page_render(
                self.file_path, self.page_number, self.dpi
            )
            self.rendered_signal.emit(rendered_dto)
        except Exception as exc:
            logger.error(
                f"Error in PDFRenderWorker rendering page {self.page_number}: {exc}"
            )
            self.error_signal.emit(str(exc))


# ---------------------------------------------------------------------------
# AppController
# ---------------------------------------------------------------------------

class AppController(QObject):
    """
    Central application controller — mediates between PySide6 UI and all
    backend services / database repositories.

    ARCHITECTURE NOTE:
    All database access from the UI must go through this controller.
    UI screens must NOT import or instantiate any repository class directly.
    Repositories are private implementation details of the controller.

    Signals
    -------
    document_loaded_signal : PDFDocumentDTO
        Emitted (on the main thread) when a PDF has been fully loaded and
        its drawing record saved to the database.
    page_rendered_signal : RenderedPageDTO
        Emitted when a background page-render completes.
    processing_error_signal : str
        Emitted on any background worker error.
    workflow_step_signal : WorkflowStepDTO
        Emitted at each step of the processing workflow pipeline.
    workflow_completed_signal : WorkflowResultDTO
        Emitted when the full workflow pipeline completes.
    user_signed_in_signal : SessionTokenDTO
        Emitted after a successful authentication.
    user_signed_out_signal :
        Emitted after the current session is signed out.
    auth_error_signal : str
        Emitted on authentication failure.
    """

    # PDF / rendering signals
    document_loaded_signal  = Signal(object)   # PDFDocumentDTO
    page_rendered_signal    = Signal(object)   # RenderedPageDTO
    processing_error_signal = Signal(str)

    # Workflow pipeline signals
    workflow_step_signal      = Signal(object)   # WorkflowStepDTO
    workflow_completed_signal = Signal(object)   # WorkflowResultDTO

    # Auth signals
    user_signed_in_signal  = Signal(object)   # SessionTokenDTO
    user_signed_out_signal = Signal()
    auth_error_signal      = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        # ── Configuration & Services ──────────────────────────────
        self.config          = get_config()
        self.pdf_adapter     = PyMuPDFAdapter()
        self.pdf_service     = PDFService(pdf_loader=self.pdf_adapter)
        self.file_service    = FileService()
        self.auth_service: Optional[Any] = None   # initialised after db_engine below

        # ── Database ──────────────────────────────────────────────
        db_path = self.config.database.get_resolved_db_path()
        self.db_engine    = DatabaseEngine(db_path=db_path)
        self.drawing_repo    = DrawingRepository(self.db_engine)
        self.project_repo    = ProjectRepository(self.db_engine)
        self.comment_repo    = CommentRepository(self.db_engine)
        self.audit_repo      = AuditLogRepository(self.db_engine)
        self.department_repo = EngineeringDepartmentRepository(self.db_engine)
        self.category_repo   = CategoryRepository(self.db_engine)

        # Auth and workflow services that depend on db_engine
        self.auth_service    = AuthService(self.db_engine)
        
        # ── New Backend Services ──────────────────────────────────
        self.analytics_service      = AnalyticsService(self.db_engine)
        self.export_service         = ExportService(self.comment_repo, self.project_repo, self.drawing_repo, self.department_repo)
        self.verification_service   = VerificationService(self.comment_repo, self.audit_repo)
        self.text_cleaning_service  = TextCleaningService()
        self.classification_service = ClassificationService()

        # ── Annotation Detection Service ──────────────────────────
        self.annotation_service = AnnotationDetectionServiceEnhanced()
        
        self.workflow_engine = ProcessingWorkflowEngine(
            file_service=self.file_service,
            pdf_service=self.pdf_service,
            drawing_repo=self.drawing_repo,
            annotation_service=self.annotation_service,
            comment_repo=self.comment_repo,
            text_cleaning_service=self.text_cleaning_service,
            classification_service=self.classification_service,
        )

        # ── In-session state ──────────────────────────────────────
        self._active_doc: Optional[PDFDocumentDTO] = None

        # INTEGRATION NOTE:
        # _current_drawing_id is the DrawingModel.id PK for the currently
        # loaded drawing. It is NOT the PDF filename. Always use this value
        # when querying or saving comments for the active drawing.
        # Value is "" (empty string) when no PDF has been loaded this session.
        self._current_drawing_id: str = ""

        self._current_session: Optional[SessionTokenDTO] = None

        # ── Worker references ─────────────────────────────────────
        self._load_worker:     Optional[PDFLoadWorker]   = None
        self._render_worker:   Optional[PDFRenderWorker] = None
        self._workflow_worker: Optional[WorkflowWorker]  = None

    # ── Properties ────────────────────────────────────────────────

    @property
    def current_document(self) -> Optional[PDFDocumentDTO]:
        """The PDFDocumentDTO for the currently loaded drawing, or None."""
        return self._active_doc

    @property
    def current_drawing_id(self) -> str:
        """
        The DrawingModel.id primary key for the currently loaded drawing.

        Returns "" if no drawing has been loaded in this session.

        INTEGRATION NOTE:
        This value is set after a successful PDF load and DB save in
        PDFLoadWorker.run(). It is the only authoritative drawing ID for
        comment operations. Do NOT substitute PDF filename for this value.
        """
        return self._current_drawing_id

    @property
    def current_user(self) -> Optional[UserDTO]:
        """The currently authenticated user, or None if not signed in."""
        return self._current_session.user if self._current_session else None

    # ── Workflow Pipeline API ──────────────────────────────────────

    def validate_file(self, file_path: str | Path) -> FileValidationResultDTO:
        """Validates an uploaded PDF drawing file before processing."""
        return self.file_service.validate_pdf_file(file_path)

    def start_processing_workflow(
        self, file_path: str | Path, department_id: Optional[str] = None
    ) -> None:
        """Triggers non-blocking background multi-step workflow execution."""
        path = Path(file_path).resolve()
        logger.info(
            f"AppController launching workflow pipeline for: {path.name} "
            f"(department_id={department_id})"
        )

        if self._workflow_worker and self._workflow_worker.isRunning():
            self._workflow_worker.quit()
            if not self._workflow_worker.wait(2000):
                self._workflow_worker.terminate()
                self._workflow_worker.wait(1000)

        self._workflow_worker = WorkflowWorker(
            self.workflow_engine, path, department_id=department_id
        )
        self._workflow_worker.step_signal.connect(self._on_workflow_step)
        self._workflow_worker.completed_signal.connect(self._on_workflow_completed)
        self._workflow_worker.error_signal.connect(self._on_doc_error)
        self._workflow_worker.start()

    def get_all_departments(self) -> List[Dict[str, Any]]:
        """Returns all active engineering departments from the repository."""
        if self.department_repo:
            return self.department_repo.get_all_departments()
        return []

    def _on_workflow_step(self, step_snapshot: WorkflowStepDTO) -> None:
        self.workflow_step_signal.emit(step_snapshot)

    def _on_workflow_completed(self, result_dto: WorkflowResultDTO) -> None:
        logger.info(f"AppController: Workflow finished for '{result_dto.file_name}'.")
        self.workflow_completed_signal.emit(result_dto)
        # Also auto-load document for viewer after workflow completes
        if self._workflow_worker:
            path = Path(self._workflow_worker.file_path)
            if path.exists():
                doc_dto = self.pdf_service.process_pdf_document(path)
                self._active_doc = doc_dto
                self._current_drawing_id = result_dto.drawing_id
                self.document_loaded_signal.emit(doc_dto)

    # ── Authentication API ─────────────────────────────────────────

    def sign_in(self, username_or_email: str, password: str) -> bool:
        """Authenticate a user. Returns True on success, False on failure."""
        try:
            session_dto = self.auth_service.authenticate_user(username_or_email, password)
            self._current_session = session_dto
            logger.info(f"AppController: User '{session_dto.user.username}' logged in.")
            self.user_signed_in_signal.emit(session_dto)
            return True
        except InvalidCredentialsError as e:
            err_msg = str(e)
            logger.warning(f"Sign in failed: {err_msg}")
            self.auth_error_signal.emit(err_msg)
            return False
        except Exception as e:
            err_msg = f"Unexpected sign in error: {e}"
            logger.error(err_msg)
            self.auth_error_signal.emit(err_msg)
            return False

    def sign_out(self) -> bool:
        """Sign out the current session. Returns True if a session was active."""
        if self._current_session:
            self.auth_service.sign_out(self._current_session.token)
            user_name = self._current_session.user.username
            self._current_session = None
            logger.info(f"AppController: User '{user_name}' signed out.")
            self.user_signed_out_signal.emit()
            return True
        return False

    # ── PDF operations ─────────────────────────────────────────────

    def load_pdf_file(self, file_path: str | Path) -> None:
        """Trigger non-blocking background loading of a PDF drawing."""
        path = Path(file_path).resolve()
        logger.info(f"AppController load request for: {path}")

        if self._load_worker and self._load_worker.isRunning():
            self._load_worker.terminate()
            self._load_worker.wait()

        self._load_worker = PDFLoadWorker(self.pdf_service, self.drawing_repo, path)
        self._load_worker.success_signal.connect(self._on_doc_loaded)
        self._load_worker.error_signal.connect(self._on_doc_error)
        self._load_worker.start()

    def request_page_render(
        self, file_path: str | Path, page_number: int, dpi: int = 300
    ) -> None:
        """Trigger non-blocking background rendering of a PDF page at target DPI."""
        path = Path(file_path).resolve()

        if self._render_worker and self._render_worker.isRunning():
            self._render_worker.terminate()
            self._render_worker.wait()

        self._render_worker = PDFRenderWorker(self.pdf_service, path, page_number, dpi)
        self._render_worker.rendered_signal.connect(self._on_page_rendered)
        self._render_worker.error_signal.connect(self._on_render_error)
        self._render_worker.start()

    # ── Project / dashboard operations ────────────────────────────

    def get_dashboard_kpis(self) -> Any:
        """Return live KPI aggregates from the database."""
        return self.analytics_service.get_global_kpis()

    def get_category_distribution(
        self,
        drawing_id: Optional[str] = None,
        department_name: Optional[str] = None,
    ) -> List[Any]:
        return self.analytics_service.get_category_distribution(
            drawing_id=drawing_id, department_name=department_name
        )

    def get_pareto_analysis(
        self,
        drawing_id: Optional[str] = None,
        department_name: Optional[str] = None,
        top_n: int = 5,
    ) -> List[Any]:
        return self.analytics_service.get_pareto_analysis(
            drawing_id=drawing_id, department_name=department_name, top_n=top_n
        )

    def get_status_trend(self, drawing_id: str = None) -> List[Any]:
        return self.analytics_service.get_status_trend(drawing_id=drawing_id)

    def get_all_departments(self) -> List[Dict[str, Any]]:
        """Return all engineering departments for UI dropdowns."""
        return self.department_repo.get_all_departments() if hasattr(self, 'department_repo') else []

    def get_all_categories(self) -> List[Dict[str, Any]]:
        """Return all classifications categories from DB."""
        return self.category_repo.get_all_categories() if hasattr(self, 'category_repo') else []

    def add_category(self, name: str, description: str = "", color_hex: str = "#808080") -> None:
        """Add a new classification category."""
        if hasattr(self, 'category_repo'):
            self.category_repo.get_or_create_category(name, description, color_hex)

    def get_all_projects(self) -> List[Dict[str, Any]]:
        """Return all project records from the database."""
        return self.project_repo.get_all_projects()

    def get_recent_drawings(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return recent drawings with comment counts and departments."""
        if hasattr(self, 'drawing_repo'):
            return self.drawing_repo.get_recent_drawings(limit=limit)
        return []

    def get_recent_activity(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return merged real-time activity events across drawing uploads, reviews, and system events."""
        activities: List[Dict[str, Any]] = []

        # 1. Audit logs (review actions, approvals, edits)
        audit_logs = self.audit_repo.get_recent_audit_logs(limit=limit) if hasattr(self, 'audit_repo') else []
        for a in audit_logs:
            action = a.get("action", "Updated")
            reviewer = a.get("reviewer_name") or "Reviewer"
            cmt_id = a.get("comment_id", "")
            time_str = a.get("timestamp", "")

            if action == "Approved":
                icon = "fa5s.check-circle"
                color = "#4ADE80"
                text = f"{reviewer} approved comment {cmt_id}"
            elif action == "Rejected":
                icon = "fa5s.times-circle"
                color = "#F87171"
                text = f"{reviewer} rejected comment {cmt_id}"
            elif action == "Flagged":
                icon = "fa5s.flag"
                color = "#FBBF24"
                text = f"{reviewer} flagged comment {cmt_id}"
            elif action == "Edited":
                icon = "fa5s.edit"
                color = "#3E9BFF"
                text = f"{reviewer} updated text on {cmt_id}"
            else:
                icon = "fa5s.history"
                color = "#8B9CFF"
                text = f"{reviewer}: {action} on {cmt_id}"

            activities.append({
                "text": text,
                "time": time_str,
                "icon": icon,
                "color": color,
                "type": "audit",
                "raw_time": time_str,
            })

        # 2. Recent drawings uploaded / processed
        recent_dwgs = self.drawing_repo.get_recent_drawings(limit=limit) if hasattr(self, 'drawing_repo') else []
        for d in recent_dwgs:
            fname = d.get("file_name", "Drawing")
            cmts = d.get("comments_count", 0)
            dept = d.get("department_name", "General")
            time_str = d.get("uploaded_at", "")

            text = f"Processed '{fname}' • {cmts} comments ({dept})"
            activities.append({
                "text": text,
                "time": time_str,
                "icon": "fa5s.file-pdf",
                "color": "#3E9BFF",
                "type": "drawing",
                "raw_time": time_str,
            })

        # 3. Baseline system readiness event if activities list is small
        activities.append({
            "text": "System initialized • 7 Engineering Departments ready",
            "time": "System Ready",
            "icon": "fa5s.shield-alt",
            "color": "#4ADE80",
            "type": "system",
            "raw_time": "1970-01-01 00:00:00",
        })

        # Sort by raw_time descending
        activities.sort(key=lambda x: str(x.get("raw_time", "")), reverse=True)
        return activities[:limit]

    # ── Comment operations ─────────────────────────────────────────
    #
    # These methods are the ONLY way UI screens should access comment data.
    # Screens must never instantiate CommentRepository themselves.

    def get_comments_for_drawing(self, drawing_id: str) -> List[Dict[str, Any]]:
        """
        Return all normalised comment display dicts for the given drawing.

        Parameters
        ----------
        drawing_id:
            The DrawingModel.id ("DWG-XXXXXXXX"). Use current_drawing_id.

        Returns
        -------
        List of normalised comment dicts (see normalise_comment for keys).
        Returns [] if drawing_id is empty or no comments exist.
        """
        if not drawing_id:
            return []
        raw = self.comment_repo.get_comments_for_drawing(drawing_id)
        return [self.normalise_comment(c) for c in raw]

    def update_comment_status(
        self, comment_id: str, status: str, verified_by_human: bool = True
    ) -> None:
        """
        Persist a status change for a single comment.

        Parameters
        ----------
        comment_id : str
            The CommentModel primary key ("CMT-XXXXXXXX").
        status : str
            One of: "Pending", "Approved", "Rejected", "Flagged".
        verified_by_human : bool
            True when the change comes from a human reviewer action.

        INTEGRATION NOTE:
        Status vocabulary is fixed. Do not pass arbitrary strings.
        Permitted values: "Pending", "Approved", "Rejected", "Flagged".
        """
        user_id = self.current_user.id if self.current_user else "anonymous"
        
        if status == "Approved":
            self.verification_service.approve_comment(comment_id, user_id)
        elif status == "Rejected":
            self.verification_service.reject_comment(comment_id, user_id, "Rejected via UI")
        elif status == "Flagged":
            self.verification_service.flag_comment(comment_id, user_id, "Flagged via UI")
        else:
            # Fallback for Pending or other statuses
            self.comment_repo.update_comment_status(comment_id, status, verified_by_human)

    def get_audit_trail(self, comment_id: str) -> List[Any]:
        """Return the audit history for a given comment."""
        return self.verification_service.get_audit_history(comment_id)

    def update_comment_text(self, comment_id: str, new_text: str) -> None:
        """
        Persist a corrected OCR text for a single comment.

        Called from the review screen (edit/save action) and the OCR
        results screen (inline text edit).
        """
        user_id = self.current_user.id if self.current_user else "anonymous"
        if hasattr(self.verification_service, "edit_comment_text"):
            self.verification_service.edit_comment_text(comment_id, new_text, user_id)
        else:
            self.comment_repo.update_comment_text(comment_id, new_text)

    def get_category_counts(
        self, drawing_id: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Return comment counts grouped by category name.

        Parameters
        ----------
        drawing_id:
            If provided, scoped to that drawing.
            If None, aggregates across all drawings (used by analytics).

        Returns
        -------
        Dict[str, int] e.g. {"Dimensional": 42, "Structural": 18}
        """
        return self.comment_repo.get_category_counts(drawing_id)

    def get_department_category_counts(
        self, drawing_id: Optional[str] = None
    ) -> Dict[tuple[str, str], int]:
        """
        Return comment counts grouped by (department_name, category_name) for Pareto charts.
        """
        return self.comment_repo.get_department_category_counts(drawing_id)

    # ── Export operations ──────────────────────────────────────────

    def export_data(self, config: ExportConfigDTO) -> Any:
        """Export comments to Excel/CSV/JSON."""
        return self.export_service.export_drawing_comments(config)

    # ── Data normalisation ─────────────────────────────────────────

    def normalise_comment(self, db_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a raw CommentRepository dict to the normalised display shape
        used by all UI screens.

        This is the single mapping point between the database representation
        and the UI representation of a comment. All field-name differences
        are resolved here — they must NOT be scattered through UI files.

        DB dict keys → display dict keys:
            "raw_text"      → "ocr_text"
            "page_number"   → "page"
            "category_name" → "category"
            "user_id"       → "reviewer"
            "created_at"    → "timestamp"
            "id"            → "id"         (unchanged)
            "drawing_id"    → "drawing_id" (unchanged)
            "confidence"    → "confidence" (unchanged)
            "status"        → "status"     (unchanged)

        BBox conversion:
            DB stores (bbox_x0, bbox_y0, bbox_x1, bbox_y1) as absolute PDF
            point coordinates inside the "bbox" tuple.
            This method returns bbox as normalised (x, y, w, h) in range 0–1
            if page dimensions are available from current_document.
            Otherwise returns the raw (x0, y0, x1, y1) tuple unchanged.

            INTEGRATION WARNING:
            If current_document is None (no PDF loaded this session),
            normalisation cannot be performed. See comment_viewer_screen.py.
        """
        raw_bbox        = db_dict.get("bbox", (0.0, 0.0, 0.0, 0.0))
        normalised_bbox = raw_bbox   # default: pass through unchanged

        doc = self._active_doc
        if doc is not None and len(doc.pages) > 0:
            page_num   = db_dict.get("page_number", 1)
            idx        = max(0, min(page_num - 1, len(doc.pages) - 1))
            page_meta  = doc.pages[idx]
            w_pt, h_pt = page_meta.width_pt, page_meta.height_pt
            if w_pt > 0 and h_pt > 0:
                x0, y0, x1, y1 = raw_bbox
                normalised_bbox = (
                    x0 / w_pt,
                    y0 / h_pt,
                    (x1 - x0) / w_pt,
                    (y1 - y0) / h_pt,
                )

        drawing_no = db_dict.get("drawing_id", "")
        if doc is not None:
            drawing_no = doc.file_name.rsplit(".", 1)[0]

        return {
            "id":          db_dict.get("id", ""),
            "drawing_id":  db_dict.get("drawing_id", ""),
            "drawing_no":  drawing_no,
            "page":        db_dict.get("page_number", 1),
            "ocr_text":    db_dict.get("raw_text", ""),
            "category":    db_dict.get("category_name") or "Uncategorized",
            "department":  db_dict.get("department_name") or "Unassigned",
            "confidence":  db_dict.get("confidence", 0.0),
            "status":      db_dict.get("status", "Pending"),
            "label":       db_dict.get("label", "comment_red"),
            "bbox":        normalised_bbox,
            "reviewer":    db_dict.get("user_id"),
            "timestamp":   db_dict.get("created_at", ""),
            "is_verified": db_dict.get("is_verified_by_human", False),
        }

    # ── Export Operations ──────────────────────────────────────────

    def export_data(self, config: ExportConfigDTO) -> Any:
        """
        Export drawing review comments to Error Tracker Excel, JSON, or CSV.
        Auto-populates drawing and project metadata if omitted.
        """
        if not config.drawing_id and self._current_drawing_id and getattr(config, 'scope', 'drawing') == 'drawing':
            config.drawing_id = self._current_drawing_id


        if not config.drawing_no and self._active_doc:
            config.drawing_no = self._active_doc.file_name.rsplit(".", 1)[0]
            if not config.drawing_title:
                config.drawing_title = getattr(self._active_doc, "title", None) or "Piping & Instrumentation Diagram"

        if not config.designer_name and self._active_session:
            config.designer_name = self._active_session.display_name or self._active_session.username

        return self.export_service.export_drawing_comments(config)

    # ── Internal slots ─────────────────────────────────────────────

    def _on_doc_loaded(self, doc_dto: PDFDocumentDTO, drawing_id: str) -> None:
        self._active_doc         = doc_dto
        self._current_drawing_id = drawing_id
        logger.info(
            f"AppController: '{doc_dto.file_name}' ready. "
            f"drawing_id='{drawing_id}', pages={doc_dto.total_pages}"
        )
        # Emit only the DTO — external consumers (MainWindow, PdfViewerPage)
        # do not need the drawing_id and their signatures are unchanged.
        self.document_loaded_signal.emit(doc_dto)

    def _on_doc_error(self, err_msg: str) -> None:
        logger.error(f"AppController document error: {err_msg}")
        self.processing_error_signal.emit(err_msg)

    def _on_page_rendered(self, rendered_dto: RenderedPageDTO) -> None:
        self.page_rendered_signal.emit(rendered_dto)

    def _on_render_error(self, err_msg: str) -> None:
        logger.error(f"AppController render error: {err_msg}")
        self.processing_error_signal.emit(err_msg)
