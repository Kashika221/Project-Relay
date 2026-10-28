"""Configuration module for Project Relay."""
import os
from pathlib import Path
from pydantic import BaseModel, Field

class RelayConfig(BaseModel):
    # Ollama settings
    ollama_base_url: str = Field(default="http://localhost:11434")
    triage_model: str = Field(default="qwen2.5:1.5b")
    drafter_model: str = Field(default="qwen2.5:3b")
    embed_model: str = Field(default="nomic-embed-text")
    fallback_model: str = Field(default="qwen2.5:1.5b")

    # Budgets
    ticket_token_budget: int = Field(default=4000)
    run_token_budget: int = Field(default=50000)

    # Database
    database_url: str = Field(default="postgresql://relay_app:relay_secret@localhost:5432/relay_db")
    admin_database_url: str = Field(default="postgresql://postgres:relay@localhost:5432/postgres")
    
    # Chaos / Testing
    chaos_fail_rate: float = Field(default=0.0)
    mock_llm: bool = Field(default=False)

    # Paths
    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent)

    @classmethod
    def from_env(cls) -> "RelayConfig":
        return cls(
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            triage_model=os.getenv("TRIAGE_MODEL", "qwen2.5:1.5b"),
            drafter_model=os.getenv("DRAFTER_MODEL", "qwen2.5:3b"),
            embed_model=os.getenv("EMBED_MODEL", "nomic-embed-text"),
            fallback_model=os.getenv("FALLBACK_MODEL", "qwen2.5:1.5b"),
            ticket_token_budget=int(os.getenv("TICKET_TOKEN_BUDGET", "4000")),
            run_token_budget=int(os.getenv("RUN_TOKEN_BUDGET", "50000")),
            database_url=os.getenv("DATABASE_URL", "postgresql://relay_app:relay_secret@localhost:5432/relay_db"),
            admin_database_url=os.getenv("ADMIN_DATABASE_URL", "postgresql://postgres:relay@localhost:5432/postgres"),
            chaos_fail_rate=float(os.getenv("CHAOS_FAIL_RATE", "0.0")),
            mock_llm=os.getenv("MOCK_LLM", "false").lower() in ("true", "1", "yes")
        )

config = RelayConfig.from_env()
