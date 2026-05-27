import os

FLASH_INPUT_RATE = 0.14 / 1_000_000
FLASH_OUTPUT_RATE = 0.28 / 1_000_000
PRO_INPUT_RATE = 0.435 / 1_000_000
PRO_OUTPUT_RATE = 0.87 / 1_000_000

BUDGET_CAP = float(os.getenv("MONTHLY_BUDGET_CAP", "9.00"))
BUDGET_WARNING = float(os.getenv("BUDGET_WARNING_THRESHOLD", "7.00"))


def get_monthly_spend() -> float:
    """Return total spend in USD for the current calendar month."""
    raise NotImplementedError


def log_usage(model: str, input_tokens: int, output_tokens: int) -> float:
    """Log a request and return the cost in USD."""
    raise NotImplementedError


def is_over_cap() -> bool:
    """Return True if monthly spend >= BUDGET_CAP."""
    raise NotImplementedError


def is_warning() -> bool:
    """Return True if monthly spend >= BUDGET_WARNING."""
    raise NotImplementedError
