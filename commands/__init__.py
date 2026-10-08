"""Surreal-commands integration for Open Notebook"""

# The worker starts via `python -m commands.worker` (commands/worker.py),
# so this package is imported before the worker connects to SurrealDB. Inject
# the internal DB hosts into no_proxy first so the DB websocket is never
# tunnelled through a configured HTTP proxy (issue #1160).
from open_notebook.utils.proxy import ensure_internal_no_proxy

ensure_internal_no_proxy()

from .analyze_commands import analyze_source_command
from .concept_commands import extract_concepts_command
from .embedding_commands import (
    embed_insight_command,
    embed_note_command,
    embed_source_command,
    rebuild_embeddings_command,
)
from .page_commands import caption_pages_command
from .page_embedding_commands import embed_pages_command
from .podcast_commands import generate_podcast_command
from .source_commands import process_source_command

__all__ = [
    # Page commands
    "caption_pages_command",
    "analyze_source_command",
    "embed_pages_command",
    "extract_concepts_command",
    # Embedding commands
    "embed_note_command",
    "embed_insight_command",
    "embed_source_command",
    "rebuild_embeddings_command",
    # Other commands
    "generate_podcast_command",
    "process_source_command",
]
