import os
import re
import sys
import json
import queue
import shutil
import threading
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "yt-dlp Quick UI"
DEFAULT_OUTPUT = os.path.join(os.path.expanduser("~"), "Downloads", "%(title)s [%(id)s].%(ext)s")

QUALITY_CHOICES = [
    ("Best available", "best"),
    ("2160p / 4K", "2160"),
    ("1440p", "1440"),
    ("1080p", "1080"),
    ("720p", "720"),
    ("480p", "480"),
    ("360p", "360"),
]

VIDEO_CONTAINER_CHOICES = ["Automatic", "mp4", "mkv", "webm"]
VIDEO_CODEC_CHOICES = [
    ("H.264 + AAC (editor compatible)", "h264"),
    ("Best available codec", "best"),
]
AUDIO_CHOICES = ["mp3", "m4a", "aac", "opus", "vorbis", "flac", "alac", "wav"]
AUDIO_QUALITY_CHOICES = [
    ("Best", "0"),
    ("320 kbps", "320K"),
    ("256 kbps", "256K"),
    ("192 kbps", "192K"),
    ("128 kbps", "128K"),
    ("96 kbps", "96K"),
]
LOSSLESS_AUDIO_FORMATS = {"flac", "alac", "wav"}
DOWNLOAD_PERCENT_RE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
SPEED_RE = re.compile(r"at\s+([^\s]+/s)")
ETA_RE = re.compile(r"ETA\s+([^\s]+)")
APPLICATION_DIR = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent


