import os
import json
import argparse
import asyncio
import subprocess
import threading
import time
import logging
from typing import List

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Requires: pip install python-telegram-bot==20.*
# 默认直接使用你提供的机器人 token，也可以通过环境变量 TELEGRAM_BOT_TOKEN 覆盖

# Cursor CLI agent 命令配置：
# - 优先从环境变量 CURSOR_AGENT_CMD 读取（例如：`agent`）
# - 默认使用 "agent"
#
# 安全提示：
# 下面的“最大权限”会让 agent 更倾向于执行命令/写入等操作。
# 请确保这是你信任的使用场景，且仅在内网/受控环境启用。
DEFAULT_CURSOR_AGENT_CMD = "agent"
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.log")

logger = logging.getLogger("bot_cursor_agent")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)


def _short_text(text: str, limit: int = 200) -> str:
    if text is None:
        return ""
    text = text.replace("\r", " ").replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"



def _build_cursor_cmd() -> List[str]:
    """
    从环境变量 `CURSOR_AGENT_CMD` 构造命令行列表（默认 `agent`）。
    按你的说明：无需额外做可执行文件路径兜底探测，直接依赖系统 PATH 即可。
    """
    cmd_str = os.getenv("CURSOR_AGENT_CMD", DEFAULT_CURSOR_AGENT_CMD).strip()
    cmd = [part for part in cmd_str.split(" ") if part]
    return cmd or ["agent"]


def _max_permission_agent_args() -> List[str]:
    """
    根据 agent --help 给 agent 分配尽可能多的执行权限（尽量减少交互/审批）。

    对应参数来自你贴的帮助文档：
      - --yolo：等价于 --force（强制允许 commands，除非明确被拒绝）
      - --approve-mcps：自动批准所有 MCP servers
    """

    # 只增加你要的最大执行权限参数：--yolo / --approve-mcps
    return [
        "--yolo",
        "--approve-mcps",
    ]


async def _reply_and_log(update: Update, text: str) -> None:
    """
    统一发送 Telegram 消息并在控制台打印，方便排查。
    """
    if update.message is None:
        return
    logger.info("[TG Reply] %s", _short_text(text))
    await update.message.reply_text(text)


