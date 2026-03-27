import argparse
import json
from datetime import datetime
from pathlib import Path

from main import (
    DEFAULT_CHAT_ID,
    _prepare_image_urls_from_paths,
    _prompt_json_set_output_paths,
    generate_all_segments,
)
from send_file_to_feishu import build_client, send_file_message, upload_file
from story_splitter import Segment
from video_concat import concatenate_segments, mux_subtitles_with_ffmpeg, write_srt


def load_segments(prompt_json_path: Path) -> tuple[list[Segment], list[str], list[Path], list[Path]]:
    doc = json.loads(prompt_json_path.read_text(encoding="utf-8"))
    items = doc.get("segments", [])
    if not items:
        raise RuntimeError("prompt.json 缺少 segments")

    segments: list[Segment] = []
    model_prompts: list[str] = []
    for i, item in enumerate(items):
        seg = Segment(
            index=int(item.get("segment_index", i)),
            raw_text=str(item.get("raw_text", "")),
            prompt=str(item.get("segment_prompt") or item.get("model_prompt") or "").strip(),
            narration=str(item.get("narration", "")),
            shot_no=int(item.get("shot_no", i + 1)),
            camera_move=str(item.get("camera_move", "")),
            shot_type=str(item.get("shot_type", "")),
            duration_seconds=float(item.get("duration_seconds", 5.0)),
            is_first=(i == 0),
        )
        segments.append(seg)
        model_prompts.append(str(item.get("model_prompt") or seg.prompt))

    meta = doc.get("meta", {})
    character_image_paths = [Path(p) for p in (meta.get("character_image_paths") or [])]
    scene_image_paths = [Path(p) for p in (meta.get("scene_image_paths") or [])]
    return segments, model_prompts, character_image_paths, scene_image_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="直接根据 prompt.json 生成并发送视频")
    parser.add_argument("--prompt-json", required=True, help="prompt.json 绝对路径")
    parser.add_argument("--chat-id", default=DEFAULT_CHAT_ID, help="飞书 chat_id")
    args = parser.parse_args()

    prompt_json_path = Path(args.prompt_json).resolve()
    if not prompt_json_path.is_file():
        raise FileNotFoundError(f"prompt.json 不存在: {prompt_json_path}")

    base_dir = prompt_json_path.parent
    sub_video_dir = base_dir / "sub_video"
    segments, model_prompts, char_paths, scene_paths = load_segments(prompt_json_path)
    char_urls = _prepare_image_urls_from_paths(char_paths)
    scene_urls = _prepare_image_urls_from_paths(scene_paths)

    segment_paths = generate_all_segments(
        segments,
        sub_video_dir,
        model_prompts=model_prompts,
        character_image_urls=char_urls,
        scene_image_urls=scene_urls,
        prompt_json_path=prompt_json_path,
    )
    if not segment_paths:
        raise RuntimeError("没有可用分段视频，无法拼接")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    merged_path = str(base_dir / f"from_prompt_{ts}_merged.mp4")
    subtitle_path = str(base_dir / f"from_prompt_{ts}.srt")
    output_path = str(base_dir / f"from_prompt_{ts}.mp4")
    concatenate_segments(segment_paths, merged_path)
    write_srt([s.narration for s in segments], subtitle_path, [float(s.duration_seconds) for s in segments])
    mux_subtitles_with_ffmpeg(merged_path, subtitle_path, output_path)
    _prompt_json_set_output_paths(prompt_json_path, merged_path, output_path)

    client = build_client()
    file_key = upload_file(client, Path(output_path))
    send_file_message(client, args.chat_id, file_key, Path(output_path))
    print(output_path)


if __name__ == "__main__":
    main()
