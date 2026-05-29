# ADR 001 — Conversation History & Context Management

**Status:** Accepted  
**Date:** 2026-05-29

---

## Context

NYC EV Intelligence is a multi-turn analytical chatbot backed by DeepSeek V3 (`deepseek-v4-flash`, 128K token context window — 131,072 tokens exactly, which is 2^17, the binary-aligned capacity that corresponds to 128K). Each user turn runs up to 4 sequential LLM calls: guard → SQL generation → SQL fix (if needed) → interpretation. Each call injects a system prompt, RAG-retrieved schema context, and optionally SQL query results.

The question was: what should be included in conversation history passed to each subsequent LLM call?

---

## Decision

### What goes in history

Each completed assistant turn contributes two things to history:

1. **Text interpretation** (`m.content`) — the Key Findings + Recommendation the model produced. Stays because it's the compact, high-signal summary of what the data showed.
2. **SQL query** (`m.sql`, appended as `[SQL used: ...]`) — the exact DuckDB query that produced the results. Stays because it gives the SQL generation LLM the precise column names, filters, and groupings used in the prior turn, enabling correct follow-up queries ("compare those to 2024", "break that down by month").

### What does NOT go in history

**Raw query result rows** are excluded. A single result set can be 200 rows × N columns — thousands of tokens. Carrying these forward in every subsequent request would:

- Inflate context rapidly across turns
- Push single requests past the ~100K degradation threshold (see Research below)
- Provide diminishing returns since the text interpretation already captures the key findings

Raw results are **re-fetchable**: re-running the SQL query returns identical data. Keeping a placeholder (the SQL) and discarding the raw output is the correct pattern per Anthropic's guidance.

### History limits

- Backend caps at `MAX_HISTORY_TURNS = 10` pairs (configurable via env var)
- Each history entry's content is capped at 2,000 characters server-side
- History is sanitized: only `user`/`assistant` roles accepted, all other keys stripped

### Guard classifier with history

Short contextual follow-ups ("can you do that?", "explain those", "compare it") contain no EV-specific keywords and previously failed the regex fast-path guard, returning the rejection message incorrectly.

Fix: two-layer guard:
1. Regex fast-path — if EV keywords found, proceed to LLM guard (no change)
2. If no EV keywords but message ≤ 20 words AND contains a follow-up signal word AND history exists → escalate to LLM guard with full history so it can judge in context
3. Long messages with no EV keywords and no history → hard reject (no LLM call wasted)

---

## Research Basis

### Context degradation is real and starts before the limit

- **"Context Length Alone Hurts LLM Performance Despite Perfect Retrieval"** (arxiv 2510.05381, Oct 2025) — context length degrades performance even with correct information present, independent of retrieval quality.
- **"Intelligence Degradation in Long-Context LLMs"** (arxiv 2601.15300, Jan 2026) — defines degradation as >30% drop in composite task performance. Finds >50% drops on agentic tasks at **100K tokens** (~78% of a 128K window). Degradation is not linear — it accelerates near the threshold.
- **"Lost in the Middle"** (Liu et al., MIT Press 2024) — U-shaped attention: beginning and end of context are recalled well, middle is not. 30%+ performance drops on multi-doc QA when relevant info lands in the middle.

### Anthropic's recommended pattern for tool results

From **"Effective Context Engineering for AI Agents"** (Anthropic Engineering Blog) and the **Context Engineering Cookbook** (platform.claude.com):

> *"Tool-result clearing: use when tool results are large and re-callable (file reads, API queries). Replace old results with placeholders while keeping the record that the call happened."*

Anthropic's research agent benchmark showed this approach cuts peak context by ~48% (335K → 173K tokens) with no meaningful quality loss.

The three primitives Anthropic recommends, in order of application:

| Primitive | When to use | Cost |
|---|---|---|
| Tool-result clearing | Results are large and re-fetchable | Zero inference cost |
| Compaction | Dialogue + reasoning accumulates | One summarization call |
| Memory | Cross-session persistence needed | Minimal token overhead |

For this app, **tool-result clearing** (keeping SQL, discarding rows) is the right primitive. Compaction and cross-session memory are not yet needed at current conversation lengths.

### DeepSeek V3 context performance

DeepSeek V3's technical report (arxiv 2412.19437) shows strong NIAH (needle-in-a-haystack) scores across its full 128K window. However, NIAH tests simple factoid retrieval — complex reasoning tasks like SQL generation degrade earlier, consistent with the general research above. The safe operating zone for agentic SQL tasks is estimated at <80K tokens per request.

---

## Consequences

- Follow-up questions that reference prior queries ("compare those", "now by month") work correctly because the SQL is in history
- "Explain the results" questions work from the text interpretation in history; for questions requiring specific row-level data not captured in the summary, the correct resolution is to re-run the prior SQL fresh (a future enhancement)
- Context stays small: a 10-turn conversation with typical queries adds ~3–5K tokens of history (text + SQL), well within safe operating range
- The context widget in the UI shows the prompt token count of the most recent LLM call — this is the per-request peak, not a cumulative session total, since SQL results don't accumulate in history

---

## Sources

- [Context Length Alone Hurts LLM Performance Despite Perfect Retrieval](https://arxiv.org/html/2510.05381v1)
- [Intelligence Degradation in Long-Context LLMs](https://arxiv.org/pdf/2601.15300)
- [Lost in the Middle: How Language Models Use Long Contexts](https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00638/119630/Lost-in-the-Middle-How-Language-Models-Use-Long)
- [Effective Context Engineering for AI Agents — Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Context Engineering: Memory, Compaction, and Tool Clearing — Anthropic Cookbook](https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools)
- [DeepSeek-V3 Technical Report](https://arxiv.org/html/2412.19437v1)
