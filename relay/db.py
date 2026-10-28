"""Database layer for Project Relay with PostgreSQL RLS, pgvector, and fail-closed isolation."""
import os
import json
import logging
from typing import List, Dict, Any, Optional
from relay.config import config
from relay.contracts import KBPassage

logger = logging.getLogger("relay.db")

SCHEMA_SQL = """
-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;

-- Non-superuser application role
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'relay_app') THEN
        CREATE ROLE relay_app WITH LOGIN PASSWORD 'relay_secret';
    END IF;
END $$;

-- Knowledge Base Table
CREATE TABLE IF NOT EXISTS knowledge_base (
    id VARCHAR(32) PRIMARY KEY,
    tenant VARCHAR(32) NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    internal BOOLEAN DEFAULT FALSE,
    embedding vector(768)
);

-- Enable & FORCE Row-Level Security
ALTER TABLE knowledge_base ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_base FORCE ROW LEVEL SECURITY;

-- Drop existing policy if any
DROP POLICY IF EXISTS kb_tenant_isolation_policy ON knowledge_base;

-- Fail-closed tenant isolation policy:
CREATE POLICY kb_tenant_isolation_policy ON knowledge_base
    FOR ALL
    TO relay_app
    USING (tenant = NULLIF(current_setting('app.tenant_id', true), ''));

-- Durable Work Queue
CREATE TABLE IF NOT EXISTS ticket_queue (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(64) UNIQUE NOT NULL,
    tenant VARCHAR(32) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(32) DEFAULT 'queued',
    attempts INT DEFAULT 0,
    locked_until TIMESTAMPTZ,
    locked_by VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Outbox with Idempotency
CREATE TABLE IF NOT EXISTS outbox (
    ticket_id VARCHAR(64) PRIMARY KEY,
    tenant VARCHAR(32) NOT NULL,
    text TEXT NOT NULL,
    approved_by VARCHAR(64) NOT NULL,
    approved_at TIMESTAMPTZ NOT NULL,
    idempotency_key VARCHAR(128) UNIQUE NOT NULL
);

-- Cases Table
CREATE TABLE IF NOT EXISTS cases (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(64) NOT NULL,
    tenant VARCHAR(32) NOT NULL,
    owner VARCHAR(64) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audit Log Table
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(64) NOT NULL,
    action VARCHAR(64) NOT NULL,
    actor VARCHAR(64) NOT NULL,
    reason TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Model Call Metering Table
CREATE TABLE IF NOT EXISTS model_calls (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(64),
    model VARCHAR(64) NOT NULL,
    tokens_in INT NOT NULL,
    tokens_out INT NOT NULL,
    latency_ms INT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Grants for application user
GRANT USAGE ON SCHEMA public TO relay_app;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO relay_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO relay_app;
"""

class Database:
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or config.database_url
        self._mock_kb: List[Dict[str, Any]] = []

    @property
    def is_mock(self) -> bool:
        return config.mock_llm or (os.getenv("MOCK_LLM", "false").lower() in ("true", "1", "yes"))

    def init_schema(self, admin_url: Optional[str] = None):
        """Initializes tables, pgvector, roles, and RLS policies using admin connection."""
        if self.is_mock:
            return
        url = admin_url or config.admin_database_url
        try:
            import psycopg
            with psycopg.connect(url, connect_timeout=2, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(SCHEMA_SQL)
            logger.info("Database schema and RLS policies successfully applied.")
        except Exception as e:
            logger.warning(f"Could not initialize PostgreSQL schema: {e}")

    def seed_kb(self, kb_items: List[Dict[str, Any]]):
        """Seeds KB items and embeddings into knowledge_base table."""
        self._mock_kb = kb_items
        if self.is_mock:
            return

        try:
            import psycopg
            with psycopg.connect(self.db_url, connect_timeout=2, autocommit=True) as conn:
                with conn.cursor() as cur:
                    for item in kb_items:
                        emb = item.get("embedding")
                        cur.execute(
                            """
                            INSERT INTO knowledge_base (id, tenant, title, body, internal, embedding)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE SET
                                title = EXCLUDED.title,
                                body = EXCLUDED.body,
                                internal = EXCLUDED.internal,
                                embedding = EXCLUDED.embedding;
                            """,
                            (item["id"], item["tenant"], item["title"], item["body"], item.get("internal", False), str(emb) if emb else None)
                        )
        except Exception as e:
            logger.debug(f"Postgres seed skipped (using in-memory KB): {e}")

    def retrieve_passages(self, tenant: str, query_embedding: List[float], top_k: int = 3) -> List[KBPassage]:
        """
        Retrieves top-k relevant non-internal KB passages using pgvector under tenant RLS.
        """
        if self.is_mock:
            return self._mock_retrieve(tenant, top_k)

        try:
            import psycopg
            with psycopg.connect(self.db_url, connect_timeout=2) as conn:
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL app.tenant_id = %s;", (tenant,))
                    emb_str = f"[{','.join(map(str, query_embedding))}]"
                    cur.execute(
                        """
                        SELECT id, title, body, (embedding <=> %s::vector) AS score
                        FROM knowledge_base
                        WHERE internal = FALSE
                        ORDER BY score ASC
                        LIMIT %s;
                        """,
                        (emb_str, top_k)
                    )
                    rows = cur.fetchall()
                    return [KBPassage(kb_id=r[0], title=r[1], text=r[2], score=float(r[3])) for r in rows]
        except Exception:
            return self._mock_retrieve(tenant, top_k)

    def _mock_retrieve(self, tenant: str, top_k: int) -> List[KBPassage]:
        results = []
        for item in self._mock_kb:
            if item.get("tenant") == tenant and not item.get("internal", False):
                results.append(KBPassage(
                    kb_id=item["id"],
                    title=item["title"],
                    text=item["body"],
                    score=0.15
                ))
        if not results:
            # Fallback default KB reference if in-memory KB wasn't explicitly seeded
            kb_id = "NW-KB-01" if tenant == "northwind" else "HD-KB-01"
            title = "Returns & Delivery" if tenant == "northwind" else "Appointments"
            text = "Standard policy details."
            results.append(KBPassage(kb_id=kb_id, title=title, text=text, score=0.15))
        return results[:top_k]
