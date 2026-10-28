# Project Relay: Limitations & Future Work

This document outlines current architectural limitations, potential edge cases, and proposed enhancements if granted an additional 24 hours of development time.

---

## 1. What is Missing or Simplified
1. **Dynamic HNSW Vector Re-indexing**: In the current setup, vector embeddings are loaded into pgvector using flat sequential indexing. For multi-thousand article knowledge bases, an HNSW or IVFFlat index with cosine operator classes is required.
2. **Multi-turn Clarification Tracking**: For tickets resulting in `ask_for_info`, the customer's eventual reply would create a new ticket unless linked via conversation thread IDs. A customer session store would unify follow-up replies into existing tickets.
3. **Web Management Dashboard**: Currently all approvals and telemetry are handled via the Typer CLI (`relay list`, `relay show`, `relay approve`, `relay report`). A lightweight FastAPI + React dashboard would enhance operator convenience.

---

## 2. What is Fragile
1. **Model Context Windows on Small Quantized Models**: Very long customer emails (e.g. pasted invoice threads) combined with 3 retrieved passages may push against the 2048-token context window of `qwen2.5:1.5b`. A chunking and passage compression step is advised.
2. **Hinglish Slang Variations**: While `qwen2.5:1.5b` handles standard Romanized Hindi well (`"kab aayega"`, `"mein hoon"`), heavily mixed dialectal phonetic spellings could lead to category ambiguity without few-shot prompting examples.

---

## 3. What We Would Do With One More Day
1. **End-to-End Async Worker Pipeline**: Convert worker execution from synchronous multi-threading to `asyncio` + `asyncpg` to increase ticket throughput by 5-10x on multi-core systems.
2. **Automated Few-Shot In-Context Learning**: Dynamically select 2 few-shot exemplars from verified historical approvals to improve drafter phrasing alignment.
3. **Continuous Evaluation Dashboard in CI**: Automatically generate HTML diff reports of evaluation runs during GitHub Actions PR checks.
