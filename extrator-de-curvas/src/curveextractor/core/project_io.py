"""Self-contained versioned project archives, atomically replaced."""

import json
from dataclasses import asdict
from pathlib import Path
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from .errors import DomainError
from .model import AxisPoint, CoordinateSystem, Curve, Document, PageImage, Project, Source, Style
from .storage import atomic_write
from .transform import Transform


def curve_record(curve: Curve) -> dict:
    return asdict(curve)


def save_project(path: Path, project: Project) -> None:
    if any(not c.locked for c in project.curves):
        raise DomainError("capture_active")

    def write(temporary: Path) -> None:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
            documents = []
            for document in project.documents:
                data = asdict(document)
                data["pages"] = []
                for page in document.pages:
                    image_path = f"images/{document.id}/{page.page_index}.png"
                    archive.writestr(image_path, page.png_bytes)
                    data["pages"].append(
                        {k: v for k, v in asdict(page).items() if k != "png_bytes"}
                        | {"image": image_path}
                    )
                documents.append(data)
            archive.writestr(
                "project.json",
                json.dumps(
                    {
                        "schema_version": 1,
                        "app_version": project.app_version,
                        "next_curve_number": project.next_curve_number,
                        "main_curve_id": project.main_curve_id,
                        "documents": documents,
                        "curves": [curve_record(c) for c in project.curves],
                    },
                    ensure_ascii=False,
                ),
            )

    atomic_write(path, write)


def load_project(path: Path) -> Project:
    try:
        with ZipFile(path) as archive:
            data = json.loads(archive.read("project.json"))
            if data["schema_version"] != 1:
                raise DomainError("project_version")
            project = Project(
                main_curve_id=data["main_curve_id"],
                app_version=data["app_version"],
                next_curve_number=data.get("next_curve_number", 1),
            )
            for item in data["documents"]:
                pages = []
                for p in item.pop("pages"):
                    pages.append(
                        PageImage(
                            **{k: v for k, v in p.items() if k != "image"},
                            png_bytes=archive.read(p["image"]),
                        )
                    )
                project.documents.append(Document(**item, pages=pages))
            for item in data["curves"]:
                cs = item.pop("coordinate_system")
                system = CoordinateSystem(
                    tuple(AxisPoint(**p) for p in cs["points"]),
                    cs["x_scale"],
                    cs["y_scale"],
                    cs["id"],
                )
                item["locked"] = False
                curve = Curve(
                    **{k: v for k, v in item.items() if k not in {"source", "style"}},
                    source=Source(**item["source"]),
                    style=Style(**item["style"]),
                )
                curve.coordinate_system = system
                Transform(system)
                project.page(curve.source)
                curve.lock()
                project.curves.append(curve)
            ids = [c.id for c in project.curves]
            if len(ids) != len(set(ids)) or (
                project.main_curve_id and project.main_curve_id not in ids
            ):
                raise DomainError("project_invalid")
            project.next_curve_number = max(project.next_curve_number, len(ids) + 1)
            return project
    except (BadZipFile, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, DomainError):
            raise
        raise DomainError("project_invalid") from exc
