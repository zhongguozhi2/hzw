"""
Generate a full storyboard script with an LLM and then split it into
shot plans for video generation.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import requests

from config import (
    VOLCENGINE_MODEL,
    STORYBOARD_MODEL,
    get_api_key,
    get_base_url,
)

log = logging.getLogger(__name__)
CHARS_PER_SEGMENT = 40
LLM_TIMEOUT_SEC = 120
LLM_MAX_RETRIES = 3


@dataclass
class Segment:
    index: int
    raw_text: str
    prompt: str
    narration: str
    shot_no: int
    camera_move: str
    shot_type: str
    duration_seconds: float = 5.0
    is_first: bool = False


@dataclass
class StoryboardPlan:
    segments: list[Segment]
    full_script: str


def _split_sentences(text: str) -> list[str]:
    """Split Chinese/English text into sentences."""
    parts = re.split(r'(?<=[。！？；\n.!?;])', text)
    return [s.strip() for s in parts if s.strip()]


def _detect_genre(text: str) -> str:
    lowered = text.lower()
    if "动漫" in text or "二次元" in text:
        return "动漫"
    if "动画" in text or "animation" in lowered:
        return "动画"
    return "短剧"


def _llm_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json",
    }


def _parse_json(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json", "", 1).strip()
    return json.loads(cleaned)


def _llm_generate_storyboard(
    story: str,
    forced_genre: str | None = None,
    include_narration: bool = True,
    segment_limit: int | None = None,
) -> StoryboardPlan:
    """
    Ask the LLM to output full production script and shot segments.
    Returns None on failure so caller can fallback.
    """
    base = get_base_url()
    url = f"{base}/chat/completions"
    genre = forced_genre or _detect_genre(story)
    llm_model = STORYBOARD_MODEL
    log.info("LLM 分镜调用: provider=volcengine url=%s model=%s", url, llm_model)
    prompt = f"""
你是专业导演和分镜师。请根据用户剧情，输出完整短剧制作脚本，并把内容拆成可生成视频的镜头。
本次题材：{genre}。风格要求：由你自行选择，必须与题材一致，并体现在每个镜头的 prompt 中（例如：写实/动画/动漫风格、光影与质感等）。

要求：
1) 镜号连续递增，从1开始；
2) 每个镜头必须包含：shot_no, shot_type, camera_move, narration, raw_text, prompt, duration_seconds；
3) duration_seconds 必须固定为 5（单位秒）；
4) 目标是尽量保证上下镜头连续、动作衔接自然；
5) raw_text是该镜头剧情；
6) narration是该镜头字幕文本（简洁口语）；
7) prompt 必须精简（建议 <= 60 个汉字，不要冗长修饰）；
8) full_script 允许为空字符串；
9) 只返回JSON，不要任何额外文本。

附加约束：
{"- 需要旁白/台词文本。" if include_narration else "- 不需要台词和旁白，narration 字段必须返回空字符串。"}
{"- 本次只需要返回前 " + str(segment_limit) + " 个镜头，segments 长度必须等于该值。" if (segment_limit is not None and segment_limit > 0) else ""}

JSON格式：
{{
  "status": "ok 或 failed",
  "failure_reason": "当 status=failed 时必填",
  "full_script": "可为空；若提供请尽量精简",
  "segments": [
    {{
      "shot_no": 1,
      "shot_type": "中景",
      "camera_move": "缓慢推进",
      "duration_seconds": 6,
      "narration": "......",
      "raw_text": "......",
      "prompt": "......"
    }}
  ]
}}

