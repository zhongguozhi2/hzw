"""
Extracts the last frame from a video file and encodes it as base64.
Uses OpenCV so we don't need a full FFmpeg binary on PATH.
"""

import base64
import os
import pathlib
import shutil
import tempfile
import uuid

import cv2


def _temp_jpg_path_for_cv2() -> pathlib.Path:
    """
    cv2.imwrite on Windows often fails for paths containing non-ASCII characters
    (e.g. username under C:\\Users\\...). Use a pure-ASCII temp dir when possible.
    """
    if os.name == "nt":
        win_tmp = pathlib.Path(r"C:\Windows\Temp")
        if win_tmp.is_dir():
            return win_tmp / f"last_frame_{uuid.uuid4().hex}.jpg"
    return pathlib.Path(tempfile.gettempdir()) / f"last_frame_{uuid.uuid4().hex}.jpg"


def extract_last_frame_base64(video_path: str) -> str:
    """
    Open *video_path*, seek to the last frame, and return a
    base64-encoded JPEG string suitable for the API reference_image field.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频文件: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        raise RuntimeError(f"视频帧数为0: {video_path}")

    cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError(f"无法读取视频最后一帧: {video_path}")

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def save_last_frame(video_path: str, output_path: str | None = None) -> str:
    """Save the last frame as a JPEG file. Returns the saved path."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频文件: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total_frames - 1))
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError(f"无法读取视频最后一帧: {video_path}")

    if output_path is None:
        stem = pathlib.Path(video_path).stem
        output_path = str(
            pathlib.Path(tempfile.gettempdir()) / f"{stem}_last_frame.jpg"
        )

    out = pathlib.Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # OpenCV on Windows often fails cv2.imwrite() to paths with non-ASCII characters.
    # Write to an ASCII temp path first, then copy to the final destination.
    tmp = _temp_jpg_path_for_cv2()
    ok = cv2.imwrite(str(tmp), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise RuntimeError(f"cv2.imwrite 失败（临时文件）: {tmp}")
    try:
        shutil.copy2(tmp, out)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    return str(out.resolve())
