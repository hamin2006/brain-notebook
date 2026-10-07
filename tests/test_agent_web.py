"""Web search and page reading: SSRF guard, redirects, parsing, tool output, gating."""

import socket
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from open_notebook.agent import web

_RealClient = httpx.AsyncClient


def _client_with(handler):
    """httpx.AsyncClient replacement that answers from `handler`."""

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return _RealClient(*args, transport=httpx.MockTransport(handler), **kwargs)

    return factory


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "10.0.0.5", "192.168.1.2", "100.120.164.122", "169.254.169.254", "::1", "fd00:ec2::254"],
)  # fmt: skip
async def test_non_public_addresses_are_refused(host):
    with pytest.raises(web.WebError, match="not a public address"):
        await web._resolve_public(host, 80)


@pytest.mark.asyncio
async def test_hostnames_resolving_to_private_addresses_are_refused():
    infos = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 80)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", 80)),
    ]
    with patch("asyncio.BaseEventLoop.getaddrinfo", new=AsyncMock(return_value=infos)):
        with pytest.raises(web.WebError, match="non-public"):
            await web._resolve_public("sneaky.example", 80)


@pytest.mark.asyncio
async def test_public_hostnames_resolve_and_pin():
    infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 443))]
    with patch("asyncio.BaseEventLoop.getaddrinfo", new=AsyncMock(return_value=infos)):
        assert await web._resolve_public("example.com", 443) == "93.184.215.14"
    url, headers, extensions = web._pinned("https://example.com/a?b=1", "93.184.215.14")
    assert url == "https://93.184.215.14/a?b=1"
    assert headers == {"Host": "example.com"}
    assert extensions == {"sni_hostname": "example.com"}


@pytest.mark.asyncio
async def test_fetch_follows_public_redirects_and_refuses_private_ones():
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.headers["host"]
        if host == "a.example":
            return httpx.Response(302, headers={"location": "https://b.example/page"})
        if host == "b.example":
            return httpx.Response(
                302, headers={"location": "http://internal.example/admin"}
            )
        return httpx.Response(200, text="secret")

    async def resolve(hostname, port):
        if hostname == "internal.example":
            raise web.WebError(f"{hostname} resolves to a non-public address")
        return "93.184.215.14"

    with (
        patch.object(web.httpx, "AsyncClient", new=_client_with(handler)),
        patch.object(web, "_resolve_public", new=resolve),
    ):
        with pytest.raises(web.WebError, match="non-public"):
            await web.fetch("https://a.example/")


@pytest.mark.asyncio
async def test_fetch_returns_body_and_type():
    def handler(request):
        return httpx.Response(
            200, headers={"content-type": "text/html; charset=utf-8"}, text="<p>hi</p>"
        )

    with (
        patch.object(web.httpx, "AsyncClient", new=_client_with(handler)),
        patch.object(
            web, "_resolve_public", new=AsyncMock(return_value="93.184.215.14")
        ),
    ):
        url, content_type, body, encoding = await web.fetch("https://example.com/x")
    assert (url, content_type, body) == (
        "https://example.com/x",
        "text/html",
        b"<p>hi</p>",
    )


@pytest.mark.asyncio
async def test_fetch_rejects_other_schemes():
    with pytest.raises(web.WebError, match="only http"):
        await web.fetch("file:///etc/passwd")


@pytest.mark.asyncio
async def test_search_parses_and_dedupes_searxng_results():
    payload = {
        "results": [
            {"title": "Adam: A Method", "url": "https://arxiv.org/abs/1412.6980", "content": "We introduce Adam", "engines": ["google", "bing"]},
            {"title": "dup", "url": "https://arxiv.org/abs/1412.6980", "content": ""},
            {"title": "bad", "url": "javascript:alert(1)", "content": ""},
        ]
    }  # fmt: skip

    def handler(request):
        assert request.url.params["format"] == "json"
        return httpx.Response(200, json=payload)

    with patch.object(web.httpx, "AsyncClient", new=_client_with(handler)):
        results = await web.search("adam optimizer")
    assert results == [
        {
            "title": "Adam: A Method",
            "url": "https://arxiv.org/abs/1412.6980",
            "snippet": "We introduce Adam",
            "engines": "google, bing",
        }
    ]


def test_page_text_keeps_the_article_and_drops_scripts():
    html = (
        "<html><head><title>Adam explained</title><script>steal()</script></head><body>"
        "<nav>Home | About</nav><article><h1>Adam</h1>"
        + "<p>Adam combines momentum with RMSProp-style scaling of the learning rate.</p>"
        * 5
        + "</article></body></html>"
    )
    title, text = web.page_text(html.encode(), "text/html", "utf-8")
    assert title == "Adam explained"
    assert "Adam combines momentum" in text and "steal()" not in text


def test_broken_pdf_is_a_web_error():
    with pytest.raises(web.WebError, match="PDF"):
        web.page_text(b"%PDF-1.4 broken", "application/pdf")


@pytest.mark.asyncio
async def test_web_read_marks_content_untrusted_and_truncates():
    with (
        patch.object(web, "fetch", new=AsyncMock(return_value=("https://x.example/", "text/plain", b"a" * 5000, "utf-8"))),
    ):  # fmt: skip
        out = await web.tool_web_read("https://x.example/", limit=1000)
    assert "Untrusted web content" in out
    assert out.endswith("[... 4000 more characters]")


@pytest.mark.asyncio
async def test_web_tools_report_failures_as_errors():
    with patch.object(
        web,
        "search",
        new=AsyncMock(
            side_effect=web.WebError("the search service is unreachable (ConnectError)")
        ),
    ):
        out = await web.tool_web_search("adam")
    assert (
        out
        == "Error: web search failed: the search service is unreachable (ConnectError)."
    )
