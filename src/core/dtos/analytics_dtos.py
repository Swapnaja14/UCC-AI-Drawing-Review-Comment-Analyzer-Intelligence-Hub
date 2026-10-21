from dataclasses import dataclass
from typing import List, Optional

@dataclass
class KPISummaryDTO:
    """
    Aggregated review metrics for one filtered comment population.

    Three distinct concepts are reported and must never be conflated or labelled
    "accuracy":

    review_progress
        (Approved + Rejected) / total. Includes auto-approvals, excludes Flagged.
    ai_confidence_avg
        Mean model score (classification_confidence) over rows classified by the
        AI model without a fallback. Says nothing about correctness.
    category_agreement_pct
        Share of human-reviewed rows whose final category still matches the
        initial AI category. The only metric here that measures the model
        against a human judgement, and only over rows a human actually reviewed.

    ``include_rejected`` records whether Rejected rows are part of the
    population, so a consumer can state the population honestly in a subtitle.
    """
    total_projects: int
    total_drawings: int
    total_comments: int
    total_pages: int
    approved_count: int
    rejected_count: int
    pending_count: int
    flagged_count: int
    avg_confidence: float
    high_confidence_pct: float
    low_confidence_pct: float
    approval_rate: Optional[float] = None
    review_progress: Optional[float] = None
    reviewed_count: Optional[int] = None
    auto_approved_count: Optional[int] = None
    auto_approval_rate: Optional[float] = None
    #: Approved rows a human confirmed / total. Not an accuracy measure.
    human_verified_approval_rate: Optional[float] = None
    #: Rows with status in (Approved, Rejected, Flagged) AND is_verified_by_human.
    human_reviewed_count: Optional[int] = None
    #: Flagged rows split by cause: a human flagged it vs OCR extraction failed.
    flagged_manual_count: Optional[int] = None
    flagged_ocr_failed_count: Optional[int] = None
    #: Mean classification_confidence where classification_method == 'ai_model'
    #: and fallback_used is False.
    ai_confidence_avg: Optional[float] = None
    ai_confidence_sample_size: Optional[int] = None
    #: Share of human-reviewed rows where category_name == initial_category.
    category_agreement_pct: Optional[float] = None
    category_agreement_sample_size: Optional[int] = None
    #: Thresholds actually used for the high/low confidence bands, from config.
    high_confidence_threshold: Optional[float] = None
    low_confidence_threshold: Optional[float] = None
    include_rejected: bool = True

@dataclass
class CategoryDistributionDTO:
    category_name: str
    count: int
    percentage: float
    color_hex: str = '#6366F1'
    #: Set by get_pareto_analysis only — running totals over the displayed bars,
    #: measured against the full population rather than the visible top_n slice.
    cumulative_count: Optional[int] = None
    cumulative_percentage: Optional[float] = None

@dataclass
class ConfidenceBucketDTO:
    range_label: str
    count: int
    percentage: float

@dataclass
class ReviewerMetricsDTO:
    reviewer_id: str
    reviewer_name: str
    comments_reviewed: int
    approved: int
    rejected: int
    flagged: int
    avg_review_time_hours: Optional[float] = None

@dataclass
class TrendDataPointDTO:
    period_label: str
    count: int
    human_reviews: Optional[int] = None

@dataclass
class ProjectAnalyticsDTO:
    project_id: str
    project_name: str
    kpi_summary: KPISummaryDTO
    category_distribution: List[CategoryDistributionDTO]
    confidence_distribution: List[ConfidenceBucketDTO]
    status_trend: List[TrendDataPointDTO]
    reviewer_metrics: List[ReviewerMetricsDTO]
