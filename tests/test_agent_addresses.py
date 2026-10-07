"""Agent addresses: parsing, formatting, citations."""

import pytest

from open_notebook.agent.addresses import CITATION, AddressError, pages, parse_address


@pytest.mark.parametrize(
    "text",
    [
        "source:abc",
        "source:abc#p12",
        "source:abc#p12-18",
        "source:abc#s3",
        "source:abc#c37",
        "source:abc/summary",
        "source:abc/outline",
        "note:xyz",
        "source_insight:k9",
    ],
)
def test_round_trip(text):
    assert str(parse_address(text)) == text


def test_page_range_fields_and_normalization():
    a = parse_address("[source:abc#p18-12]")
    assert (a.record_id, a.page_start, a.page_end) == ("source:abc", 12, 18)
    assert str(parse_address("source:abc#p5-5")) == "source:abc#p5"
    assert parse_address("source:abc").is_document
    assert not parse_address("source:abc/summary").is_document


@pytest.mark.parametrize("bad", ["lecture 4", "source:", "source:abc#x1", "web:abc"])
def test_bad_addresses_explain_the_valid_forms(bad):
    with pytest.raises(AddressError, match="source:abc#p12"):
        parse_address(bad)


def test_page_zero_rejected():
    with pytest.raises(AddressError, match="start at 1"):
        parse_address("source:abc#p0")


def test_citations_found_in_answer_text():
    text = "Adam combines momentum and RMSProp [source:l4#p94], see also [note:n1] and [source:l3/summary]."
    assert CITATION.findall(text) == ["source:l4#p94", "note:n1", "source:l3/summary"]


def test_pages_helper():
    assert str(pages("source:l4", 86, 94)) == "source:l4#p86-94"
    assert str(pages("source:l4", 7)) == "source:l4#p7"


@pytest.mark.parametrize(
    "value",
    [
        ["source:a", "source:b"],
        '["source:a", "source:b"]',
        "source:a, source:b",
        "['source:a', 'source:b']",
    ],
)
def test_address_list_arguments_accept_string_forms(value):
    # Some models send list arguments JSON-encoded or comma-separated.
    from open_notebook.agent.graph import DelegateArgs
    from open_notebook.agent.tools import GrepArgs, SearchArgs

    assert GrepArgs(pattern="x", addresses=value).addresses == ["source:a", "source:b"]
    assert SearchArgs(addresses=value).addresses == ["source:a", "source:b"]
    assert DelegateArgs(task="t", addresses=value).addresses == [
        "source:a",
        "source:b",
    ]


def test_address_list_single_address_and_schema():
    from open_notebook.agent.tools import GrepArgs

    assert GrepArgs(pattern="x", addresses="source:a").addresses == ["source:a"]
    assert GrepArgs(pattern="x").addresses is None
    # The model is still told it is an array.
    schema = GrepArgs.model_json_schema()["properties"]["addresses"]
    assert {"type": "array", "items": {"type": "string"}} in schema["anyOf"]
