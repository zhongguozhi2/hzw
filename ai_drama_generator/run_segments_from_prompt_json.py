import argparse
import json
from pathlib import Path

from main import generate_all_segments, _prepare_image_urls_from_paths
from story_splitter import Segment


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

    meta = doc.get("meta", {}) or {}
    character_image_paths = [Path(p) for p in (meta.get("character_image_paths") or [])]
    scene_image_paths = [Path(p) for p in (meta.get("scene_image_paths") or [])]
    return segments, model_prompts, character_image_paths, scene_image_paths


def _load_prompt_json_for_check(prompt_json_path: Path) -> dict:
    return json.loads(prompt_json_path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="仅根据 prompt.json 生成指定段视频并校验尾帧引用")
    parser.add_argument("--prompt-json", required=True, help="prompt.json 绝对路径")
    parser.add_argument("--segment-start", type=int, default=1, help="1-based，默认生成第1段开始")
    parser.add_argument("--segment-end", type=int, default=2, help="1-based，默认生成到第2段结束（含）")
    args = parser.parse_args()

    prompt_json_path = Path(args.prompt_json).resolve()
    if not prompt_json_path.is_file():
        raise FileNotFoundError(f"prompt.json 不存在: {prompt_json_path}")

    base_dir = prompt_json_path.parent
    sub_video_dir = base_dir / "sub_video"
    refs_dir = base_dir / "refs_files"

    segments, model_prompts, char_paths, scene_paths = load_segments(prompt_json_path)
    char_urls = _prepare_image_urls_from_paths(char_paths)
    scene_urls = _prepare_image_urls_from_paths(scene_paths)

    # Generate only requested segments; generate_all_segments 会在第2段提交时抽取上一段尾帧。
    generate_all_segments(
        segments,
        sub_video_dir,
        model_prompts=model_prompts,
        character_image_urls=char_urls,
        scene_image_urls=scene_urls,
        prompt_json_path=prompt_json_path,
        segment_start=args.segment_start,
        segment_end=args.segment_end,
    )

    # Reload prompt.json for verification.
    prompt_doc = _load_prompt_json_for_check(prompt_json_path)
    seg_items = prompt_doc.get("segments", []) or []
    seg_by_index = {int(s.get("segment_index", i)): s for i, s in enumerate(seg_items)}

    def pexists(p: str | None) -> bool:
        return bool(p) and Path(p).expanduser().exists()

    seg0_mp4 = sub_video_dir / "segment_000.mp4"
    seg1_mp4 = sub_video_dir / "segment_001.mp4"
    tail0 = refs_dir / "segment_000_last_frame.jpg"

    seg1_meta = seg_by_index.get(1, {}) or {}
    seg0_ref_extracted_path_expected = str(tail0.resolve())

    print("\n=== 尾帧与引用核对 ===")
    print(f"segment_000.mp4 exists: {seg0_mp4.exists()} -> {seg0_mp4}")
    print(f"segment_001.mp4 exists: {seg1_mp4.exists()} -> {seg1_mp4}")
    print(f"refs_files/segment_000_last_frame.jpg exists: {tail0.exists()} -> {tail0}")

    ref_source_path = seg1_meta.get("ref_frame_source_path")
    ref_extracted_path = seg1_meta.get("ref_frame_extracted_path")
    print(f"segment_001.ref_frame_source_path: {ref_source_path}")
    print(f"segment_001.ref_frame_extracted_path: {ref_extracted_path}")

    ok_source = bool(ref_source_path) and Path(ref_source_path).resolve() == seg0_mp4.resolve()
    ok_extracted = bool(ref_extracted_path) and Path(ref_extracted_path).resolve() == tail0.resolve()

    print(f"segment_001 是否引用了 segment_000 尾帧（source 匹配）: {ok_source}")
    print(f"segment_001 是否引用了 segment_000 尾帧（extracted_path 匹配）: {ok_extracted}")
    print(f"尾帧文件是否存在（按 extracted_path）: {pexists(ref_extracted_path)}")

    # Keep the output explicit for debugging.
    if not ok_extracted:
        print(f"[WARN] 预期 extracted_path: {seg0_ref_extracted_path_expected}")


if __name__ == "__main__":
    main()

