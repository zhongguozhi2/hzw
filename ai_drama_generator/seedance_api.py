"""
Seedance 2.0 API client.
Uses Volcengine Ark API (Seedance 2.0) with async pattern: submit → poll → download.
"""

import logging
import os
import time
from pathlib import Path
from typing import Any

import requests

from config import (
    ASPECT_RATIO,
    GENERATE_AUDIO,
    MAX_RETRIES,
    MULTI_REF_MODEL,
    POLL_INTERVAL,
    POLL_TIMEOUT,
    RETRY_BACKOFF,
    VIDEO_FPS,
    VIDEO_QUALITY,
    VOLCENGINE_MODEL,
    get_api_key,
    get_base_url,
)

log = logging.getLogger(__name__)


def _normalize_duration_for_model(model: str, duration_seconds: float) -> int:
    """Normalize duration to integer seconds in [4, 12]."""
    requested = float(duration_seconds)
    # 全局统一约束：duration 取整数秒，范围固定 [4, 12]。
    normalized = int(round(requested))
    return max(4, min(12, normalized))


def _duration_to_frames(duration_seconds: int, fps: int) -> int:
    """Convert integer seconds to frame count."""
    return int(duration_seconds * fps)


# ═══════════════════════════════════════════════════════════════════════════
# Provider-agnostic helpers
# ═══════════════════════════════════════════════════════════════════════════

def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json",
    }


def _post(url: str, payload: dict, *, retries: int = MAX_RETRIES) -> dict:
    """POST with exponential-backoff retries on transient errors."""
    delay = 2
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, json=payload, headers=_headers(), timeout=30)
            if resp.status_code == 429:
                wait = delay * (RETRY_BACKOFF ** attempt)
                log.warning("限流 (429)，%d 秒后重试 (%d/%d)", wait, attempt, retries)
                time.sleep(wait)
                continue
            if not resp.ok:
                body_preview = (resp.text or "")[:800]
                log.error(
                    "API 返回非成功: status=%s url=%s body=%s",
                    resp.status_code,
                    url,
                    body_preview,
                )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as exc:
            last_err = exc
            if attempt < retries:
                wait = delay * (RETRY_BACKOFF ** attempt)
                log.warning("请求失败，%d 秒后重试 (%d/%d): %s", wait, attempt, retries, exc)
                time.sleep(wait)
    raise RuntimeError(f"API 请求失败（已重试 {retries} 次）: {last_err}")


def _get(url: str) -> dict:
    resp = requests.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


# ═══════════════════════════════════════════════════════════════════════════
# Volcengine Ark API
# ═══════════════════════════════════════════════════════════════════════════

