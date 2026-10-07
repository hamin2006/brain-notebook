"""Addresses: one way to name anything the agent can read, view or cite.

    source:abc              a document
    source:abc#p12          one page            source:abc#p12-18   a page range
    source:abc#s3           a section (index from the outline)
    source:abc#c37          a chunk (sources without pages)
    source:abc/summary      the stored document summary
    source:abc/outline      the stored outline
    note:xyz                a note
    source_insight:xyz      an insight

Every tool takes and returns these, and answers cite them, so the UI can link a
citation straight to the page.
"""

import re
from dataclasses import dataclass
from typing import Optional

_ADDRESS = re.compile(
    r"^(?P<table>source|note|source_insight):(?P<key>[A-Za-z0-9_]+)"
    r"(?:#p(?P<p1>\d+)(?:-(?P<p2>\d+))?|#s(?P<section>\d+)|#c(?P<chunk>\d+)|/(?P<layer>summary|outline))?$"
)
# Citations as they appear inside answer text: [source:abc#p12-18]
CITATION = re.compile(
    r"\[((?:source|note|source_insight):[A-Za-z0-9_]+(?:#p\d+(?:-\d+)?|#s\d+|#c\d+|/summary|/outline)?)\]"
)


class AddressError(ValueError):
    """An address the model wrote that doesn't parse; the message says the valid forms."""


@dataclass(frozen=True)
class Address:
    table: str
    key: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    section: Optional[int] = None
    chunk: Optional[int] = None
    layer: Optional[str] = None

    @property
    def record_id(self) -> str:
        return f"{self.table}:{self.key}"

    @property
    def is_document(self) -> bool:
        return (
            self.page_start is None
            and self.section is None
            and self.chunk is None
            and self.layer is None
        )

    def __str__(self) -> str:
        suffix = ""
        if self.page_start is not None:
            suffix = f"#p{self.page_start}"
            if self.page_end is not None and self.page_end != self.page_start:
                suffix += f"-{self.page_end}"
        elif self.section is not None:
            suffix = f"#s{self.section}"
        elif self.chunk is not None:
            suffix = f"#c{self.chunk}"
        elif self.layer:
            suffix = f"/{self.layer}"
        return self.record_id + suffix


def parse_address(text: str) -> Address:
    match = _ADDRESS.match(text.strip().strip("[]"))
    if not match:
        raise AddressError(
            f"'{text}' is not an address. Use forms like source:abc, source:abc#p12, "
            "source:abc#p12-18, source:abc#s3, source:abc/summary or note:xyz."
        )
    p1, p2 = match["p1"], match["p2"]
    start = int(p1) if p1 else None
    end = int(p2) if p2 else start
    if start is not None and end is not None and end < start:
        start, end = end, start
    if start == 0:
        raise AddressError("Page numbers start at 1.")
    return Address(
        table=match["table"],
        key=match["key"],
        page_start=start,
        page_end=end,
        section=int(match["section"]) if match["section"] else None,
        chunk=int(match["chunk"]) if match["chunk"] else None,
        layer=match["layer"],
    )


def pages(record_id: str, start: int, end: Optional[int] = None) -> Address:
    table, key = record_id.split(":", 1)
    return Address(
        table=table,
        key=key,
        page_start=start,
        page_end=end if end is not None else start,
    )
