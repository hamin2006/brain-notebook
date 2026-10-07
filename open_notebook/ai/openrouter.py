"""OpenRouter endpoints that LangChain/esperanto don't cover: rerank and
multimodal (image) embeddings. The key comes from the configured OpenRouter
credential (or OPENROUTER_API_KEY)."""

from typing import Any, Dict, List, Sequence, Tuple

import httpx

from open_notebook.ai.key_provider import get_api_key
from open_notebook.exceptions import ConfigurationError, ExternalServiceError

BASE_URL = "https://openrouter.ai/api/v1"
TIMEOUT = 60.0


async def _post(path: str, body: Dict[str, Any]) -> Dict[str, Any]:
    key = await get_api_key("openrouter")
    if not key:
        raise ConfigurationError("No OpenRouter credential is configured.")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            BASE_URL + path,
            json=body,
            headers={"Authorization": f"Bearer {key}"},
        )
    if response.status_code >= 400:
        raise ExternalServiceError(
            f"OpenRouter {path} failed ({response.status_code}): {response.text[:200]}"
        )
    return response.json()


async def rerank(
    model: str, query: str, documents: Sequence[str], top_n: int
) -> List[Tuple[int, float]]:
    """(document index, relevance score) pairs, best first."""
    if not documents:
        return []
    data = await _post(
        "/rerank",
        {
            "model": model,
            "query": query,
            "documents": list(documents),
            "top_n": min(top_n, len(documents)),
        },
    )
    return [(int(r["index"]), float(r["relevance_score"])) for r in data["results"]]


def image_input(data_url: str) -> Dict[str, Any]:
    return {"content": [{"type": "image_url", "image_url": {"url": data_url}}]}


def text_input(text: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


async def embed_multimodal(
    model: str, inputs: Sequence[Dict[str, Any]]
) -> List[List[float]]:
    """Embeddings for image and/or text inputs (see image_input / text_input),
    in input order."""
    if not inputs:
        return []
    data = await _post(
        "/embeddings",
        {"model": model, "input": list(inputs), "encoding_format": "float"},
    )
    rows = sorted(data["data"], key=lambda r: r["index"])
    return [r["embedding"] for r in rows]
