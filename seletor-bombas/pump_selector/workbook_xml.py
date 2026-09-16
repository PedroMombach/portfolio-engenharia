"""Small OOXML edits that keep Excel-authored chart styles intact.

The report template contains chart style/color parts that a workbook-library
round trip would drop.  Only known worksheet cells and package metadata are
changed here; every drawing and chart part is copied byte-for-byte.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import posixpath
import re
from typing import Mapping
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from zipfile import ZipFile


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CELL_RE = re.compile(
    rb'<c\b[^>]*?\br="([A-Z]{1,3}[1-9][0-9]*)"[^>]*?(?:/>|>.*?</c>)', re.DOTALL
)


def worksheet_parts(archive: ZipFile) -> dict[str, str]:
    """Resolve sheet names through workbook relationships, not sheet order."""
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        relation.attrib["Id"]: relation.attrib["Target"]
        for relation in relationships.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
    }
    result = {}
    for sheet in workbook.findall(f"{{{MAIN_NS}}}sheets/{{{MAIN_NS}}}sheet"):
        target = targets[sheet.attrib[f"{{{OFFICE_REL_NS}}}id"]]
        result[sheet.attrib["name"]] = (
            target.lstrip("/") if target.startswith("/")
            else posixpath.normpath(posixpath.join("xl", target))
        )
    return result


def patch_cells(xml: bytes, updates: Mapping[str, object]) -> bytes:
    """Replace existing reserved cells while retaining their style attributes."""
    remaining = set(updates)

    def replacement(match: re.Match[bytes]) -> bytes:
        reference = match.group(1).decode("ascii")
        if reference not in updates:
            return match.group(0)
        remaining.remove(reference)
        old = match.group(0)
        opening = old[:-2] if old.endswith(b"/>") else old[:old.index(b">")]
        opening = re.sub(rb'\s+t="[^"]*"', b"", opening)
        value = updates[reference]
        if value is None:
            return opening + b"/>"
        if isinstance(value, str):
            text = escape(value).encode("utf-8")
            return opening + b' t="inlineStr"><is><t xml:space="preserve">' + text + b"</t></is></c>"
        if isinstance(value, bool):
            return opening + b' t="b"><v>' + (b"1" if value else b"0") + b"</v></c>"
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError(f"non-finite value at {reference}")
        number = str(value) if isinstance(value, int) else repr(numeric)
        return opening + b"><v>" + number.encode("ascii") + b"</v></c>"

    result = CELL_RE.sub(replacement, xml)
    if remaining:
        raise ValueError(f"template has no reserved cells for: {sorted(remaining)[:8]}")
    ET.fromstring(result)
    return result


def _patch_workbook(xml: bytes, hidden_sheets: set[str]) -> bytes:
    for name in hidden_sheets:
        pattern = rb'(<sheet\s+name="' + re.escape(name.encode("utf-8")) + rb'"[^>]*)(/>)'
        xml, count = re.subn(pattern, lambda m: m.group(1) + b' state="hidden"' + m.group(2), xml)
        if count != 1:
            raise ValueError(f"cannot hide sheet {name!r}")
    if b"<calcPr " in xml and b"fullCalcOnLoad=" not in xml:
        xml = xml.replace(b"<calcPr ", b'<calcPr fullCalcOnLoad="1" ', 1)
    ET.fromstring(xml)
    return xml


def _patch_core(xml: bytes, title: str | None = None) -> bytes:
    if title is not None:
        text = escape(title).encode("utf-8")
        xml, count = re.subn(rb'<dc:title\b[^>]*>.*?</dc:title>',
                             lambda m: m.group(0)[:m.group(0).index(b">") + 1] + text + b"</dc:title>",
                             xml, count=1, flags=re.DOTALL)
        if count != 1:
            raise ValueError("template core properties have no title")
    xml, count = re.subn(rb'<cp:lastModifiedBy>.*?</cp:lastModifiedBy>',
                         b'<cp:lastModifiedBy>Pump Selector contributors</cp:lastModifiedBy>',
                         xml, count=1, flags=re.DOTALL)
    if count != 1:
        raise ValueError("template core properties have no lastModifiedBy")
    ET.fromstring(xml)
    return xml


def write_template_copy(
    template_path: str | Path, output_path: str | Path,
    updates: Mapping[str, Mapping[str, object]], title: str,
    hidden_sheets: set[str] | None = None,
) -> Path:
    """Build a report by changing only cell XML in an exact template copy."""
    template = Path(template_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".writing")
    hidden = hidden_sheets or set()
    try:
        with ZipFile(template, "r") as source:
            parts = worksheet_parts(source)
            unknown = set(updates) - set(parts)
            if unknown:
                raise ValueError(f"template is missing sheets: {sorted(unknown)}")
            by_part = {parts[name]: cells for name, cells in updates.items()}
            with ZipFile(temporary, "w") as destination:
                for item in source.infolist():
                    data = source.read(item.filename)
                    if item.filename in by_part:
                        data = patch_cells(data, by_part[item.filename])
                    elif item.filename == "xl/workbook.xml":
                        data = _patch_workbook(data, hidden)
                    elif item.filename == "docProps/core.xml":
                        data = _patch_core(data, title)
                    destination.writestr(item, data)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return output

