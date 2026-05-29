import json
import os
from datetime import datetime

FLASH_INPUT_RATE = 0.14 / 1_000_000
FLASH_OUTPUT_RATE = 0.28 / 1_000_000
PRO_INPUT_RATE = 0.435 / 1_000_000
PRO_OUTPUT_RATE = 0.87 / 1_000_000
REASONER_INPUT_RATE = 0.55 / 1_000_000
REASONER_OUTPUT_RATE = 2.19 / 1_000_000

BUDGET_CAP = float(os.getenv("MONTHLY_BUDGET_CAP", "9.00"))
BUDGET_WARNING = float(os.getenv("BUDGET_WARNING_THRESHOLD", "7.00"))

_LOG_PATH = os.getenv("BUDGET_LOG_PATH", "./data/usage.jsonl")


def get_monthly_spend() -> float:
    if not os.path.exists(_LOG_PATH):
        return 0.0
    month = datetime.now().strftime("%Y-%m")
    total = 0.0
    with open(_LOG_PATH) as f:
        for line in f:
            try:
                rec = json.loads(line)
                if rec.get("month") == month:
                    total += rec["cost"]
            except (json.JSONDecodeError, KeyError):
                pass
    return total


def log_usage(model: str, input_tokens: int, output_tokens: int) -> float:
    if "reasoner" in model.lower():
        cost = input_tokens * REASONER_INPUT_RATE + output_tokens * REASONER_OUTPUT_RATE
    elif "pro" in model.lower():
        cost = input_tokens * PRO_INPUT_RATE + output_tokens * PRO_OUTPUT_RATE
    else:
        cost = input_tokens * FLASH_INPUT_RATE + output_tokens * FLASH_OUTPUT_RATE

    os.makedirs(os.path.dirname(os.path.abspath(_LOG_PATH)), exist_ok=True)
    record = {
        "ts": datetime.now().isoformat(),
        "month": datetime.now().strftime("%Y-%m"),
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": round(cost, 8),
    }
    with open(_LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")
    return cost


def is_over_cap() -> bool:
    return get_monthly_spend() >= BUDGET_CAP


def is_warning() -> bool:
    return get_monthly_spend() >= BUDGET_WARNING
