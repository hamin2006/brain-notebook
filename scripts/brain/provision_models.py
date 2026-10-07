"""Configure Brain Notebook's recommended OpenRouter models through its API.

Creates (or reuses) an OpenRouter credential, registers the chat, research and
embedding models, and sets them as defaults. Safe to re-run. The key is only
ever sent to the Brain Notebook API (where it is stored encrypted).

Usage (on the machine running the API; stdlib only, no venv needed):
  OPENROUTER_API_KEY=sk-or-... python3 scripts/brain/provision_models.py
  python3 scripts/brain/provision_models.py --key-file path/to/.env   # a line OPENROUTER_API_KEY=...
  python3 scripts/brain/provision_models.py --api http://127.0.0.1:5055/api
If neither is given, the key is asked for interactively.
"""

import argparse
import getpass
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("BRAIN_API_URL", "http://127.0.0.1:5055/api")
CHAT_MODEL = "z-ai/glm-5.3-flash"
# The agent's research loop makes many calls over a growing transcript, so it runs
# on a model 5x cheaper than the chat model, which only writes the final answer.
# Qwen3.7 Flash: tool calling and vision (the agent's view tool) at $0.03/$0.13 per M.
RESEARCH_MODEL = "qwen/qwen3.7-flash"
# Qwen3-Embedding-8B on OpenRouter: the strongest model of the family for ~$0.01/M
# tokens. Chat already sends notebook text to OpenRouter, so embedding locally
# bought no privacy, and the GTX 1660 could only run the 0.6B model at a usable speed.
EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"


def call(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:300]}")


def read_key(path: str) -> str:
    for line in Path(path).expanduser().read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit(f"OPENROUTER_API_KEY not found in {path}")


def ensure_credential(provider: str, name: str, modalities, **fields) -> str:
    for cred in call("GET", f"/credentials/by-provider/{provider}") or []:
        if cred.get("name") == name:
            if set(modalities) - set(cred.get("modalities") or []):
                call("PUT", f"/credentials/{cred['id']}", {"modalities": modalities})
            return cred["id"]
    created = call(
        "POST",
        "/credentials",
        {"name": name, "provider": provider, "modalities": modalities, **fields},
    )
    return created["id"]


def ensure_model(name: str, provider: str, type_: str, credential: str) -> str:
    for model in call("GET", "/models") or []:
        if (
            model["name"] == name
            and model["provider"] == provider
            and model["type"] == type_
        ):
            return model["id"]
    created = call(
        "POST",
        "/models",
        {"name": name, "provider": provider, "type": type_, "credential": credential},
    )
    return created["id"]


def main():
    global API
    ap = argparse.ArgumentParser()
    ap.add_argument("--key-file", help="dotenv file with OPENROUTER_API_KEY=...")
    ap.add_argument("--api", default=API, help="Brain Notebook API base URL")
    args = ap.parse_args()
    API = args.api.rstrip("/")
    if args.key_file:
        key = read_key(args.key_file)
    else:
        key = os.environ.get("OPENROUTER_API_KEY") or getpass.getpass(
            "OpenRouter API key: "
        )
    if not key.strip():
        raise SystemExit("No OpenRouter API key given.")

    openrouter = ensure_credential(
        "openrouter",
        "brain-openrouter",
        ["language", "embedding"],
        api_key=key.strip(),
    )

    chat = ensure_model(CHAT_MODEL, "openrouter", "language", openrouter)
    research = ensure_model(RESEARCH_MODEL, "openrouter", "language", openrouter)
    embedding = ensure_model(EMBEDDING_MODEL, "openrouter", "embedding", openrouter)

    defaults = call("GET", "/models/defaults") or {}
    defaults.update(
        default_chat_model=chat,
        default_transformation_model=chat,
        default_tools_model=research,
        large_context_model=chat,
        default_embedding_model=embedding,
    )
    call("PUT", "/models/defaults", defaults)

    for model_id, label in (
        (chat, CHAT_MODEL),
        (research, RESEARCH_MODEL),
        (embedding, EMBEDDING_MODEL),
    ):
        result = call("POST", f"/models/{model_id}/test")
        print(
            f"{label}: {'ok' if result.get('success') else 'FAILED'} - {str(result.get('message', ''))[:120]}"
        )


if __name__ == "__main__":
    main()
