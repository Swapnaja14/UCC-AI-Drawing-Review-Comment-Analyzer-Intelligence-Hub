from dataclasses import dataclass
from typing import List

@dataclass
class CategoryPredictionDTO:
    category_name: str
    confidence: float
    matched_keywords: List[str]

@dataclass
class ClassificationResultDTO:
    comment_id: str
    text: str
    primary_category: CategoryPredictionDTO
    alternative_categories: List[CategoryPredictionDTO]
    classification_method: str
    requires_human_review: bool
    fallback_used: bool = False
    fallback_reason: str = ""

@dataclass
class BatchClassificationDTO:
    drawing_id: str
    total_classified: int
    results: List[ClassificationResultDTO]
    high_confidence_count: int
    low_confidence_count: int
    flagged_count: int
    ai_classified_count: int = 0
    fallback_count: int = 0
    rule_classified_count: int = 0

