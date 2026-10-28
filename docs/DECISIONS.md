# Project Relay: Architectural Decisions & Trade-Offs

This document records the core architectural trade-offs made during Project Relay, the alternatives considered and rejected, and the rationale for each choice.

---

## 1. Five Core Trade-Offs

### Decision 1: Database Kernel RLS vs. Application-Level Query Filtering
* **Choice**: PostgreSQL Row-Level Security (`FORCE ROW LEVEL SECURITY`) with `SET LOCAL app.tenant_id = :tenant` on a non-superuser connection (`relay_app`).
* **Alternative Rejected**: Filtering in application ORM/queries (`WHERE tenant = :tenant`).
* **Rationale**: Application-level filtering is vulnerable to developer oversight, subtle ORM join bugs, and prompt injection attacks that manipulate search parameters. Database-enforced RLS with a fail-closed policy (`NULLIF(current_setting('app.tenant_id', true), '')`) guarantees zero rows are returned if the context variable is omitted.

### Decision 2: Clean Python & Pydantic vs. Heavy Agent Frameworks (LangGraph / CrewAI)
* **Choice**: Native Python pipelines with typed Pydantic contracts and explicit retry logic.
* **Alternative Rejected**: Wrapping the fleet in LangGraph or CrewAI.
* **Rationale**: The assessment prioritizes transparent orchestration, clean error classification, and explainability during the 45-minute live technical walkthrough. Framework abstractions introduce hidden state, complex dependency graphs, and debugging friction without adding tangible value to a well-defined sequential handoff flow.

### Decision 3: Deterministic Rule-Based Checker vs. LLM-as-a-Judge
* **Choice**: Pure regex and deterministic string/ID verification for safety, canaries, and clinical prohibitions.
* **Alternative Rejected**: Calling a secondary LLM to judge safety and canary leaks.
* **Rationale**: LLM judges are non-deterministic, susceptible to adversarial framing, and introduce unnecessary token overhead and latency. Canary tokens (`CANARY-NW-4K9P`, `CANARY-HD-7Q2X`), clinical medication keywords, and word count constraints are mathematical properties best verified by deterministic rules.

### Decision 4: Two-Tier Prompt Injection Defense (Structural Heuristic + LLM Triage) vs. Keyword Denylist
* **Choice**: Combining structural delimiter detection (`---- SYSTEM:`, `admin mode`, `ignore instructions`) with few-shot triage classification.
* **Alternative Rejected**: Simple keyword denylists.
* **Rationale**: The brief notes that a keyword list alone is weak. Adversaries bypass simple keywords with spacing, encoding, or rephrasing. Our approach looks for structural command boundaries; if flagged by either the heuristic or the model, the Lead Agent halts execution, escalates, and completely isolates the ticket from retrieval and drafting.

### Decision 5: Postgres SKIP LOCKED Work Queue vs. External Message Broker (RabbitMQ / Redis / Celery)
* **Choice**: Relational queue table utilizing `SELECT ... FOR UPDATE SKIP LOCKED` and lease timestamps.
* **Alternative Rejected**: Adding Redis + Celery or RabbitMQ.
* **Rationale**: Eliminates external operational dependencies. Postgres already provides ACID transactions, durable persistence, lease expiration, and dead-letter queueing within the same database engine, guaranteeing zero duplicate processing on worker crashes.

---

## 2. Nuances & Observations on Golden Labels

* **Prompt Injections (`NW-T07`, `HD-T07`)**: Both tickets attempt system override and canary exfiltration. By overriding the action to `escalate` and withholding KB retrieval context, the platform ensures the system prompt and canary notes remain completely inaccessible to the adversary.
* **Missing Details (`NW-T03`, `HD-T04`, `HD-T11`)**: We strictly enforced `ask_for_info` without guessing missing order IDs or patient authorization. This prevents legal exposure and adheres to real-world support desk protocols.

---

## 3. Scaling Note: Supporting 50 Tenants (Stretch S4)

To expand Project Relay from 2 to 50 enterprise tenants in production:

1. **Database & Isolation Architecture**:
   - **Connection Pooling**: Deploy **PgBouncer** in transaction pooling mode. `SET LOCAL app.tenant_id` executes cleanly per transaction without polluting pooled connections.
   - **Partitioning**: Partition the `knowledge_base` and `ticket_queue` tables by `tenant` using PostgreSQL declarative table partitioning.
   - **Vector Indexing**: Switch from IVFFlat to **HNSW** (`m=16, ef_construction=64`) per partition to maintain sub-10ms retrieval latency across 50,000+ passages.

2. **Hosting & Compute Infrastructure**:
   - **Model Serving**: Migrate local Ollama instances to a dedicated GPU cluster running **vLLM** on Kubernetes (e.g. 2x NVIDIA A10G or L4 GPUs on AWS/GCP).
   - **Application Tier**: Run the orchestrator workers as stateless containers on AWS ECS Fargate or Google Cloud Run, autoscaling horizontally based on queue depth.

3. **Estimated Monthly Operating Cost (50 Tenants)**:
   - Managed PostgreSQL (AWS RDS db.r6g.xlarge, 32GB RAM, Multi-AZ): ~$350/mo.
   - GPU Inference (1x AWS g5.2xlarge with A10G on-demand or reserved): ~$750/mo.
   - Container Compute (ECS Fargate 4 vCPU, 8GB RAM): ~$120/mo.
   - Total Estimated Infrastructure Cost: **~$1,220 / month** (~$24.40 / tenant / month).
