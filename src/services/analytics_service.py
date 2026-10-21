from typing import Any, List, Optional, Dict, Tuple
from sqlalchemy import func, case
from datetime import datetime

from src.infrastructure.storage.repository import DatabaseEngine
from src.infrastructure.storage.models import (
    ProjectModel, DrawingModel, PageModel, CommentModel, CategoryModel, UserModel, EngineeringDepartmentModel,
    OCR_FAILED_ENGINE,
)
from src.infrastructure.logging.logger import get_logger
from src.core.dtos.analytics_dtos import (
    KPISummaryDTO, CategoryDistributionDTO, ConfidenceBucketDTO,
    ReviewerMetricsDTO, TrendDataPointDTO, ProjectAnalyticsDTO
)

logger = get_logger(__name__)

#: Statuses that mean a human took a decision on the comment.
REVIEWED_STATUSES = ("APPROVED", "REJECTED", "FLAGGED")

#: Buckets always drawn last in a Pareto chart: they are leftovers rather than
#: findings, so putting them first would make the cumulative line meaningless.
PARETO_TAIL_BUCKETS = ("uncategorized", "other")

#: Label for the bucket that absorbs everything below ``top_n`` when a Pareto is
#: asked to group its tail.
OTHER_BUCKET = "Other"

#: Neutral colour for a grouped tail when there is no Uncategorized bucket to
#: inherit one from.
NEUTRAL_COLOR = '#9CA3AF'

CATEGORY_COLORS = {
    'Technical': '#EF4444',
    'Drafting': '#8B5CF6',
    'Dimension': '#3B82F6',
    'Cosmetic': '#EC4899',
    'Standards': '#F59E0B',
    'Coordination': '#10B981',
    'Documentation': '#6B7280',
    'Revision': '#F97316',
    'Calculation': '#6366F1',
    'Feasibility': '#14B8A6',
    'Material': '#06B6D4',
    'Notes': '#84CC16',
    'BOM': '#A855F7',
    # Backwards compatibility
    'Piping/Process': '#3B82F6',
    'Electrical/Instrumentation': '#F59E0B',
    'Structural/Civil': '#10B981',
    'Safety/HSE': '#EF4444',
    'Dimensional/Tolerancing': '#8B5CF6',
    'General/Administrative': '#6B7280',
    'Uncategorized': '#9CA3AF'
}


def get_confidence_thresholds() -> Tuple[float, float]:
    """
    Return (high, low) confidence band edges from application config.

    ``high`` is the auto-approve threshold — the score at which the pipeline
    itself would approve a comment without a human — so the "high confidence"
    band means something operationally rather than being an arbitrary 0.85.
    """
    high, low = 0.80, 0.60
    try:
        from src.config import get_config
        ai_cfg = get_config().ai
        high = float(getattr(ai_cfg, "auto_approve_threshold", high))
        low = float(getattr(ai_cfg, "low_confidence_threshold", low))
    except Exception as exc:
        logger.warning(f"Could not read confidence thresholds from config, using defaults: {exc}")
    return high, low


def _status_clean():
    """Normalised comment status so counts stay exhaustive across casing/whitespace."""
    return func.upper(func.trim(func.coalesce(CommentModel.status, "PENDING")))


def _category_clean(column=None):
    """NULL, '' and whitespace-only categories collapse to a single 'Uncategorized'."""
    return func.coalesce(func.nullif(func.trim(column if column is not None else CommentModel.category_name), ''), 'Uncategorized')


def _pareto_sort_key(item) -> tuple:
    """Count descending, then name ascending, with leftover buckets pushed last."""
    name = (item.category_name or '').strip()
    return (1 if name.lower() in PARETO_TAIL_BUCKETS else 0, -item.count, name)

