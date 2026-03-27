#!/usr/bin/env python3
"""AI短剧自动生成工具：剧本 -> 分镜脚本 -> 5秒片段 -> 流畅拼接+字幕 -> 飞书发送。"""

import argparse
import base64
import json
import logging
import mimetypes
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

from story_splitter import Segment, StoryboardPlan, split_story
from seedance_api import create_video_task, wait_for_video, download_video
from frame_extractor import extract_last_frame_base64, save_last_frame
from video_concat import concatenate_segments, mux_subtitles_with_ffmpeg, write_srt
from send_file_to_feishu import build_client, send_file_message, send_text_message, upload_file

log = logging.getLogger("ai_drama")

DEFAULT_CHAT_ID = "oc_64dd7b229c2a269377853397c575cc97"
DEFAULT_OUTPUT_ROOT = Path(r"D:\cbc\hzw\ai_drama_generator")

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def setup_logging(verbose: bool = False) -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    root_logger = logging.getLogger()
    # Keep console logging behavior, but also persist to log file.
    if not root_logger.handlers:
        logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")
    else:
        root_logger.setLevel(level)
    log_path = Path(__file__).resolve().parent / "log.log"
    # Avoid duplicate file handlers across repeated runs.
    file_exists = False
    for h in root_logger.handlers:
        if isinstance(h, logging.FileHandler):
            base = getattr(h, "baseFilename", "")
            if str(log_path) in base:
                file_exists = True
                break
    if not file_exists:
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(level)
        formatter = logging.Formatter(fmt, datefmt="%H:%M:%S")
        fh.setFormatter(formatter)
        root_logger.addHandler(fh)


def print_storyboard(segments: list[Segment]) -> None:
    """Pretty-print the generated storyboard."""
    print("\n" + "=" * 60)
    print("  分镜脚本")
    print("=" * 60)
    for seg in segments:
        tag = "【首段】" if seg.is_first else f"【第{seg.index + 1}段】"
        print(f"\n{tag}")
        print(f"  镜号: {seg.shot_no}")
        print(f"  原文: {seg.raw_text}")
        if seg.narration:
            print(f"  旁白: {seg.narration}")
        print(f"  景别: {seg.shot_type}  |  运镜: {seg.camera_move}  |  时长: {seg.duration_seconds:.1f}s")
        print(f"  提示词: {seg.prompt}")
    print("\n" + "=" * 60 + "\n")


def _local_image_to_data_url(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    mime = mime or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def _list_image_files(directory: Path) -> list[Path]:
    """List image files under *directory* (sorted by name)."""
    if not directory.is_dir():
        return []
    return sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )


def _copy_images_to_dir(sources: list[str], dest_dir: Path) -> None:
    """Copy user-provided images into *dest_dir* with stable numbered names."""
    if not sources:
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    existing = _list_image_files(dest_dir)
    start = len(existing)
    for i, raw in enumerate(sources):
        src = Path(raw).expanduser().resolve()
        if not src.is_file():
            raise FileNotFoundError(f"图片文件不存在: {src}")
        dest_name = f"{start + i + 1:03d}_{src.name}"
        shutil.copy2(src, dest_dir / dest_name)


def _prepare_image_urls_from_paths(paths: list[Path]) -> list[str]:
    return [_local_image_to_data_url(p) for p in paths]


def _merge_character_and_scene_refs(
    title_dir: Path,
    episode_base_dir: Path,
) -> tuple[list[Path], list[Path]]:
    """
    主角色/主场景：{剧名}/role、{剧名}/scene
    本集角色/本集场景：{剧名}/{集数}/role、{剧名}/{集数}/scene
    生成时合并：主 + 本集，全部发给视频模型。
    """
    main_role = _list_image_files(title_dir / "role")
    ep_role = _list_image_files(episode_base_dir / "role")
    main_scene = _list_image_files(title_dir / "scene")
    ep_scene = _list_image_files(episode_base_dir / "scene")

    char_paths = main_role + ep_role
    scene_paths = main_scene + ep_scene
    return char_paths, scene_paths


