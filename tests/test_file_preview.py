"""The file viewer's previews: one per supported kind, bounded, never raising."""

import tarfile
import zipfile

import pytest

from open_notebook.utils import file_preview
from open_notebook.utils.file_preview import build_preview, media_type, preview_kind


@pytest.mark.parametrize(
    "name,kind",
    [
        ("Lecture 1.pdf", "pages"),
        ("diagram.PNG", "image"),
        ("scan.tiff", "image"),
        ("talk.mp3", "audio"),
        ("talk.m4a", "audio"),
        ("demo.mp4", "video"),
        ("demo.mov", "video"),
        ("demo.avi", "none"),
        ("notes.txt", "text"),
        ("README.md", "markdown"),
        ("page.html", "html"),
        ("grades.csv", "table"),
        ("grades.xlsx", "table"),
        ("grades.ods", "table"),
        ("grades.xls", "none"),
        ("essay.docx", "document"),
        ("deck.pptx", "document"),
        ("book.epub", "document"),
        ("bundle.zip", "archive"),
        ("bundle.tar.gz", "archive"),
        ("unknown.bin", "none"),
    ],
)
def test_kind_follows_the_suffix(name, kind):
    assert preview_kind(name) == kind


def test_media_types_for_players():
    assert media_type("a.mp3") == "audio/mpeg"
    assert media_type("a.m4a") == "audio/mp4"
    assert media_type("a.mov") == "video/quicktime"
    assert media_type("a.weird") == "application/octet-stream"


def test_text_is_inline_and_bounded(tmp_path, monkeypatch):
    path = tmp_path / "notes.txt"
    path.write_text("héllo world\n" * 10, encoding="utf-8")
    preview = build_preview(str(path))
    assert preview["kind"] == "text"
    assert preview["text"].startswith("héllo world")
    assert preview["truncated"] is False

    monkeypatch.setattr(file_preview, "MAX_TEXT_CHARS", 20)
    text, truncated = file_preview.read_text(str(path), limit=20)
    assert len(text) == 20 and truncated


def test_csv_sniffs_the_delimiter_and_caps_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(file_preview, "MAX_ROWS", 3)
    path = tmp_path / "grades.csv"
    path.write_text("name;score\nada;90\nalan;85\ngrace;99\nedsger;70\n")
    sheet = build_preview(str(path))["sheets"][0]
    assert sheet["rows"] == [["name", "score"], ["ada", "90"], ["alan", "85"]]
    assert sheet["total_rows"] == 5
    assert sheet["truncated"] is True


def test_xlsx_sheets(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    book = openpyxl.Workbook()
    book.active.title = "Week 1"
    book.active.append(["topic", "hours"])
    book.active.append(["gradients", 2.0])
    book.create_sheet("Week 2").append(["attention", 3.5])
    path = tmp_path / "plan.xlsx"
    book.save(path)
    sheets = build_preview(str(path))["sheets"]
    assert [s["name"] for s in sheets] == ["Week 1", "Week 2"]
    assert sheets[0]["rows"] == [["topic", "hours"], ["gradients", "2"]]
    assert sheets[1]["rows"] == [["attention", "3.5"]]


def test_docx_becomes_html_with_headings_and_tables(tmp_path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_heading("Backpropagation", level=1)
    document.add_paragraph("Uses the <chain rule>.")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "a"
    table.rows[0].cells[1].text = "b"
    path = tmp_path / "essay.docx"
    document.save(path)
    page = build_preview(str(path))["html"]
    assert "<h2>Backpropagation</h2>" in page
    assert "Uses the &lt;chain rule&gt;." in page  # escaped, not markup
    assert "<td>a</td><td>b</td>" in page


def test_pptx_becomes_one_section_per_slide(tmp_path):
    pptx = pytest.importorskip("pptx")
    deck = pptx.Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[1])
    slide.shapes.title.text = "Attention"
    slide.placeholders[1].text = "Queries, keys and values"
    slide.notes_slide.notes_text_frame.text = "Mention scaling"
    path = tmp_path / "deck.pptx"
    deck.save(path)
    page = build_preview(str(path))["html"]
    assert '<span class="n">1</span> Attention' in page
    assert "Queries, keys and values" in page
    assert "Mention scaling" in page


def _epub(path):
    with zipfile.ZipFile(path, "w") as book:
        book.writestr(
            "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>',
        )
        book.writestr(
            "OEBPS/content.opf",
            '<package xmlns="http://www.idpf.org/2007/opf"><manifest>'
            '<item id="c2" href="two.xhtml"/><item id="c1" href="one.xhtml"/>'
            '</manifest><spine><itemref idref="c1"/><itemref idref="c2"/></spine></package>',
        )
        book.writestr(
            "OEBPS/one.xhtml",
            "<html><body><h1>One</h1><script>alert(1)</script><img src='x.png'/></body></html>",
        )
        book.writestr("OEBPS/two.xhtml", "<html><body><h1>Two</h1></body></html>")


def test_epub_chapters_in_spine_order_without_scripts(tmp_path):
    path = tmp_path / "book.epub"
    _epub(path)
    page = build_preview(str(path))["html"]
    assert page.index("<h1>One</h1>") < page.index("<h1>Two</h1>")
    assert "<script" not in page and "<img" not in page


def test_archives_list_entries(tmp_path):
    zipped = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zipped, "w") as archive:
        archive.writestr("slides/a.pdf", b"12345")
    preview = build_preview(str(zipped))
    assert preview["entries"] == [{"name": "slides/a.pdf", "size": 5, "dir": False}]

    member = tmp_path / "x.txt"
    member.write_text("hi")
    tarred = tmp_path / "bundle.tar.gz"
    with tarfile.open(tarred, "w:gz") as archive:
        archive.add(member, arcname="x.txt")
    assert build_preview(str(tarred))["entries"][0]["name"] == "x.txt"


def test_a_plain_gzip_or_damaged_file_has_no_preview(tmp_path):
    import gzip

    path = tmp_path / "notes.gz"
    path.write_bytes(gzip.compress(b"not a tar"))
    assert build_preview(str(path))["kind"] == "none"

    broken = tmp_path / "broken.xlsx"
    broken.write_bytes(b"not a zip")
    preview = build_preview(str(broken))
    assert preview["kind"] == "none"
    assert preview["filename"] == "broken.xlsx"


def test_pdf_page_count_comes_from_the_file(tmp_path):
    pdfium = pytest.importorskip("pypdfium2")
    pdf = pdfium.PdfDocument.new()
    for _ in range(3):
        pdf.new_page(200, 100)
    path = tmp_path / "deck.pdf"
    pdf.save(str(path))
    pdf.close()
    assert build_preview(str(path))["pages"] == 3
    assert build_preview(str(path), pages=7)["pages"] == 7
