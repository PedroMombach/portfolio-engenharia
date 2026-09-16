import csv
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest
from PIL import Image

from curveextractor.core import settings as settings_module
from curveextractor.core.aggregation import Table
from curveextractor.core.dataset import record_extractions
from curveextractor.core.errors import DomainError
from curveextractor.core.export_csv import write_csv
from curveextractor.core.export_profiles import profiles
from curveextractor.core.export_xlsx import write_xlsx
from curveextractor.core.model import Project, Source
from curveextractor.core.project_io import load_project, save_project
from curveextractor.core.raster import load_image
from curveextractor.core.settings import Settings, project_root


def test_csv_settings_and_profile(tmp_path):
    table = Table(["Q", "H", "Eta1", "NPSH"], np.array([[1.0, 2.0, 3.0, np.nan]]))
    path = tmp_path / "result.csv"
    write_csv(path, table)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    with pytest.raises(DomainError):
        write_csv(path, table, decimal=",")
    write_csv(path, table, decimal=",", profile=profiles()[1])
    assert path.read_bytes() == b"Q,H,Eta1,NPSH\r\n1.0,2.0,3.0,\r\n"


def test_real_mk3_bytes(tmp_path):
    sample = Path(__file__).parent / "fixtures" / "mk3.csv"
    with sample.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    table = Table(rows[0], np.array([[float(v) if v else np.nan for v in r] for r in rows[1:]]))
    target = tmp_path / "regenerated.csv"
    write_csv(target, table, profile=profiles()[1])
    assert target.read_bytes() == sample.read_bytes()


def test_xlsx_cells(tmp_path):
    import xml.etree.ElementTree as ET

    path = tmp_path / "out.xlsx"
    values = np.array([[1.0, 2.0, np.nan], [3.0, 4.0, 5.0]])
    write_xlsx(path, Table(["X", "A", "B"], values), [("A/A", Table(["x", "y"], values[:, :2]))])
    with ZipFile(path) as archive:
        tree = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        cells = {
            c.attrib["r"]: float(c.find("m:v", ns).text)
            for c in tree.findall(".//m:c", ns)
            if c.attrib.get("t") != "s"
        }
        assert cells == {"A2": 1, "B2": 2, "A3": 3, "B3": 4, "C3": 5}


def test_settings_unknown_defaults_and_delete(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.default.json").write_bytes(
        (project_root() / "config" / "settings.default.json").read_bytes()
    )
    settings = Settings(tmp_path)
    settings.data["future"] = {"key": 42}
    settings.data["raster_dpi"] = 300
    settings.save()
    loaded = Settings(tmp_path)
    assert loaded.data["future"] == {"key": 42}
    assert loaded.data["raster_dpi"] == 300
    loaded.path.unlink()
    assert Settings(tmp_path).data["raster_dpi"] == 200


def test_frozen_settings_follow_executable_directory(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.default.json").write_bytes(
        (project_root() / "config" / "settings.default.json").read_bytes()
    )
    monkeypatch.setattr(settings_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(settings_module.sys, "executable", str(tmp_path / "ExtratorDeCurvasMK2.exe"))
    settings = Settings()
    assert settings.root == tmp_path
    settings.data["raster_dpi"] = 300
    settings.save()
    assert settings.path == tmp_path / "config" / "settings.json"
    assert Settings().data["raster_dpi"] == 300


def test_project_and_dataset_roundtrip(curve_factory, tmp_path):
    image = BytesIO()
    Image.new("RGB", (32, 32), "white").save(image, format="PNG")
    document = load_image(data=image.getvalue())
    project = Project(documents=[document], next_curve_number=9)
    for index in range(4):
        curve = curve_factory(name=f"C{index}")
        curve.source = Source(document.id, 0)
        curve.lock()
        project.curves.append(curve)
    project.main_curve_id = project.curves[0].id
    path = tmp_path / "saved.ecp"
    save_project(path, project)
    loaded = load_project(path)
    assert loaded.next_curve_number == 9
    assert loaded.curves[0].points_px == project.curves[0].points_px
    assert all(c.locked for c in loaded.curves)
    assert loaded.documents[0].pages[0].png_bytes == document.pages[0].png_bytes
    archives = record_extractions(tmp_path, project, project.curves)
    record_extractions(tmp_path, project, project.curves[:1])
    with ZipFile(archives[0]) as archive:
        assert sum(n.endswith(".png") for n in archive.namelist()) == 1
        records = [n for n in archive.namelist() if n.startswith("extractions/")]
        assert len(records) == 5
        assert json.loads(archive.read(records[0]))["source"]["image_size_px"] == [32, 32]
