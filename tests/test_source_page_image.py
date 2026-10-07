"""GET /api/sources/{id}/pages/{n}/image renders the cited page."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from PIL import Image


def _client():
    from api.main import app

    return TestClient(app)


def _source(path):
    source = MagicMock()
    source.asset.file_path = str(path)
    return source


def test_renders_a_pdf_page(tmp_path):
    pdf = tmp_path / "deck.pdf"
    Image.new("RGB", (800, 450), "white").save(
        pdf, "PDF", save_all=True, append_images=[Image.new("RGB", (800, 450))]
    )
    with patch(
        "api.routers.sources.Source.get", new=AsyncMock(return_value=_source(pdf))
    ):
        response = _client().get("/api/sources/abc/pages/2/image?max_side=300")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")


def test_page_out_of_range_is_404(tmp_path):
    pdf = tmp_path / "deck.pdf"
    Image.new("RGB", (800, 450), "white").save(pdf, "PDF")
    with patch(
        "api.routers.sources.Source.get", new=AsyncMock(return_value=_source(pdf))
    ):
        response = _client().get("/api/sources/source:abc/pages/5/image")
    assert response.status_code == 404


def test_missing_original_file_is_404(tmp_path):
    with patch(
        "api.routers.sources.Source.get",
        new=AsyncMock(return_value=_source(tmp_path / "gone.pdf")),
    ):
        response = _client().get("/api/sources/abc/pages/1/image")
    assert response.status_code == 404
    assert "not stored" in response.json()["detail"]
