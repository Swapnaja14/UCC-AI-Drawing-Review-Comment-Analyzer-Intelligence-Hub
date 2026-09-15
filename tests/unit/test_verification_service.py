import pytest
from src.services.verification_service import VerificationService
from src.infrastructure.storage.repository import CommentRepository

class MockCommentRepository(CommentRepository):
    def __init__(self, engine=None):
        self.comments = []
        self._id_counter = 1

    def save_comment(self, drawing_id, page_number, raw_text, bbox, confidence=0.0, status='Pending', category='general'):
        c = {
            'id': str(self._id_counter),
            'drawing_id': drawing_id,
            'page_number': page_number,
            'raw_text': raw_text,
            'bbox': bbox,
            'confidence': confidence,
            'status': status,
            'category': category,
            'verified_by_human': False
        }
        self.comments.append(c)
        self._id_counter += 1
        return c['id']

    def get_comments_for_drawing(self, drawing_id):
        return [c for c in self.comments if c['drawing_id'] == drawing_id]

    def update_comment_status(self, comment_id, status, verified_by_human):
        for c in self.comments:
            if c['id'] == comment_id:
                c['status'] = status
                c['verified_by_human'] = verified_by_human
                return True
        return False

    def update_comment_text(self, comment_id, new_text):
        for c in self.comments:
            if c['id'] == comment_id:
                c['raw_text'] = new_text
                return True
        return False

    def get_comment_by_id(self, comment_id):
        for c in self.comments:
            if c['id'] == comment_id:
                return c
        return None

def setup_repo():
    # Helper simulating the in-memory SQLite repo requirement
    return MockCommentRepository()

def test_approve_comment_updates_status():
    repo = setup_repo()
    cid = repo.save_comment("draw1", 1, "test", (0,0,1,1))
    service = VerificationService(repo)
    
    assert service.approve_comment(cid, "rev1")
    c = repo.comments[0]
    assert c['status'] == 'Approved'
    assert c['verified_by_human'] is True

def test_reject_comment_updates_status():
    repo = setup_repo()
    cid = repo.save_comment("draw1", 1, "test", (0,0,1,1))
    service = VerificationService(repo)
    
    assert service.reject_comment(cid, "rev1")
    c = repo.comments[0]
    assert c['status'] == 'Rejected'
    assert c['verified_by_human'] is True

def test_flag_comment_updates_status():
    repo = setup_repo()
    cid = repo.save_comment("draw1", 1, "test", (0,0,1,1))
    service = VerificationService(repo)
    
    assert service.flag_comment(cid, "rev1")
    c = repo.comments[0]
    assert c['status'] == 'Flagged'
    assert c['verified_by_human'] is True

def test_audit_log_records_action():
    repo = setup_repo()
    cid = repo.save_comment("draw1", 1, "test", (0,0,1,1))
    service = VerificationService(repo)
    
    service.approve_comment(cid, "rev1")
    logs = service.get_audit_log(cid)
    assert len(logs) == 1
    assert logs[0].action == 'approve'
    assert logs[0].reviewer_id == 'rev1'

def test_bulk_approve_high_confidence():
    repo = setup_repo()
    repo.save_comment("draw1", 1, "low", (0,0,1,1), confidence=0.5)
    repo.save_comment("draw1", 1, "high1", (0,0,1,1), confidence=0.9)
    repo.save_comment("draw1", 1, "high2", (0,0,1,1), confidence=0.95)
    
    service = VerificationService(repo)
    res = service.approve_all_high_confidence("draw1", 0.85)
    
    assert res.total_processed == 2
    assert res.successful == 2
    assert res.skipped == 1
    
    summary = service.get_verification_summary("draw1")
    assert summary.approved == 2
    assert summary.pending == 1

def test_verification_summary_counts():
    repo = setup_repo()
    cid1 = repo.save_comment("draw1", 1, "test", (0,0,1,1))
    cid2 = repo.save_comment("draw1", 1, "test", (0,0,1,1))
    repo.save_comment("draw1", 1, "test", (0,0,1,1))
    
    service = VerificationService(repo)
    service.approve_comment(cid1, "rev1")
    service.reject_comment(cid2, "rev1")
    
    summary = service.get_verification_summary("draw1")
    assert summary.total_comments == 3
    assert summary.approved == 1
    assert summary.rejected == 1
    assert summary.pending == 1
    assert summary.verified_by_human_count == 2
    assert summary.approval_rate == (1/3)

def test_edit_comment_text():
    repo = setup_repo()
    cid = repo.save_comment("draw1", 1, "old text", (0,0,1,1))
    service = VerificationService(repo)
    
    assert service.edit_comment_text(cid, "new text", "rev1")
    assert repo.comments[0]['raw_text'] == "new text"
