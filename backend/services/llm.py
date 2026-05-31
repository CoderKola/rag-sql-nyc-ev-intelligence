import httpx


async def call_deepseek_reasoner(
    client: httpx.AsyncClient,
    *,
    system: str,
    user: str,
    history: list[dict] | None = None,
) -> tuple[str, str, int, int]:
    """Returns (reasoning_content, answer_content, prompt_tokens, completion_tokens)."""
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user})

    resp = await client.post(
        "https://api.deepseek.com/chat/completions",
        json={"model": "deepseek-reasoner", "messages": messages},
        timeout=120.0,
    )
    if not resp.is_success:
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        msg = body.get("error", {}).get("message", f"DeepSeek API error {resp.status_code}")
        raise ValueError(msg)
    data = resp.json()
    msg_obj = data["choices"][0]["message"]
    reasoning = msg_obj.get("reasoning_content") or ""
    content = msg_obj.get("content") or ""
    usage = data.get("usage", {})
    return reasoning, content, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)


async def call_deepseek(
    client: httpx.AsyncClient,
    *,
    system: str,
    user: str,
    history: list[dict] | None = None,
) -> tuple[str, int, int]:
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user})

    resp = await client.post(
        "https://api.deepseek.com/chat/completions",
        json={
            "model": "deepseek-v4-flash",
            "messages": messages,
            "temperature": 0,
        },
    )
    if not resp.is_success:
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        msg = body.get("error", {}).get("message", f"DeepSeek API error {resp.status_code}")
        raise ValueError(msg)
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return content, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
