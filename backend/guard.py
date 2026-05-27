from prompts import GUARD_PROMPT


async def is_real_estate_question(user_input: str, client) -> bool:
    """Returns True if the query is real-estate related, False otherwise."""
    raise NotImplementedError
