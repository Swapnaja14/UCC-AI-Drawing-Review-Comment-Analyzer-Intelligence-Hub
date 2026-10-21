"""
User-facing definitions of the review metrics.

Every screen that shows one of these numbers must state the same definition, so
the wording lives here instead of being retyped per screen. None of these
metrics measures how correct the AI is, so the words "accuracy" and "correct"
are deliberately absent from all of them.
"""

#: Review Progress counts a comment as decided once a status other than Pending
#: or Flagged is on it, whether a human or the auto-approve policy set it.
REVIEW_PROGRESS_TOOLTIP = (
    "Review Progress = (Approved + Rejected) / Total comments in the current filter.\n"
    "Auto-approved comments count as reviewed; Flagged counts as NOT yet reviewed."
)

#: classification_confidence is not a pure model score: workflow_engine
#: synthesises one from the OCR confidence when the model returned none, so
#: restricting to classification_method='ai_model' narrows the problem but does
#: not eliminate it.
AI_CONFIDENCE_CAVEAT = (
    "Model score only — not a measure of correctness.\n"
    "Restricted to rows classified by the AI model without a fallback, but the\n"
    "pipeline can still synthesise a missing classification confidence from the\n"
    "OCR confidence, so treat this as indicative."
)

#: Audit rows written before reviewer pass-through was fixed carry no acting user.
REVIEWER_ATTRIBUTION_CAVEAT = (
    "Reviewer attribution starts from the audit log. Rows recorded before "
    "attribution was fixed remain anonymous."
)

#: Category agreement compares the category a human left on a comment with the
#: one the pipeline first proposed, and only over comments a human decided on.
CATEGORY_AGREEMENT_TOOLTIP_HEADER = (
    "Category agreement (reviewed comments only):\n"
    "Share of human-verified comments whose final category still equals the\n"
    "category the pipeline first proposed.\n"
    "Excludes Pending rows, auto-approved rows, and rows with no initial category."
)
