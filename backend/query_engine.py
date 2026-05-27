import pandas as pd


def run_query(sql: str, parquet_path: str) -> pd.DataFrame | str:
    """Execute a DuckDB SQL query against the parquet file.

    Returns a DataFrame on success, or an error string on failure.
    Enforces a 10-second timeout.
    """
    raise NotImplementedError
