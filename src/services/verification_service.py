from datetime import datetime
from typing import List, Optional

from src.core.dtos.audit_dtos import (
    AuditAction,
    AuditLogEntryDTO,
    VerificationSummaryDTO,
    BulkActionResultDTO
)
from src.core.dtos.audit_dtos import (
    AuditAction,
    AuditLogEntryDTO,
    VerificationSummaryDTO,
    BulkActionResultDTO
)
from src.infrastructure.storage.repository import CommentRepository, AuditLogRepository
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

class VerificationService:
    def __init__(
        self,
        comment_repo: CommentRepository,
        audit_repo: Optional[AuditLogRepository] = None,
    ):
        self.comment_repo = comment_repo
        self.audit_repo = audit_repo
        self._audit_log: List[AuditLogEntryDTO] = []

    def _log_audit(self, comment_id: str, action: str, reviewer_id: str, old_value: str, new_value: str, notes: str = '') -> None:
        now_dt = datetime.now()
        entry = AuditLogEntryDTO(
            comment_id=comment_id,
            action=action,
            reviewer_id=reviewer_id,
            old_value=old_value,
            new_value=new_value,
            timestamp=now_dt,
            notes=notes
        )
        self._audit_log.append(entry)

        if self.audit_repo:
            try:
                self.audit_repo.create_audit_entry(
                    comment_id=comment_id,
                    action=action,
                    reviewer_id=reviewer_id,
                    old_value=old_value,
                    new_value=new_value,
                    notes=notes,
                    timestamp=now_dt,
                )
            except Exception as e:
                logger.warning(f"Could not persist audit log to database: {e}")

    def approve_comment(self, comment_id: str, reviewer_id: str = '', notes: str = '') -> bool:
        old_status = 'Pending'
        try:
            if hasattr(self.comment_repo, 'get_comment_by_id'):
                c_data = self.comment_repo.get_comment_by_id(comment_id)
                if c_data:
                    old_status = c_data.get('status', 'Pending')
        except Exception:
            pass
        success = self.comment_repo.update_comment_status(comment_id, 'Approved', True)
        if success:
            audit_note = notes or ('Confirmed by reviewer' if old_status == 'Approved' else '')
            self._log_audit(comment_id, AuditAction.APPROVE, reviewer_id, old_status, 'Approved', audit_note)
        return success

    def reject_comment(self, comment_id: str, reviewer_id: str = '', notes: str = '') -> bool:
        old_status = 'Pending'
        try:
            if hasattr(self.comment_repo, 'get_comment_by_id'):
                c_data = self.comment_repo.get_comment_by_id(comment_id)
                if c_data:
                    old_status = c_data.get('status', 'Pending')
        except Exception:
            pass
        success = self.comment_repo.update_comment_status(comment_id, 'Rejected', True)
        if success:
            audit_note = notes or ('Overridden by reviewer' if old_status == 'Approved' else '')
            self._log_audit(comment_id, AuditAction.REJECT, reviewer_id, old_status, 'Rejected', audit_note)
        return success

    def flag_comment(self, comment_id: str, reviewer_id: str = '', notes: str = '') -> bool:
        old_status = 'Pending'
        try:
            if hasattr(self.comment_repo, 'get_comment_by_id'):
                c_data = self.comment_repo.get_comment_by_id(comment_id)
                if c_data:
                    old_status = c_data.get('status', 'Pending')
        except Exception:
            pass
        success = self.comment_repo.update_comment_status(comment_id, 'Flagged', True)
        if success:
            audit_note = notes or ('Flagged for follow-up' if old_status == 'Approved' else '')
            self._log_audit(comment_id, AuditAction.FLAG, reviewer_id, old_status, 'Flagged', audit_note)
        return success

    def edit_comment_text(self, comment_id: str, new_text: str, reviewer_id: str = '') -> bool:
        success = self.comment_repo.update_comment_text(comment_id, new_text)
        if success:
            self._log_audit(comment_id, AuditAction.EDIT_TEXT, reviewer_id, '', new_text, '')
        return success

    def approve_all_high_confidence(self, drawing_id: str, threshold: float = 0.85, reviewer_id: str = 'system') -> BulkActionResultDTO:
        comments = self.comment_repo.get_comments_for_drawing(drawing_id)
        result = BulkActionResultDTO(
            total_processed=0,
            successful=0,
            failed=0,
            skipped=0,
            failed_ids=[]
        )
        for comment in comments:
            if comment.get('confidence', 0.0) >= threshold and comment.get('status') == 'Pending':
                result.total_processed += 1
                success = self.approve_comment(comment['id'], reviewer_id, 'Bulk approved')
                if success:
                    result.successful += 1
                else:
                    result.failed += 1
                    result.failed_ids.append(comment['id'])
            else:
                result.skipped += 1
        return result

    def get_verification_summary(self, drawing_id: str) -> VerificationSummaryDTO:
        comments = self.comment_repo.get_comments_for_drawing(drawing_id)
        total = len(comments)
        approved = 0
        rejected = 0
        flagged = 0
        pending = 0
        verified = 0

        for comment in comments:
            status = comment.get('status', 'Pending')
            if status == 'Approved':
                approved += 1
            elif status == 'Rejected':
                rejected += 1
            elif status == 'Flagged':
                flagged += 1
            elif status == 'Pending':
                pending += 1
            
            if comment.get('verified_by_human', False):
                verified += 1
                
        approval_rate = approved / total if total > 0 else 0.0

        return VerificationSummaryDTO(
            total_comments=total,
            approved=approved,
            rejected=rejected,
            flagged=flagged,
            pending=pending,
            approval_rate=approval_rate,
            verified_by_human_count=verified
        )

    def get_audit_log(self, comment_id: Optional[str] = None) -> List[AuditLogEntryDTO]:
        if self.audit_repo:
            try:
                if comment_id:
                    db_logs = self.audit_repo.get_audit_logs_for_comment(comment_id)
                else:
                    db_logs = self.audit_repo.get_recent_audit_logs(limit=100)
                
                dtos = []
                for row in db_logs:
                    ts_raw = row.get("timestamp") or row.get("created_at")
                    if isinstance(ts_raw, str):
                        try:
                            ts = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S")
                        except Exception:
                            ts = datetime.now()
                    elif isinstance(ts_raw, datetime):
                        ts = ts_raw
                    else:
                        ts = datetime.now()

                    dtos.append(
                        AuditLogEntryDTO(
                            comment_id=row.get("comment_id", ""),
                            action=row.get("action", ""),
                            reviewer_id=row.get("reviewer_id", "") or row.get("user_id", "") or "system",
                            old_value=row.get("old_value", ""),
                            new_value=row.get("new_value", ""),
                            timestamp=ts,
                            notes=row.get("notes", ""),
                        )
                    )
                if dtos:
                    return dtos
            except Exception as e:
                logger.warning(f"Error reading audit log from database: {e}")

        if comment_id:
            return [entry for entry in self._audit_log if entry.comment_id == comment_id]
        return self._audit_log

    def get_audit_history(self, comment_id: Optional[str] = None) -> List[AuditLogEntryDTO]:
        return self.get_audit_log(comment_id)

