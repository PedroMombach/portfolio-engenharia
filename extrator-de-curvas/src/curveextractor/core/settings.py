"""Portable settings with recursive defaults and unknown-key retention."""

import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

from .errors import DomainError
from .storage import atomic_write


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def merge(defaults: dict, stored: dict) -> dict:
    result = copy.deepcopy(defaults)
    for key, value in stored.items():
        result[key] = (
            merge(result[key], value)
            if isinstance(value, dict) and isinstance(result.get(key), dict)
            else value
        )
    return result


class Settings:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or project_root()
        self.path = self.root / "config" / "settings.json"
        self.defaults = json.loads(
            (self.root / "config" / "settings.default.json").read_text("utf-8")
        )
        try:
            stored = json.loads(self.path.read_text("utf-8")) if self.path.exists() else {}
            if not isinstance(stored, dict):
                raise DomainError("settings_invalid")
            self.data = merge(self.defaults, stored)
            self.data["schema_version"] = max(1, self.data.get("schema_version", 1))
            self.validate(self.data)
        except (ValueError, TypeError) as exc:
            if isinstance(exc, DomainError):
                raise
            raise DomainError("settings_invalid") from exc

    def validate(self, data: dict[str, Any]) -> None:
        if not 72 <= data["raster_dpi"] <= 600:
            raise DomainError("dpi")
        if data["decimal"] not in {".", ","} or len(data["delimiter"]) != 1:
            raise DomainError("separators")
        if data["decimal"] == data["delimiter"]:
            raise DomainError("separators")
        for key in ("curve_opacity", "axis_opacity", "image_opacity"):
            if not 0 <= data[key] <= 1:
                raise DomainError("settings_invalid")
        if not data["palette"] or data["theme"] not in {"claro", "escuro", "sistema"}:
            raise DomainError("settings_invalid")
        if data["font_color"] != "auto" and not re.fullmatch(
            r"#[0-9a-fA-F]{6}", data["font_color"]
        ):
            raise DomainError("settings_invalid")
        sequences = [s.casefold() for s in data["shortcuts"].values() if s]
        if len(sequences) != len(set(sequences)):
            raise DomainError("shortcuts_duplicate")

    def save(self) -> None:
        self.validate(self.data)
        atomic_write(
            self.path,
            lambda p: p.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8"),
        )
