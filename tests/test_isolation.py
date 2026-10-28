"""Tests for C6: Tenant Isolation with fail-closed behavior."""
import pytest
from relay.contracts import TicketInput
from relay.db import Database

def test_unknown_tenant_rejected_fail_closed():
    """Validates that any tenant other than northwind or harbor raises ValidationError."""
    with pytest.raises(ValueError) as excinfo:
        TicketInput(
            id="TEST-01",
            tenant="evil_tenant",
            subject="Test",
            body="Hello",
            received_at="2026-10-20T00:00:00Z"
        )
    assert "fail-closed" in str(excinfo.value)

def test_tenant_retrieval_isolation():
    """Validates that tenant A never receives passages belonging to tenant B."""
    db = Database()
    # Seed mock data
    db.seed_kb([
        {"id": "NW-KB-01", "tenant": "northwind", "title": "Returns", "body": "Northwind cycle returns.", "internal": False},
        {"id": "HD-KB-01", "tenant": "harbor", "title": "Appointments", "body": "Harbor dental appointments.", "internal": False}
    ])

    nw_passages = db.retrieve_passages(tenant="northwind", query_embedding=[0.1]*768)
    assert len(nw_passages) > 0
    assert all("NW-" in p.kb_id for p in nw_passages)
    assert not any("HD-" in p.kb_id for p in nw_passages)

    hd_passages = db.retrieve_passages(tenant="harbor", query_embedding=[0.1]*768)
    assert len(hd_passages) > 0
    assert all("HD-" in p.kb_id for p in hd_passages)
    assert not any("NW-" in p.kb_id for p in hd_passages)
