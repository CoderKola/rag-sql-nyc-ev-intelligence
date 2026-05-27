"""
Socrata → parquet + ChromaDB schema index.

Run once locally after EDA findings are confirmed.
Usage: python ingest.py
"""
import os

DATASET_ID = "w2pb-icbu"
DOMAIN = "data.cityofnewyork.us"
PARQUET_PATH = os.getenv("PARQUET_PATH", "./data/parquet/property_sales.parquet")
CHROMA_PATH = os.getenv("CHROMA_PERSIST_PATH", "./data/chroma")
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def fetch_and_save() -> None:
    """Pull full dataset from Socrata and save as parquet."""
    raise NotImplementedError


def build_chroma_index() -> None:
    """Generate schema chunks, embed with nomic-embed-text, store in ChromaDB."""
    raise NotImplementedError


if __name__ == "__main__":
    fetch_and_save()
    build_chroma_index()
    print("Ingest complete.")
