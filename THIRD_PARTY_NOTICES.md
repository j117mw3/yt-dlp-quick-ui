# Third-party software

The Windows release packages include separate copies of the following tools.
Each tool remains under its own license; the MIT license for this application
does not change those terms.

| Tool | Version | License | Source |
| --- | --- | --- | --- |
| yt-dlp | 2026.08.19 | The upstream Windows PyInstaller executable is GPLv3+; component notices are included with the binary | [Release source](https://github.com/yt-dlp/yt-dlp/tree/2026.08.19) |
| FFmpeg | n9.0.2-27-g7e93014c5b | LGPL 3 or later build, based on its pinned `--enable-version3` configuration | [FFmpeg source](https://github.com/FFmpeg/FFmpeg/tree/7e93014c5b) and [Windows build recipes](https://github.com/BtbN/FFmpeg-Builds/tree/autobuild-2026-10-12-13-12) |
| Deno | 2.9.7 | MIT | [Deno source](https://github.com/denoland/deno/tree/v2.9.7) |
| PyInstaller | 6.22.3 | GPL with the PyInstaller bootloader exception | [PyInstaller source](https://github.com/pyinstaller/pyinstaller/tree/v6.22.3) |
| CPython | 3.12 | Python Software Foundation License | [CPython source](https://github.com/python/cpython/tree/v3.12.10) |

The release's `third-party-source.zip` contains source snapshots for the
redistributed yt-dlp, FFmpeg, and FFmpeg Windows build recipe revisions. The
FFmpeg package is the LGPL build; its own `-L` output and included notice files
identify the license and build configuration. Deno and PyInstaller source
links above are version-pinned.

The release builder verifies the official Deno archive checksum before
replacing embedded Windows build-profile prefixes with a neutral, same-length
path. This only normalizes source-location strings included in the upstream
binary; it does not alter executable code. The Deno source archive is included
in the third-party source package.

yt-dlp's standalone executable carries its own compiled third-party notices.
The downloaded upstream notices, FFmpeg notices, and Deno license are copied
into the installed application's `licenses` directory when the release is
built. Consult those files for the complete component-level license details.

The separate yt-dlp and FFmpeg tools have their own upstream behavior and
licenses. This application simply invokes those programs as child processes.