def find_tool(name: str):
    """Find a companion tool beside the script/app before consulting PATH."""
    candidates = (
        APPLICATION_DIR / "tools" / name,
        APPLICATION_DIR / name,
        Path(sys.executable).resolve().parent / name,
        Path.cwd() / name,
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return shutil.which(name)


def find_executable():
    for name in ("yt-dlp.exe", "yt-dlp"):
        candidate = find_tool(name)
        if candidate and os.path.isfile(candidate):
            return [candidate]

    # When running from source, use the same interpreter that launched the GUI.
    # A frozen PyInstaller executable cannot run Python modules this way.
    launchers = []
    if not getattr(sys, "frozen", False):
        launchers.append(sys.executable)
    launchers.extend((shutil.which("py"), shutil.which("python")))
    for launcher in dict.fromkeys(item for item in launchers if item):
        if not launcher:
            continue
        try:
            result = subprocess.run(
                [launcher, "-m", "yt_dlp", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                return [launcher, "-m", "yt_dlp"]
        except Exception:
            pass
    return None


def build_video_format(height_choice: str, codec_choice: str = "best") -> str:
    height_filter = "" if height_choice == "best" else f"[height<={height_choice}]"
    if codec_choice == "h264":
        # avc1 (H.264) + mp4a (AAC) is broadly supported by video editors.
        # Do not silently fall back to VP9/AV1, since an MP4 container alone
        # does not make those codecs compatible with every editor.
        return (
            f"bv*[vcodec^=avc1]{height_filter}+ba[acodec^=mp4a]/"
            f"b[vcodec^=avc1][acodec^=mp4a]{height_filter}/"
            f"b[vcodec^=avc1]{height_filter}"
        )
    if height_choice == "best":
        return "bv*+ba/b"
    return (
        f"bv*{height_filter}+ba/"
        f"b{height_filter}/"
        f"bestvideo{height_filter}+bestaudio/"
        f"best{height_filter}"
    )


def text_progress_bar(percent: float, width: int = 18) -> str:
    percent = max(0.0, min(100.0, percent))
    filled = round((percent / 100.0) * width)
    return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"


class YTDLPGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1220x760")
        self.minsize(980, 650)

        self.exe = find_executable()
        self.ffmpeg_path = find_tool("ffmpeg.exe") or find_tool("ffmpeg")
        self.deno_path = find_tool("deno.exe") or find_tool("deno")
        self.event_queue = queue.Queue()
        self.job_counter = 0
        self.jobs = {}

        self.url_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="video")
        self.quality_var = tk.StringVar(value="Best available")
        self.video_container_var = tk.StringVar(value="mp4")
        self.video_codec_var = tk.StringVar(value=VIDEO_CODEC_CHOICES[0][0])
        self.audio_var = tk.StringVar(value="mp3")
        self.audio_quality_var = tk.StringVar(value="Best")
        self.output_var = tk.StringVar(value=DEFAULT_OUTPUT)
        self.cookies_var = tk.StringVar()
        self.embed_thumb_var = tk.BooleanVar(value=False)
        self.embed_metadata_var = tk.BooleanVar(value=True)
        self.write_subs_var = tk.BooleanVar(value=False)
        self.playlist_var = tk.BooleanVar(value=False)
        self.skip_existing_var = tk.BooleanVar(value=True)
        self.limit_manifest_var = tk.BooleanVar(value=True)
        self.auto_scroll_var = tk.BooleanVar(value=True)

        self._build_ui()
        self._set_initial_state()
        self.after(100, self._drain_queue)

    def _build_ui(self):
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")

        status_frame = ttk.Frame(top)
        status_frame.pack(fill="x", pady=(0, 8))

        self.tool_status = ttk.Label(status_frame, text=self._tool_status_text())
        self.tool_status.pack(side="left")
        ttk.Button(status_frame, text="Refresh yt-dlp detection", command=self._refresh_tool_detection).pack(side="right")

        input_frame = ttk.LabelFrame(top, text="New job", padding=10)
        input_frame.pack(fill="x")

        ttk.Label(input_frame, text="Link").grid(row=0, column=0, sticky="w")
        url_entry = ttk.Entry(input_frame, textvariable=self.url_var)
        url_entry.grid(row=0, column=1, columnspan=5, sticky="ew", padx=(8, 8))
        url_entry.bind("<Return>", lambda _e: self.add_job())
        ttk.Button(input_frame, text="Add job", command=self.add_job).grid(row=0, column=6, sticky="ew")

        ttk.Label(input_frame, text="Mode").grid(row=1, column=0, sticky="w", pady=(10, 0))
        mode_box = ttk.Combobox(
            input_frame,
            textvariable=self.mode_var,
            values=["video", "audio", "links"],
            state="readonly",
            width=16,
        )
        mode_box.grid(row=1, column=1, sticky="w", padx=(8, 12), pady=(10, 0))
        mode_box.bind("<<ComboboxSelected>>", lambda _e: self._sync_mode_widgets())

        ttk.Label(input_frame, text="Video quality").grid(row=1, column=2, sticky="w", pady=(10, 0))
        self.quality_box = ttk.Combobox(
            input_frame,
            textvariable=self.quality_var,
            values=[label for label, _ in QUALITY_CHOICES],
            state="readonly",
            width=18,
        )
        self.quality_box.grid(row=1, column=3, sticky="w", padx=(8, 12), pady=(10, 0))
        self.quality_box.current(0)

        ttk.Label(input_frame, text="Video file type").grid(row=1, column=4, sticky="w", pady=(10, 0))
        self.video_container_box = ttk.Combobox(
            input_frame,
            textvariable=self.video_container_var,
            values=VIDEO_CONTAINER_CHOICES,
            state="readonly",
            width=12,
        )
        self.video_container_box.grid(row=1, column=5, sticky="w", padx=(8, 12), pady=(10, 0))

        ttk.Label(input_frame, text="Audio format").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.audio_box = ttk.Combobox(
            input_frame,
            textvariable=self.audio_var,
            values=AUDIO_CHOICES,
            state="readonly",
            width=12,
        )
        self.audio_box.grid(row=2, column=1, sticky="w", padx=(8, 12), pady=(10, 0))
        self.audio_box.bind("<<ComboboxSelected>>", lambda _e: self._sync_audio_quality_widget())

        ttk.Label(input_frame, text="Audio quality").grid(row=2, column=2, sticky="w", pady=(10, 0))
        self.audio_quality_box = ttk.Combobox(
            input_frame,
            textvariable=self.audio_quality_var,
            values=[label for label, _ in AUDIO_QUALITY_CHOICES],
            state="readonly",
            width=18,
        )
        self.audio_quality_box.grid(row=2, column=3, sticky="w", padx=(8, 12), pady=(10, 0))

        ttk.Label(input_frame, text="Video codec").grid(row=2, column=4, sticky="w", pady=(10, 0))
        self.video_codec_box = ttk.Combobox(
            input_frame,
            textvariable=self.video_codec_var,
            values=[label for label, _ in VIDEO_CODEC_CHOICES],
            state="readonly",
            width=28,
        )
        self.video_codec_box.grid(row=2, column=5, columnspan=2, sticky="w", padx=(8, 0), pady=(10, 0))

        settings_frame = ttk.LabelFrame(input_frame, text="Download settings", padding=8)
        settings_frame.grid(row=3, column=0, columnspan=7, sticky="ew", pady=(10, 0))
        ttk.Checkbutton(
            settings_frame,
            text="Embed thumbnail (audio/video)",
            variable=self.embed_thumb_var,
        ).pack(side="left")

        ttk.Checkbutton(
            settings_frame,
            text="Embed metadata",
            variable=self.embed_metadata_var,
        ).pack(side="left", padx=(14, 0))

        ttk.Checkbutton(
            settings_frame,
            text="Write subtitles if available",
            variable=self.write_subs_var,
        ).pack(side="left", padx=(14, 0))

        ttk.Checkbutton(
            settings_frame,
            text="Download playlists",
            variable=self.playlist_var,
        ).pack(side="left", padx=(14, 0))

        ttk.Checkbutton(
            settings_frame,
            text="Skip existing files",
            variable=self.skip_existing_var,
        ).pack(side="left", padx=(14, 0))

        ttk.Checkbutton(
            settings_frame,
            text="Links: manifests only",
            variable=self.limit_manifest_var,
        ).pack(side="left", padx=(14, 0))

        ttk.Label(input_frame, text="Save to").grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(input_frame, textvariable=self.output_var).grid(row=4, column=1, columnspan=5, sticky="ew", padx=(8, 8), pady=(10, 0))
        ttk.Button(input_frame, text="Browse", command=self.pick_output).grid(row=4, column=6, sticky="ew", pady=(10, 0))

        ttk.Label(input_frame, text="Cookies file (optional)").grid(row=5, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(input_frame, textvariable=self.cookies_var).grid(row=5, column=1, columnspan=5, sticky="ew", padx=(8, 8), pady=(10, 0))
        ttk.Button(input_frame, text="Browse", command=self.pick_cookies).grid(row=5, column=6, sticky="ew", pady=(10, 0))

        for i in range(7):
            input_frame.columnconfigure(i, weight=1 if i in (1, 3, 5) else 0)
        input_frame.columnconfigure(1, weight=3)
        input_frame.columnconfigure(3, weight=1)
        input_frame.columnconfigure(5, weight=1)

        mid = ttk.Frame(self, padding=(12, 0, 12, 12))
        mid.pack(fill="both", expand=True)

        jobs_frame = ttk.LabelFrame(mid, text="Jobs", padding=8)
        jobs_frame.pack(fill="both", expand=True)

        cols = ("id", "mode", "status", "progress", "link", "detail")
        self.tree = ttk.Treeview(jobs_frame, columns=cols, show="headings", height=16)
        self.tree.heading("id", text="#")
        self.tree.heading("mode", text="Mode")
        self.tree.heading("status", text="Status")
        self.tree.heading("progress", text="Progress")
        self.tree.heading("link", text="Link")
        self.tree.heading("detail", text="Detail")
        self.tree.column("id", width=55, anchor="center")
        self.tree.column("mode", width=80, anchor="center")
        self.tree.column("status", width=110, anchor="center")
        self.tree.column("progress", width=210, anchor="w")
        self.tree.column("link", width=380)
        self.tree.column("detail", width=360)
        self.tree.pack(side="left", fill="both", expand=True)

        tree_scroll = ttk.Scrollbar(jobs_frame, orient="vertical", command=self.tree.yview)
        tree_scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=tree_scroll.set)

        buttons = ttk.Frame(mid)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Open selected folder", command=self.open_selected_folder).pack(side="left")
        ttk.Button(buttons, text="Copy selected detail", command=self.copy_selected_detail).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Copy selected link", command=self.copy_selected_link).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Clear finished", command=self.clear_finished).pack(side="right")

        summary_frame = ttk.LabelFrame(self, text="Activity summary", padding=8)
        summary_frame.pack(fill="both", expand=False, padx=12, pady=(0, 12))

        summary_top = ttk.Frame(summary_frame)
        summary_top.pack(fill="x", pady=(0, 6))
        ttk.Checkbutton(summary_top, text="Auto-scroll", variable=self.auto_scroll_var).pack(side="left")
        ttk.Button(summary_top, text="Clear activity", command=self.clear_activity).pack(side="right")

        self.log = tk.Text(summary_frame, wrap="word", height=8)
        self.log.pack(side="left", fill="both", expand=True)
        log_scroll = ttk.Scrollbar(summary_frame, orient="vertical", command=self.log.yview)
        log_scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=log_scroll.set)

    def _tool_status_text(self):
        if self.exe:
            return f"yt-dlp detected: {' '.join(self.exe)}"
        return "yt-dlp not found. Put yt-dlp.exe next to this script, install yt-dlp, or make it available on PATH."

    def _refresh_tool_detection(self):
        self.exe = find_executable()
        self.ffmpeg_path = find_tool("ffmpeg.exe") or find_tool("ffmpeg")
        self.deno_path = find_tool("deno.exe") or find_tool("deno")
        self.tool_status.config(text=self._tool_status_text())

    def _set_initial_state(self):
        self.quality_var.set("Best available")
        self.video_container_var.set("mp4")
        self.video_codec_var.set(VIDEO_CODEC_CHOICES[0][0])
        self.audio_var.set("mp3")
        self.audio_quality_var.set("Best")
        self._sync_mode_widgets()

    def _sync_mode_widgets(self):
        mode = self.mode_var.get()
        if mode == "video":
            self.quality_box.configure(state="readonly")
            self.video_container_box.configure(state="readonly")
            self.video_codec_box.configure(state="readonly")
            self.audio_box.configure(state="disabled")
            self.audio_quality_box.configure(state="disabled")
        elif mode == "audio":
            self.quality_box.configure(state="disabled")
            self.video_container_box.configure(state="disabled")
            self.video_codec_box.configure(state="disabled")
            self.audio_box.configure(state="readonly")
            self._sync_audio_quality_widget()
        else:
            self.quality_box.configure(state="disabled")
            self.video_container_box.configure(state="disabled")
            self.video_codec_box.configure(state="disabled")
            self.audio_box.configure(state="disabled")
            self.audio_quality_box.configure(state="disabled")

    def _sync_audio_quality_widget(self):
        if self.mode_var.get() == "audio" and self.audio_var.get() not in LOSSLESS_AUDIO_FORMATS:
            self.audio_quality_box.configure(state="readonly")
        else:
            self.audio_quality_box.configure(state="disabled")

    def pick_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_var.set(os.path.join(folder, "%(title)s [%(id)s].%(ext)s"))

    def pick_cookies(self):
        path = filedialog.askopenfilename(
            title="Choose cookies.txt file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.cookies_var.set(path)

    def add_job(self):
        if not self.exe:
            messagebox.showerror("yt-dlp not found", "I could not find yt-dlp. Install it or place yt-dlp.exe next to this script.")
            return

        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing link", "Paste a link first.")
            return

        self.job_counter += 1
        job_id = str(self.job_counter)
        mode = self.mode_var.get().strip()
        settings = {
            "video_quality": self.quality_var.get(),
            "video_container": self.video_container_var.get(),
            "video_codec": self.video_codec_var.get(),
            "audio_format": self.audio_var.get(),
            "audio_quality": self.audio_quality_var.get(),
            "output": self.output_var.get().strip() or DEFAULT_OUTPUT,
            "cookies": self.cookies_var.get().strip(),
            "embed_thumbnail": self.embed_thumb_var.get(),
            "embed_metadata": self.embed_metadata_var.get(),
            "write_subtitles": self.write_subs_var.get(),
            "download_playlist": self.playlist_var.get(),
            "skip_existing": self.skip_existing_var.get(),
            "limit_manifest": self.limit_manifest_var.get(),
        }
        if mode == "video":
            selected_type = settings["video_container"]
        elif mode == "audio":
            selected_type = settings["audio_format"]
        else:
            selected_type = "URLs"
        mode_display = f"{mode}/{selected_type}"

        self.jobs[job_id] = {
            "status": "Queued",
            "mode": mode,
            "url": url,
            "detail": "Waiting to start",
            "save_to": settings["output"],
            "settings": settings,
            "progress": 0.0,
            "progress_text": text_progress_bar(0) + "   0%",
        }
        self.tree.insert(
            "",
            "end",
            iid=job_id,
            values=(job_id, mode_display, "Queued", self.jobs[job_id]["progress_text"], url, "Waiting to start"),
        )

        worker = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        worker.start()
        self.url_var.set("")
        self._append_log(f"Job {job_id} queued: {mode} | {url}")

    def _enqueue(self, kind, *payload):
        self.event_queue.put((kind, payload))

    def _append_log(self, text):
        self.log.insert("end", text + "\n")
        if self.auto_scroll_var.get():
            self.log.see("end")

    def _drain_queue(self):
        try:
            while True:
                kind, payload = self.event_queue.get_nowait()
                if kind == "log":
                    self._append_log(*payload)
                elif kind == "status":
                    self._set_tree_status(*payload)
                elif kind == "detail":
                    self._set_tree_detail(*payload)
                elif kind == "progress":
                    self._set_tree_progress(*payload)
                elif kind == "done":
                    self._mark_done(*payload)
                elif kind == "clipboard":
                    self.clipboard_clear()
                    self.clipboard_append(*payload)
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)

    def _row_values(self, job_id):
        return list(self.tree.item(job_id, "values"))

    def _set_tree_status(self, job_id, status):
        if job_id in self.jobs:
            self.jobs[job_id]["status"] = status
        row = self._row_values(job_id)
        if row:
            row[2] = status
            self.tree.item(job_id, values=row)

    def _set_tree_detail(self, job_id, detail):
        if job_id in self.jobs:
            self.jobs[job_id]["detail"] = detail
        row = self._row_values(job_id)
        if row:
            row[5] = detail
            self.tree.item(job_id, values=row)

    def _set_tree_progress(self, job_id, percent, label_text=None):
        if job_id not in self.jobs:
            return
        percent = max(0.0, min(100.0, float(percent)))
        if label_text is None:
            label_text = f"{percent:.1f}%"
        progress_text = f"{text_progress_bar(percent)} {label_text}"
        self.jobs[job_id]["progress"] = percent
        self.jobs[job_id]["progress_text"] = progress_text
        row = self._row_values(job_id)
        if row:
            row[3] = progress_text
            self.tree.item(job_id, values=row)

    def _mark_done(self, job_id, status, detail):
        if status == "Done":
            self._set_tree_progress(job_id, 100.0, "100%")
        self._set_tree_status(job_id, status)
        self._set_tree_detail(job_id, detail)
        self._append_log(f"Job {job_id} {status.lower()}: {detail}")

    def _run_job(self, job_id):
        job = self.jobs[job_id]
        mode = job["mode"]
        url = job["url"]
        settings = job["settings"]
        self._enqueue("status", job_id, "Starting")
        self._enqueue("detail", job_id, "Launching yt-dlp...")
        self._enqueue("progress", job_id, 0, "0%")

        try:
            if mode == "links":
                self._run_links_job(job_id, url, settings)
            elif mode == "audio":
                self._run_audio_job(job_id, url, settings)
            else:
                self._run_video_job(job_id, url, settings)
        except Exception as e:
            self._enqueue("done", job_id, "Failed", str(e))

    def _base_cmd(self, settings):
        cmd = list(self.exe)
        cmd += ["--no-warnings", "--newline"]
        if self.ffmpeg_path:
            cmd += ["--ffmpeg-location", os.path.dirname(self.ffmpeg_path)]
        if self.deno_path:
            cmd += ["--js-runtimes", f"deno:{self.deno_path}"]
        cookies = settings["cookies"]
        if cookies:
            cmd += ["--cookies", cookies]
        cmd += ["--yes-playlist" if settings["download_playlist"] else "--no-playlist"]
        if settings["skip_existing"]:
            cmd += ["--no-overwrites"]
        return cmd

    def _extract_progress(self, line):
        match = DOWNLOAD_PERCENT_RE.search(line)
        if not match:
            return None

        percent = float(match.group(1))
        speed_match = SPEED_RE.search(line)
        eta_match = ETA_RE.search(line)
        extra = []
        if speed_match:
            extra.append(speed_match.group(1))
        if eta_match:
            extra.append(f"ETA {eta_match.group(1)}")
        label = f"{percent:.1f}%"
        if extra:
            label += " | " + " | ".join(extra)
        return percent, label

    def _run_and_stream(self, job_id, cmd, success_status="Done", success_detail="Completed"):
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            universal_newlines=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        last_line = ""
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.rstrip()
            if not line:
                continue
            last_line = line

            progress = self._extract_progress(line)
            if progress:
                percent, label = progress
                self._enqueue("status", job_id, "Downloading")
                self._enqueue("progress", job_id, percent, label)
                self._enqueue("detail", job_id, label)
                continue

            lower = line.lower()
            if "destination:" in lower:
                destination = line.split("Destination:", 1)[-1].strip() if "Destination:" in line else line
                self._enqueue("status", job_id, "Writing")
                self._enqueue("detail", job_id, destination)
            elif "merging formats" in lower or "ffmpeg" in lower or "extractaudio" in lower:
                self._enqueue("status", job_id, "Processing")
                self._enqueue("progress", job_id, max(self.jobs[job_id].get("progress", 0.0), 99.0), "99%")
                self._enqueue("detail", job_id, "Processing output...")
            elif "downloaded" in lower or "finished downloading playlist" in lower:
                self._enqueue("status", job_id, "Finishing")
                self._enqueue("detail", job_id, "Finalizing...")
            elif "error" in lower:
                self._enqueue("detail", job_id, line[:320])

        code = proc.wait()
        if code == 0:
            final_detail = success_detail if success_detail else (last_line or "Completed")
            self._enqueue("done", job_id, success_status, final_detail)
        else:
            self._enqueue("done", job_id, "Failed", last_line or f"Exit code {code}")

    def _run_video_job(self, job_id, url, settings):
        label_to_choice = {label: value for label, value in QUALITY_CHOICES}
        selected = label_to_choice.get(settings["video_quality"], "best")
        codec_values = {label: value for label, value in VIDEO_CODEC_CHOICES}
        codec = codec_values.get(settings["video_codec"], "h264")
        fmt = build_video_format(selected, codec)

        cmd = self._base_cmd(settings)
        cmd += [
            "-f", fmt,
            "-o", settings["output"],
        ]

        container = settings["video_container"]
        if container != "Automatic":
            cmd += ["--merge-output-format", container, "--remux-video", container]
        if settings["write_subtitles"]:
            cmd += ["--write-auto-subs", "--sub-langs", "all,-live_chat"]
        if settings["embed_thumbnail"]:
            cmd += ["--embed-thumbnail"]
        if settings["embed_metadata"]:
            cmd += ["--embed-metadata"]

        cmd += [url]
        detail = f"Video download finished ({settings['video_quality']}, {container}, {settings['video_codec']})"
        self._run_and_stream(job_id, cmd, success_detail=detail)

    def _run_audio_job(self, job_id, url, settings):
        audio_format = settings["audio_format"]
        quality_values = {label: value for label, value in AUDIO_QUALITY_CHOICES}
        cmd = self._base_cmd(settings)
        cmd += [
            "-x",
            "--audio-format", audio_format,
            "-o", settings["output"],
        ]
        if audio_format not in LOSSLESS_AUDIO_FORMATS:
            cmd += ["--audio-quality", quality_values.get(settings["audio_quality"], "0")]
        if settings["embed_thumbnail"]:
            cmd += ["--embed-thumbnail"]
        if settings["embed_metadata"]:
            cmd += ["--embed-metadata"]
        if settings["write_subtitles"]:
            cmd += ["--write-auto-subs", "--sub-langs", "all,-live_chat"]
        cmd += [url]
        if audio_format in LOSSLESS_AUDIO_FORMATS:
            detail = f"Audio download finished ({audio_format}, lossless)"
        else:
            detail = f"Audio download finished ({audio_format}, {settings['audio_quality']})"
        self._run_and_stream(job_id, cmd, success_detail=detail)

    def _run_links_job(self, job_id, url, settings):
        self._enqueue("status", job_id, "Inspecting")
        self._enqueue("detail", job_id, "Reading direct links...")
        self._enqueue("progress", job_id, 15, "15%")

        cmd = self._base_cmd(settings) + ["-J", url]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        if result.returncode != 0:
            out = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
            self._enqueue("done", job_id, "Failed", (out.strip() or "Could not read links")[:320])
            return

        self._enqueue("progress", job_id, 60, "60%")
        self._enqueue("detail", job_id, "Parsing format list...")

        try:
            info = json.loads(result.stdout)
        except json.JSONDecodeError:
            self._enqueue("done", job_id, "Failed", "yt-dlp did not return valid JSON")
            return

        urls = []
        seen = set()

        def add_url(val):
            if isinstance(val, str) and val.startswith(("http://", "https://")) and val not in seen:
                seen.add(val)
                urls.append(val)

        add_url(info.get("url"))
        add_url(info.get("manifest_url"))

        for fmt in info.get("formats", []):
            candidate = fmt.get("manifest_url") or fmt.get("url")
            if settings["limit_manifest"]:
                if isinstance(candidate, str) and (".m3u8" in candidate.lower() or "manifest" in candidate.lower()):
                    add_url(candidate)
            else:
                add_url(candidate)

        if not urls:
            self._enqueue("done", job_id, "Done", "No direct URLs found")
            return

        top_clipboard = "\n".join(urls)
        self._enqueue("clipboard", top_clipboard)

        preview = f"{len(urls)} link(s) copied to clipboard"
        if len(urls) == 1:
            preview += ": " + urls[0][:140]
        self._enqueue("progress", job_id, 100, "100%")
        self._enqueue("done", job_id, "Done", preview)

    def open_selected_folder(self):
        selected = self.tree.selection()
        if not selected:
            return
        job_id = selected[0]
        path = self.jobs.get(job_id, {}).get("save_to") or DEFAULT_OUTPUT
        folder = os.path.dirname(path)
        if not folder:
            folder = os.path.expanduser("~/Downloads")
        os.makedirs(folder, exist_ok=True)

        if sys.platform.startswith("win"):
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])

    def copy_selected_detail(self):
        selected = self.tree.selection()
        if not selected:
            return
        job_id = selected[0]
        detail = self.jobs.get(job_id, {}).get("detail", "")
        if detail:
            self.clipboard_clear()
            self.clipboard_append(detail)

    def copy_selected_link(self):
        selected = self.tree.selection()
        if not selected:
            return
        job_id = selected[0]
        url = self.jobs.get(job_id, {}).get("url", "")
        if url:
            self.clipboard_clear()
            self.clipboard_append(url)

    def clear_finished(self):
        for iid in list(self.tree.get_children()):
            status = self.jobs.get(iid, {}).get("status", "")
            if status in {"Done", "Failed"}:
                self.tree.delete(iid)
                self.jobs.pop(iid, None)

    def clear_activity(self):
        self.log.delete("1.0", "end")


if __name__ == "__main__":
    app = YTDLPGui()
    app.mainloop()
