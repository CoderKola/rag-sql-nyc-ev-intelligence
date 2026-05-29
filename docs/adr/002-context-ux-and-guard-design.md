# ADR 002 — Context UX, Guard Design & Explain Route

**Status:** Accepted  
**Date:** 2026-05-29

---

## Context

Following ADR 001 (conversation history strategy), this ADR covers three related decisions made in the same session: how to surface context limits to users, how to make the guard classifier handle follow-up messages reliably, and how to handle "explain the results" requests without storing raw query data in history.

---

## Decision 1 — Context Limit UX: Cumulative Client-Side Estimate (Cursor-style)

### What was considered

| Approach | Description | Rejected because |
|---|---|---|
| Token % of 131K | Show per-request prompt_tokens vs context window (131,072 = 2^17, DeepSeek V3's binary-aligned 128K capacity) | Per-request tokens spike based on SQL result size, not conversation length — not monotonic, misleading |
| Turn counter | Show N / MAX_HISTORY_TURNS | Correct but doesn't feel like "filling up" — no visual weight |
| **Cumulative estimate** | Sum `(chars ÷ 4)` per turn, grow monotonically | **Chosen** |

### What was implemented

After each completed turn, estimate tokens as:
```
turnTokens = Math.ceil((userMsg.length + assistantText.length + sql.length) / 4)
convTokens += turnTokens
```

Budget = `max_history_turns × 1000` tokens, fetched from `/api/status`. Default: 10,000 tokens (10 turns × ~1,000 tokens/turn).

Widget: a small rectangle next to the send button — shows `%` label + horizontal fill bar. Amber at 75%, red at 100%. Input disabled at 100% with "Conversation full — start a new chat" placeholder. Hover tooltip shows `~4,200 / 10,000 tokens`.

### Why this approach

- **Grows monotonically** — users see it filling up with each turn, like Cursor and Claude.ai
- **No server round-trip needed** — estimation is pure client-side arithmetic
- **Honest about what accumulates** — only history text and SQL grow per turn; SQL result rows don't (re-fetched fresh each call per ADR 001)
- **Directly tied to the backend cap** — budget is derived from `MAX_HISTORY_TURNS`, so the widget reaches 100% at exactly the turn limit the backend enforces

### Research basis

Context degradation research (see ADR 001) shows >50% performance drops on agentic tasks at ~100K tokens (78% of a 128K window). At ~1,000 tokens/turn, 10 turns of history = ~10K tokens — well within safe range. The budget is a UX signal, not a hard technical limit.

---

## Decision 2 — Two-Layer Guard with History Awareness

### Problem

Short contextual follow-ups ("can you investigate", "can you do that?", "explain that", "yes") contain no EV-specific keywords. The regex fast-path rejected them immediately, returning the "I can only answer EV questions" error to users.

### Solution

Three-layer guard:

**Layer 1 — EV keyword regex (fast-path pass):**
If EV signal found → escalate to LLM guard immediately. No change.

**Layer 2 — Ultra-short with history (≤8 words + history exists):**
Very short messages in an active conversation are almost certainly follow-ups. Escalate to LLM guard unconditionally. Covers: "can you investigate", "yes", "why?", "do that", "explain more".

**Layer 3 — Longer follow-up signal (9–20 words + signal word + history):**
If the message contains a follow-up signal word (`investigate`, `analyze`, `explain`, `elaborate`, `can you`, `could you`, `compare`, `show`, `drill`, `expand`, `why`, `how`, etc.) and history exists → escalate to LLM guard.

**Hard reject:** long message (>20 words) with no EV keywords and no history → rejected without LLM call.

**Guard system prompt** was updated to explicitly instruct the LLM: *"If the conversation history shows an EV-related discussion, short follow-ups like 'can you investigate', 'explain that', 'yes', or 'do that' should be classified YES."*

### Why the LLM guard still matters

The LLM guard (not just the regex) catches ambiguous cases — e.g., "what about the weather?" in an EV conversation should be NO. The regex layers only decide whether to escalate to the LLM, not the final answer.

---

## Decision 3 — Explain Route: Re-Run Prior SQL on Elaboration Requests

### Problem

When users ask "explain the results" or "elaborate on that", two things could happen:
1. The pipeline treats it as a new SQL query → generates a redundant or wrong query
2. The pipeline tries to answer from history text alone → may miss specific numbers not in the summary

### Solution

A dedicated `explain` route in the pipeline. Triggered when:
- Message matches elaboration intent (`explain`, `elaborate`, `interpret`, `tell me more`, `dig into`, `clarify`, etc.)
- AND the conversation history contains a prior SQL query (parsed from `[SQL used: ...]` appended to assistant entries per ADR 001)

The handler:
1. Extracts the prior SQL from history
2. Re-runs it fresh against the parquet file
3. Passes the live result rows to the interpretation LLM with the user's elaboration request
4. Falls back to answering from history text if the SQL re-run fails

### Why re-run instead of storing results in history

Raw result rows can be 200+ rows × N columns — thousands of tokens. Storing them in history would rapidly inflate context per ADR 001's analysis. Re-running is zero-cost (DuckDB on a local parquet file, <1s) and always returns current data.

This follows Anthropic's tool-result clearing pattern: keep the record of what was called (SQL query), discard the output (result rows), re-fetch when needed.

---

## Consequences

- Users get a Cursor-style "filling up" experience — clear, progressive, honest
- Short follow-ups no longer bounce off the guard incorrectly
- "Explain the results" and similar elaboration requests re-run prior SQL and produce fresh, full-data interpretations
- The `MAX_HISTORY_TURNS` env var now controls both the backend history cap and the frontend budget — one knob for both
- The `context_tokens` field still returned in SSE events (server-side prompt token count) but no longer drives the UI — available for future debugging or analytics use
