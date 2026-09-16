"""One archive per source document; full pages are stored once."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from .errors import DomainError
from .model import Curve, Project, new_id
from .storage import atomic_write, slug
from .transform import Transform


def record_extractions(
    root: Path, project: Project, curves: list[Curve], provenance: dict | None = None
) -> list[Path]:
    paths = []
    for document in project.documents:
        selected = [c for c in curves if c.source.document_id == document.id]
        if not selected:
            continue
        stem = Path(document.origin_path).stem if document.origin_path else "clipboard"
        # A fingerprint suffix prevents collisions between equal source names.
        path = root / f"{slug(stem)}_{document.sha256[:12]}.zip"

        def write(temporary: Path) -> None:
            with ZipFile(temporary, "w", ZIP_DEFLATED) as target:
                names: set[str] = set()
                if path.exists():
                    with ZipFile(path) as previous:
                        metadata = json.loads(previous.read("document.json"))
                        if metadata["sha256"] != document.sha256:
                            raise DomainError("dataset_conflict")
                        for name in previous.namelist():
                            if name != "document.json":
                                target.writestr(name, previous.read(name))
                                names.add(name)
                target.writestr(
                    "document.json",
                    json.dumps(
                        {
                            "schema_version": 1,
                            "origin": document.origin_path,
                            "sha256": document.sha256,
                            "page_count": document.page_count,
                            "raster_dpi": document.pages[0].raster_dpi,
                            "app_version": project.app_version,
                        }
                    ),
                )
                for curve in selected:
                    page = project.page(curve.source)
                    image_name = f"pages/page_{page.page_index + 1:04d}.png"
                    if image_name in names:
                        if path.exists():
                            with ZipFile(path) as previous:
                                if image_name in previous.namelist():
                                    if previous.read(image_name) != page.png_bytes:
                                        raise DomainError("dataset_dpi")
                    else:
                        target.writestr(image_name, page.png_bytes)
                        names.add(image_name)
                    transform = Transform(curve.coordinate_system)
                    now = datetime.now().astimezone()
                    record = {
                        "schema_version": 1,
                        "app_version": project.app_version,
                        "created_at": now.isoformat(),
                        "source": {
                            "file": document.origin_path,
                            "sha256": document.sha256,
                            "page": page.page_index + 1,
                            "image": image_name,
                            "image_size_px": [page.width_px, page.height_px],
                            "raster_dpi": page.raster_dpi,
                        },
                        "provenance": {
                            "fabricante": None,
                            "modelo": None,
                            "observacao": None,
                            "uso_restrito": True,
                        }
                        | (provenance or {}),
                        "curve": {
                            "id": curve.id,
                            "name": curve.name,
                            "points_px": curve.points_px,
                            "points_real": transform.to_real(curve.points_px).tolist(),
                        },
                        "calibration": asdict(curve.coordinate_system)
                        | {"affine": transform.affine.tolist()},
                    }
                    target.writestr(
                        f"extractions/{now:%Y%m%dT%H%M%S%f}_{new_id()}.json",
                        json.dumps(record, ensure_ascii=False),
                    )

        atomic_write(path, write)
        paths.append(path)
    return paths
