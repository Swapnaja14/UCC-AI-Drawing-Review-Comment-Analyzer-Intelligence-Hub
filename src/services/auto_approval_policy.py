"""
Auto-Approval Policy for UCC Drawing Review Intelligence.

Hardens auto-approval rules to ensure only high-certainty, high-quality,
non-fallback DistilBERT AI classifications are automatically marked as 'Approved'.
"""
from typing import Tuple


def evaluate_auto_approval(
    ocr_confidence: float,
    classification_confidence: float,
    text: str,
    fallback_used: bool = False,
    classification_method: str = "ai_model",
    auto_approve_enabled: bool = True,
    threshold: float = 0.85,
) -> Tuple[bool, str]:
    """
    Evaluates whether an extracted comment is eligible for automatic approval.

    Requirements enforced:
    1. Feature flag:
       - auto_approve_enabled must be True.
    2. Fallback prevention:
       - fallback_used must be False.
       - classification_method must be 'ai_model'. Fallback or rule-based classifications
         are strictly prohibited from auto-approving.
    3. Multi-stage disentangled confidence requirements:
       - ocr_confidence >= threshold (default 0.85)
       - classification_confidence >= threshold (default 0.85)
       Both must be satisfied independently. High OCR confidence cannot mask
       lower classification confidence, and vice-versa.
    4. Text quality and length:
       - Short text rejection: text must contain more than 3 words (> 3 words).
         Texts with <= 3 words (e.g. single labels, abbreviations, page noise) are rejected.
       - Noisy text rejection: text must contain at least 3 alphanumeric characters and
         cannot consist purely of symbols, punctuation, or repeated non-informative characters.

    Returns:
        (is_approved: bool, reason: str)
    """
    if not auto_approve_enabled:
        return False, "Auto-approval disabled in configuration"

    # Rule 2: Strictly prevent fallback or non-AI classifications from auto-approving
    norm_method = (classification_method or "").lower()
    if fallback_used or norm_method != "ai_model" or "fallback" in norm_method:
        return False, f"Fallback classification used ({classification_method})"

    # Rule 4: Text quality & length check
    clean_text = (text or "").strip()
    if not clean_text:
        return False, "Empty or whitespace-only text"

    # Count meaningful words (ignoring standalone punctuation)
    words = [w for w in clean_text.split() if any(c.isalnum() for c in w)]
    if len(words) <= 3:
        return False, f"Text too short for auto-approval ({len(words)} word{'s' if len(words) != 1 else ''} <= 3 words)"

    # Alphanumeric check to reject pure noise or punctuation clusters (e.g. "--- ... ###")
    alnum_count = sum(1 for ch in clean_text if ch.isalnum())
    if alnum_count < 3:
        return False, "Text lacks sufficient alphanumeric characters (noisy/symbolic)"

    # Rule 3: Both disentangled confidences must independently meet or exceed the threshold
    if ocr_confidence < threshold:
        return False, f"OCR confidence ({ocr_confidence:.2f}) below threshold ({threshold:.2f})"

    if classification_confidence < threshold:
        return False, f"Classification confidence ({classification_confidence:.2f}) below threshold ({threshold:.2f})"

    return True, f"AI model, OCR: {int(ocr_confidence * 100)}%, Cat: {int(classification_confidence * 100)}%, {len(words)} words"