def _load_role_design_context(title_dir: Path, episode_base_dir: Path) -> str:
    """
    Load optional role design files:
      - {剧名}/role_design.txt
      - {剧名}/{集数}/role_design.txt
    Return merged text for model context.
    """
    chunks: list[str] = []
    main_design = title_dir / "role_design.txt"
    ep_design = episode_base_dir / "role_design.txt"
    if main_design.is_file():
        chunks.append(f"[全剧角色设定]\n{main_design.read_text(encoding='utf-8').strip()}")
    if ep_design.is_file():
        chunks.append(f"[本集角色设定]\n{ep_design.read_text(encoding='utf-8').strip()}")
    return "\n\n".join([c for c in chunks if c.strip()])


def _compose_model_prompt(seg: Segment, role_design_context: str) -> str:
    if not role_design_context:
        return seg.prompt
    max_chars = 1200
    compact_context = role_design_context
    if len(compact_context) > max_chars:
        compact_context = compact_context[:max_chars] + "\n...(角色设定过长，已截断)"
    return (
        "严格遵循以下角色设定与本集设定，保持人物外观和性格一致。\n"
        f"{compact_context}\n\n"
        f"[当前镜头脚本]\n{seg.prompt}"
    )


def _dump_prompt_json(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_initial_prompt_json(
    prompt_json_path: Path,
    segments: list[Segment],
    model_prompts: list[str],
    character_image_paths: list[Path],
    scene_image_paths: list[Path],
    generation_mode: str,
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    doc: dict = {
        "meta": {
            "generation_mode": generation_mode,
            "segment_count": len(segments),
            "image_strategy": "A (首段传角色/场景图；续帧段仅传上一段尾帧)",
            "character_image_paths": [str(p.resolve()) for p in character_image_paths],
            "scene_image_paths": [str(p.resolve()) for p in scene_image_paths],
            "created_at": now,
            "updated_at": now,
            "merged_video_path": None,
            "final_video_path": None,
        },
        "segments": [],
    }
    for i, seg in enumerate(segments):
        mp = model_prompts[i] if i < len(model_prompts) else seg.prompt
        # Seedance 的策略：首段发送角色/场景 refs，续帧段仅传上一段尾帧。
        is_first = bool(seg.is_first)
        character_ref_paths = [str(p.resolve()) for p in character_image_paths] if is_first else []
        scene_ref_paths = [str(p.resolve()) for p in scene_image_paths] if is_first else []
        doc["segments"].append(
            {
                "segment_index": seg.index,
                "shot_no": seg.shot_no,
                "raw_text": seg.raw_text,
                "narration": seg.narration or "",
                "shot_type": seg.shot_type,
                "camera_move": seg.camera_move,
                "duration_seconds": seg.duration_seconds,
                "segment_prompt": seg.prompt,
                "model_prompt": mp,
                "ref_frame_source_path": None,
                # 预生成阶段：只展示“首段会发送哪些图”；direct 阶段会再补齐 task_id/视频路径等。
                "character_refs_sent": bool(character_ref_paths),
                "scene_refs_sent": bool(scene_ref_paths),
                "character_ref_paths": character_ref_paths,
                "scene_ref_paths": scene_ref_paths,
                "api_request_at": None,
                "task_id": None,
                "remote_video_url": None,
                "local_video_path": None,
            }
        )
    _dump_prompt_json(prompt_json_path, doc)


def _prompt_json_touch_segment(
    prompt_json_path: Path,
    segment_list_index: int,
    patch: dict,
) -> None:
    doc = json.loads(prompt_json_path.read_text(encoding="utf-8"))
    doc["segments"][segment_list_index].update(patch)
    doc["meta"]["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _dump_prompt_json(prompt_json_path, doc)


def _prompt_json_set_output_paths(
    prompt_json_path: Path,
    merged_path: str,
    final_path: str,
) -> None:
    doc = json.loads(prompt_json_path.read_text(encoding="utf-8"))
    doc["meta"]["merged_video_path"] = str(Path(merged_path).resolve())
    doc["meta"]["final_video_path"] = str(Path(final_path).resolve())
    doc["meta"]["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _dump_prompt_json(prompt_json_path, doc)


def generate_all_segments(
    segments: list[Segment],
    sub_video_dir: Path,
    model_prompts: list[str],
    character_image_urls: list[str] | None = None,
    scene_image_urls: list[str] | None = None,
    prompt_json_path: Path | None = None,
    segment_limit: int | None = None,
    segment_start: int | None = None,
    segment_end: int | None = None,
) -> list[str]:
    """
    Generate video for each segment via Seedance API.
    Uses the last frame of the previous segment as a reference image.
    Returns ordered list of local .mp4 paths.
    """
    sub_video_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    prev_video_path: str | None = None

    t_all_start = time.perf_counter()
    # Segment selection (1-based inclusive) for convenience.
    # Example: start=2 end=5 -> generate segments[1:5]
    if segment_start is not None or segment_end is not None:
        start0 = 0 if segment_start is None else max(0, segment_start - 1)
        end0_excl = len(segments) if segment_end is None else min(len(segments), segment_end)
        segments = segments[start0:end0_excl]
    elif segment_limit is not None:
        segments = segments[: max(0, segment_limit)]

    # If we start from a later segment, reuse previous segment as continuity ref.
    if segment_start is not None and segment_start > 1:
        prev_idx = segment_start - 2  # 0-based segment index of previous item
        prev_candidate = sub_video_dir / f"segment_{prev_idx:03d}.mp4"
        if prev_candidate.is_file():
            prev_video_path = str(prev_candidate)
            log.info("起始分段=%s，复用上一段作为连续性参考: %s", segment_start, prev_video_path)
    segment_char_paths: list[list[str]] | None = None
    segment_scene_paths: list[list[str]] | None = None
    if prompt_json_path is not None and prompt_json_path.is_file():
        # Only use ref file paths for logging (never log data URL/base64 payload).
        try:
            prompt_doc = json.loads(prompt_json_path.read_text(encoding="utf-8"))
            seg_entries = prompt_doc.get("segments", []) or []
            segment_char_paths = [
                list(seg.get("character_ref_paths", []) or []) for seg in seg_entries
            ]
            segment_scene_paths = [
                list(seg.get("scene_ref_paths", []) or []) for seg in seg_entries
            ]
        except Exception:
            segment_char_paths = None
            segment_scene_paths = None
    for idx, seg in enumerate(segments):
        tag = f"片段 {seg.index + 1}/{len(segments)}"
        print(f"\n>>> 正在生成 {tag} ...")

        # If segment already exists, reuse it and keep continuity.
        dest = str(sub_video_dir / f"segment_{seg.index:03d}.mp4")
        if Path(dest).is_file():
            print(f"    已存在，跳过生成: {dest}")
            log.info("%s 已存在，跳过生成并复用: %s", tag, dest)
            if prompt_json_path is not None:
                _prompt_json_touch_segment(
                    prompt_json_path,
                    seg.index,
                    {
                        "local_video_path": str(Path(dest).resolve()),
                        "remote_video_url": None,
                        "task_id": None,
                        "api_request_at": datetime.now().isoformat(timespec="seconds"),
                    },
                )
            paths.append(dest)
            prev_video_path = dest
            continue

        ref_image_url: str | None = None
        ref_frame_path: str | None = None
        has_tail_frame = False
        refs_dir = sub_video_dir.parent / "refs_files"
        refs_dir.mkdir(parents=True, exist_ok=True)

        if not seg.is_first and prev_video_path:
            log.info("提取上一段最后一帧作为参考图...")
            prev_stem = Path(prev_video_path).stem
            ref_frame_path = save_last_frame(
                prev_video_path,
                output_path=str(refs_dir / f"{prev_stem}_last_frame.jpg"),
            )
            ref_image_url = f"data:image/jpeg;base64,{extract_last_frame_base64(prev_video_path)}"
            has_tail_frame = True
            log.info("参考帧已就绪: %s", ref_frame_path)

        # Submit generation task
        prompt_with_design = model_prompts[idx] if idx < len(model_prompts) else seg.prompt

        # Strategy A: first segment uses role/scene refs;续帧段只传尾帧，避免请求过重导致 400.
        # 如果你从中间 segment_start>1 开始，且上一段视频缺失导致尾帧未能提取，
        # 则本段会退化为“无引用”影响连续性。这里把“这一段（slice 的第一段）”
        # 作为临时 first，发送角色/场景 refs 并复用首段的降维重试策略。
        effective_is_first_for_payload = seg.is_first or (idx == 0 and not has_tail_frame)
        seg_character_urls = character_image_urls if effective_is_first_for_payload else None
        seg_scene_urls = scene_image_urls if effective_is_first_for_payload else None

        ref_prev_resolved: str | None = None
        if not seg.is_first and prev_video_path:
            ref_prev_resolved = str(Path(prev_video_path).resolve())

        t_segment_start = time.perf_counter()
        prompt_preview = prompt_with_design.replace("\n", " ").strip()
        char_ref_paths = None
        scene_ref_paths = None
        if segment_char_paths is not None and idx < len(segment_char_paths):
            char_ref_paths = segment_char_paths[idx]
        if segment_scene_paths is not None and idx < len(segment_scene_paths):
            scene_ref_paths = segment_scene_paths[idx]
        char_ref_count = len(seg_character_urls or [])
        scene_ref_count = len(seg_scene_urls or [])

        log.info(
            "%s 提交生成任务: shot_no=%s is_first=%s duration=%.1fs prompt_len=%d prompt_preview=%r char_refs=%d scene_refs=%d tail_frame=%s",
            tag,
            seg.shot_no,
            seg.is_first,
            float(seg.duration_seconds),
            len(prompt_with_design),
            prompt_preview,
            char_ref_count,
            scene_ref_count,
            "set" if ref_image_url else None,
        )
        if char_ref_paths is not None or scene_ref_paths is not None:
            log.info(
                "%s refs_files: char_paths=%s scene_paths=%s ref_frame_source=%s ref_frame_extracted=%s",
                tag,
                (char_ref_paths[:5] if char_ref_paths else []),
                (scene_ref_paths[:5] if scene_ref_paths else []),
                ref_prev_resolved,
                ref_frame_path,
            )

        t_submit_start = time.perf_counter()
        used_character_urls = seg_character_urls
        used_scene_urls = seg_scene_urls

        # Some providers reject very large image payloads (400). For the first segment,
        # retry with fewer reference images to improve success rate.
        candidates: list[tuple[list[str] | None, list[str] | None]] = []
        if effective_is_first_for_payload:
            char_list = list(seg_character_urls or [])
            scene_list = list(seg_scene_urls or [])
            candidates = [
                (seg_character_urls, seg_scene_urls),
                (([char_list[0]] if char_list else None), seg_scene_urls),
                (([char_list[0]] if char_list else None), ([scene_list[0]] if scene_list else None)),
                (seg_character_urls, ([scene_list[0]] if scene_list else None)),
                (([char_list[0]] if char_list else None), None),
                (None, ([scene_list[0]] if scene_list else None)),
                (None, None),
            ]
        else:
            candidates = [(seg_character_urls, seg_scene_urls)]

        last_exc: Exception | None = None
        task_id: str | None = None
        for attempt_i, (char_urls_try, scene_urls_try) in enumerate(candidates, 1):
            if prompt_json_path is not None:
                _prompt_json_touch_segment(
                    prompt_json_path,
                    idx,
                    {
                        "model_prompt": prompt_with_design,
                        "api_request_at": datetime.now().isoformat(timespec="seconds"),
                        "character_refs_sent": bool(char_urls_try),
                        "scene_refs_sent": bool(scene_urls_try),
                        "ref_frame_source_path": ref_prev_resolved,
                        "ref_frame_extracted_path": ref_frame_path,
                    },
                )

            try:
                used_character_urls = char_urls_try
                used_scene_urls = scene_urls_try
                t_submit_start = time.perf_counter()
                task_id = create_video_task(
                    prompt_with_design,
                    ref_image_url,
                    character_image_urls=used_character_urls,
                    scene_image_urls=used_scene_urls,
                    duration_seconds=float(seg.duration_seconds),
                    use_reference_role=bool(seg.is_first),
                )
                t_submit_end = time.perf_counter()
                print(f"    任务已提交: {task_id}")
                break
            except Exception as exc:
                last_exc = exc
                msg = str(exc)
                # Some providers reject large image payloads with either 400 or 403.
                # For the first segment we have candidates that progressively reduce
                # reference images; try them when we see either error.
                if seg.is_first and attempt_i < len(candidates) and (
                    ("400" in msg) or ("403" in msg) or ("Forbidden" in msg)
                ):
                    log.warning(
                        "%s 首段请求失败(400/403)，第%d/%d次降维重试: char_try=%d scene_try=%d err=%s",
                        tag,
                        attempt_i,
                        len(candidates),
                        len(char_urls_try or []),
                        len(scene_urls_try or []),
                        msg[:200],
                    )
                    continue
                raise

        if not task_id:
            raise RuntimeError(f"任务提交失败: {last_exc}")

        if prompt_json_path is not None:
            _prompt_json_touch_segment(prompt_json_path, idx, {"task_id": task_id})

        # Poll until completion
        t_poll_start = time.perf_counter()
        try:
            video_url = wait_for_video(task_id)
        except Exception as exc:
            msg = str(exc)
            if "SetLimitExceeded" in msg or "inference limit" in msg:
                log.warning(
                    "%s 第%d段轮询失败：推理上限已触发(SetLimitExceeded)。将停止后续分段生成。已下载=%d",
                    tag,
                    seg.index + 1,
                    len(paths),
                )
                return paths
            raise
        t_poll_end = time.perf_counter()
        print(f"    视频已生成: {video_url[:80]}...")

        # Download segment
        t_download_start = time.perf_counter()
        download_video(video_url, dest)
        t_download_end = time.perf_counter()
        print(f"    已下载: {dest}")

        if prompt_json_path is not None:
            _prompt_json_touch_segment(
                prompt_json_path,
                idx,
                {
                    "task_id": task_id,
                    "remote_video_url": video_url,
                    "local_video_path": str(Path(dest).resolve()),
                },
            )

        paths.append(dest)
        prev_video_path = dest

        t_segment_end = time.perf_counter()
        log.info(
            "%s 完成: task_id=%s poll_ms=%d download_ms=%d submit_ms=%d total_ms=%d local_video=%s remote_video_preview=%r",
            tag,
            task_id,
            int((t_poll_end - t_poll_start) * 1000),
            int((t_download_end - t_download_start) * 1000),
            int((t_submit_end - t_submit_start) * 1000),
            int((t_segment_end - t_segment_start) * 1000),
            dest,
            (video_url[:120] if video_url else ""),
        )

    t_all_end = time.perf_counter()
    log.info("全部片段生成完成: total_segments=%d total_ms=%d", len(segments), int((t_all_end - t_all_start) * 1000))
    return paths


def _safe_name(text: str, default: str) -> str:
    cleaned = "".join(ch for ch in text.strip() if ch not in r'<>:"/\|?*').strip().rstrip(".")
    return cleaned or default


def _write_storyboard_script(path: Path, segments: list[Segment], include_narration: bool) -> None:
    blocks: list[str] = []
    for seg in segments:
        lines = [
            f"镜号{seg.shot_no} | 景别:{seg.shot_type} | 运镜:{seg.camera_move} | 时长:{seg.duration_seconds:.1f}s",
            f"剧情:{seg.raw_text}",
        ]
        if include_narration and seg.narration:
            lines.append(f"旁白:{seg.narration}")
        lines.append(f"提示词:{seg.prompt}")
        blocks.append("\n".join(lines) + "\n")
    path.write_text("\n".join(blocks), encoding="utf-8")


def _write_role_design_from_source_file(dest: Path, source_file: str | None) -> None:
    """
    主角色设定 → {剧名}/role_design.txt
    本集角色设定 → {剧名}/{集数}/role_design.txt
    """
    if not source_file:
        return
    src = Path(source_file).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"角色设定文件不存在: {src}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    log.info("已写入角色设定: %s", dest)


def _write_subtitle_txt(path: Path, subtitles: list[str], segment_durations: list[float]) -> None:
    lines: list[str] = []
    cursor = 0.0
    for i, text in enumerate(subtitles, 1):
        duration = segment_durations[i - 1] if i - 1 < len(segment_durations) else 5.0
        start = cursor
        end = cursor + duration
        lines.append(f"[{start:.2f}-{end:.2f}] {text.strip()}")
        cursor = end
    path.write_text("\n".join(lines), encoding="utf-8")


def run(
    story: str,
    output_root: Path,
    drama_title: str,
    episode: str,
    dry_run: bool = False,
    genre: str | None = None,
    main_character_image_paths: list[str] | None = None,
    main_scene_image_paths: list[str] | None = None,
    episode_character_image_paths: list[str] | None = None,
    episode_scene_image_paths: list[str] | None = None,
    role_design_file: str | None = None,
    episode_role_design_file: str | None = None,
    generation_mode: str = "direct",
    include_narration: bool = False,
    chat_id: str = DEFAULT_CHAT_ID,
    send_to_feishu: bool = True,
    segment_limit: int | None = None,
    segment_start: int | None = None,
    segment_end: int | None = None,
) -> str | None:
    """
    Main pipeline:
      1. Split story → segments
      2. Print storyboard
      3. Generate videos (unless dry_run)
      4. Concatenate
      5. Add subtitles
      6. Send to Feishu
    Returns the final video path, or None for dry_run.
    """
    # Step 1: split
    t_run_start = time.perf_counter()
    log.info("开始运行: title=%s episode=%s mode=%s dry_run=%s", drama_title, episode, generation_mode, dry_run)
    try:
        plan: StoryboardPlan = split_story(
            story,
            forced_genre=genre,
            include_narration=include_narration,
            segment_limit=segment_limit,
        )
    except Exception as exc:
        msg = str(exc)
        log.error("分镜生成失败（已强制使用大语言模型）：%s", msg)
        print(f"[ERROR] 分镜生成失败（已强制使用大语言模型）：{msg}")
        sys.exit(1)
    segments = plan.segments
    total_duration = sum(float(s.duration_seconds) for s in segments)
    avg_duration = (total_duration / len(segments)) if segments else 0.0
    log.info("剧情已拆分为 %d 个片段（总时长约%.1fs，平均每段%.1fs）", len(segments), total_duration, avg_duration)

    title_safe = _safe_name(drama_title, "未命名短剧")
    episode_safe = _safe_name(episode, "第1集")
    title_dir = output_root / title_safe
    base_dir = title_dir / episode_safe
    sub_video_dir = base_dir / "sub_video"
    base_dir.mkdir(parents=True, exist_ok=True)

    _write_role_design_from_source_file(title_dir / "role_design.txt", role_design_file)
    _write_role_design_from_source_file(base_dir / "role_design.txt", episode_role_design_file)

    # 主角色/主场景 → {剧名}/role、{剧名}/scene；本集 → {剧名}/{集数}/role、scene
    _copy_images_to_dir(main_character_image_paths or [], title_dir / "role")
    _copy_images_to_dir(main_scene_image_paths or [], title_dir / "scene")
    _copy_images_to_dir(episode_character_image_paths or [], base_dir / "role")
    _copy_images_to_dir(episode_scene_image_paths or [], base_dir / "scene")

    story_path = base_dir / "story.txt"
    script_path = base_dir / "script.txt"
    subtitle_txt_path = base_dir / "subtitle.txt"
    prompt_json_path = base_dir / "prompt.json"

    story_path.write_text(story, encoding="utf-8")
    _write_storyboard_script(script_path, segments, include_narration=include_narration)

    character_image_paths, scene_image_paths = _merge_character_and_scene_refs(title_dir, base_dir)
    character_image_urls = _prepare_image_urls_from_paths(character_image_paths)
    scene_image_urls = _prepare_image_urls_from_paths(scene_image_paths)
    role_design_context = _load_role_design_context(title_dir, base_dir)
    n_main_r = len(_list_image_files(title_dir / "role"))
    n_ep_r = len(_list_image_files(base_dir / "role"))
    n_main_s = len(_list_image_files(title_dir / "scene"))
    n_ep_s = len(_list_image_files(base_dir / "scene"))
    if character_image_urls:
        log.info(
            "角色参考图共 %d 张（主 %d + 本集 %d）",
            len(character_image_urls),
            n_main_r,
            n_ep_r,
        )
    if scene_image_urls:
        log.info(
            "场景参考图共 %d 张（主 %d + 本集 %d）",
            len(scene_image_urls),
            n_main_s,
            n_ep_s,
        )
    if role_design_context:
        log.info("已加载角色设定上下文（主设定/本集设定）")
    model_prompts = [_compose_model_prompt(seg, role_design_context) for seg in segments]
    log.info("开始写入 prompt.json: %s", prompt_json_path if 'prompt_json_path' in locals() else '(unknown)')
    _write_initial_prompt_json(
        prompt_json_path,
        segments,
        model_prompts,
        character_image_paths,
        scene_image_paths,
        generation_mode=("预生成" if generation_mode == "pre" else "直接生成"),
    )
    log.info("已写入模型输入清单: %s", prompt_json_path)

    # Step 2: print
    print_storyboard(segments)

    if dry_run or generation_mode == "pre":
        print("[预生成] 已写入 prompt.json 与脚本，未调用视频生成模型。")
        log.info("预生成完成: title=%s episode=%s mode=%s segments=%d", title_safe, episode_safe, generation_mode, len(segments))
        return None

    # Step 3: generate
    if segment_start is not None or segment_end is not None:
        start_v = 1 if segment_start is None else segment_start
        end_v = (len(segments) if segment_end is None else segment_end)
        gen_count = max(0, end_v - start_v + 1)
    else:
        gen_count = len(segments) if segment_limit is None else max(0, segment_limit)
    print(f"即将生成 {gen_count} 个视频片段，预计耗时较长，请耐心等待...\n")
    segment_paths = generate_all_segments(
        segments,
        sub_video_dir,
        model_prompts=model_prompts,
        character_image_urls=character_image_urls,
        scene_image_urls=scene_image_urls,
        prompt_json_path=prompt_json_path,
        segment_limit=segment_limit,
        segment_start=segment_start,
        segment_end=segment_end,
    )
    log.info("片段全部生成返回: %d segment_paths", len(segment_paths))

    if segment_limit is not None or segment_start is not None or segment_end is not None:
        # Only generate segment mp4s. No merge/subtitle/feishu upload.
        if segment_start is not None or segment_end is not None:
            print(f"\n>>> 已生成分镜片段 {segment_start or 1}-{segment_end or len(segments)}（不拼接、不发送飞书）")
        else:
            print(f"\n>>> 已生成前 {segment_limit} 个分镜片段（不拼接、不发送飞书）")
        for p in segment_paths:
            print(f"  - {p}")
        log.info("仅生成片段完成: segment_limit=%s segment_start=%s segment_end=%s", segment_limit, segment_start, segment_end)
        return None

    # Step 4: concatenate
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    merged_path = str(base_dir / f"{title_safe}_{episode_safe}_{ts}_merged.mp4")
    subtitle_path = str(base_dir / f"{title_safe}_{episode_safe}_{ts}.srt")
    output_path = str(base_dir / f"{title_safe}_{episode_safe}_{ts}.mp4")
    print(f"\n>>> 正在拼接 {len(segment_paths)} 个片段 → {output_path}")
    t_concat_start = time.perf_counter()
    concatenate_segments(segment_paths, merged_path)
    segment_durations = [float(s.duration_seconds) for s in segments]
    write_srt([s.narration for s in segments], subtitle_path, segment_durations)
    _write_subtitle_txt(subtitle_txt_path, [s.narration for s in segments], segment_durations)
    mux_subtitles_with_ffmpeg(merged_path, subtitle_path, output_path)
    t_concat_end = time.perf_counter()
    log.info("拼接+字幕封装完成: merged=%s output=%s concat_ms=%d", merged_path, output_path, int((t_concat_end - t_concat_start) * 1000))
    log.info("本次运行总耗时: total_ms=%d", int((time.perf_counter() - t_run_start) * 1000))
    _prompt_json_set_output_paths(prompt_json_path, merged_path, output_path)

    if send_to_feishu:
        print(f"\n>>> 正在发送到飞书 chat_id={chat_id}")
        log.info("飞书发送开始: chat_id=%s output=%s", chat_id, output_path)
        t_send_start = time.perf_counter()
        client = build_client()
        send_text_message(client, chat_id, "短剧已生成，见附件")
        file_key = upload_file(client, Path(output_path))
        send_file_message(client, chat_id, file_key, Path(output_path))
        t_send_end = time.perf_counter()
        log.info("飞书发送完成: file_key=%s send_ms=%d", file_key, int((t_send_end - t_send_start) * 1000))

    print("\n" + "=" * 60)
    print(f"  完成！最终视频已保存: {output_path}")
    print("=" * 60 + "\n")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI短剧自动生成与拼接工具 (Seedance 2.0)",
    )
    parser.add_argument(
        "--story", "-s",
        help="剧情文本（直接在命令行传入）",
    )
    parser.add_argument(
        "--file", "-f",
        help="从文本文件读取剧情",
    )
    parser.add_argument(
        "--output", "-o",
        default=str(DEFAULT_OUTPUT_ROOT),
        help=f"输出根目录（默认: {DEFAULT_OUTPUT_ROOT}）",
    )
    parser.add_argument("--title", default="未命名短剧", help="剧名（用于目录与成片命名）")
    parser.add_argument("--episode", default="第1集", help="集数（用于目录与成片命名）")
    parser.add_argument(
        "--genre",
        choices=["短剧", "动画", "动漫"],
        help="强制指定题材（覆盖自动识别）",
    )
    parser.add_argument(
        "--character-image",
        action="append",
        default=[],
        help="主角色参考图，保存到 {剧名}/role/，可重复传入",
    )
    parser.add_argument(
        "--scene-image",
        action="append",
        default=[],
        help="主场景参考图，保存到 {剧名}/scene/，可重复传入",
    )
    parser.add_argument(
        "--episode-character-image",
        action="append",
        default=[],
        help="本集角色参考图，保存到 {剧名}/{集数}/role/，可重复传入",
    )
    parser.add_argument(
        "--episode-scene-image",
        action="append",
        default=[],
        help="本集场景参考图，保存到 {剧名}/{集数}/scene/，可重复传入",
    )
    parser.add_argument(
        "--role-design-file",
        help="主角色设定文本文件（UTF-8），保存为 {剧名}/role_design.txt",
    )
    parser.add_argument(
        "--episode-role-design-file",
        help="本集角色设定文本文件（UTF-8），保存为 {剧名}/{集数}/role_design.txt",
    )
    parser.add_argument(
        "--chat-id",
        default=DEFAULT_CHAT_ID,
        help=f"飞书 chat_id（默认: {DEFAULT_CHAT_ID}）",
    )
    parser.add_argument(
        "--no-send",
        action="store_true",
        help="仅生成视频，不发送飞书",
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="仅生成分镜脚本，不调用 API",
    )
    parser.add_argument(
        "--mode",
        choices=["pre", "direct", "预生成", "直接生成"],
        default="direct",
        help="生成模式：pre/预生成=不调视频模型，direct/直接生成=调用视频模型",
    )
    parser.add_argument(
        "--segment-limit",
        type=int,
        default=None,
        help="仅生成前 N 个分镜视频片段（direct 模式可用，不会拼接、不发送飞书）",
    )
    parser.add_argument(
        "--segment-start",
        type=int,
        default=None,
        help="仅生成从第 N 个分镜开始（1-based，direct 模式可用）",
    )
    parser.add_argument(
        "--segment-end",
        type=int,
        default=None,
        help="仅生成到第 N 个分镜结束（1-based，direct 模式可用）",
    )
    parser.add_argument(
        "--no-narration",
        "--no-dialogue-narration",
        action="store_true",
        help="不生成台词和旁白（narration 置空）",
    )
    parser.add_argument(
        "--with-narration",
        action="store_true",
        help="生成台词和旁白（默认关闭）",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细日志输出",
    )
    args = parser.parse_args()
    setup_logging(args.verbose)

    # Resolve story text
    story: str | None = None
    if args.story:
        story = args.story
    elif args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"错误: 文件不存在 — {args.file}", file=sys.stderr)
            sys.exit(1)
        story = p.read_text(encoding="utf-8")
    else:
        print("请输入完整剧情文本（输入完成后按两次回车）：")
        lines: list[str] = []
        empty_count = 0
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line == "":
                empty_count += 1
                if empty_count >= 2:
                    break
            else:
                empty_count = 0
            lines.append(line)
        story = "\n".join(lines).strip()

    if not story:
        print("错误: 未提供剧情文本", file=sys.stderr)
        sys.exit(1)

    mode = "pre" if args.mode in {"pre", "预生成"} else "direct"

    run(
        story,
        Path(args.output),
        args.title,
        args.episode,
        dry_run=args.dry_run,
        genre=args.genre,
        main_character_image_paths=args.character_image,
        main_scene_image_paths=args.scene_image,
        episode_character_image_paths=args.episode_character_image,
        episode_scene_image_paths=args.episode_scene_image,
        role_design_file=args.role_design_file,
        episode_role_design_file=args.episode_role_design_file,
        generation_mode=mode,
        include_narration=args.with_narration and (not args.no_narration),
        chat_id=args.chat_id,
        send_to_feishu=not args.no_send,
        segment_limit=args.segment_limit,
        segment_start=args.segment_start,
        segment_end=args.segment_end,
    )


if __name__ == "__main__":
    main()