def _run_cursor_agent_sync(prompt: str) -> str:
    """
    同步执行 Cursor agent，返回完整输出文本（给飞书通道使用）。
    """
    cmd = _build_cursor_cmd()
    cmd = [*cmd, *_max_permission_agent_args()]
    logger.info("[Agent Exec Sync] %s", " ".join(cmd))

    if os.name == "nt":
        full_cmd = " ".join(cmd)
        proc = subprocess.run(
            ["cmd.exe", "/c", full_cmd],
            input=(prompt + "\n"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
    else:
        proc = subprocess.run(
            cmd,
            input=(prompt + "\n"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
        )
        output = (proc.stdout or "") + (proc.stderr or "")

    return output.strip()


async def run_cursor_agent_stream(prompt: str, update: Update) -> None:
    """
    调用 Cursor Agent，并把 stdout 实时转发到 Telegram。
    """
    if update.message is None:
        return

    cmd = _build_cursor_cmd()
    cmd = [*cmd, *_max_permission_agent_args()]
    logger.info("[Agent Exec] %s", " ".join(cmd))
    try:
        # Windows 下直接 create_subprocess_exec("agent", ...) 可能找不到 .cmd shim；
        # 走 cmd.exe 让系统命令解析接管，避免 WinError 2。
        if os.name == "nt":
            full_cmd = " ".join(cmd)
            proc = await asyncio.create_subprocess_exec(
                "cmd.exe",
                "/c",
                full_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
    except Exception as exc:
        await _reply_and_log(
            update,
            (
                f"启动 agent 失败: {exc}\n"
                f"当前命令: {' '.join(cmd)}\n"
                "请先在 PowerShell 里确认: agent --help"
            ),
        )
        return

    if proc.stdout is None:
        await _reply_and_log(update, "(无输出)")
        return

    if proc.stdin is None:
        await _reply_and_log(update, "(无stdin通道)")
        return

    # 通过 stdin 传入初始 prompt，避免 agent 进入交互式等待输入
    try:
        proc.stdin.write((prompt + "\n").encode("utf-8", errors="ignore"))
        await proc.stdin.drain()
        proc.stdin.close()
    except Exception as exc:
        await _reply_and_log(update, f"向 agent 写入任务失败: {exc}")
        return

    try:
        stdout_bytes, _ = await proc.communicate()
        output = (stdout_bytes or b"").decode("utf-8", errors="ignore").strip()

        # 控制台打印完整输出，便于你对照排查
        if output:
            logger.info("[Agent Output TG] %s", _short_text(output, limit=500))
        else:
            await _reply_and_log(update, "(无输出)")
            return

        # Telegram 单条消息上限 4096，这里做一个安全余量切片
        max_chunk = 3500
        for i in range(0, len(output), max_chunk):
            chunk = output[i : i + max_chunk]
            if chunk:
                await _reply_and_log(update, chunk)

    except asyncio.TimeoutError:
        await _reply_and_log(update, "agent 执行超时。")
    except Exception as exc:
        await _reply_and_log(update, f"agent 执行异常: {exc}")


async def cursor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /cursor 命令：/cursor 后面跟任务描述。
    """
    if update.message is None:
        return

    prompt = " ".join(context.args).strip()
    if not prompt:
        await _reply_and_log(update, "用法: /cursor 你的任务描述")
        return

    logger.info("[TG Received /cursor] %s", _short_text(prompt))
    await run_cursor_agent_stream(prompt, update)


async def cursor_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    任何纯文本消息都视为任务，转给 Cursor CLI agent。
    """
    if update.message is None:
        return

    prompt = (update.message.text or "").strip()
    if not prompt:
        return

    logger.info("[TG Received text] %s", _short_text(prompt))
    await run_cursor_agent_stream(prompt, update)


def run_tg_bot() -> None:
    # 可以通过环境变量覆盖 token；否则使用你给出的默认 token
    token = os.getenv(
        "TELEGRAM_BOT_TOKEN",
        "8288588979:AAE8jsy9qtbxYRJwxrUJQcv06IAfgJCA3Mw",
    ).strip()
    if not token:
        raise SystemExit("缺少环境变量 TELEGRAM_BOT_TOKEN")

    app = Application.builder().token(token).build()

    # /cursor 显式命令
    app.add_handler(CommandHandler("cursor", cursor_cmd))
    # 其他文本消息全部作为任务转发
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cursor_text))

    app.run_polling()


def run_feishu_bot() -> None:
    """
    长连接飞书机器人：把收到的文本消息转给 Cursor agent，结果回发到会话。
    """
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
    from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1

    app_id = os.getenv("FEISHU_APP_ID", "cli_a94a6b06cdf81bc8").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "n9diR85BeOoAZqsmZvhTJc4ZmQGlQ1gH").strip()
    if not app_id or not app_secret:
        raise SystemExit("缺少环境变量 FEISHU_APP_ID / FEISHU_APP_SECRET")

    openapi_client = (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .log_level(lark.LogLevel.INFO)
        .build()
    )
    processed_message_ts = {}
    processed_lock = threading.Lock()
    dedup_ttl_seconds = 600

    def reply_text(chat_id: str, text: str) -> None:
        logger.info("[Feishu Reply] %s", _short_text(text))
        body = json.dumps({"text": text}, ensure_ascii=False)
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("text")
                .content(body)
                .build()
            )
            .build()
        )
        response = openapi_client.im.v1.message.create(request)
        if not response.success():
            raise RuntimeError(
                f"client.im.v1.message.create failed, code: {response.code}, "
                f"msg: {response.msg}, log_id: {response.get_log_id()}"
            )

    def is_duplicate_message(message_id: str) -> bool:
        if not message_id:
            return False
        now = time.time()
        with processed_lock:
            expired = [mid for mid, ts in processed_message_ts.items() if now - ts > dedup_ttl_seconds]
            for mid in expired:
                processed_message_ts.pop(mid, None)
            if message_id in processed_message_ts:
                return True
            processed_message_ts[message_id] = now
            return False

    def process_prompt_and_reply(chat_id: str, prompt: str) -> None:
        try:
            output = _run_cursor_agent_sync(prompt)
        except Exception as exc:
            reply_text(chat_id, f"agent 执行异常: {exc}")
            return

        if not output:
            reply_text(chat_id, "(无输出)")
            return

        logger.info("[Agent Output Feishu] %s", _short_text(output, limit=500))

        max_chunk = 3500
        for i in range(0, len(output), max_chunk):
            chunk = output[i : i + max_chunk]
            if chunk:
                reply_text(chat_id, chunk)

    def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
        event = data.event
        if event is None:
            return

        sender = getattr(event, "sender", None)
        if sender is not None and getattr(sender, "sender_type", None) == "app":
            return

        message = event.message
        if message is None or not message.chat_id:
            return
        message_id = getattr(message, "message_id", "")
        if is_duplicate_message(message_id):
            logger.info("[Feishu duplicate ignored] message_id=%s", message_id)
            return

        if (message.message_type or "").lower() == "text":
            try:
                content = json.loads(message.content or "{}")
                prompt = (content.get("text", "") or "").strip()
            except json.JSONDecodeError:
                prompt = (message.content or "").strip()
        else:
            reply_text(message.chat_id, f"暂只支持文本消息，当前类型：{message.message_type or 'unknown'}")
            return

        if not prompt:
            return

        logger.info("[Feishu Received text] %s", _short_text(prompt))
        # 长连接事件需要尽快返回 ACK，耗时任务放后台线程执行，避免平台重试导致重复消费。
        threading.Thread(
            target=process_prompt_and_reply,
            args=(message.chat_id, prompt),
            daemon=True,
        ).start()

    event_handler = (
        lark.EventDispatcherHandler.builder("", "", lark.LogLevel.INFO)
        .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
        .build()
    )

    ws_client = lark.ws.Client(
        app_id,
        app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )
    logger.info("[Feishu] long-connection started")
    ws_client.start()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Cursor agent bot by chat channel.")
    parser.add_argument(
        "--chat_by",
        choices=["tg", "feishu"],
        default="tg",
        help="Select message channel: tg (Telegram) or feishu (Lark).",
    )
    args = parser.parse_args()

    if args.chat_by == "tg":
        run_tg_bot()
    else:
        run_feishu_bot()


if __name__ == "__main__":
    main()