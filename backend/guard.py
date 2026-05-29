import re

import httpx

from . import llm
from .prompts import GUARD_PROMPT

# Fast-path reject: if none of these EV-specific signals appear, skip the LLM call entirely.
# No trailing \b — allows plurals (stations, sessions, chargers) and inflections (charging).
_EV_SIGNAL = re.compile(
    r"\b(ev\b|electric.?vehicle|charg|station|charger|plug|kwh|kilowatt|"
    r"battery|connector|level.?2|dc.?fast|dcfc|"
    r"parking|garage|"
    r"plugnyc|plug.nyc|"
    r"session|idle.?time|network|utiliz|"
    r"rate|price|cost|fee)",
    re.IGNORECASE,
)

# Short follow-up messages (pronouns, references, continuations) that only make sense in context.
_FOLLOWUP_SIGNAL = re.compile(
    r"\b(that|this|it|those|them|these|the above|the same|previous|last|prior|more|again|"
    r"compare|breakdown|detail|explain|show|investigate|analyze|analyse|elaborate|"
    r"can you|could you|do that|go ahead|yes|sure|please|"
    r"drill|zoom|expand|further|also|instead|now|what about|how about|why|how)\b",
    re.IGNORECASE,
)


async def is_ev_question(
    user_input: str,
    client: httpx.AsyncClient,
    history: list[dict] | None = None,
) -> bool:
    has_ev_signal = bool(_EV_SIGNAL.search(user_input))

    if not has_ev_signal:
        words = len(user_input.split())
        # Very short messages in an active conversation are almost certainly follow-ups —
        # escalate directly without checking for specific signal words.
        if history and words <= 8:
            pass  # fall through to LLM guard
        else:
            is_short_followup = words <= 20 and bool(_FOLLOWUP_SIGNAL.search(user_input))
            if not history or not is_short_followup:
                return False
        # fall through — LLM guard uses history to decide

    answer, _, _ = await llm.call_deepseek(
        client,
        system=GUARD_PROMPT.system,
        user=GUARD_PROMPT.user.format(user_input=user_input),
        history=history or None,
    )
    return answer.strip().upper().startswith("YES")
