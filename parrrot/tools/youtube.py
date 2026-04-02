"""
Parrrot — YouTube video understanding tools
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional

from parrrot.tools.registry import registry

_YTDLP_MSG = "YouTube tools require yt-dlp. Install: pip install yt-dlp"


def _get_video_info(url: str) -> str:
    """Get video metadata without downloading."""
    try:
        import yt_dlp  # type: ignore[import]
    except ImportError:
        return _YTDLP_MSG

    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return (
            f"Title:       {info.get('title', 'N/A')}\n"
            f"Channel:     {info.get('uploader', 'N/A')}\n"
            f"Duration:    {info.get('duration', 0) // 60}m {info.get('duration', 0) % 60}s\n"
            f"Views:       {info.get('view_count', 'N/A'):,}\n"
            f"Upload date: {info.get('upload_date', 'N/A')}\n"
            f"Description: {(info.get('description') or '')[:300]}"
        )
    except Exception as e:
        return f"Could not get video info: {e}"


def _get_transcript(url: str) -> str:
    """Fetch YouTube auto-generated transcript."""
    try:
        import yt_dlp
    except ImportError:
        return _YTDLP_MSG

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en"],
        "subtitlesformat": "vtt",
        "outtmpl": os.path.join(tempfile.gettempdir(), "%(id)s.%(ext)s"),
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info.get("id", "")

        # Find the .vtt file
        vtt_path = os.path.join(tempfile.gettempdir(), f"{video_id}.en.vtt")
        if not os.path.exists(vtt_path):
            return "No English transcript available for this video."

        # Parse VTT — strip timestamps and dedup
        import re
        text = open(vtt_path, encoding="utf-8").read()
        lines = re.sub(r"\d+:\d+:\d+\.\d+ --> .*\n", "", text)
        lines = re.sub(r"WEBVTT.*\n", "", lines)
        lines = re.sub(r"\n{2,}", "\n", lines).strip()
        os.unlink(vtt_path)
        return lines[:5000]
    except Exception as e:
        return f"Could not get transcript: {e}"


async def _extract_frames(url: str, n_frames: int = 5) -> str:
    """Extract key frames from a YouTube video."""
    try:
        import yt_dlp
        from PIL import Image
    except ImportError:
        return _YTDLP_MSG + "\nAlso install: pip install Pillow"

    tmpdir = tempfile.mkdtemp()
    ydl_opts = {
        "quiet": True,
        "format": "best[height<=480]",
        "outtmpl": os.path.join(tmpdir, "video.%(ext)s"),
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            duration = info.get("duration", 60)

        # Find downloaded file
        video_file = next(
            (os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.startswith("video.")),
            None,
        )
        if not video_file:
            return "Video download failed."

        # Extract frames using ffmpeg
        frame_paths: list[str] = []
        for i in range(n_frames):
            t = int(duration * (i + 1) / (n_frames + 1))
            out = os.path.join(tmpdir, f"frame_{i}.jpg")
            os.system(f'ffmpeg -ss {t} -i "{video_file}" -vframes 1 -q:v 2 "{out}" -y -loglevel quiet')
            if os.path.exists(out):
                frame_paths.append(out)

        return f"Extracted {len(frame_paths)} frames:\n" + "\n".join(frame_paths)
    except Exception as e:
        return f"Frame extraction failed: {e}"


async def _summarize_video(url: str) -> str:
    """Full video summary using transcript + metadata."""
    info = _get_video_info(url)
    transcript = _get_transcript(url)

    prompt = (
        f"Here is a YouTube video:\n\n{info}\n\n"
        f"Transcript (partial):\n{transcript[:3000]}\n\n"
        f"Please give a clear, concise summary of what this video is about, "
        f"the main points covered, and who it would be useful for."
    )

    try:
        from parrrot.core.router import Router
        from parrrot.models.base import CompletionRequest, Message

        router = Router()
        request = CompletionRequest(
            messages=[Message(role="user", content=prompt)],
            max_tokens=1024,
        )
        response = await router.complete(request)
        return response.content
    except Exception as e:
        return f"Could not summarize: {e}"


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

registry.register("get_video_info", "Get title, duration, views, description of a YouTube video", {"url": "YouTube URL"})(_get_video_info)
registry.register("get_transcript", "Fetch the auto-generated transcript of a YouTube video", {"url": "YouTube URL"})(_get_transcript)
registry.register("extract_frames", "Extract key frames from a YouTube video as images", {"url": "YouTube URL", "n_frames": "number of frames to extract (default 5)"})(_extract_frames)
registry.register("summarize_video", "Get a full AI summary of a YouTube video", {"url": "YouTube URL"})(_summarize_video)
