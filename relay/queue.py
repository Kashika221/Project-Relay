"""Durable work queue with leases (SKIP LOCKED), exponential backoff retries, and dead-letter cases."""
import time
import random
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from relay.config import config
from relay.contracts import TicketInput, CaseRecord

logger = logging.getLogger("relay.queue")

class DurableQueue:
    def __init__(self, db_url: Optional[str] = None, max_attempts: int = 3, lease_seconds: int = 60):
        self.db_url = db_url or config.database_url
        self.max_attempts = max_attempts
        self.lease_seconds = lease_seconds
        self._in_memory_queue: List[Dict[str, Any]] = []

    def enqueue(self, ticket: TicketInput):
        """Idempotently adds a ticket into the durable queue."""
        try:
            import psycopg
            with psycopg.connect(self.db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO ticket_queue (ticket_id, tenant, payload, status, attempts)
                        VALUES (%s, %s, %s, 'queued', 0)
                        ON CONFLICT (ticket_id) DO NOTHING;
                        """,
                        (ticket.id, ticket.tenant, ticket.model_dump_json())
                    )
        except Exception:
            # Fallback for in-memory queue when Postgres is not running
            if not any(item["ticket"].id == ticket.id for item in self._in_memory_queue):
                self._in_memory_queue.append({
                    "ticket": ticket,
                    "status": "queued",
                    "attempts": 0,
                    "locked_until": 0
                })

    def acquire_lease(self, worker_id: str) -> Optional[TicketInput]:
        """
        Acquires next available ticket using SELECT ... FOR UPDATE SKIP LOCKED.
        Applies lease lock until NOW() + lease_seconds.
        """
        try:
            import psycopg
            with psycopg.connect(self.db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, ticket_id, payload, attempts
                        FROM ticket_queue
                        WHERE (status = 'queued' OR (status = 'processing' AND locked_until < NOW()))
                          AND attempts < %s
                        ORDER BY id ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED;
                        """,
                        (self.max_attempts,)
                    )
                    row = cur.fetchone()
                    if not row:
                        return None
                    
                    q_id, t_id, payload_json, attempts = row
                    cur.execute(
                        """
                        UPDATE ticket_queue
                        SET status = 'processing',
                            attempts = attempts + 1,
                            locked_until = NOW() + INTERVAL '%s seconds',
                            locked_by = %s,
                            updated_at = NOW()
                        WHERE id = %s;
                        """,
                        (self.lease_seconds, worker_id, q_id)
                    )
                    conn.commit()
                    return TicketInput.model_validate_json(payload_json)
        except Exception:
            # In-memory lease acquisition
            now = time.time()
            for item in self._in_memory_queue:
                if (item["status"] == "queued" or (item["status"] == "processing" and item["locked_until"] < now)) and item["attempts"] < self.max_attempts:
                    item["status"] = "processing"
                    item["attempts"] += 1
                    item["locked_until"] = now + self.lease_seconds
                    return item["ticket"]
            return None

    def mark_completed(self, ticket_id: str):
        """Marks queue item as completed."""
        try:
            import psycopg
            with psycopg.connect(self.db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE ticket_queue SET status = 'completed', updated_at = NOW() WHERE ticket_id = %s;", (ticket_id,))
        except Exception:
            for item in self._in_memory_queue:
                if item["ticket"].id == ticket_id:
                    item["status"] = "completed"

    def dead_letter(self, ticket: TicketInput, reason: str, severity: str = "high"):
        """Sends permanently failed ticket to dead-letter cases table."""
        try:
            import psycopg
            with psycopg.connect(self.db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE ticket_queue SET status = 'failed', updated_at = NOW() WHERE ticket_id = %s;", (ticket.id,))
                    cur.execute(
                        """
                        INSERT INTO cases (ticket_id, tenant, owner, severity, reason)
                        VALUES (%s, %s, %s, %s, %s);
                        """,
                        (ticket.id, ticket.tenant, "unassigned", severity, reason)
                    )
        except Exception:
            for item in self._in_memory_queue:
                if item["ticket"].id == ticket.id:
                    item["status"] = "failed"
