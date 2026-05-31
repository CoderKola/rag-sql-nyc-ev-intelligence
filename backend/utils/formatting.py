import json
import re

from tabulate import tabulate


def extract_sql(text: str) -> str:
    m = re.search(r"```(?:sql)?\n?(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else text.strip()


def extract_code(text: str) -> str | None:
    m = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    return m.group(1) if m else None


_HEADER_RE = re.compile(
    r"^(#{1,3}\s+.*|(?:\*\*)?(?:answer|direct answer|python plotly (?:code|chart)|plotly chart|chart code)(?:\*\*)?\s*:?\s*)",
    re.IGNORECASE | re.MULTILINE,
)


def strip_code(text: str) -> str:
    text = re.sub(r"```python\n.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"```map_style\n.*?```", "", text, flags=re.DOTALL)
    text = _HEADER_RE.sub("", text)
    return text.strip()


_RESULTS_CAP = 200


def format_results(df) -> str:
    truncated = len(df) > _RESULTS_CAP
    table = tabulate(df.head(_RESULTS_CAP), headers="keys", tablefmt="github", showindex=False)
    if truncated:
        table += (
            f"\n\n[Note: results truncated — showing {_RESULTS_CAP} of {len(df)} rows. "
            f"Interpret trends cautiously; aggregate further if needed.]"
        )
    return table


def sse(**kwargs) -> str:
    return f"data: {json.dumps(kwargs)}\n\n"
