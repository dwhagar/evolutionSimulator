"""Build the downloadable viewer (UX.19): a PyInstaller folder, zipped.

Run from anywhere: ``python scripts/package.py``. Needs the ``gui`` and ``package`` extras
(``pip install -e ".[gui,package]"``). The output is ``dist/evolutionSimulator-<version>-<platform>.zip``
holding one ``evolutionSimulator`` folder. The Windows build is the shipped one; the same spec builds
on Linux so the packaging can be tested there. ``--no-zip`` stops after the folder.
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "evolutionSimulator.spec"
APP = "evolutionSimulator"
EXTRA_FILES = (
    (ROOT / "LICENSE", "LICENSE"),
    (ROOT / "packaging" / "THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md"),
    (ROOT / "packaging" / "README-windows.txt", "README.txt"),
)


def current_version() -> str:
    spec = importlib.util.spec_from_file_location("version_script", ROOT / "scripts" / "version.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.get_version()


def platform_tag(platform: str = sys.platform) -> str:
    if platform.startswith("win"):
        return "win64"
    if platform == "darwin":
        return "macos"
    return "linux64"


def archive_name(version: str, platform: str = sys.platform) -> str:
    return f"{APP}-{version}-{platform_tag(platform)}.zip"


def add_extras(folder: Path, version: str) -> None:
    """The licence, notices, a short readme and the version next to the program."""
    for source, name in EXTRA_FILES:
        shutil.copyfile(source, folder / name)
    (folder / "VERSION").write_text(version + "\n", encoding="utf-8")


def zip_folder(folder: Path, archive: Path) -> None:
    """Zip ``folder`` so it unpacks to a single top-level folder of the same name."""
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                bundle.write(path, Path(folder.name) / path.relative_to(folder))


def build(dist: Path, work: Path) -> Path:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(dist),
            "--workpath",
            str(work),
            str(SPEC),
        ],
        cwd=ROOT,
        check=True,
    )
    return dist / APP


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dist", type=Path, default=ROOT / "dist", help="output folder")
    parser.add_argument("--work", type=Path, default=ROOT / "build", help="PyInstaller scratch")
    parser.add_argument("--no-zip", action="store_true", help="stop after the folder")
    args = parser.parse_args(argv)

    version = current_version()
    folder = build(args.dist.resolve(), args.work.resolve())
    add_extras(folder, version)
    print(f"Built {folder}")
    if not args.no_zip:
        archive = args.dist.resolve() / archive_name(version)
        zip_folder(folder, archive)
        print(f"Wrote {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
