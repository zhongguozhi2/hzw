"""
Concatenate multiple video segments into one final MP4 with audio crossfade.
Uses moviepy for cross-platform compatibility.
"""

import logging
import shutil
import subprocess
from pathlib import Path

import numpy as np

from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    VideoFileClip,
    concatenate_videoclips,
)

log = logging.getLogger(__name__)

AUDIO_CROSSFADE_SEC = 0.3


def concatenate_segments(
    segment_paths: list[str],
    output_path: str,
    audio_crossfade: float = AUDIO_CROSSFADE_SEC,
) -> str:
    """
    Concatenate *segment_paths* (ordered list of .mp4 files) into a single
    video at *output_path*.

    - Applies a short audio crossfade between segments.
    - Preserves original resolution and frame rate.
    """
    if not segment_paths:
        raise ValueError("没有可拼接的视频片段")

    if len(segment_paths) == 1:
        import shutil
        shutil.copy2(segment_paths[0], output_path)
        log.info("仅一个片段，直接复制: %s", output_path)
        return output_path

    clips: list[VideoFileClip] = []
    for p in segment_paths:
        log.info("加载片段: %s", p)
        clips.append(VideoFileClip(p))

    try:
        final = _concat_with_audio_fade(clips, audio_crossfade)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        log.info("正在写入最终视频: %s", output_path)
        final.write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            logger="bar",
        )
        log.info("拼接完成: %s (%.1f 秒)", output_path, final.duration)
    finally:
        for c in clips:
            c.close()

    return output_path


def write_srt(subtitles: list[str], srt_path: str, segment_durations: list[float]) -> str:
    """Write plain SRT with variable-duration subtitle entries."""
    Path(srt_path).parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    cursor = 0.0
    for i, text in enumerate(subtitles, 1):
        duration = segment_durations[i - 1] if i - 1 < len(segment_durations) else 5.0
        start = cursor
        end = cursor + duration
        lines.append(str(i))
        lines.append(f"{_fmt_ts(start)} --> {_fmt_ts(end)}")
        lines.append(text.strip() or " ")
        lines.append("")
        cursor = end
    Path(srt_path).write_text("\n".join(lines), encoding="utf-8")
    return srt_path


def mux_subtitles_with_ffmpeg(input_video: str, srt_path: str, output_video: str) -> str:
    """
    Add subtitle track into MP4 using ffmpeg (mov_text).
    If ffmpeg is unavailable, copies source to output.
    """
    Path(output_video).parent.mkdir(parents=True, exist_ok=True)
    if not shutil.which("ffmpeg"):
        shutil.copy2(input_video, output_video)
        log.warning("未找到 ffmpeg，已输出无字幕版本: %s", output_video)
        return output_video
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_video,
        "-i",
        srt_path,
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        "-c:s",
        "mov_text",
        output_video,
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output_video


def _fmt_ts(value: float) -> str:
    ms = int(round(value * 1000))
    hours = ms // 3600000
    ms %= 3600000
    mins = ms // 60000
    ms %= 60000
    secs = ms // 1000
    ms %= 1000
    return f"{hours:02d}:{mins:02d}:{secs:02d},{ms:03d}"


def _concat_with_audio_fade(
    clips: list[VideoFileClip],
    fade_sec: float,
) -> VideoFileClip:
    """
    Concatenate clips with a small audio crossfade at each boundary
    to avoid volume jumps or click artifacts.
    """
    processed: list[VideoFileClip] = []
    for i, clip in enumerate(clips):
        if clip.audio is None:
            processed.append(clip)
            continue

        c = clip
        if i > 0 and fade_sec > 0:
            c = c.with_effects([_AudioFadeIn(fade_sec)])
        if i < len(clips) - 1 and fade_sec > 0:
            c = c.with_effects([_AudioFadeOut(fade_sec)])
        processed.append(c)

    return concatenate_videoclips(processed, method="compose")


# ─── Lightweight audio fade effects ─────────────────────────────────────

class _AudioFadeIn:
    """moviepy effect: fade in the audio over *duration* seconds."""
    def __init__(self, duration: float):
        self.duration = duration

    def copy(self):
        return _AudioFadeIn(self.duration)

    def apply(self, clip: VideoFileClip) -> VideoFileClip:
        if clip.audio is None:
            return clip

        dur = self.duration

        def volume_filter(get_frame, t):
            frame = get_frame(t)
            factor = np.minimum(1.0, np.asarray(t) / dur) if dur > 0 else 1.0
            return frame * np.array([factor]).T if np.ndim(factor) > 0 else frame * factor

        new_audio = clip.audio.transform(volume_filter)
        return clip.with_audio(new_audio)


class _AudioFadeOut:
    """moviepy effect: fade out the audio over the last *duration* seconds."""
    def __init__(self, duration: float):
        self.duration = duration

    def copy(self):
        return _AudioFadeOut(self.duration)

    def apply(self, clip: VideoFileClip) -> VideoFileClip:
        if clip.audio is None:
            return clip

        total = clip.duration
        dur = self.duration

        def volume_filter(get_frame, t):
            frame = get_frame(t)
            remaining = total - np.asarray(t)
            factor = np.minimum(1.0, remaining / dur) if dur > 0 else 1.0
            return frame * np.array([factor]).T if np.ndim(factor) > 0 else frame * factor

        new_audio = clip.audio.transform(volume_filter)
        return clip.with_audio(new_audio)
