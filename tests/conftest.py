"""Pytest configuration: Sets up deterministic mock environment without Ollama."""
import pytest
import os
import sys
from pathlib import Path
import tempfile
import shutil

# Ensure repository root is on PYTHONPATH
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Set MOCK_LLM so all gateway calls use deterministic responses without network/Ollama
os.environ["MOCK_LLM"] = "true"
os.environ["CHAOS_FAIL_RATE"] = "0.0"

from relay.gateway import ModelGateway
from relay.checker import DeterministicChecker
from relay.approval import ApprovalManager
from relay.db import Database
from relay.agents import LeadOrchestrator

@pytest.fixture
def mock_gateway():
    return ModelGateway()

@pytest.fixture
def checker():
    return DeterministicChecker()

@pytest.fixture
def temp_out_dir():
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.fixture
def approval_manager(temp_out_dir):
    return ApprovalManager(out_dir=temp_out_dir)

@pytest.fixture
def lead_orchestrator(mock_gateway, checker):
    db = Database()
    return LeadOrchestrator(gateway=mock_gateway, db=db, checker=checker)
