"""Tests for C5: Approval State Machine and Audit Trail."""
import json
from relay.contracts import DecisionRecord

def test_approval_state_and_audit(approval_manager):
    mock_dec = DecisionRecord(
        ticket_id="HD-T01",
        tenant="harbor",
        run_id="run-1",
        category="appointments",
        priority="normal",
        action="draft_reply",
        injection_detected=False,
        kb_refs=["HD-KB-01"],
        draft_reply="Appointments can be moved online (HD-KB-01).",
        status="pending_approval",
        model="mock",
        tokens_in=80,
        tokens_out=15,
        latency_ms=40
    )
    with open(approval_manager.decisions_file, "w", encoding="utf-8") as f:
        f.write(mock_dec.model_dump_json() + "\n")

    pending = approval_manager.list_pending()
    assert len(pending) == 1
    assert pending[0].ticket_id == "HD-T01"

    # Reject with reason
    rejected = approval_manager.reject("HD-T01", reason="Needs tone adjustment", approver="lead_reviewer")
    assert rejected is True

    # Verify audit file contains the state change
    with open(approval_manager.audit_file, "r", encoding="utf-8") as f:
        audit_lines = [json.loads(l) for l in f if l.strip()]
    assert len(audit_lines) == 1
    assert audit_lines[0]["ticket_id"] == "HD-T01"
    assert audit_lines[0]["action"] == "rejected"
    assert audit_lines[0]["actor"] == "lead_reviewer"
    assert audit_lines[0]["reason"] == "Needs tone adjustment"
