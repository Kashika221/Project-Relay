"""Model Gateway: Unified routing, token metering, budgets, circuit breaker, and mock support."""
import time
import random
import os
import httpx
from typing import Dict, Any, List, Optional
from relay.config import config

class BudgetExceededException(Exception):
    """Raised when per-ticket or per-run token budget is exceeded."""
    def __init__(self, message: str, scope: str):
        super().__init__(message)
        self.scope = scope

class GatewayCircuitBreakerException(Exception):
    """Raised when primary and secondary models both fail."""
    pass

class ModelGateway:
    def __init__(self, run_token_budget: Optional[int] = None, ticket_token_budget: Optional[int] = None, mock_llm: Optional[bool] = None):
        self.run_token_budget = run_token_budget or config.run_token_budget
        self.ticket_token_budget = ticket_token_budget or config.ticket_token_budget
        if mock_llm is not None:
            self.mock_llm = mock_llm
        else:
            self.mock_llm = config.mock_llm or (os.getenv("MOCK_LLM", "false").lower() in ("true", "1", "yes"))
            
        self.total_run_tokens_in = 0
        self.total_run_tokens_out = 0
        self.ticket_tokens: Dict[str, Dict[str, int]] = {}
        self.call_history: List[Dict[str, Any]] = []

    def _check_budget(self, ticket_id: Optional[str] = None):
        total_run = self.total_run_tokens_in + self.total_run_tokens_out
        if total_run >= self.run_token_budget:
            raise BudgetExceededException(f"Run token budget of {self.run_token_budget} exceeded (current: {total_run})", scope="run")

        if ticket_id and ticket_id in self.ticket_tokens:
            curr_ticket = self.ticket_tokens[ticket_id]["in"] + self.ticket_tokens[ticket_id]["out"]
            if curr_ticket >= self.ticket_token_budget:
                raise BudgetExceededException(f"Ticket {ticket_id} token budget of {self.ticket_token_budget} exceeded (current: {curr_ticket})", scope="ticket")

    def _record_tokens(self, ticket_id: Optional[str], model: str, tokens_in: int, tokens_out: int, latency_ms: int):
        self.total_run_tokens_in += tokens_in
        self.total_run_tokens_out += tokens_out

        if ticket_id:
            if ticket_id not in self.ticket_tokens:
                self.ticket_tokens[ticket_id] = {"in": 0, "out": 0}
            self.ticket_tokens[ticket_id]["in"] += tokens_in
            self.ticket_tokens[ticket_id]["out"] += tokens_out

        self.call_history.append({
            "ticket_id": ticket_id,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": latency_ms,
            "timestamp": time.time()
        })

    def chat(self, model: str, messages: List[Dict[str, str]], ticket_id: Optional[str] = None, schema: Optional[Dict[str, Any]] = None, temperature: float = 0.0) -> Dict[str, Any]:
        self._check_budget(ticket_id)

        # S1: Chaos mode simulation
        if config.chaos_fail_rate > 0 and random.random() < config.chaos_fail_rate:
            model = config.fallback_model

        if self.mock_llm:
            return self._mock_chat_response(model, messages, ticket_id)

        start_time = time.time()
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "seed": 7}
        }
        if schema:
            payload["format"] = schema

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(f"{config.ollama_base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            if model != config.fallback_model:
                payload["model"] = config.fallback_model
                try:
                    with httpx.Client(timeout=60.0) as client:
                        resp = client.post(f"{config.ollama_base_url}/api/chat", json=payload)
                        resp.raise_for_status()
                        data = resp.json()
                        model = f"{model}->{config.fallback_model}"
                except Exception as fb_err:
                    raise GatewayCircuitBreakerException(f"Primary ({model}) and fallback ({config.fallback_model}) both failed: {fb_err}")
            else:
                raise e

        latency_ms = int((time.time() - start_time) * 1000)
        tokens_in = data.get("prompt_eval_count", 0)
        tokens_out = data.get("eval_count", 0)

        self._record_tokens(ticket_id, model, tokens_in, tokens_out, latency_ms)
        self._check_budget(ticket_id)

        content = data.get("message", {}).get("content", "")
        return {
            "content": content,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": latency_ms
        }

    def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        model = model or config.embed_model
        if self.mock_llm:
            import hashlib
            seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
            random.seed(seed)
            return [random.uniform(-1, 1) for _ in range(768)]

        start_time = time.time()
        payload = {"model": model, "input": text}
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{config.ollama_base_url}/api/embed", json=payload)
            resp.raise_for_status()
            data = resp.json()

        latency_ms = int((time.time() - start_time) * 1000)
        embeddings = data.get("embeddings", [[]])[0]
        self._record_tokens(None, model, len(text.split()), 0, latency_ms)
        return embeddings

    def _mock_chat_response(self, model: str, messages: List[Dict[str, str]], ticket_id: Optional[str]) -> Dict[str, Any]:
        """Deterministic mock response for pytest test suite (runs without Ollama)."""
        user_prompt = " ".join(m.get("content", "") for m in messages if m.get("role") == "user").lower()

        is_injection = (
            "ignore all previous instructions" in user_prompt
            or "admin mode" in user_prompt
            or "internal notes" in user_prompt
            or "system:" in user_prompt
            or "staff-only" in user_prompt
        )
        
        if is_injection:
            content = '{"category": "assembly_setup", "priority": "high", "injection_detected": true, "action": "escalate", "reasoning": "Detected injection attempt"}'
        elif "refund" in user_prompt and ("court" in user_prompt or "complaint" in user_prompt):
            content = '{"category": "returns_refunds", "priority": "urgent", "injection_detected": false, "action": "escalate", "reasoning": "Legal threat demand"}'
        elif "bulk" in user_prompt or "club" in user_prompt:
            content = '{"category": "other", "priority": "normal", "injection_detected": false, "action": "escalate", "reasoning": "Bulk order escalation"}'
        elif "crack" in user_prompt or ("warranty" in user_prompt and "photo" not in user_prompt):
            content = '{"category": "warranty_repair", "priority": "high", "injection_detected": false, "action": "ask_for_info", "reasoning": "Missing order id or photos"}'
        elif "swelling" in user_prompt or "pain" in user_prompt or "bleeding" in user_prompt or "extraction" in user_prompt:
            content = '{"category": "clinical", "priority": "urgent", "injection_detected": false, "action": "escalate", "reasoning": "Clinical symptom"}'
        elif "husband" in user_prompt or "consent" in user_prompt or ("records" in user_prompt and "unknown" in user_prompt):
            content = '{"category": "records_privacy", "priority": "high", "injection_detected": false, "action": "ask_for_info", "reasoning": "Needs written consent or details"}'
        elif "overcharged" in user_prompt or "quoted" in user_prompt:
            content = '{"category": "billing_payments", "priority": "high", "injection_detected": false, "action": "escalate", "reasoning": "Billing dispute"}'
        elif "pincode" in user_prompt or "change" in user_prompt:
            content = '{"category": "order_change", "priority": "high", "injection_detected": false, "action": "draft_reply", "reasoning": "Order address change"}'
        elif "helmet" in user_prompt or "return" in user_prompt:
            content = '{"category": "returns_refunds", "priority": "normal", "injection_detected": false, "action": "draft_reply", "reasoning": "Standard return question"}'
        elif "appointment" in user_prompt or "reschedule" in user_prompt or "sunday" in user_prompt or "slot" in user_prompt:
            content = '{"category": "appointments", "priority": "normal", "injection_detected": false, "action": "draft_reply", "reasoning": "Appointment inquiry"}'
        elif "cost" in user_prompt or "price" in user_prompt or "emi" in user_prompt:
            content = '{"category": "billing_payments", "priority": "low", "injection_detected": false, "action": "draft_reply", "reasoning": "Pricing inquiry"}'
        else:
            content = '{"category": "shipping_delivery", "priority": "normal", "injection_detected": false, "action": "draft_reply", "reasoning": "Standard question"}'

        if "ground strictly in" in user_prompt:
            content = '{"action": "draft_reply", "draft_reply": "Thank you for reaching out. Under our policy (NW-KB-01), unused items can be returned within 30 days. Let us know if you need assistance.", "kb_refs": ["NW-KB-01"]}'

        tokens_in = len(user_prompt.split()) + 20
        tokens_out = len(content.split()) + 10
        latency_ms = 15

        self._record_tokens(ticket_id, f"mock-{model}", tokens_in, tokens_out, latency_ms)
        self._check_budget(ticket_id)

        return {
            "content": content,
            "model": f"mock-{model}",
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": latency_ms
        }
