# PyInstaller spec for the viewer (UX.19). Build with: python -m evolution_tools.package
#
# One folder, no console window. The same spec builds on Linux for testing; the Windows build is the
# one that is shipped. Run from the repository root (evolution_tools.package does).
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    # `evolution_simulator.__version__` reads the installed package's metadata.
    datas=copy_metadata("evolution-simulator"),
    # The simulation runs in a spawned process that imports its recipes by name; they are not
    # imported from the viewer's own code, so name them.
    hiddenimports=[
        "evolution_simulator.session.specs",
        "evolution_simulator.session.host",
        # The run store keeps every run in a SQLite file (STORE.2).
        "sqlite3",
        "evolution_simulator.runs.legacy",
    ],
    excludes=["tkinter", "unittest", "pytest", "ruff", "PySide6.QtWebEngineCore", "PySide6.QtQml"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="evolutionSimulator",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="evolutionSimulator")
