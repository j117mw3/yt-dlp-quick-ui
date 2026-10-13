"""Build pinned Windows packages and source materials for the 1.0.0 release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"
APP_NAME = "yt-dlp Quick UI"
PACKAGE_NAME = "yt-dlp-quick-ui"
CACHE = ROOT / ".release-cache"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
STAGE = DIST / PACKAGE_NAME
RELEASE = ROOT / "release-assets"
DEPENDENCIES = json.loads((ROOT / "tools" / "dependencies.json").read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return destination
    request = urllib.request.Request(url, headers={"User-Agent": "yt-dlp-quick-ui-release-builder"})
    temporary = destination.with_suffix(destination.suffix + ".part")
    print(f"Downloading {destination.name} ...", flush=True)
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    temporary.replace(destination)
    return destination


def verify_checksum_file(url: str, filename: str, expected: str, destination: Path) -> None:
    text = fetch(url, destination).read_text(encoding="utf-8", errors="replace")
    found = None
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == filename:
            found = parts[0].lower()
            break
    if found != expected.lower():
        raise RuntimeError(f"Upstream checksum mismatch for {filename}: expected {expected}, got {found}")


def download_verified(name: str, dependency: dict, url: str | None = None) -> Path:
    asset_url = url or dependency["url"]
    filename = Path(asset_url.split("?", 1)[0]).name
    destination = CACHE / name / filename
    expected = dependency["sha256"].lower()
    if destination.exists() and sha256(destination) == expected:
        return destination
    destination.unlink(missing_ok=True)
    download = fetch(asset_url, destination)
    actual = sha256(download)
    if actual != expected:
        download.unlink(missing_ok=True)
        raise RuntimeError(f"SHA-256 mismatch for {filename}: expected {expected}, got {actual}")
    return download


def verify_upstream_assets() -> dict[str, Path]:
    files: dict[str, Path] = {}
    ytdlp = DEPENDENCIES["yt_dlp"]
    verify_checksum_file(
        ytdlp["upstream_checksums"],
        ytdlp["upstream_filename"],
        ytdlp["sha256"],
        CACHE / "checksums" / "yt-dlp-SHA2-256SUMS.txt",
    )
    ffmpeg = DEPENDENCIES["ffmpeg"]
    verify_checksum_file(
        ffmpeg["upstream_checksums"],
        ffmpeg["upstream_filename"],
        ffmpeg["sha256"],
        CACHE / "checksums" / "ffmpeg-checksums.sha256",
    )
    deno = DEPENDENCIES["deno"]
    sidecar = fetch(
        deno["upstream_checksum_url"],
        CACHE / "checksums" / "deno-windows-x64.sha256sum",
    ).read_text(encoding="utf-8", errors="replace")
    match = re.search(r"Hash\s*:\s*([0-9a-fA-F]{64})", sidecar)
    if not match or match.group(1).lower() != deno["sha256"].lower():
        raise RuntimeError("Deno's upstream SHA-256 sidecar does not match the pinned digest")

    files["yt_dlp"] = download_verified("yt_dlp", ytdlp)
    files["ffmpeg"] = download_verified("ffmpeg", ffmpeg)
    files["deno"] = download_verified("deno", deno)
    return files


def copy_ffmpeg_license_files(archive: Path, license_dir: Path) -> None:
    license_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            name = Path(entry.filename).name.lower()
            if entry.is_dir() or not (name.startswith("copying") or name in {"license", "licenses.txt"}):
                continue
            relative = Path(entry.filename)
            try:
                relative.relative_to(Path("doc"))
            except ValueError:
                pass
            else:
                target = license_dir / ("FFmpeg-" + Path(entry.filename).name)
                target.write_bytes(bundle.read(entry))


def extract_bundled_tools(files: dict[str, Path]) -> None:
    tools_dir = STAGE / "tools"
    licenses_dir = STAGE / "licenses"
    tools_dir.mkdir(parents=True, exist_ok=True)
    licenses_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(files["yt_dlp"], tools_dir / "yt-dlp.exe")
    with zipfile.ZipFile(files["deno"]) as archive:
        deno_entry = next((item for item in archive.namelist() if item.lower().endswith("/deno.exe") or item.lower() == "deno.exe"), None)
        if deno_entry is None:
            raise RuntimeError("The pinned Deno archive did not contain deno.exe")
        (tools_dir / "deno.exe").write_bytes(archive.read(deno_entry))
    with zipfile.ZipFile(files["ffmpeg"]) as archive:
        for tool in ("ffmpeg.exe", "ffprobe.exe"):
            matches = [item for item in archive.namelist() if item.lower().endswith("/bin/" + tool)]
            if len(matches) != 1:
                raise RuntimeError(f"Expected one {tool} in the pinned FFmpeg archive; found {len(matches)}")
            (tools_dir / tool).write_bytes(archive.read(matches[0]))
    copy_ffmpeg_license_files(files["ffmpeg"], licenses_dir)

    for filename, url in (
        ("yt-dlp-THIRD_PARTY_LICENSES.txt", "https://raw.githubusercontent.com/yt-dlp/yt-dlp/2026.08.19/THIRD_PARTY_LICENSES.txt"),
        ("Deno-MIT-LICENSE.txt", "https://raw.githubusercontent.com/denoland/deno/v2.9.7/LICENSE.md"),
        ("PyInstaller-COPYING.txt", "https://raw.githubusercontent.com/pyinstaller/pyinstaller/v6.22.3/COPYING.txt"),
        ("Python-PSF-LICENSE.txt", "https://raw.githubusercontent.com/python/cpython/v3.12.10/LICENSE"),
        ("FFmpeg-LGPLv3-LICENSE.txt", "https://raw.githubusercontent.com/FFmpeg/FFmpeg/7e93014c5b/COPYING.LGPLv3"),
    ):
        target = fetch(url, CACHE / "licenses" / filename)
        shutil.copy2(target, licenses_dir / filename)

    (licenses_dir / "FFmpeg-LICENSE.txt").write_text(
        "FFmpeg version n9.0.2-27-g7e93014c5b, LGPL v3-or-later build.\n"
        "Run tools\\ffmpeg.exe -L for its license summary. The matching FFmpeg source and the pinned Windows build recipes are included in the third-party-source ZIP.\n",
        encoding="utf-8",
    )
    for output_name, args in (
        ("FFmpeg-BUILD-CONFIGURATION.txt", [str(tools_dir / "ffmpeg.exe"), "-buildconf"]),
        ("FFmpeg-ENCODERS.txt", [str(tools_dir / "ffmpeg.exe"), "-encoders"]),
        ("FFmpeg-LICENSE-SUMMARY.txt", [str(tools_dir / "ffmpeg.exe"), "-L"]),
    ):
        result = subprocess.run(args, capture_output=True, text=True, check=True)
        (licenses_dir / output_name).write_text(result.stdout + result.stderr, encoding="utf-8")


def find_iscc() -> str | None:
    configured = os.environ.get("ISCC_EXE")
    candidates = [configured, shutil.which("ISCC.exe"), shutil.which("ISCC")]
    candidates.extend(
        str(path)
        for path in (
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
            Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        )
    )
    return next((item for item in candidates if item and Path(item).is_file()), None)


def run_checked(command: list[str]) -> None:
    print("Running:", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def build_application() -> None:
    if sys.platform != "win32" or sys.maxsize < 2**32:
        raise RuntimeError("The Windows release builder requires 64-bit Windows and Python 3.12")
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Use the pinned Python 3.12 build environment")
    missing_screenshots = [
        name for name in ("app-overview.png",)
        if not (ROOT / "screenshots" / name).is_file()
    ]
    if missing_screenshots:
        raise RuntimeError("Add and privacy-check the README screenshots before building a public release: " + ", ".join(missing_screenshots))
    for folder in (BUILD, DIST, RELEASE):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True, exist_ok=True)
    tool_files = verify_upstream_assets()
    run_checked(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--windowed",
            "--name",
            APP_NAME,
            "--distpath",
            str(DIST),
            "--workpath",
            str(BUILD / "pyinstaller-work"),
            "--specpath",
            str(BUILD),
            str(ROOT / "yt_dlp_quick_ui.py"),
        ]
    )
    built_app = DIST / APP_NAME
    if not built_app.is_dir():
        raise RuntimeError("PyInstaller did not create the application folder")
    if STAGE.exists():
        shutil.rmtree(STAGE)
    shutil.move(str(built_app), str(STAGE))
    extract_bundled_tools(tool_files)
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", STAGE / "THIRD_PARTY_NOTICES.md")
    shutil.copy2(ROOT / "LICENSE", STAGE / "LICENSE-MIT.txt")

    for executable in ("yt-dlp.exe", "ffmpeg.exe", "ffprobe.exe", "deno.exe"):
        tool_path = STAGE / "tools" / executable
        if not tool_path.is_file():
            raise RuntimeError(f"Missing bundled tool: {tool_path.name}")
    ytdlp_result = subprocess.run([str(STAGE / "tools" / "yt-dlp.exe"), "--version"], capture_output=True, text=True)
    if ytdlp_result.returncode != 0 or ytdlp_result.stdout.strip() != DEPENDENCIES["yt_dlp"]["version"]:
        raise RuntimeError("The bundled yt-dlp executable failed its version check")
    if subprocess.run([str(STAGE / "tools" / "deno.exe"), "--version"], capture_output=True, text=True).returncode != 0:
        raise RuntimeError("The bundled Deno executable failed its version check")


def _zip_tree(zip_path: Path, source_root: Path, prefix: str | None = None) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(source_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source_root)
            arcname = Path(prefix, relative) if prefix else relative
            archive.write(path, arcname.as_posix())


def create_portable_zip() -> Path:
    destination = RELEASE / f"{PACKAGE_NAME}-v{VERSION}-portable.zip"
    print("Creating portable ZIP ...", flush=True)
    _zip_tree(destination, STAGE, PACKAGE_NAME)
    return destination


SOURCE_FILES = (
    ".gitignore",
    "README.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "CHANGELOG.md",
    "requirements-source.txt",
    "requirements-build.txt",
    "run.bat",
    "yt_dlp_quick_ui.py",
    "tools/dependencies.json",
    "tools/build_release.py",
    "tools/privacy_audit.py",
    "packaging/setup.iss",
    "screenshots/app-overview.png",
    "tests/test_app.py",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/workflows/release.yml",
)


def create_source_zip() -> Path:
    destination = RELEASE / f"{PACKAGE_NAME}-v{VERSION}-source.zip"
    print("Creating app source ZIP ...", flush=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for relative in SOURCE_FILES:
            path = ROOT / relative
            if path.is_file():
                archive.write(path, Path(PACKAGE_NAME, relative).as_posix())
    return destination


SOURCE_ARCHIVES = (
    ("yt-dlp-2026.08.19.tar.gz", "https://github.com/yt-dlp/yt-dlp/releases/download/2026.08.19/yt-dlp.tar.gz", "072aad4f2a7604e92155f61a275a4752dc64046c8f6d90df3710525d94cd37c1"),
    ("ffmpeg-7e93014c5b.zip", DEPENDENCIES["ffmpeg"]["source_url"], None),
    ("ffmpeg-windows-build-autobuild-2026-10-12-13-12.zip", DEPENDENCIES["ffmpeg"]["build_source_url"], None),
    ("deno-v2.9.7-source.zip", "https://github.com/denoland/deno/archive/refs/tags/v2.9.7.zip", None),
    ("pyinstaller-v6.22.3-source.zip", "https://github.com/pyinstaller/pyinstaller/archive/refs/tags/v6.22.3.zip", None),
)


def create_third_party_source_zip() -> Path:
    destination = RELEASE / f"{PACKAGE_NAME}-v{VERSION}-third-party-source.zip"
    print("Downloading pinned third-party source snapshots ...", flush=True)
    source_files = []
    for name, url, expected in SOURCE_ARCHIVES:
        path = fetch(url, CACHE / "sources" / name)
        if expected and sha256(path) != expected:
            path.unlink(missing_ok=True)
            raise RuntimeError(f"Pinned source checksum mismatch for {name}")
        source_files.append(path)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        materials = {
            "release": VERSION,
            "sources": [
                {"file": path.name, "url": url, "sha256": sha256(path)}
                for path, (_, url, _) in zip(source_files, SOURCE_ARCHIVES)
            ],
        }
        archive.writestr(
            "SOURCE-MATERIALS.txt",
            "yt-dlp Quick UI 1.0.0 third-party source materials\n\n"
            "These archives are the source snapshots for the versions recorded in THIRD_PARTY_NOTICES.md and tools/dependencies.json.\n"
            "The FFmpeg binary is the pinned LGPL Windows build; its command line build configuration and license summary are included in the portable and setup packages.\n"
            "The FFmpeg source tag and Windows build recipe archive are pinned in tools/dependencies.json. The build recipe archive documents its external build inputs.\n"
            "The yt-dlp archive is the upstream source tarball from its 2026.08.19 release.\n",
        )
        archive.writestr("SOURCE-MATERIALS.json", json.dumps(materials, indent=2) + "\n")
        archive.writestr(
            "SHA256SUMS.txt",
            "".join(f"{sha256(path)}  sources/{path.name}\n" for path in source_files),
        )
        for path in source_files:
            archive.write(path, Path("sources", path.name).as_posix())
    return destination


def compile_installer() -> Path:
    compiler = find_iscc()
    if not compiler:
        raise RuntimeError("Inno Setup 6 was not found. Install Inno Setup 6 or set ISCC_EXE to ISCC.exe.")
    destination = RELEASE / f"{PACKAGE_NAME}-setup-v{VERSION}.exe"
    destination.unlink(missing_ok=True)
    run_checked(
        [
            compiler,
            "/Qp",
            f"/DStageDir={STAGE}",
            f"/DReleaseDir={RELEASE}",
            f"/DAppVersion={VERSION}",
            str(ROOT / "packaging" / "setup.iss"),
        ]
    )
    if not destination.is_file():
        raise RuntimeError("Inno Setup completed without producing the setup EXE")
    return destination


def write_checksums() -> Path:
    expected = (
        RELEASE / f"{PACKAGE_NAME}-setup-v{VERSION}.exe",
        RELEASE / f"{PACKAGE_NAME}-v{VERSION}-portable.zip",
        RELEASE / f"{PACKAGE_NAME}-v{VERSION}-source.zip",
        RELEASE / f"{PACKAGE_NAME}-v{VERSION}-third-party-source.zip",
    )
    missing = [path.name for path in expected if not path.is_file()]
    if missing:
        raise RuntimeError("Cannot write final checksums; missing release assets: " + ", ".join(missing))
    manifest = RELEASE / "SHA256SUMS.txt"
    manifest.write_text("".join(f"{sha256(path)}  {path.name}\n" for path in expected), encoding="ascii")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-installer", action="store_true", help="Build the portable/source packages without compiling Inno Setup")
    args = parser.parse_args()
    build_application()
    portable = create_portable_zip()
    source = create_source_zip()
    third_party_source = create_third_party_source_zip()
    print("Prepared:", portable.name, source.name, third_party_source.name, sep="\n  ")
    if args.skip_installer:
        print("Installer skipped by request; no SHA256SUMS.txt was emitted.")
        return 0
    installer = compile_installer()
    manifest = write_checksums()
    print("Release assets:", installer.name, portable.name, source.name, third_party_source.name, manifest.name, sep="\n  ")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError, urllib.error.URLError) as exc:
        print(f"Release build failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