def _apply_comment_filters(
    query,
    session,
    project_id: Optional[str] = None,
    drawing_id: Optional[str] = None,
    department_name: Optional[str] = None,
    category_name: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    drawing_ids: Optional[List[str]] = None,
):
    if drawing_id:
        query = query.filter(CommentModel.drawing_id == drawing_id)
    elif drawing_ids is not None:
        if drawing_ids:
            query = query.filter(CommentModel.drawing_id.in_(drawing_ids))
        else:
            query = query.filter(False)
    elif project_id:
        dwg_subquery = session.query(DrawingModel.id).filter(DrawingModel.project_id == project_id)
        query = query.filter(CommentModel.drawing_id.in_(dwg_subquery))
    
    if department_name:
        if department_name == "Unassigned":
            query = query.outerjoin(
                EngineeringDepartmentModel,
                CommentModel.department_id == EngineeringDepartmentModel.id
            ).filter(EngineeringDepartmentModel.id.is_(None))
        else:
            query = query.join(
                EngineeringDepartmentModel,
                CommentModel.department_id == EngineeringDepartmentModel.id
            ).filter(EngineeringDepartmentModel.name == department_name)

    if category_name and category_name != "All Categories":
        if category_name == "Uncategorized":
            query = query.filter(
                (CommentModel.category_name == "Uncategorized") |
                (CommentModel.category_name.is_(None)) |
                (CommentModel.category_name == "")
            )
        else:
            query = query.filter(CommentModel.category_name == category_name)

    from datetime import date as date_type, time as time_type
    if date_from:
        if isinstance(date_from, date_type) and not isinstance(date_from, datetime):
            date_from_start = datetime.combine(date_from, time_type.min)
        else:
            date_from_start = date_from
        query = query.filter(CommentModel.created_at >= date_from_start)
    if date_to:
        if isinstance(date_to, datetime):
            if date_to.hour == 0 and date_to.minute == 0 and date_to.second == 0:
                date_to_end = date_to.replace(hour=23, minute=59, second=59, microsecond=999999)
            else:
                date_to_end = date_to
        elif isinstance(date_to, date_type):
            date_to_end = datetime.combine(date_to, time_type(23, 59, 59, 999999))
        else:
            date_to_end = date_to
        query = query.filter(CommentModel.created_at <= date_to_end)

    return query


