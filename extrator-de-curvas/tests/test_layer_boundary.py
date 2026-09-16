import ast
import subprocess
import sys
from pathlib import Path


def test_core_has_no_qt_imports():
    root = Path(__file__).parents[1] / "src" / "curveextractor" / "core"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    not alias.name.startswith(("PySide", "PyQt", "curveextractor.gui"))
                    for alias in node.names
                )
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(("PySide", "PyQt", "curveextractor.gui"))
    code = """
import importlib, pkgutil, sys
import curveextractor.core
for module in pkgutil.iter_modules(curveextractor.core.__path__):
    importlib.import_module('curveextractor.core.' + module.name)
assert not any(n.startswith(('PySide', 'PyQt')) for n in sys.modules)
"""
    subprocess.run([sys.executable, "-c", code], check=True)
