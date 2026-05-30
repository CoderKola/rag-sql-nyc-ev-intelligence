import os

import chromadb
import httpx

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def retrieve_context(query: str, client: chromadb.ClientAPI, n_results: int = 7) -> str:
    # 7 balances coverage (enough columns for complex questions) vs prompt noise (weak matches add tokens, not signal)
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": "nomic-embed-text", "input": query},
        timeout=30,
    )
    resp.raise_for_status()
    query_embedding = resp.json()["embeddings"][0]

    collection = client.get_collection("ev_charging_schema")
    results = collection.query(query_embeddings=[query_embedding], n_results=n_results)

    chunks = []
    for col_id, doc in zip(results["ids"][0], results["documents"][0]):
        chunks.append(f"Column: {col_id}\n{doc}")
    return "\n\n".join(chunks)
