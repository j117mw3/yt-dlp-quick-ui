import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yt_dlp_quick_ui as app


class FormatTests(unittest.TestCase):
    def test_h264_prefers_compatible_streams_and_respects_quality(self):
        actual = app.build_video_format("1080", "h264")
        self.assertIn("bv*[vcodec^=avc1][height<=1080]+ba[acodec^=mp4a]", actual)

    def test_best_codec_uses_best_available_streams(self):
        self.assertEqual(app.build_video_format("best", "best"), "bv*+ba/b")

    def test_progress_bar_clamps_values(self):
        self.assertEqual(app.text_progress_bar(-5), "[------------------]")
        self.assertEqual(app.text_progress_bar(100), "[##################]")
        self.assertEqual(app.text_progress_bar(200), "[##################]")


class ToolDiscoveryTests(unittest.TestCase):
    def test_companion_tool_is_resolved_from_app_folder_first(self):
        with tempfile.TemporaryDirectory() as directory:
            app_dir = Path(directory)
            tool = app_dir / "tools" / "yt-dlp.exe"
            tool.parent.mkdir()
            tool.write_bytes(b"test executable placeholder")
            with patch.object(app, "APPLICATION_DIR", app_dir), patch("shutil.which", return_value=None):
                self.assertEqual(app.find_tool("yt-dlp.exe"), str(tool.resolve()))

    def test_source_mode_uses_active_python_for_module_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(app, "APPLICATION_DIR", Path(directory)),
                patch.object(app.sys, "executable", "python-active.exe"),
                patch("shutil.which", return_value=None),
                patch("subprocess.run", return_value=SimpleNamespace(returncode=0)) as run,
            ):
                self.assertEqual(app.find_executable(), ["python-active.exe", "-m", "yt_dlp"])
                self.assertEqual(run.call_args.args[0], ["python-active.exe", "-m", "yt_dlp", "--version"])

    def test_job_command_passes_companion_ffmpeg_and_deno(self):
        shell = object.__new__(app.YTDLPGui)
        shell.exe = ["C:\\demo\\tools\\yt-dlp.exe"]
        shell.ffmpeg_path = "C:\\demo\\tools\\ffmpeg.exe"
        shell.deno_path = "C:\\demo\\tools\\deno.exe"
        command = shell._base_cmd({"cookies": "", "download_playlist": False, "skip_existing": True})
        self.assertIn("--ffmpeg-location", command)
        self.assertIn("C:\\demo\\tools", command)
        self.assertIn("deno:C:\\demo\\tools\\deno.exe", command)


if __name__ == "__main__":
    unittest.main()

