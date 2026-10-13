"""Reject local profile paths and credential-like strings from release inputs."""

from __future__ import annotations

import os
import re
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", ".venv", ".build-venv", ".build-tools", ".release-cache", "build", "__pycache__", ".pytest_cache"}
TOKEN_PATTERNS = (
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}", re.IGNORECASE),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}", re.IGNORECASE),
    re.compile(rb"Bearer\s+[A-Za-z0-9._~+/-]{24,}", re.IGNORECASE),
)


def private_markers() -> list[tuple[str, bytes]]:
    markers: list[tuple[str, bytes]] = []
    profile = os.environ.get("USERPROFILE")
    if profile:
        account = Path(profile).name.strip()
        if len(account) >= 3:
            markers.append(("current Windows profile name", account.encode("utf-8")))
        markers.append(("current Windows profile path", str(Path(profile)).encode("utf-8")))
    markers.append(("current checkout path", str(ROOT).encode("utf-8")))
    expanded = []
    for label, value in markers:
        expanded.extend((label, item) for item in (value, value.decode("utf-8", "ignore").encode("utf-16le")))
    return [(label, value.lower()) for label, value in expanded if value]


def scan_stream(stream, markers: list[tuple[str, bytes]]) -> list[str]:
    problems: list[str] = []
    carry = b""
    chunk_size = 1024 * 1024
    overlap = max((len(marker) for _, marker in markers), default=0) + 32
    while True:
        block = stream.read(chunk_size)
        if not block:
            break
        data = carry + block
        lowered = data.lower()
        for label, marker in markers:
            if marker and marker in lowered:
                problems.append(label)
        for pattern in TOKEN_PATTERNS:
            if pattern.search(data):
                problems.append("credential-like token")
        carry = data[-overlap:] if overlap else b""
    return sorted(set(problems))


def included_files() -> list[Path]:
    found = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.name.endswith((".part", ".pyc")):
            continue
        found.append(path)
    return found


def main() -> int:
    markers = private_markers()
    problems: list[str] = []
    checked = 0
    for path in included_files():
        relative = path.relative_to(ROOT).as_posix()
        try:
            with path.open("rb") as stream:
                findings = scan_stream(stream, markers)
            checked += 1
            problems.extend(f"{relative}: {item}" for item in findings)
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path) as archive:
                    for member in archive.infolist():
                        if member.is_dir():
                            continue
                        with archive.open(member) as stream:
                            member_findings = scan_stream(stream, markers)
                        checked += 1
                        problems.extend(
                            f"{relative}!{member.filename}: {item}" for item in member_findings
                        )
        except (OSError, zipfile.BadZipFile) as error:
            problems.append(f"{relative}: could not inspect ({type(error).__name__})")
    if problems:
        print("Privacy audit failed:")
        for item in sorted(set(problems)):
            print(f"- {item}")
        return 1
    print(f"Privacy audit passed; inspected {checked} files and archive entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

