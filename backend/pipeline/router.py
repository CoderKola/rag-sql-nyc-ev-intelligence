import datetime
import re

_TEMPORAL_PATTERNS = re.compile(
    r"\b(this year|current year|so far this year|year to date|ytd|in \d{4})\b",
    re.IGNORECASE,
)

_INFO_RE = re.compile(
    r"\b(rate|price|cost|how much|how to pay|payment|fee|what does it cost|"
    r"how do i|how do you|how can i|opening hour|hours|open|closed|when|"
    r"register|sign.?up|how to use|how to charge|instructions|"
    r"what is plug.?nyc|about the program|about plugnyc|"
    r"contact|phone|email|website|app|ev connect|"
    r"what charger|type of charger|level 2|dc fast|dcfc|"
    r"can i use|do i need|do i have to|is it free)\b",
    re.IGNORECASE,
)

_NEAREST_RE = re.compile(
    r"\b(nearest|closest|near me|close to|near|find.*charger|charger.*near|"
    r"where.*can.*i.*charge|find.*station|station.*near|distance|how far)\b",
    re.IGNORECASE,
)

_EXPLAIN_RE = re.compile(
    r"\b(explain|elaborate|interpret|clarify|what do (these|those|the) (numbers|results|data|figures) mean|"
    r"tell me more|more detail|break.?down (those|these|the) results|what does this (mean|show|tell)|"
    r"dig into|go deeper|unpack)\b",
    re.IGNORECASE,
)

_CONFUSION_RE = re.compile(
    r"\b("
    r"confused|confusing|i.m confused|"
    r"don.t understand|didn.t understand|do not understand|"
    r"not following|i.m not following|"
    r"lost me|you lost me|"
    r"doesn.t make sense|doesn.t add up|make sense of this|help me understand|"
    r"what do you mean|what does that mean|"
    r"analogy|metaphor|"
    r"in simpler terms|plain english|plain language|"
    r"eli5|explain like|layman|layperson|"
    r"can you rephrase|rephrase that|different way|another way|"
    r"why is|why are|why does|why did|why do|"
    r"what causes|what.s causing|"
    r"what explains|what.s the reason|"
    r"what.s driving|what drives|"
    r"what accounts for|"
    r"how does (that|this) work"
    r")\b",
    re.IGNORECASE,
)

_SQL_FROM_HISTORY_RE = re.compile(r"\[SQL used: (.*?)\]$", re.DOTALL)


def data_gap_warning(message: str, data_year_int: int) -> bool:
    current_year = datetime.date.today().year
    if data_year_int >= current_year:
        return False
    for m in re.finditer(r"\b(20\d{2})\b", message):
        if int(m.group(1)) > data_year_int:
            return True
    return bool(_TEMPORAL_PATTERNS.search(message))


def extract_last_sql_from_history(history: list[dict]) -> str | None:
    for msg in reversed(history):
        if msg["role"] == "assistant":
            m = _SQL_FROM_HISTORY_RE.search(msg["content"])
            if m:
                return m.group(1).strip()
    return None


def detect_route(message: str, history: list[dict]) -> str:
    if _NEAREST_RE.search(message):
        return "nearest"
    if _INFO_RE.search(message):
        return "direct"
    if _EXPLAIN_RE.search(message) and extract_last_sql_from_history(history):
        return "explain"
    return "sql"


def needs_reasoning(message: str, history: list[dict]) -> bool:
    if _CONFUSION_RE.search(message):
        return True
    if _EXPLAIN_RE.search(message) and history:
        return True
    return False
