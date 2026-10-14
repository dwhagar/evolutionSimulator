"""The Windows package (UX.19): what can be checked without Windows or a PyInstaller build."""

import importlib
import importlib.util
import sys
import types
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


entry = load("packaging_entry", ROOT / "packaging" / "entry.py")
package = load("package_script", ROOT / "scripts" / "package.py")


def test_selftest_starts_the_simulation_process():
    # A real spawned process, as the frozen program does it.
    assert entry.run(["--selftest"]) == 0


def test_quiet_streams_replaces_missing_streams(monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    entry.quiet_streams()
    print("no console", file=sys.stderr)  # would raise on None
    print("no console")
    sys.stdout.close()
    sys.stderr.close()


def test_quiet_streams_leaves_real_streams_alone():
    out, err = sys.stdout, sys.stderr
    entry.quiet_streams()
    assert (sys.stdout, sys.stderr) == (out, err)


def test_entry_calls_freeze_support_before_anything_else(monkeypatch):
    order = []
    monkeypatch.setattr(entry.multiprocessing, "freeze_support", lambda: order.append("freeze"))
    monkeypatch.setattr(entry, "quiet_streams", lambda: order.append("quiet"))
    monkeypatch.setattr(entry, "selftest", lambda: order.append("selftest") or 0)
    assert entry.run(["--selftest"]) == 0
    assert order == ["freeze", "quiet", "selftest"]


def test_viewer_main_module_does_nothing_on_import():
    # A spawned process imports the main module under another name; it must not open a window.
    importlib.import_module("evolution_simulator.viewer.__main__")


def test_viewer_main_module_is_guarded():
    source = (ROOT / "src" / "evolution_simulator" / "viewer" / "__main__.py").read_text()
    assert 'if __name__ == "__main__":' in source
    assert source.index("freeze_support()") < source.index("import main")


def test_spec_builds_the_windowed_folder_app(monkeypatch):
    calls = {}

    def recorder(name):
        def record(*args, **kwargs):
            calls[name] = (args, kwargs)
            return types.SimpleNamespace(pure=[], scripts=[], binaries=[], datas=[])

        return record

    hooks = types.ModuleType("PyInstaller.utils.hooks")
    hooks.copy_metadata = lambda name: [(f"{name}.dist-info", f"{name}.dist-info")]
    for name, module in (
        ("PyInstaller", types.ModuleType("PyInstaller")),
        ("PyInstaller.utils", types.ModuleType("PyInstaller.utils")),
        ("PyInstaller.utils.hooks", hooks),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    namespace = {
        "SPECPATH": str(ROOT / "packaging"),
        "Analysis": recorder("Analysis"),
        "PYZ": recorder("PYZ"),
        "EXE": recorder("EXE"),
        "COLLECT": recorder("COLLECT"),
    }
    spec = (ROOT / "packaging" / "evolutionSimulator.spec").read_text()
    exec(compile(spec, "evolutionSimulator.spec", "exec"), namespace)  # noqa: S102 - our own spec

    scripts, analysis = calls["Analysis"]
    assert Path(scripts[0][0]) == ROOT / "packaging" / "entry.py"
    assert analysis["datas"] == [("evolution-simulator.dist-info", "evolution-simulator.dist-info")]
    assert Path(analysis["pathex"][0]) == ROOT / "src"
    assert calls["EXE"][1]["console"] is False
    assert calls["EXE"][1]["exclude_binaries"] is True  # folder mode, not one file
    assert calls["COLLECT"][1]["name"] == "evolutionSimulator"


def test_spec_hidden_imports_exist():
    for line in (ROOT / "packaging" / "evolutionSimulator.spec").read_text().splitlines():
        line = line.strip().strip(",").strip('"')
        if line.startswith("evolution_simulator."):
            assert importlib.util.find_spec(line) is not None


@pytest.mark.parametrize(
    ("platform", "tag"), [("win32", "win64"), ("linux", "linux64"), ("darwin", "macos")]
)
def test_archive_name(platform, tag):
    assert package.archive_name("0.1.7", platform) == f"evolutionSimulator-0.1.7-{tag}.zip"


def test_add_extras_and_zip_layout(tmp_path):
    folder = tmp_path / "dist" / "evolutionSimulator"
    (folder / "_internal").mkdir(parents=True)
    (folder / "evolutionSimulator.exe").write_bytes(b"MZ")
    (folder / "_internal" / "lib.dll").write_bytes(b"dll")
    package.add_extras(folder, "1.2.3")
    archive = tmp_path / "out" / "x.zip"
    package.zip_folder(folder, archive)

    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        assert bundle.read("evolutionSimulator/VERSION") == b"1.2.3\n"
    assert names == {
        "evolutionSimulator/evolutionSimulator.exe",
        "evolutionSimulator/_internal/lib.dll",
        "evolutionSimulator/LICENSE",
        "evolutionSimulator/THIRD_PARTY_NOTICES.md",
        "evolutionSimulator/README.txt",
        "evolutionSimulator/VERSION",
    }


def test_zip_replaces_an_old_archive(tmp_path):
    folder = tmp_path / "evolutionSimulator"
    folder.mkdir()
    (folder / "a.txt").write_text("a")
    archive = tmp_path / "x.zip"
    archive.write_bytes(b"stale")
    package.zip_folder(folder, archive)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.namelist() == ["evolutionSimulator/a.txt"]


def test_notices_and_readme_say_what_the_licence_and_the_warning_need():
    notices = (ROOT / "packaging" / "THIRD_PARTY_NOTICES.md").read_text()
    assert "LGPL" in notices and "replace" in notices and "PySide6" in notices
    for package_name in ("pyqtgraph", "NumPy"):
        assert package_name in notices
    readme = (ROOT / "README.md").read_text()
    assert "SmartScreen" in readme and "not signed" in readme


def test_workflow_is_started_by_hand_only():
    workflow = (ROOT / ".github" / "workflows" / "package-windows.yml").read_text()
    triggers = workflow.split("jobs:")[0]
    assert "workflow_dispatch" in triggers
    for trigger in ("push", "pull_request", "schedule"):
        assert f"\n  {trigger}:" not in triggers
