import os
import re

from dotenv import load_dotenv

load_dotenv()

PARQUET_PATH = os.path.abspath(os.getenv("PARQUET_PATH", "./data/parquet/nyc_ev_charging.parquet"))
CHROMA_PATH = os.getenv("CHROMA_PERSIST_PATH", "./data/chroma")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "500"))
CONTEXT_WINDOW = int(os.getenv("CONTEXT_WINDOW", "131072"))
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "10"))
DATA_YEAR = os.getenv("DATA_THROUGH_YEAR", "May 2026")

_year_match = re.search(r"\d{4}", DATA_YEAR)
DATA_YEAR_INT = int(_year_match.group()) if _year_match else 2024

_month_names = [
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
    "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december",
]
_is_partial_year = any(m in DATA_YEAR.lower() for m in _month_names)
DATA_COMPLETE_YEAR = DATA_YEAR_INT - 1 if _is_partial_year else DATA_YEAR_INT
