"""
AWS Lambda — chart executor.
Receives Plotly Python code, runs it, returns self-contained HTML.
"""
import json


def lambda_handler(event, context):
    """
    event: { "code": "import plotly..." }
    returns: { "chart_html": "<div>...</div>" }
    """
    raise NotImplementedError
