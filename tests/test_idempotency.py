"""Tests for C5 & C7: Outbox idempotency and exactly-once semantics."""
import json
from relay.contracts import DecisionRecord

def test_outbox_exactly_once(approval_manager):
    # Setup mock decisions file with a pending approval decision
    mock_dec = DecisionRecord(
        ticket_id="NW-T01",
        tenant="northwind",
        run_id="run-1",
        category="returns_refunds",
        priority="normal",
        action="draft_reply",
        injection_detected=False,
        kb_refs=["NW-KB-01"],
        draft_reply="You may return unused items within 30 days (NW-KB-01).",
        status="pending_approval",
        model="mock",
        tokens_in=100,
        tokens_out=20,
        latency_ms=50
    )
    with open(approval_manager.decisions_file, "w", encoding="utf-8") as f:
        f.write(mock_dec.model_dump_json() + "\n")

    # First approval -> emits to outbox
    res1 = approval_manager.approve("NW-T01", approver="lead_agent")
    assert res1 is not None
    assert res1.ticket_id == "NW-T01"
    assert res1.idempotency_key != ""

    # Second approval -> blocked (idempotent, returns None)
    res2 = approval_manager.approve("NW-T01", approver="lead_agent")
    assert res2 is None

    # Verify outbox.jsonl has exactly one line
    with open(approval_manager.outbox_file, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["ticket_id"] == "NW-T01"
