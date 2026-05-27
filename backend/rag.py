from typing import Optional
import chromadb


def get_client(persist_path: str) -> chromadb.ClientAPI:
    """Return a ChromaDB persistent client."""
    raise NotImplementedError


def retrieve_context(query: str, client: chromadb.ClientAPI, n_results: int = 5) -> str:
    """Retrieve relevant schema chunks for the given query."""
    raise NotImplementedError
