#!/usr/bin/env python3
"""Build Kodi add-on zip(s) exactly like CI does.

Usage:
    python3 scripts/build_zip.py
    python3 scripts/build_zip.py --addon plugin.video.fmovies
    python3 scripts/build_zip.py --out dist

Rules:
- Source of truth for version is <addon>/addon.xml  version="x.y.z"
- Output: <addon>-<version>.zip containing top-level <addon>/ folder
- Excludes: venv, __pycache__, *.pyc, .pytest_cache, tests, .git, .github, etc.
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]

EXCLUDE_DIRS = {
    "venv", ".venv", "env",
    "__pycache__", ".pytest_cache", ".tox",
    ".git", ".github", ".idea", ".vscode",
    "tests", "test", ".coverage",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".bak"}
EXCLUDE_NAMES = {".DS_Store", "Thumbs.db"}


def find_addons(specific: str | None) -> list[pathlib.Path]:
    if specific:
        p = ROOT / specific
        if not p.is_dir() or not (p / "addon.xml").exists():
            raise SystemExit(f"addon not found: {p}")
        return [p]
    return sorted(
        p for p in ROOT.iterdir()
        if p.is_dir()
        and p.name.startswith("plugin.")
        and (p / "addon.xml").exists()
    )


def addon_version(addon_dir: pathlib.Path) -> str:
    tree = ET.parse(addon_dir / "addon.xml")
    version = tree.getroot().get("version", "").strip()
    if not version:
        raise SystemExit(f"no version in {addon_dir}/addon.xml")
    return version


def should_include(path: pathlib.Path, addon_dir: pathlib.Path) -> bool:
    rel = path.relative_to(addon_dir)
    if rel.parts[0] == ".":
        return False
    for part in rel.parts[:-1]:
        if part in EXCLUDE_DIRS:
            return False
    name = path.name
    if name in EXCLUDE_NAMES:
        return False
    if path.is_dir():
        return path.name not in EXCLUDE_DIRS
    if path.suffix in EXCLUDE_SUFFIXES:
        return False
    return True


def build_one(addon_dir: pathlib.Path, out_dir: pathlib.Path) -> pathlib.Path:
    version = addon_version(addon_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{addon_dir.name}-{version}.zip"

    with tempfile.TemporaryDirectory() as tmp:
        stage = pathlib.Path(tmp) / addon_dir.name
        shutil.copytree(
            addon_dir, stage,
            ignore=lambda d, names: [
                n for n in names
                if not should_include(pathlib.Path(d) / n, addon_dir)
                and (pathlib.Path(d) / n).exists()
            ],
        )
        # Defensive cleanup in case ignore missed nested junk
        for p in stage.rglob("*"):
            if p.is_dir() and p.name in EXCLUDE_DIRS:
                shutil.rmtree(p, ignore_errors=True)
        for p in stage.rglob("*.pyc"):
            p.unlink(missing_ok=True)

        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for f in sorted(stage.rglob("*")):
                if f.is_file():
                    zf.write(f, f.relative_to(tmp))

    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (out_dir / f"{zip_path.name}.sha256").write_text(f"{sha}  {zip_path.name}\n")
    print(f"built {zip_path} ({zip_path.stat().st_size} bytes) sha256={sha[:12]}...")
    return zip_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--addon", default=None, help="e.g. plugin.video.fmovies")
    ap.add_argument("--out", default="dist", help="output dir (default: dist)")
    args = ap.parse_args()

    addons = find_addons(args.addon)
    if not addons:
        raise SystemExit("no plugin.* addons found")
    out_dir = ROOT / args.out
    for addon in addons:
        build_one(addon, out_dir)


if __name__ == "__main__":
    sys.exit(main())
