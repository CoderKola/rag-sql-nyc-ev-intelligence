import threading

import duckdb
import pandas as pd


def run_query(sql: str, parquet_path: str) -> pd.DataFrame | str:
    """Execute a DuckDB SQL query. Returns a DataFrame on success, error string on failure."""
    result: list = [None]
    error: list = [None]

    def _run() -> None:
        try:
            conn = duckdb.connect()
            result[0] = conn.execute(sql).df()
        except Exception as exc:
            error[0] = str(exc)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=10)

    if t.is_alive():
        return "Query timed out after 10 seconds"
    if error[0]:
        return error[0]
    return result[0]
