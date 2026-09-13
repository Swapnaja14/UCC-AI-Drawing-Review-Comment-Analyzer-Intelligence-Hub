from typing import List, Optional, Dict
from sqlalchemy import func
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
            
            comments = session.query(CommentModel).all()
            total_comments = len(comments)
            
            approved_count = sum(1 for c in comments if c.status == "Approved")
            rejected_count = sum(1 for c in comments if c.status == "Rejected")
            pending_count = sum(1 for c in comments if c.status == "Pending")
            flagged_count = sum(1 for c in comments if c.status == "Flagged")
            
            approved_verified = sum(1 for c in comments if c.status == "Approved" and c.is_verified_by_human)
            accuracy_rate = (approved_verified / total_comments * 100.0) if total_comments > 0 else None
            
            avg_confidence = sum((c.confidence or 0.0) for c in comments) / total_comments if total_comments > 0 else 0.0
            
            high_conf = sum(1 for c in comments if (c.confidence or 0.0) >= 0.85)
            low_conf = sum(1 for c in comments if (c.confidence or 0.0) < 0.60)
            
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
    ) -> List[CategoryDistributionDTO]:
        with self._db.get_session() as session:
            query = session.query(CommentModel.category_name, func.count(CommentModel.id)).group_by(CommentModel.category_name)
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
    ) -> List[CategoryDistributionDTO]:
        distribution = self.get_category_distribution(drawing_id=drawing_id, department_name=department_name)
        return distribution[:top_n]

    def get_reviewer_metrics(self) -> List[ReviewerMetricsDTO]:
        with self._db.get_session() as session:
            comments = session.query(CommentModel).filter(CommentModel.is_verified_by_human == True, CommentModel.user_id != None).all()
            user_ids = {c.user_id for c in comments}
            
            users = session.query(UserModel).filter(UserModel.id.in_(user_ids)).all()
            user_map = {u.id: getattr(u, 'display_name', 'Unknown User') for u in users}
            
            metrics_map = {}
            for c in comments:
                if c.user_id not in metrics_map:
                    metrics_map[c.user_id] = {'reviewed': 0, 'approved': 0, 'rejected': 0, 'flagged': 0}
                
                metrics_map[c.user_id]['reviewed'] += 1
                if c.status == 'Approved':
                    metrics_map[c.user_id]['approved'] += 1
                elif c.status == 'Rejected':
                    metrics_map[c.user_id]['rejected'] += 1
                elif c.status == 'Flagged':
                    metrics_map[c.user_id]['flagged'] += 1
            
            results = []
            for uid, m in metrics_map.items():
                results.append(ReviewerMetricsDTO(
                    reviewer_id=uid,
                    reviewer_name=user_map.get(uid, 'Unknown User'),
                    comments_reviewed=m['reviewed'],
                    approved=m['approved'],
                    rejected=m['rejected'],
                    flagged=m['flagged']
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
            
            comments = session.query(CommentModel).filter(CommentModel.drawing_id.in_(drawing_ids)).all() if drawing_ids else []
            pages = session.query(PageModel).filter(PageModel.drawing_id.in_(drawing_ids)).all() if drawing_ids else []
            
            total_drawings = len(drawings)
            total_comments = len(comments)
            total_pages = len(pages)
            
            approved_count = sum(1 for c in comments if c.status == "Approved")
            rejected_count = sum(1 for c in comments if c.status == "Rejected")
            pending_count = sum(1 for c in comments if c.status == "Pending")
            flagged_count = sum(1 for c in comments if c.status == "Flagged")
            
            approved_verified = sum(1 for c in comments if c.status == "Approved" and c.is_verified_by_human)
            accuracy_rate = (approved_verified / total_comments * 100.0) if total_comments > 0 else None
            
            avg_confidence = sum((c.confidence or 0.0) for c in comments) / total_comments if total_comments > 0 else 0.0
            
            high_conf = sum(1 for c in comments if (c.confidence or 0.0) >= 0.85)
            low_conf = sum(1 for c in comments if (c.confidence or 0.0) < 0.60)
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
            
            cat_counts = {}
            for c in comments:
                cat = c.category_name or 'Uncategorized'
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
            
            category_distribution = []
            for cat, count in cat_counts.items():
                pct = (count / total_comments * 100.0) if total_comments > 0 else 0.0
                color = CATEGORY_COLORS.get(cat, '#9CA3AF')
                category_distribution.append(CategoryDistributionDTO(
                    category_name=cat, count=count, percentage=pct, color_hex=color
                ))
            category_distribution.sort(key=lambda x: x.count, reverse=True)
            
            buckets = [
                {'label': '0.0-0.2', 'count': sum(1 for c in comments if 0.0 <= (c.confidence or 0.0) < 0.2)},
                {'label': '0.2-0.4', 'count': sum(1 for c in comments if 0.2 <= (c.confidence or 0.0) < 0.4)},
                {'label': '0.4-0.6', 'count': sum(1 for c in comments if 0.4 <= (c.confidence or 0.0) < 0.6)},
                {'label': '0.6-0.8', 'count': sum(1 for c in comments if 0.6 <= (c.confidence or 0.0) < 0.8)},
                {'label': '0.8-1.0', 'count': sum(1 for c in comments if 0.8 <= (c.confidence or 0.0) <= 1.0)},
            ]
            confidence_distribution = [
                ConfidenceBucketDTO(
                    range_label=b['label'],
                    count=b['count'],
                    percentage=(b['count'] / total_comments * 100.0) if total_comments > 0 else 0.0
                ) for b in buckets
            ]
            
            trends = {}
            for c in comments:
                if c.created_at:
                    if isinstance(c.created_at, datetime):
                        date_str = c.created_at.strftime('%Y-%m-%d')
                    else:
                        date_str = str(c.created_at).split('T')[0]
                    trends[date_str] = trends.get(date_str, 0) + 1
            status_trend = [TrendDataPointDTO(period_label=k, count=v) for k, v in sorted(trends.items())]
            
            reviewer_metrics = []
            user_ids = {c.user_id for c in comments if c.is_verified_by_human and c.user_id}
            if user_ids:
                users = session.query(UserModel).filter(UserModel.id.in_(user_ids)).all()
                user_map = {u.id: getattr(u, 'display_name', 'Unknown User') for u in users}
                
                metrics_map = {}
                for c in comments:
                    if c.is_verified_by_human and c.user_id:
                        if c.user_id not in metrics_map:
                            metrics_map[c.user_id] = {'reviewed': 0, 'approved': 0, 'rejected': 0, 'flagged': 0}
                        
                        metrics_map[c.user_id]['reviewed'] += 1
                        if c.status == 'Approved':
                            metrics_map[c.user_id]['approved'] += 1
                        elif c.status == 'Rejected':
                            metrics_map[c.user_id]['rejected'] += 1
                        elif c.status == 'Flagged':
                            metrics_map[c.user_id]['flagged'] += 1
                
                for uid, m in metrics_map.items():
                    reviewer_metrics.append(ReviewerMetricsDTO(
                        reviewer_id=uid,
                        reviewer_name=user_map.get(uid, 'Unknown User'),
                        comments_reviewed=m['reviewed'],
                        approved=m['approved'],
                        rejected=m['rejected'],
                        flagged=m['flagged']
                    ))
            
            return ProjectAnalyticsDTO(
                project_id=project.id,
                project_name=getattr(project, 'name', 'Unknown Project'),
                kpi_summary=kpi_summary,
                category_distribution=category_distribution,
                confidence_distribution=confidence_distribution,
                status_trend=status_trend,
                reviewer_metrics=reviewer_metrics
            )
