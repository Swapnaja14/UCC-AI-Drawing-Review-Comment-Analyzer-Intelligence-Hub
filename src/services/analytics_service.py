from typing import List, Optional, Dict
from sqlalchemy import func, case
from datetime import datetime

from src.infrastructure.storage.repository import DatabaseEngine
from src.infrastructure.storage.models import (
    ProjectModel, DrawingModel, PageModel, CommentModel, CategoryModel, UserModel, EngineeringDepartmentModel
)
from src.infrastructure.logging.logger import get_logger
from src.core.dtos.analytics_dtos import (
    KPISummaryDTO, CategoryDistributionDTO, ConfidenceBucketDTO,
    ReviewerMetricsDTO, TrendDataPointDTO, ProjectAnalyticsDTO
)

logger = get_logger(__name__)

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

class AnalyticsService:
    def __init__(self, db_engine: DatabaseEngine):
        self._db = db_engine

    def get_global_kpis(self) -> KPISummaryDTO:
        with self._db.get_session() as session:
            total_projects = session.query(func.count(ProjectModel.id)).scalar() or 0
            total_drawings = session.query(func.count(DrawingModel.id)).scalar() or 0
            total_pages = session.query(func.count(PageModel.id)).scalar() or 0
            
            # Fast-path single SQL aggregation query
            stats = session.query(
                func.count(CommentModel.id),
                func.sum(case((CommentModel.status == "Approved", 1), else_=0)),
                func.sum(case((CommentModel.status == "Rejected", 1), else_=0)),
                func.sum(case((CommentModel.status == "Pending", 1), else_=0)),
                func.sum(case((CommentModel.status == "Flagged", 1), else_=0)),
                func.avg(CommentModel.confidence),
                func.sum(case((CommentModel.confidence >= 0.85, 1), else_=0)),
                func.sum(case((CommentModel.confidence < 0.60, 1), else_=0)),
                func.sum(case(((CommentModel.status == "Approved") & (CommentModel.is_verified_by_human == True), 1), else_=0))
            ).first()
            
            if stats:
                total_comments = stats[0] or 0
                approved_count = stats[1] or 0
                rejected_count = stats[2] or 0
                pending_count = stats[3] or 0
                flagged_count = stats[4] or 0
                avg_confidence = float(stats[5] or 0.0)
                high_conf = stats[6] or 0
                low_conf = stats[7] or 0
                approved_verified = stats[8] or 0
            else:
                total_comments = approved_count = rejected_count = pending_count = flagged_count = 0
                avg_confidence = 0.0
                high_conf = low_conf = approved_verified = 0

            accuracy_rate = (approved_verified / total_comments * 100.0) if total_comments > 0 else None
            high_confidence_pct = (high_conf / total_comments * 100.0) if total_comments > 0 else 0.0
            low_confidence_pct = (low_conf / total_comments * 100.0) if total_comments > 0 else 0.0
            
            return KPISummaryDTO(
                total_projects=total_projects,
                total_drawings=total_drawings,
                total_comments=total_comments,
                total_pages=total_pages,
                accuracy_rate=accuracy_rate,
                approved_count=approved_count,
                rejected_count=rejected_count,
                pending_count=pending_count,
                flagged_count=flagged_count,
                avg_confidence=avg_confidence,
                high_confidence_pct=high_confidence_pct,
                low_confidence_pct=low_confidence_pct
            )

    def get_category_distribution(
        self,
        drawing_id: Optional[str] = None,
        department_name: Optional[str] = None,
        include_rejected: bool = True,
    ) -> List[CategoryDistributionDTO]:
        with self._db.get_session() as session:
            query = session.query(CommentModel.category_name, func.count(CommentModel.id))
            if not include_rejected:
                query = query.filter(CommentModel.status != "Rejected")
            query = query.group_by(CommentModel.category_name)
            if drawing_id:
                query = query.filter(CommentModel.drawing_id == drawing_id)
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
            
            results = query.all()
            total = sum(count for _, count in results)
            
            distribution = []
            for category_name, count in results:
                cat_name = category_name or 'Uncategorized'
                pct = (count / total * 100.0) if total > 0 else 0.0
                color = CATEGORY_COLORS.get(cat_name, '#9CA3AF')
                distribution.append(CategoryDistributionDTO(
                    category_name=cat_name,
                    count=count,
                    percentage=pct,
                    color_hex=color
                ))
            
            distribution.sort(key=lambda x: x.count, reverse=True)
            return distribution

    def get_confidence_distribution(self, drawing_id: Optional[str] = None) -> List[ConfidenceBucketDTO]:
        with self._db.get_session() as session:
            query = session.query(CommentModel.confidence)
            if drawing_id:
                query = query.filter(CommentModel.drawing_id == drawing_id)
                
            confidences = [r[0] or 0.0 for r in query.all()]
            total = len(confidences)
            
            buckets = [
                {'label': '0.0-0.2', 'count': sum(1 for c in confidences if 0.0 <= c < 0.2)},
                {'label': '0.2-0.4', 'count': sum(1 for c in confidences if 0.2 <= c < 0.4)},
                {'label': '0.4-0.6', 'count': sum(1 for c in confidences if 0.4 <= c < 0.6)},
                {'label': '0.6-0.8', 'count': sum(1 for c in confidences if 0.6 <= c < 0.8)},
                {'label': '0.8-1.0', 'count': sum(1 for c in confidences if 0.8 <= c <= 1.0)},
            ]
            
            return [
                ConfidenceBucketDTO(
                    range_label=b['label'],
                    count=b['count'],
                    percentage=(b['count'] / total * 100.0) if total > 0 else 0.0
                )
                for b in buckets
            ]

    def get_pareto_analysis(
        self,
        drawing_id: Optional[str] = None,
        department_name: Optional[str] = None,
        top_n: int = 10,
        include_rejected: bool = False,
    ) -> List[CategoryDistributionDTO]:
        distribution = self.get_category_distribution(
            drawing_id=drawing_id,
            department_name=department_name,
            include_rejected=include_rejected,
        )
        return distribution[:top_n]

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

    def get_status_trend(self, drawing_id: Optional[str] = None) -> List[TrendDataPointDTO]:
        with self._db.get_session() as session:
            query = session.query(CommentModel.created_at)
            if drawing_id:
                query = query.filter(CommentModel.drawing_id == drawing_id)
                
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
        with self._db.get_session() as session:
            project = session.query(ProjectModel).filter(ProjectModel.id == project_id).first()
            if not project:
                return None
                
            drawings = session.query(DrawingModel).filter(DrawingModel.project_id == project_id).all()
            drawing_ids = [d.id for d in drawings]
            
            if not drawing_ids:
                empty_kpi = KPISummaryDTO(
                    total_projects=1, total_drawings=0, total_comments=0, total_pages=0,
                    accuracy_rate=None, approved_count=0, rejected_count=0, pending_count=0,
                    flagged_count=0, avg_confidence=0.0, high_confidence_pct=0.0, low_confidence_pct=0.0
                )
                return ProjectAnalyticsDTO(
                    project_id=project.id,
                    project_name=getattr(project, 'name', 'Unknown Project'),
                    kpi_summary=empty_kpi,
                    category_distribution=[],
                    confidence_distribution=[],
                    status_trend=[],
                    reviewer_metrics=[]
                )

            total_drawings = len(drawing_ids)
            total_pages = session.query(func.count(PageModel.id)).filter(PageModel.drawing_id.in_(drawing_ids)).scalar() or 0
            
            stats = session.query(
                func.count(CommentModel.id),
                func.sum(case((CommentModel.status == "Approved", 1), else_=0)),
                func.sum(case((CommentModel.status == "Rejected", 1), else_=0)),
                func.sum(case((CommentModel.status == "Pending", 1), else_=0)),
                func.sum(case((CommentModel.status == "Flagged", 1), else_=0)),
                func.avg(CommentModel.confidence),
                func.sum(case((CommentModel.confidence >= 0.85, 1), else_=0)),
                func.sum(case((CommentModel.confidence < 0.60, 1), else_=0)),
                func.sum(case(((CommentModel.status == "Approved") & (CommentModel.is_verified_by_human == True), 1), else_=0))
            ).filter(CommentModel.drawing_id.in_(drawing_ids)).first()

            if stats:
                total_comments = stats[0] or 0
                approved_count = stats[1] or 0
                rejected_count = stats[2] or 0
                pending_count = stats[3] or 0
                flagged_count = stats[4] or 0
                avg_confidence = float(stats[5] or 0.0)
                high_conf = stats[6] or 0
                low_conf = stats[7] or 0
                approved_verified = stats[8] or 0
            else:
                total_comments = approved_count = rejected_count = pending_count = flagged_count = 0
                avg_confidence = 0.0
                high_conf = low_conf = approved_verified = 0

            accuracy_rate = (approved_verified / total_comments * 100.0) if total_comments > 0 else None
            high_confidence_pct = (high_conf / total_comments * 100.0) if total_comments > 0 else 0.0
            low_confidence_pct = (low_conf / total_comments * 100.0) if total_comments > 0 else 0.0

            kpi_summary = KPISummaryDTO(
                total_projects=1,
                total_drawings=total_drawings,
                total_comments=total_comments,
                total_pages=total_pages,
                accuracy_rate=accuracy_rate,
                approved_count=approved_count,
                rejected_count=rejected_count,
                pending_count=pending_count,
                flagged_count=flagged_count,
                avg_confidence=avg_confidence,
                high_confidence_pct=high_confidence_pct,
                low_confidence_pct=low_confidence_pct
            )

            # Category distribution query
            cat_rows = session.query(
                CommentModel.category_name, func.count(CommentModel.id)
            ).filter(CommentModel.drawing_id.in_(drawing_ids)).group_by(CommentModel.category_name).all()

            category_distribution = []
            for cat_name, count in cat_rows:
                c_name = cat_name or 'Uncategorized'
                pct = (count / total_comments * 100.0) if total_comments > 0 else 0.0
                color = CATEGORY_COLORS.get(c_name, '#9CA3AF')
                category_distribution.append(CategoryDistributionDTO(
                    category_name=c_name, count=count, percentage=pct, color_hex=color
                ))
            category_distribution.sort(key=lambda x: x.count, reverse=True)

            # Confidence distribution query
            conf_rows = session.query(
                func.sum(case((CommentModel.confidence < 0.2, 1), else_=0)),
                func.sum(case(((CommentModel.confidence >= 0.2) & (CommentModel.confidence < 0.4), 1), else_=0)),
                func.sum(case(((CommentModel.confidence >= 0.4) & (CommentModel.confidence < 0.6), 1), else_=0)),
                func.sum(case(((CommentModel.confidence >= 0.6) & (CommentModel.confidence < 0.8), 1), else_=0)),
                func.sum(case((CommentModel.confidence >= 0.8, 1), else_=0)),
            ).filter(CommentModel.drawing_id.in_(drawing_ids)).first()

            buckets_counts = conf_rows if conf_rows else (0, 0, 0, 0, 0)
            labels = ['0.0-0.2', '0.2-0.4', '0.4-0.6', '0.6-0.8', '0.8-1.0']
            confidence_distribution = [
                ConfidenceBucketDTO(
                    range_label=labels[i],
                    count=cnt or 0,
                    percentage=((cnt or 0) / total_comments * 100.0) if total_comments > 0 else 0.0
                )
                for i, cnt in enumerate(buckets_counts)
            ]

            status_trend = self.get_status_trend()
            reviewer_metrics = self.get_reviewer_metrics()

            return ProjectAnalyticsDTO(
                project_id=project.id,
                project_name=getattr(project, 'name', 'Unknown Project'),
                kpi_summary=kpi_summary,
                category_distribution=category_distribution,
                confidence_distribution=confidence_distribution,
                status_trend=status_trend,
                reviewer_metrics=reviewer_metrics
            )