用户剧情：
{story}
""".strip()

    payload = {
        "model": llm_model,
        "messages": [
            {"role": "system", "content": "你是电影分镜与短剧脚本专家。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
        # 分镜 JSON 较长时避免响应截断导致 JSON 不完整
        "max_tokens": 4096,
    }
    last_exc: Exception | None = None
    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=payload, headers=_llm_headers(), timeout=LLM_TIMEOUT_SEC)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = _parse_json(content)
            status = str(parsed.get("status", "ok")).strip().lower()
            if status == "failed":
                reason = str(parsed.get("failure_reason", "")).strip() or "模型判定无法满足分镜约束"
                raise RuntimeError(f"LLM 分镜失败: {reason}")

            script = parsed.get("full_script", "").strip()
            if script:
                log.info("LLM 完整制作脚本:\n%s", script)
            items = parsed.get("segments", [])
            if not items:
                raise RuntimeError("LLM 返回 JSON，但缺少 segments 字段或 segments 为空")
            result: list[Segment] = []
            prev_prompt: str | None = None
            for idx, item in enumerate(items):
                # Strict mode: no fallback/兜底.
                raw = str(item.get("raw_text", "")).strip()
                if not raw:
                    raise RuntimeError(f"LLM 分镜第 {idx+1} 段缺少 raw_text/raw_text 为空（不允许跳过）")

                shot_no_val = item.get("shot_no", None)
                if shot_no_val is None or str(shot_no_val).strip() == "":
                    raise RuntimeError(f"LLM 分镜第 {idx+1} 段缺少 shot_no")
                shot_no = int(str(shot_no_val).strip())

                shot = str(item.get("shot_type", "")).strip()
                if not shot:
                    raise RuntimeError(f"LLM 分镜第 {idx+1} 段缺少 shot_type/shot_type 为空（不允许兜底）")

                cam = str(item.get("camera_move", "")).strip()
                if not cam:
                    raise RuntimeError(f"LLM 分镜第 {idx+1} 段缺少 camera_move/camera_move 为空（不允许兜底）")

                duration_raw = item.get("duration_seconds", None)
                if duration_raw is None or str(duration_raw).strip() == "":
                    raise RuntimeError(f"LLM 分镜第 {idx+1} 段缺少 duration_seconds")
                try:
                    float(duration_raw)
                except Exception as exc:
                    raise RuntimeError(f"LLM 分镜第 {idx+1} 段 duration_seconds 非法: {duration_raw!r}") from exc
                # 统一固定时长策略：无论模型返回多少，落地为 5 秒。
                duration_seconds = 5.0

                narration_field_present = "narration" in item
                narration_raw = str(item.get("narration", "")).strip() if narration_field_present else ""
                if include_narration:
                    if not narration_raw:
                        raise RuntimeError(f"LLM 分镜第 {idx+1} 段缺少 narration/为空（include_narration=True）")
                    narration = narration_raw
                else:
                    # include_narration=False：要求 narration 字段必须为空字符串或不存在
                    if narration_field_present and narration_raw != "":
                        raise RuntimeError(
                            f"LLM 分镜第 {idx+1} 段 narration 不应非空（include_narration=False），实际={narration_raw!r}"
                        )
                    narration = ""

                prompt_text = str(item.get("prompt", "")).strip()
                if not prompt_text:
                    raise RuntimeError(f"LLM 分镜第 {idx+1} 段缺少 prompt/prompt 为空（不允许兜底）")
                seg = Segment(
                    index=idx,
                    raw_text=raw,
                    prompt=prompt_text,
                    narration=narration,
                    shot_no=shot_no,
                    camera_move=cam,
                    shot_type=shot,
                    duration_seconds=duration_seconds,
                    is_first=(idx == 0),
                )
                result.append(seg)
                prev_prompt = prompt_text
            if not result:
                raise RuntimeError("LLM 解析 segments 后发现结果为空（所有 raw_text 为空？）")
            return StoryboardPlan(segments=result, full_script=script)
        except Exception as exc:
            last_exc = exc
            msg = str(exc)
            if isinstance(exc, json.JSONDecodeError) or ("Unterminated string" in msg) or ("Expecting value" in msg):
                log.warning(
                    "LLM 返回 JSON 非法，准备重试 (%d/%d): %s",
                    attempt,
                    LLM_MAX_RETRIES,
                    msg[:200],
                )
                continue
            if "Read timed out" in msg or "timeout" in msg.lower() or "ConnectTimeout" in msg:
                log.warning(
                    "LLM 分镜调用超时/网络波动，准备重试 (%d/%d): %s",
                    attempt,
                    LLM_MAX_RETRIES,
                    msg[:200],
                )
                continue
            # 非超时错误：直接失败并把原因抛出
            raise RuntimeError(f"LLM 分镜生成失败: {msg}") from exc

    # 仅超时/网络波动也重试失败：直接失败并把原因抛出
    raise RuntimeError(f"LLM 分镜多次重试仍失败: {last_exc}") from last_exc


def split_story(
    story: str,
    forced_genre: str | None = None,
    include_narration: bool = True,
    segment_limit: int | None = None,
) -> StoryboardPlan:
    """
    Main entry:
      - Only LLM-based split. If LLM output is invalid or missing required fields,
        generation fails explicitly (no deterministic fallback).
    """
    # 强制使用大语言模型分镜：失败则直接退出并告知失败原因
    return _llm_generate_storyboard(
        story,
        forced_genre=forced_genre,
        include_narration=include_narration,
        segment_limit=segment_limit,
    )