class AnalyticsService:
    def __init__(self, db_engine: DatabaseEngine):
        self._db = db_engine

    def get_global_kpis(
        self,
        project_id: Optional[str] = None,
        drawing_id: Optional[str] = None,
        department_name: Optional[str] = None,
        category_name: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        drawing_ids: Optional[List[str]] = None,
        include_rejected: bool = True,
    ) -> KPISummaryDTO:
        """
        Aggregate review metrics for one filtered comment population.

        ``include_rejected=False`` drops Rejected rows from every count and rate
        returned here; the flag is echoed on the DTO so callers can state the
        population they are showing.

        ``department_name`` always means the department recorded on the comment
        (``comments.department_id``), never the one recorded on the drawing, and
        ``"Unassigned"`` selects comments with no department. The project,
        drawing and page counts follow the same rule: they count only what
        carries a comment in this population, so the KPI cards, the charts and
        the drawing dropdown cannot disagree about what a department filter
        means.
        """
        high_threshold, low_threshold = get_confidence_thresholds()

        with self._db.get_session() as session:
            # A comment's department is recorded on the comment, not on the
            # drawing, so with a department filter active a project, drawing or
            # page only counts when it actually carries a comment for that
            # department. Every other filter keeps its drawing-level scope.
            dept_drawing_ids = None
            if department_name:
                dept_query = session.query(CommentModel.drawing_id).distinct()
                dept_query = _apply_comment_filters(
                    dept_query, session, department_name=department_name
                )
                dept_drawing_ids = [row[0] for row in dept_query.all() if row[0]]

            p_query = session.query(func.count(ProjectModel.id))
            if project_id:
                p_query = p_query.filter(ProjectModel.id == project_id)
            if dept_drawing_ids is not None:
                p_query = p_query.filter(
                    ProjectModel.id.in_(
                        session.query(DrawingModel.project_id)
                        .filter(DrawingModel.id.in_(dept_drawing_ids))
                    ) if dept_drawing_ids else False
                )
            total_projects = p_query.scalar() or 0

            d_query = session.query(func.count(DrawingModel.id))
            if drawing_id:
                d_query = d_query.filter(DrawingModel.id == drawing_id)
            elif drawing_ids is not None:
                d_query = d_query.filter(DrawingModel.id.in_(drawing_ids)) if drawing_ids else d_query.filter(False)
            elif project_id:
                d_query = d_query.filter(DrawingModel.project_id == project_id)
            if dept_drawing_ids is not None:
                d_query = d_query.filter(
                    DrawingModel.id.in_(dept_drawing_ids) if dept_drawing_ids else False
                )
            total_drawings = d_query.scalar() or 0

            pg_query = session.query(func.count(PageModel.id))
            if drawing_id:
                pg_query = pg_query.filter(PageModel.drawing_id == drawing_id)
            elif drawing_ids is not None:
                pg_query = pg_query.filter(PageModel.drawing_id.in_(drawing_ids)) if drawing_ids else pg_query.filter(False)
            elif project_id:
                dwg_sub = session.query(DrawingModel.id).filter(DrawingModel.project_id == project_id)
                pg_query = pg_query.filter(PageModel.drawing_id.in_(dwg_sub))
            if dept_drawing_ids is not None:
                pg_query = pg_query.filter(
                    PageModel.drawing_id.in_(dept_drawing_ids) if dept_drawing_ids else False
                )
            total_pages = pg_query.scalar() or 0
            
            # Single SQL aggregation query with comment filters
            # Status normalization ensures Total == Pending + Approved + Rejected + Flagged unconditionally
            status_clean = _status_clean()
            reviewed_by_human = (
                status_clean.in_(list(REVIEWED_STATUSES))
                & (CommentModel.is_verified_by_human == True)
            )
            ai_scored = (
                (func.lower(func.coalesce(CommentModel.classification_method, '')) == 'ai_model')
                & (CommentModel.fallback_used == False)
            )
            initial_clean = func.lower(func.trim(func.coalesce(CommentModel.initial_category, '')))
            category_clean = func.lower(_category_clean())

            stats_query = session.query(
                func.count(CommentModel.id),
                func.sum(case((status_clean == "APPROVED", 1), else_=0)),
                func.sum(case((status_clean == "REJECTED", 1), else_=0)),
                func.sum(case((status_clean.notin_(list(REVIEWED_STATUSES)), 1), else_=0)),
                func.sum(case((status_clean == "FLAGGED", 1), else_=0)),
                func.avg(CommentModel.confidence),
                func.sum(case((CommentModel.confidence >= high_threshold, 1), else_=0)),
                func.sum(case((CommentModel.confidence < low_threshold, 1), else_=0)),
                func.sum(case(((status_clean == "APPROVED") & (CommentModel.is_verified_by_human == True), 1), else_=0)),
                func.sum(case(((status_clean == "APPROVED") & (CommentModel.is_verified_by_human == False), 1), else_=0)),
                func.sum(case((
                    (status_clean == "FLAGGED")
                    & (func.coalesce(CommentModel.ocr_engine, '') == OCR_FAILED_ENGINE), 1
                ), else_=0)),
                func.sum(case((reviewed_by_human, 1), else_=0)),
                func.avg(case((ai_scored, CommentModel.classification_confidence), else_=None)),
                func.sum(case((ai_scored, 1), else_=0)),
                func.sum(case((reviewed_by_human & (initial_clean != ''), 1), else_=0)),
                func.sum(case((
                    reviewed_by_human & (initial_clean != '') & (category_clean == initial_clean), 1
                ), else_=0)),
            )
            stats_query = _apply_comment_filters(
                stats_query, session, project_id, drawing_id, department_name, category_name, date_from, date_to, drawing_ids=drawing_ids
            )
            if not include_rejected:
                stats_query = stats_query.filter(status_clean != "REJECTED")
            stats = stats_query.first()

            if stats:
                total_comments = int(stats[0] or 0)
                approved_count = int(stats[1] or 0)
                rejected_count = int(stats[2] or 0)
                pending_count = int(stats[3] or 0)
                flagged_count = int(stats[4] or 0)
                avg_confidence = float(stats[5] or 0.0)
                high_conf = int(stats[6] or 0)
                low_conf = int(stats[7] or 0)
                approved_verified = int(stats[8] or 0)
                auto_approved_count = int(stats[9] or 0)
                flagged_ocr_failed = int(stats[10] or 0)
                human_reviewed_count = int(stats[11] or 0)
                ai_confidence_avg = float(stats[12]) if stats[12] is not None else None
                ai_confidence_n = int(stats[13] or 0)
                agreement_n = int(stats[14] or 0)
                agreement_hits = int(stats[15] or 0)
            else:
                total_comments = approved_count = rejected_count = pending_count = flagged_count = 0
                avg_confidence = 0.0
                high_conf = low_conf = approved_verified = auto_approved_count = 0
                flagged_ocr_failed = human_reviewed_count = ai_confidence_n = 0
                agreement_n = agreement_hits = 0
                ai_confidence_avg = None

            flagged_manual_count = max(0, flagged_count - flagged_ocr_failed)

            human_verified_approval_rate = (
                (approved_verified / total_comments * 100.0) if total_comments > 0 else None
            )
            approval_rate = (approved_count / total_comments * 100.0) if total_comments > 0 else 0.0
            reviewed_count = approved_count + rejected_count
            review_progress = (reviewed_count / total_comments * 100.0) if total_comments > 0 else 0.0
            high_confidence_pct = (high_conf / total_comments * 100.0) if total_comments > 0 else 0.0
            low_confidence_pct = (low_conf / total_comments * 100.0) if total_comments > 0 else 0.0
            auto_approval_rate = (auto_approved_count / total_comments * 100.0) if total_comments > 0 else 0.0
            category_agreement_pct = (
                (agreement_hits / agreement_n * 100.0) if agreement_n > 0 else None
            )

            return KPISummaryDTO(
                total_projects=total_projects,
                total_drawings=total_drawings,
                total_comments=total_comments,
                total_pages=total_pages,
                approved_count=approved_count,
                rejected_count=rejected_count,
                pending_count=pending_count,
                flagged_count=flagged_count,
                avg_confidence=avg_confidence,
                high_confidence_pct=high_confidence_pct,
                low_confidence_pct=low_confidence_pct,
                approval_rate=approval_rate,
                review_progress=review_progress,
                reviewed_count=reviewed_count,
                auto_approved_count=auto_approved_count,
                auto_approval_rate=auto_approval_rate,
                human_verified_approval_rate=human_verified_approval_rate,
                human_reviewed_count=human_reviewed_count,
                flagged_manual_count=flagged_manual_count,
                flagged_ocr_failed_count=flagged_ocr_failed,
                ai_confidence_avg=ai_confidence_avg,
                ai_confidence_sample_size=ai_confidence_n,
                category_agreement_pct=category_agreement_pct,
                category_agreement_sample_size=agreement_n,
                high_confidence_threshold=high_threshold,
                low_confidence_threshold=low_threshold,
                include_rejected=include_rejected,
            )

    def get_department_options(self) -> Dict[str, Any]:
        """
        Departments the Analytics filter can offer.

        ``has_unassigned`` is True when at least one comment carries no
        department, so the UI offers "Unassigned" only when selecting it would
        actually return rows.
        """
        with self._db.get_session() as session:
            names = [
                row[0]
                for row in session.query(EngineeringDepartmentModel.name)
                .filter(EngineeringDepartmentModel.is_active.is_(True))
                .order_by(EngineeringDepartmentModel.name)
                .all()
            ]
            unassigned = session.query(func.count(CommentModel.id)).outerjoin(
                EngineeringDepartmentModel,
                CommentModel.department_id == EngineeringDepartmentModel.id,
            ).filter(EngineeringDepartmentModel.id.is_(None)).scalar() or 0

            return {"departments": [n for n in names if n], "has_unassigned": bool(unassigned)}

    def get_drawing_options(
        self,
        project_id: Optional[str] = None,
        department_name: Optional[str] = None,
        drawing_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lightweight drawing list for filter dropdowns: id, file name and the
        number of comments in scope. No comment rows are loaded.

        ``department_name`` is a name, not a ``DEPT-xxxxxxxx`` id, and is matched
        against the comment-level department used everywhere else in analytics,
        so the dropdown lists exactly the drawings the counts describe and the
        comment count next to each name is the count for that department.
        """
        with self._db.get_session() as session:
            count_query = session.query(
                CommentModel.drawing_id.label("drawing_id"),
                func.count(CommentModel.id).label("comment_count"),
            )
            count_query = _apply_comment_filters(
                count_query, session, project_id=project_id, department_name=department_name
            )
            comment_counts = count_query.group_by(CommentModel.drawing_id).subquery()

            query = session.query(
                DrawingModel.id,
                DrawingModel.file_name,
                func.coalesce(comment_counts.c.comment_count, 0),
            )
            # With a department selected, a drawing that carries no comment for
            # that department is not part of the population and must not appear.
            join_kind = query.join if department_name else query.outerjoin
            query = join_kind(comment_counts, comment_counts.c.drawing_id == DrawingModel.id)

            if project_id:
                query = query.filter(DrawingModel.project_id == project_id)
            if drawing_ids is not None:
                query = query.filter(DrawingModel.id.in_(drawing_ids)) if drawing_ids else query.filter(False)

            rows = query.order_by(DrawingModel.file_name).all()
            return [
                {"id": r[0], "file_name": r[1], "comments_count": int(r[2] or 0)}
                for r in rows
            ]

    def get_category_distribution(
        self,
        project_id: Optional[str] = None,
        drawing_id: Optional[str] = None,
        department_name: Optional[str] = None,
        category_name: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        include_rejected: bool = True,
        drawing_ids: Optional[List[str]] = None,
    ) -> List[CategoryDistributionDTO]:
        with self._db.get_session() as session:
            status_clean = func.upper(func.trim(func.coalesce(CommentModel.status, "PENDING")))
            query = session.query(CommentModel.category_name, func.count(CommentModel.id))
            if not include_rejected:
                query = query.filter(status_clean != "REJECTED")
            query = _apply_comment_filters(
                query, session, project_id, drawing_id, department_name, category_name, date_from, date_to, drawing_ids=drawing_ids
            )
            query = query.group_by(CommentModel.category_name)
            
            results = query.all()
            total = sum(count for _, count in results)
            
            distribution = []
            for cat_n, count in results:
                c_name = cat_n or 'Uncategorized'
                pct = (count / total * 100.0) if total > 0 else 0.0
                color = CATEGORY_COLORS.get(c_name, '#9CA3AF')
                distribution.append(CategoryDistributionDTO(
                    category_name=c_name,
                    count=count,
                    percentage=pct,
                    color_hex=color
                ))
            
            distribution.sort(key=lambda x: x.count, reverse=True)
            return distribution

    def get_confidence_distribution(
        self,
        project_id: Optional[str] = None,
        drawing_id: Optional[str] = None,
        department_name: Optional[str] = None,
        category_name: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        drawing_ids: Optional[List[str]] = None,
    ) -> List[ConfidenceBucketDTO]:
        with self._db.get_session() as session:
            query = session.query(CommentModel.confidence)
            query = _apply_comment_filters(
                query, session, project_id, drawing_id, department_name, category_name, date_from, date_to, drawing_ids=drawing_ids
            )
            confidences = [r[0] or 0.0 for r in query.all()]
            total = len(confidences)
            
            buckets = [
                {'label': '0.0-0.2', 'count': sum(1 for c in confidences if c < 0.2)},
                {'label': '0.2-0.4', 'count': sum(1 for c in confidences if 0.2 <= c < 0.4)},
                {'label': '0.4-0.6', 'count': sum(1 for c in confidences if 0.4 <= c < 0.6)},
                {'label': '0.6-0.8', 'count': sum(1 for c in confidences if 0.6 <= c < 0.8)},
                {'label': '0.8-1.0', 'count': sum(1 for c in confidences if c >= 0.8)},
            ]
            
            return [
                ConfidenceBucketDTO(
                    range_label=b['label'],
                    count=b['count'],
                    percentage=(b['count'] / total * 100.0) if total > 0 else 0.0
                )
                for b in buckets
            ]

    def get_status_distribution(
        self,
        project_id: Optional[str] = None,
        drawing_id: Optional[str] = None,
        department_name: Optional[str] = None,
        category_name: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        drawing_ids: Optional[List[str]] = None,
    ) -> Dict[str, int]:
        """Return status counts (Pending, Approved, Rejected, Flagged) for the exact filtered population."""
        kpi = self.get_global_kpis(
            project_id=project_id,
            drawing_id=drawing_id,
            department_name=department_name,
            category_name=category_name,
            date_from=date_from,
            date_to=date_to,
            drawing_ids=drawing_ids,
        )
        return {
            "Pending": kpi.pending_count,
            "Approved": kpi.approved_count,
            "Rejected": kpi.rejected_count,
            "Flagged": kpi.flagged_count,
        }

    def get_pareto_analysis(
        self,
        project_id: Optional[str] = None,
        drawing_id: Optional[str] = None,
        department_name: Optional[str] = None,
        category_name: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        top_n: int = 20,
        include_rejected: bool = True,
        drawing_ids: Optional[List[str]] = None,
        group_tail: bool = False,
    ) -> List[CategoryDistributionDTO]:
        """
        Pareto view of the category distribution.

        ``cumulative_percentage`` is always measured against the FULL population,
        never against the ``top_n`` slice that is returned, so the cumulative line
        reaches 100% only when every category is on screen. Ordering is stable —
        count descending, then name ascending — with Uncategorized and a grouped
        Other drawn last.

        ``group_tail=True`` folds every category below ``top_n`` into one "Other"
        bucket so the returned counts still add up to the population total.
        """
        distribution = self.get_category_distribution(
            project_id=project_id,
            drawing_id=drawing_id,
            department_name=department_name,
            category_name=category_name,
            date_from=date_from,
            date_to=date_to,
            include_rejected=include_rejected,
            drawing_ids=drawing_ids,
        )
        total = sum(d.count for d in distribution)
        distribution = sorted(distribution, key=_pareto_sort_key)

        if group_tail and top_n >= 0 and len(distribution) > top_n:
            head, tail = distribution[:top_n], distribution[top_n:]
            tail_count = sum(d.count for d in tail)
            other_color = next(
                (d.color_hex for d in tail
                 if (d.category_name or '').strip().lower() == 'uncategorized'),
                NEUTRAL_COLOR,
            )
            distribution = head + [CategoryDistributionDTO(
                category_name=OTHER_BUCKET,
                count=tail_count,
                percentage=(tail_count / total * 100.0) if total > 0 else 0.0,
                color_hex=other_color,
            )]
        elif top_n >= 0:
            distribution = distribution[:top_n]

        running = 0
        for item in distribution:
            running += item.count
            item.cumulative_count = running
            item.cumulative_percentage = (running / total * 100.0) if total > 0 else None

        return distribution

    def get_reviewer_metrics(self) -> List[ReviewerMetricsDTO]:
        with self._db.get_session() as session:
            rows = session.query(
                CommentModel.user_id,
                func.count(CommentModel.id),
                func.sum(case((CommentModel.status == "Approved", 1), else_=0)),
                func.sum(case((CommentModel.status == "Rejected", 1), else_=0)),
                func.sum(case((CommentModel.status == "Flagged", 1), else_=0)),
            ).filter(
                CommentModel.is_verified_by_human == True,
                CommentModel.user_id != None
            ).group_by(CommentModel.user_id).all()

            if not rows:
                return []

            user_ids = {r[0] for r in rows if r[0]}
            users = session.query(UserModel).filter(UserModel.id.in_(user_ids)).all() if user_ids else []
            user_map = {u.id: getattr(u, 'display_name', 'Unknown User') for u in users}

            results = []
            for uid, reviewed, app_c, rej_c, flg_c in rows:
                if not uid:
                    continue
                results.append(ReviewerMetricsDTO(
                    reviewer_id=uid,
                    reviewer_name=user_map.get(uid, 'Unknown User'),
                    comments_reviewed=reviewed or 0,
                    approved=app_c or 0,
                    rejected=rej_c or 0,
                    flagged=flg_c or 0
                ))

            return results

    def get_status_trend(
        self,
        project_id: Optional[str] = None,
        drawing_id: Optional[str] = None,
        department_name: Optional[str] = None,
        category_name: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        drawing_ids: Optional[List[str]] = None,
    ) -> List[TrendDataPointDTO]:
        with self._db.get_session() as session:
            query = session.query(CommentModel.created_at)
            query = _apply_comment_filters(
                query, session, project_id, drawing_id, department_name, category_name, date_from, date_to, drawing_ids=drawing_ids
            )
            dates = [r[0] for r in query.all() if r[0]]
            
            trends = {}
            for dt in dates:
                if isinstance(dt, datetime):
                    date_str = dt.strftime('%Y-%m-%d')
                elif isinstance(dt, str):
                    date_str = dt.split('T')[0]
                else:
                    date_str = str(dt)
                    
                trends[date_str] = trends.get(date_str, 0) + 1
                
            return [
                TrendDataPointDTO(period_label=k, count=v)
                for k, v in sorted(trends.items())
            ]

    def get_project_analytics(self, project_id: str) -> Optional[ProjectAnalyticsDTO]:
        """
        Project-scoped analytics, built entirely from the same filtered queries
        the global dashboard uses so the two can never disagree.
        """
        with self._db.get_session() as session:
            project = session.query(ProjectModel).filter(ProjectModel.id == project_id).first()
            if not project:
                return None
            project_name = getattr(project, 'name', 'Unknown Project')

        return ProjectAnalyticsDTO(
            project_id=project_id,
            project_name=project_name,
            kpi_summary=self.get_global_kpis(project_id=project_id),
            category_distribution=self.get_category_distribution(project_id=project_id),
            confidence_distribution=self.get_confidence_distribution(project_id=project_id),
            status_trend=self.get_status_trend(project_id=project_id),
            reviewer_metrics=self.get_reviewer_metrics(),
        )