def _volcengine_create_task(
    prompt: str,
    ref_image_url: str | None = None,
    character_image_urls: list[str] | None = None,
    scene_image_urls: list[str] | None = None,
    duration_seconds: float = 5.0,
    use_reference_role: bool = False,
) -> str:
    """Create a video generation task via the Volcengine Ark API, return task_id."""
    # "多图片参考"：同一次请求 content 里参考图数量 >= 2 时使用专用模型。
    ref_image_count = (
        len(character_image_urls or [])
        + len(scene_image_urls or [])
        + (1 if ref_image_url else 0)
    )
    model = MULTI_REF_MODEL if ref_image_count >= 2 else VOLCENGINE_MODEL
    duration_for_api = _normalize_duration_for_model(model, duration_seconds)
    frames_for_api = _duration_to_frames(duration_for_api, VIDEO_FPS)
    msg = (
        f"视频生成模型选择: model={model} ref_image_count={ref_image_count} "
        f"(char={len(character_image_urls or [])} scene={len(scene_image_urls or [])} "
        f"tail_ref={bool(ref_image_url)}) use_reference_role={use_reference_role} "
        f"duration_req={float(duration_seconds):.1f}s duration_api={duration_for_api}s "
        f"frames_api={frames_for_api}"
    )
    # run_segments_from_prompt_json.py 可能未初始化 logging handler，所以这里同时 print。
    print(msg)
    log.info(msg)

    base = get_base_url()
    url = f"{base}/contents/generations/tasks"

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for img_url in character_image_urls or []:
        item: dict[str, Any] = {
            "type": "image_url",
            "image_url": {"url": img_url},
        }
        if use_reference_role:
            item["role"] = "reference_image"
        content.append(item)
    for img_url in scene_image_urls or []:
        item = {
            "type": "image_url",
            "image_url": {"url": img_url},
        }
        if use_reference_role:
            item["role"] = "reference_image"
        content.append(item)
    if ref_image_url:
        item = {
            "type": "image_url",
            "image_url": {"url": ref_image_url},
        }
        if use_reference_role:
            item["role"] = "reference_image"
        content.append(item)

    payload: dict[str, Any] = {
        "model": model,
        "content": content,
        "extra": {
            # 文档说明 frames 优先于 duration，这里仅传 frames 以避免被默认时长覆盖。
            "frames": frames_for_api,
            "resolution": VIDEO_QUALITY,
            "fps": VIDEO_FPS,
            "aspect_ratio": ASPECT_RATIO,
            "generate_audio": GENERATE_AUDIO,
            "style": "cinematic",
        },
    }

    data = _post(url, payload)
    task_id = (
        data.get("id")
        or data.get("data", {}).get("task_id")
        or data.get("task_id")
    )
    if not task_id:
        raise RuntimeError(f"创建任务失败，未返回 task_id: {data}")
    log.info("Volcengine 任务已创建: %s", task_id)
    return task_id


def _volcengine_poll(task_id: str) -> str:
    """Poll a Volcengine task until completion. Return the video URL."""
    base = get_base_url()
    url = f"{base}/contents/generations/tasks/{task_id}"
    start = time.time()

    while True:
        elapsed = time.time() - start
        if elapsed > POLL_TIMEOUT:
            raise TimeoutError(f"任务 {task_id} 超时 ({POLL_TIMEOUT}s)")

        data = _get(url)
        inner = data.get("data", data)
        status = inner.get("status", "unknown")
        progress = inner.get("progress", "?")
        log.info("[%ds] 任务 %s: %s (%s%%)", int(elapsed), task_id, status, progress)

        # Some providers return "completed", others may return "succeeded".
        if status in {"completed", "succeeded"}:
            video_url = (
                (inner.get("results") or [None])[0]
                or inner.get("output", {}).get("video_url")
                or inner.get("content", {}).get("video_url")
            )
            if not video_url:
                raise RuntimeError(f"任务完成但未获取到视频 URL: {inner}")
            return video_url

        if status == "failed":
            raise RuntimeError(f"任务 {task_id} 失败: {inner}")

        time.sleep(POLL_INTERVAL)


# ═══════════════════════════════════════════════════════════════════════════
# Public interface
# ═══════════════════════════════════════════════════════════════════════════

def create_video_task(
    prompt: str,
    ref_image_url: str | None = None,
    character_image_urls: list[str] | None = None,
    scene_image_urls: list[str] | None = None,
    duration_seconds: float = 5.0,
    use_reference_role: bool = False,
) -> str:
    """Create a video generation task via Volcengine Ark. Returns task_id."""
    return _volcengine_create_task(
        prompt,
        ref_image_url,
        character_image_urls,
        scene_image_urls,
        duration_seconds=duration_seconds,
        use_reference_role=use_reference_role,
    )


def wait_for_video(task_id: str) -> str:
    """Block until the task completes and return the video download URL."""
    return _volcengine_poll(task_id)


def download_video(url: str, dest: str) -> str:
    """Stream-download a video from *url* to *dest*. Returns dest path."""
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    log.info("下载视频: %s → %s", url, dest)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    size_kb = os.path.getsize(dest) // 1024
    log.info("下载完成: %s (%d KB)", dest, size_kb)
    return dest
