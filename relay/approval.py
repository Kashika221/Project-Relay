"""Human-in-the-loop approval state machine and idempotent outbox for Project Relay."""
import json
import os
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pathlib import Path
from relay.contracts import OutboxRecord, DecisionRecord

class ApprovalManager:
    def __init__(self, out_dir: Optional[Path] = None):
        self.out_dir = out_dir or Path("out")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.decisions_file = self.out_dir / "decisions.jsonl"
        self.outbox_file = self.out_dir / "outbox.jsonl"
        self.audit_file = self.out_dir / "audit.jsonl"

    def list_pending(self) -> List[DecisionRecord]:
        """Lists all decisions that are currently pending human approval."""
        if not self.decisions_file.exists():
            return []
        
        pending = []
        with open(self.decisions_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                if d.get("status") == "pending_approval":
                    pending.append(DecisionRecord(**d))
        return pending

    def show(self, ticket_id: str) -> Optional[DecisionRecord]:
        """Shows details of a specific ticket decision."""
        if not self.decisions_file.exists():
            return None
        with open(self.decisions_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                if d.get("ticket_id") == ticket_id:
                    return DecisionRecord(**d)
        return None

    def approve(self, ticket_id: str, approver: str = "human_operator") -> Optional[OutboxRecord]:
        """
        Approves a pending draft.
        Emits an outbox record with an idempotency key.
        Guarantees exactly-once write to outbox.jsonl.
        """
        decision = self.show(ticket_id)
        if not decision or not decision.draft_reply:
            return None

        # Check existing outbox to guarantee idempotency
        existing_ids = set()
        if self.outbox_file.exists():
            with open(self.outbox_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        existing_ids.add(json.loads(line).get("ticket_id"))

        if ticket_id in existing_ids:
            return None

        now = datetime.now(timezone.utc).isoformat()
        raw_key = f"{ticket_id}:{decision.tenant}:{now}"
        idempotency_key = hashlib.sha256(raw_key.encode()).hexdigest()[:16]

        outbox_entry = OutboxRecord(
            ticket_id=ticket_id,
            tenant=decision.tenant,
            text=decision.draft_reply,
            approved_by=approver,
            approved_at=now,
            idempotency_key=idempotency_key
        )

        with open(self.outbox_file, "a", encoding="utf-8") as f:
            f.write(outbox_entry.model_dump_json() + "\n")

        self._audit(ticket_id=ticket_id, action="approved", actor=approver, reason="Operator approved draft")
        return outbox_entry

    def reject(self, ticket_id: str, reason: str, approver: str = "human_operator") -> bool:
        """
        Rejects a draft with a required reason.
        Audits state change.
        """
        decision = self.show(ticket_id)
        if not decision:
            return False

        self._audit(ticket_id=ticket_id, action="rejected", actor=approver, reason=reason)
        return True

    def _audit(self, ticket_id: str, action: str, actor: str, reason: Optional[str] = None):
        audit_entry = {
            "ticket_id": ticket_id,
            "action": action,
            "actor": actor,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        with open(self.audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_entry) + "\n")
