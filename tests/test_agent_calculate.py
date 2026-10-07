"""The agent's calculate tool: exact arithmetic, nothing else."""

import pytest

from open_notebook.agent.scope import ToolError
from open_notebook.agent.tools import evaluate, tool_calculate


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("(32 - 5 + 2*2)/1 + 1", 32),  # conv output size with padding 2
        ("7*7*512*4096", 102_760_448),  # VGG-16 first FC weights
        ("(7 - 3 + 2*1)//2 + 1", 4),
        ("sqrt(16) + log2(8)", 7),
        ("max(3, 9, 4) - abs(-2)", 7),
        ("2**10", 1024),
        ("2**-1", 0.5),
    ],
)
def test_evaluates_arithmetic(expression, expected):
    assert evaluate(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "'a' * 10**9",  # strings could build huge objects
        "9**9**9",  # non-literal exponent
        "2**100000",  # exponent too large
        "__import__('os')",  # unknown name
        "(1).__class__",  # attribute access
        "[x for x in range(10)]",  # comprehension
        "(lambda: 1)()",
        "open('/etc/passwd')",
        "True + 1",
    ],
)
def test_rejects_anything_but_arithmetic(expression):
    with pytest.raises((ToolError, SyntaxError)):
        evaluate(expression)


@pytest.mark.asyncio
async def test_tool_formats_integers_with_separators():
    assert await tool_calculate(None, "7*7*512*4096") == "7*7*512*4096 = 102,760,448"  # type: ignore[arg-type]
    assert await tool_calculate(None, "1/3") == "1/3 = 0.3333333333333333"  # type: ignore[arg-type]
