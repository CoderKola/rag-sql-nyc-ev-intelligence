import os

ALLOWED_IMPORTS = {"plotly", "pandas", "numpy", "math", "random", "collections", "itertools"}


def run_chart_code(code: str) -> dict:
    """Execute Plotly chart code in a subprocess sandbox.

    Returns {"success": bool, "chart_html": str | None, "error": str | None}
    """
    raise NotImplementedError
