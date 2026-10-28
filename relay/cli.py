"""Unified CLI for Project Relay: demo, run, approve, reject, list, eval, and report."""
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table

from relay.config import config
from relay.contracts import TicketInput, DecisionRecord
from relay.agents import LeadOrchestrator
from relay.gateway import ModelGateway
from relay.db import Database
from relay.checker import DeterministicChecker
from relay.approval import ApprovalManager
from relay.eval import Evaluator

app = typer.Typer(name="relay", help="Project Relay: Multi-Tenant AI Agent Support Desk")
console = Console()

@app.command()
def demo():
    """C1: One command demo. Seeds KBs, processes both inboxes, prints approval queue."""
    console.print("[bold green]Starting Project Relay Demo...[/bold green]")
    db = Database()
    
    # 1. Seed Knowledge Bases
    kb_data = []
    for tenant in ["northwind", "harbor"]:
        kb_file = Path("data") / tenant / "kb.jsonl"
        if kb_file.exists():
            with open(kb_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        kb_data.append(json.loads(line))
    db.seed_kb(kb_data)
    console.print(f"[cyan]Loaded and seeded {len(kb_data)} KB articles.[/cyan]")

    # 2. Process both inboxes
    inbox_files = [Path("data/northwind/tickets.jsonl"), Path("data/harbor/tickets.jsonl")]
    run_id = f"demo-{uuid.uuid4().hex[:6]}"
    
    out_dir = Path("out")
    out_dir.mkdir(parents=True, exist_ok=True)
    decisions_path = out_dir / "decisions.jsonl"

    gateway = ModelGateway()
    lead = LeadOrchestrator(gateway, db, DeterministicChecker())

    total_processed = 0
    with open(decisions_path, "w", encoding="utf-8") as df:
        for ibox in inbox_files:
            if not ibox.exists():
                continue
            with open(ibox, "r", encoding="utf-8") as inf:
                for line in inf:
                    if not line.strip():
                        continue
                    ticket = TicketInput.model_validate_json(line)
                    dec = lead.process_ticket(ticket, run_id=run_id)
                    df.write(dec.model_dump_json() + "\n")
                    total_processed += 1

    console.print(f"[bold green]Successfully processed {total_processed} tickets into out/decisions.jsonl[/bold green]")

    # 3. Print Approval Queue
    list_queue()

@app.command("run")
def run_inbox(inbox: str = typer.Option(..., "--inbox", "-i", help="Path to input tickets JSONL file")):
    """C7: Processes any input tickets JSONL file idempotently."""
    inbox_path = Path(inbox)
    if not inbox_path.exists():
        console.print(f"[red]Error: inbox file '{inbox}' does not exist.[/red]")
        sys.exit(1)

    out_dir = Path("out")
    out_dir.mkdir(parents=True, exist_ok=True)
    decisions_path = out_dir / "decisions.jsonl"

    # Read existing decision ticket IDs to avoid duplicates
    existing_ids = set()
    if decisions_path.exists():
        with open(decisions_path, "r", encoding="utf-8") as df:
            for line in df:
                if line.strip():
                    existing_ids.add(json.loads(line).get("ticket_id"))

    db = Database()
    gateway = ModelGateway()
    lead = LeadOrchestrator(gateway, db, DeterministicChecker())
    run_id = f"run-{uuid.uuid4().hex[:6]}"

    processed = 0
    with open(decisions_path, "a", encoding="utf-8") as df:
        with open(inbox_path, "r", encoding="utf-8") as inf:
            for line in inf:
                if not line.strip():
                    continue
                ticket = TicketInput.model_validate_json(line)
                if ticket.id in existing_ids:
                    continue
                dec = lead.process_ticket(ticket, run_id=run_id)
                df.write(dec.model_dump_json() + "\n")
                existing_ids.add(ticket.id)
                processed += 1

    console.print(f"[green]Processed {processed} new tickets from {inbox_path}.[/green]")

@app.command("list")
def list_queue():
    """C5: Lists all tickets awaiting human approval."""
    mgr = ApprovalManager()
    pending = mgr.list_pending()
    
    table = Table(title="Project Relay: Approval Queue (Pending Human Review)")
    table.add_column("Ticket ID", style="bold cyan")
    table.add_column("Tenant", style="magenta")
    table.add_column("Category", style="yellow")
    table.add_column("Priority", style="red")
    table.add_column("Action", style="green")
    table.add_column("Status", style="blue")
    table.add_column("Draft Preview", style="white")

    for p in pending:
        preview = (p.draft_reply[:60] + "...") if p.draft_reply else "None"
        table.add_row(p.ticket_id, p.tenant, p.category, p.priority, p.action, p.status, preview)

    console.print(table)

@app.command("show")
def show_ticket(ticket_id: str):
    """C5: Shows full decision details for a ticket."""
    mgr = ApprovalManager()
    dec = mgr.show(ticket_id)
    if not dec:
        console.print(f"[red]Ticket '{ticket_id}' not found.[/red]")
        return
    console.print(dec.model_dump_json(indent=2))

@app.command("approve")
def approve_ticket(ticket_id: str, approver: str = "human_operator"):
    """C5: Approves a ticket draft, writing exactly-once to outbox.jsonl."""
    mgr = ApprovalManager()
    res = mgr.approve(ticket_id, approver=approver)
    if res:
        console.print(f"[bold green]Ticket {ticket_id} approved by {approver}![/bold green]")
        console.print(f"Idempotency Key: {res.idempotency_key}")
    else:
        console.print(f"[yellow]Ticket {ticket_id} could not be approved (already approved or not pending).[/yellow]")

@app.command("reject")
def reject_ticket(ticket_id: str, reason: str = typer.Option(..., "--reason", "-r", help="Reason for rejection"), approver: str = "human_operator"):
    """C5: Rejects a draft with an audited reason and sends it back to the drafter."""
    mgr = ApprovalManager()
    ok = mgr.reject(ticket_id, reason=reason, approver=approver)
    if ok:
        console.print(f"[bold red]Ticket {ticket_id} rejected. Reason: '{reason}'[/bold red]")
    else:
        console.print(f"[red]Ticket {ticket_id} not found.[/red]")

@app.command("eval")
def run_evaluation(runs: int = 5):
    """E3: Runs evaluation harness over golden set N times and writes docs/EVAL.md."""
    console.print(f"[cyan]Running evaluation harness ({runs} runs)...[/cyan]")
    evaluator = Evaluator(data_dir=Path("data"), out_eval_dir=Path("eval/runs"))
    evaluator.run_eval(num_runs=runs)
    console.print("[bold green]Evaluation complete! Output written to eval/runs/ and docs/EVAL.md[/bold green]")

@app.command("report")
def generate_report(
    view: str = typer.Option("internal", "--view", "-v", help="View type: internal or client"),
    tenant: Optional[str] = typer.Option(None, "--tenant", "-t", help="Tenant filter for client view (northwind or harbor)")
):
    """S2: Generates internal telemetry report or client-facing summary."""
    decisions_path = Path("out/decisions.jsonl")
    if not decisions_path.exists():
        console.print("[yellow]No decisions found in out/decisions.jsonl[/yellow]")
        return

    decisions = []
    with open(decisions_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                decisions.append(json.loads(line))

    if view == "internal":
        table = Table(title="Project Relay: Internal Telemetry Report")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        total_tokens_in = sum(d.get("tokens_in", 0) for d in decisions)
        total_tokens_out = sum(d.get("tokens_out", 0) for d in decisions)
        avg_latency = sum(d.get("latency_ms", 0) for d in decisions) / max(len(decisions), 1)

        table.add_row("Total Tickets Processed", str(len(decisions)))
        table.add_row("Total Input Tokens", str(total_tokens_in))
        table.add_row("Total Output Tokens", str(total_tokens_out))
        table.add_row("Average Latency", f"{avg_latency:.1f} ms")
        table.add_row("Escalated Tickets", str(sum(1 for d in decisions if d.get("action") == "escalate")))
        console.print(table)

    elif view == "client":
        if not tenant:
            console.print("[red]Error: --tenant must be specified for client view.[/red]")
            return
        
        tenant_decs = [d for d in decisions if d.get("tenant") == tenant]
        table = Table(title=f"Project Relay: Client Summary Report ({tenant.title()})")
        table.add_column("Category", style="yellow")
        table.add_column("Action", style="green")
        table.add_column("Count", style="cyan")

        counts = {}
        for d in tenant_decs:
            key = (d.get("category", "other"), d.get("action", "unknown"))
            counts[key] = counts.get(key, 0) + 1

        for (cat, act), cnt in counts.items():
            table.add_row(cat, act, str(cnt))

        console.print(table)
    else:
        console.print(f"[red]Unknown view '{view}'. Choose 'internal' or 'client'.[/red]")

if __name__ == "__main__":
    app()
