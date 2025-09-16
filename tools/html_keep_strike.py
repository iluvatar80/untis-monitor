# tools/html_keep_strike.py
from __future__ import annotations

import re
from bs4 import BeautifulSoup, Tag

ALLOWED_TAGS = {"s", "del", "strike", "b", "strong", "span", "br"}

def extract_cell_html(cell: Tag) -> str:
    """Sanitisiertes innerHTML einer <td>, erhält Durchstreichungen.

    - erlaubt: <s>, <del>, <strike>, <b>, <strong>, <span style="text-decoration:line-through">, <br>
    - alle anderen Tags werden entfernt (unwrap)
    - Attribute werden entfernt, außer minimaler style bei <span>
    """
    raw = cell.decode_contents()
    soup = BeautifulSoup(raw, "lxml")

    for t in soup(["script", "style"]):
        t.decompose()

    # <strike> vereinheitlichen
    for t in soup.find_all("strike"):
        t.name = "s"

    for t in soup.find_all(True):
        if t.name not in ALLOWED_TAGS:
            t.unwrap()
            continue
        if t.name == "span":
            style = t.attrs.get("style", "")
            if "line-through" in style:
                t.attrs = {"style": "text-decoration:line-through"}
            else:
                t.attrs = {}
        else:
            t.attrs = {}

    html = str(soup)
    html = re.sub(r"\s+", " ", html).strip()
    return html

def extract_cell_text(cell: Tag) -> str:
    """Nur Text (ohne HTML) – nützlich für Dedupe/Filter."""
    cleaned_html = extract_cell_html(cell)
    txt = BeautifulSoup(cleaned_html, "lxml").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", txt)
