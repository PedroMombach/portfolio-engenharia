"""Build a portable Windows release from the project's Python environment."""

import hashlib
import os
import shutil
import subprocess
import sys
import tomllib
from importlib.metadata import distribution
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
NAME = "ExtratorDeCurvasMK2"
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"]
RELEASE = ROOT / "release"
BUILD = RELEASE / "build"
LICENSE_PACKAGES = (
    "PySide6-Essentials",
    "shiboken6",
    "pypdfium2",
    "numpy",
    "scipy",
    "Pillow",
    "XlsxWriter",
    "pyinstaller",
)


def copy_licenses(bundle: Path) -> None:
    destination = bundle / "THIRD_PARTY_LICENSES"
    destination.mkdir()
    for license_name in ("GPL-3.0.txt", "LGPL-3.0.txt"):
        shutil.copy2(ROOT / "tools" / "licenses" / license_name, destination / license_name)
    for name in LICENSE_PACKAGES:
        package = distribution(name)
        for member in package.files or ():
            parts = [part.lower() for part in member.parts]
            filename = member.name.lower()
            if "licenses" not in parts and not filename.startswith(
                ("license", "copying", "notice")
            ):
                continue
            if filename == "licenseref-qt-commercial.txt":
                continue
            source = Path(package.locate_file(member))
            if not source.is_file():
                continue
            target = destination / f"{name}-{package.version}" / Path(*member.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def write_notices(bundle: Path) -> None:
    qt_version = distribution("PySide6-Essentials").version
    qt_series = ".".join(qt_version.split(".")[:2])
    packages = "\n".join(f"- {name}: {distribution(name).version}" for name in LICENSE_PACKAGES)
    (bundle / "THIRD_PARTY_NOTICES.txt").write_text(
        "Dependências distribuídas com o Extrator de Curvas MK2\n\n"
        f"{packages}\n\n"
        "Qt for Python (PySide6/Shiboken6) e Qt são usados sob as licenças abertas "
        "LGPLv3/GPLv3 disponíveis para estes componentes. A cópia da LGPLv3 está em "
        "THIRD_PARTY_LICENSES/LGPL-3.0.txt, acompanhada pela GPL-3.0.txt. "
        "É permitido substituir as bibliotecas "
        "compartilhadas Qt incluídas no pacote por versões compatíveis modificadas. "
        "Consulte os arquivos de licença dos demais componentes na mesma pasta.\n\n"
        "Código-fonte correspondente às bibliotecas Qt usadas nesta construção:\n"
        f"https://download.qt.io/archive/qt/{qt_series}/{qt_version}/single/\n"
        "Código-fonte do Qt for Python, tag correspondente:\n"
        f"https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v{qt_version}\n\n"
        "Termos e obrigações de uso do Qt: "
        "https://www.qt.io/development/open-source-lgpl-obligations\n",
        encoding="utf-8",
    )


def build() -> tuple[Path, Path]:
    if sys.platform != "win32" or sys.maxsize <= 2**32:
        raise SystemExit("Build requires 64-bit Windows Python.")
    env = os.environ.copy()
    paths = [str(ROOT / "src")]
    local_build_deps = ROOT / "tools" / "_build_deps"
    if local_build_deps.is_dir():
        paths.insert(0, str(local_build_deps))
        sys.path.insert(0, str(local_build_deps))
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    windows = Path(env.get("SystemRoot", "C:\\Windows"))
    env["PATH"] = os.pathsep.join(
        (str(Path(sys.executable).parent), str(windows / "System32"), str(windows))
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--noupx",
            "--onedir",
            "--windowed",
            "--name",
            NAME,
            "--paths",
            str(ROOT / "src"),
            "--distpath",
            str(BUILD / "dist"),
            "--workpath",
            str(BUILD / "work"),
            "--specpath",
            str(BUILD),
            str(ROOT / "src" / "curveextractor" / "__main__.py"),
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )
    bundle = BUILD / "dist" / NAME
    if not (bundle / f"{NAME}.exe").is_file():
        raise RuntimeError("PyInstaller did not produce the expected executable.")
    (bundle / "config").mkdir(exist_ok=True)
    (bundle / "test-output").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "config" / "settings.default.json", bundle / "config")
    shutil.copy2(ROOT / "LICENSE", bundle)
    shutil.copy2(ROOT / "README.md", bundle)
    copy_licenses(bundle)
    write_notices(bundle)
    RELEASE.mkdir(exist_ok=True)
    archive = RELEASE / f"{NAME}-v{VERSION}-windows-x64.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=6) as zip_file:
        zip_file.writestr(f"{NAME}/test-output/", "")
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                zip_file.write(path, f"{NAME}/{path.relative_to(bundle).as_posix()}")
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    checksum = digest.hexdigest()
    checksum_file = RELEASE / f"{archive.name}.sha256"
    checksum_file.write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    return archive, checksum_file


if __name__ == "__main__":
    zip_path, sha_path = build()
    print(zip_path)
    print(sha_path)
