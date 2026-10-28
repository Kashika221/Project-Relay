"""Tests for E1: Model Gateway Token Budgets and held_budget state."""
from relay.contracts import TicketInput
from relay.gateway import ModelGateway
from relay.agents import LeadOrchestrator
from relay.db import Database
from relay.checker import DeterministicChecker

def test_ticket_token_budget_held(checker):
    # Set a very low ticket budget: 5 tokens
    gateway = ModelGateway(ticket_token_budget=5, run_token_budget=10000)
    db = Database()
    lead = LeadOrchestrator(gateway=gateway, db=db, checker=checker)

    ticket = TicketInput(
        id="BUDGET-01",
        tenant="northwind",
        subject="Where is my cycle?",
        body="Order NW-55902 placed 5 days ago.",
        received_at="2026-10-20T10:00:00Z"
    )

    decision = lead.process_ticket(ticket, run_id="test-budget-run")
    assert decision.status == "held_budget"
    assert decision.action == "escalate"

def test_run_token_budget_held(checker):
    # Set a very low run budget: 10 tokens
    gateway = ModelGateway(ticket_token_budget=1000, run_token_budget=10)
    db = Database()
    lead = LeadOrchestrator(gateway=gateway, db=db, checker=checker)

    ticket = TicketInput(
        id="BUDGET-02",
        tenant="harbor",
        subject="Reschedule visit",
        body="Can I reschedule my appointment?",
        received_at="2026-10-20T10:00:00Z"
    )

    decision = lead.process_ticket(ticket, run_id="test-budget-run")
    assert decision.status == "held_budget"
