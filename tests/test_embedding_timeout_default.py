"""Open Notebook defaults ESPERANTO_EMBEDDING_TIMEOUT to 180 s.

esperanto's 60 s embedding default is shorter than one batch takes on a modest
local GPU, so local embedding batches timed out and retried indefinitely.
"""

import pytest

from open_notebook.config import (
    DEFAULT_EMBEDDING_TIMEOUT_SECONDS,
    ensure_embedding_timeout_default,
)


def test_default_applies_when_unset():
    env: dict[str, str] = {}
    ensure_embedding_timeout_default(env)
    assert env["ESPERANTO_EMBEDDING_TIMEOUT"] == "180"
    assert DEFAULT_EMBEDDING_TIMEOUT_SECONDS == 180


@pytest.mark.parametrize("value", ["", "   "])
def test_default_applies_when_blank(value):
    env = {"ESPERANTO_EMBEDDING_TIMEOUT": value}
    ensure_embedding_timeout_default(env)
    assert env["ESPERANTO_EMBEDDING_TIMEOUT"] == "180"


def test_explicit_value_wins():
    env = {"ESPERANTO_EMBEDDING_TIMEOUT": "300"}
    ensure_embedding_timeout_default(env)
    assert env["ESPERANTO_EMBEDDING_TIMEOUT"] == "300"
