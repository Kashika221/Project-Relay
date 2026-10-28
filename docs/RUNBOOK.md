# Project Relay: Operations Runbook

This runbook outlines operational procedures and recovery steps for system operators managing Project Relay.

---

## Incident Scenarios & Standard Operating Procedures (SOP)

### 1. Ollama Service is Down
* **Symptoms**: Logs report `Connection refused on http://localhost:11434` or `GatewayCircuitBreakerException`.
* **Impact**: Incoming tickets cannot be triaged or drafted.
* **Resolution**:
  1. Verify Ollama process status:
     ```bash
     ollama list
     ```
  2. Restart the Ollama daemon:
     ```bash
     ollama serve
     ```
  3. Confirm model availability:
     ```bash
     ollama run qwen2.5:1.5b "test"
     ```
  4. Once restored, the worker will automatically resume processing queued tickets without data loss.

---

### 2. Relay Worker Process Crashes or Dies
* **Symptoms**: Queue depth in `ticket_queue` stops decreasing; tickets remain in `processing` status.
* **Impact**: Ticket processing is temporarily halted.
* **Resolution**:
  1. Simply restart the worker process:
     ```bash
     python -m relay.cli run --inbox data/northwind/tickets.jsonl
     ```
  2. **Automatic Lease Expiry**: Tickets that were locked by the terminated worker have a lease timeout (`locked_until < NOW()`). The newly started worker automatically reclaims expired leases via `SELECT ... FOR UPDATE SKIP LOCKED`.
  3. **Idempotency Guarantee**: Partially processed tickets will not create duplicate decisions or outbox entries.

---

### 3. Token Budget Exhausted (`held_budget`)
* **Symptoms**: Tickets in `out/decisions.jsonl` show `status: "held_budget"`.
* **Impact**: Tickets are paused safely to prevent runaway compute costs.
* **Resolution**:
  1. Check token usage in telemetry:
     ```bash
     python -m relay.cli report --view internal
     ```
  2. If the volume surge is legitimate, adjust budget limits in `.env`:
     ```env
     RUN_TOKEN_BUDGET=100000
     TICKET_TOKEN_BUDGET=8000
     ```
  3. Re-run the inbox to process the held tickets:
     ```bash
     python -m relay.cli run --inbox data/northwind/tickets.jsonl
     ```

---

### 4. Database is Unreachable
* **Symptoms**: `psycopg.OperationalError: could not connect to server`.
* **Impact**: RLS queries and durable queue cannot be accessed.
* **Resolution**:
  1. Inspect Postgres container:
     ```bash
     docker ps -a --filter name=relay-pg
     ```
  2. Check container logs:
     ```bash
     docker logs relay-pg --tail 50
     ```
  3. Restart the container:
     ```bash
     docker restart relay-pg
     ```
  4. Verify connectivity:
     ```bash
     docker exec -it relay-pg psql -U relay_app -d postgres -c "SELECT 1;"
     ```

---

### 5. A Draft is Rejected Twice by Human Approver
* **Symptoms**: Reviewer uses `relay reject --reason "..."` on the same ticket draft twice.
* **Impact**: The ticket remains unresolved in the approval queue.
* **Resolution**:
  1. Two rejections signal that the knowledge base lacks sufficient clarity or the inquiry requires specialized human handling.
  2. The ticket is immediately moved to `cases` table:
     ```bash
     # Move to escalation cases
     python -m relay.cli show <ticket_id>
     ```
  3. Assign the case to a human support agent or update the company's knowledge base article with missing details.
