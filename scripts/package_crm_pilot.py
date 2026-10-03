"""Build a CRM release from an explicit allowlist; never include local data."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import uuid


ROOT = Path(__file__).resolve().parents[1]
FIXED_FILES = (
    "crm_pilot.py", "models.py", "extensions.py",
    "requirements-crm-pilot.txt", "README_CRM.md", "DEVELOPMENT_LOG.md",
    "deploy/crm-pilot.service", "deploy/nginx-crm-pilot.conf", "deploy/README.md",
)
OCR_BASE = "static/crm/vendor/ocr/"
OCR_FILES = (
    "tesseract.min.js", "worker.min.js",
    "tesseract.min.js.LICENSE.txt", "worker.min.js.LICENSE.txt",
    "lang/slk.traineddata.gz", "lang/eng.traineddata.gz",
)
OCR_VARIANTS = ("", "-lstm", "-simd", "-simd-lstm", "-relaxedsimd", "-relaxedsimd-lstm")
REQUIRED_FILES = (
    *FIXED_FILES, "crm/__init__.py", "crm/routes.py", "crm/receipts.py", "crm/ai_receipts.py",
    "templates/crm/base.html", "templates/crm/detail.html", "templates/crm/receipt.html",
    "static/crm/crm.css", "static/crm/job-notes.js", "static/crm/receipt-ui.js", "static/crm/receipt-parser.mjs",
    *(OCR_BASE + name for name in OCR_FILES),
    *(f"{OCR_BASE}core/tesseract-core{variant}.wasm{suffix}"
      for variant in OCR_VARIANTS for suffix in ("", ".js")),
)


def checked_file(relative: str) -> Path:
    path = ROOT / relative
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Chýba potrebný súbor alebo je prázdny: {relative}")
    # Symlinked ancestors could otherwise pull a secret from outside the repo.
    cursor = path
    while cursor != ROOT:
        if cursor.is_symlink():
            raise ValueError(f"Balík nepovoľuje symbolické odkazy: {relative}")
        cursor = cursor.parent
    if not path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError(f"Súbor je mimo projektu: {relative}")
    return path


def release_files() -> list[str]:
    for relative in REQUIRED_FILES:
        checked_file(relative)
    names = set(FIXED_FILES)
    for directory, suffixes in (
        ("crm", {".py"}),
        ("templates/crm", {".html"}),
        ("static/crm", {".css", ".svg", ".js", ".mjs", ".wasm", ".gz", ".txt"}),
    ):
        folder = ROOT / directory
        for path in folder.rglob("*"):
            relative = path.relative_to(ROOT).as_posix()
            if path.is_symlink():
                raise ValueError(f"Balík nepovoľuje symbolické odkazy: {relative}")
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix not in suffixes:
                raise ValueError(f"Nepovolený súbor v priečinku CRM: {relative}")
            checked_file(relative)
            names.add(relative)
    return sorted(names)


def build_release(names: list[str]) -> tuple[Path, Path]:
    work = ROOT / "work"
    if work.is_symlink():
        raise ValueError("Priečinok work nesmie byť symbolický odkaz.")
    if not work.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Priečinok work musí zostať v projekte.")
    work.mkdir(exist_ok=True)
    created = datetime.now(timezone.utc)
    release_id = created.strftime("%Y%m%dT%H%M%S%fZ")
    archive = work / f"crm-pilot-release-{release_id}.tar.gz"
    manifest_path = archive.with_name(archive.name.removesuffix(".tar.gz") + ".manifest.json")
    temporary = work / f".crm-release-{uuid.uuid4().hex}.tmp"
    files = []
    try:
        with temporary.open("xb") as output:
            with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w") as package:
                    for relative in names:
                        content = checked_file(relative).read_bytes()
                        metadata = tarfile.TarInfo(relative)
                        metadata.size = len(content)
                        metadata.mode = 0o644
                        metadata.mtime = int(created.timestamp())
                        metadata.uid = metadata.gid = 0
                        metadata.uname = metadata.gname = ""
                        package.addfile(metadata, io.BytesIO(content))
                        files.append({"path": relative, "size": len(content),
                                      "sha256": hashlib.sha256(content).hexdigest()})
        temporary.replace(archive)
        manifest = {
            "release_id": release_id,
            "created_at": created.isoformat(),
            "archive": archive.name,
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "files": files,
        }
        with manifest_path.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(manifest, output, ensure_ascii=False, indent=2)
            output.write("\n")
    finally:
        temporary.unlink(missing_ok=True)
    return archive, manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Balík CRM bez lokálnych databáz a tajných údajov.")
    parser.add_argument("--check", action="store_true", help="Iba overí povolené súbory; nevytvorí archív.")
    args = parser.parse_args()
    try:
        names = release_files()
        if args.check:
            print(f"Overené: {len(names)} povolených súborov, vrátane slovenského a anglického OCR.")
            return 0
        archive, manifest = build_release(names)
        print(f"Balík: {archive}")
        print(f"Kontrolný zoznam: {manifest}")
        print("Balík neobsahuje .env, databázy, bločky ani pôvodné nahraté prílohy.")
        return 0
    except (OSError, ValueError) as error:
        parser.exit(1, f"Balík nevytvorený: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
