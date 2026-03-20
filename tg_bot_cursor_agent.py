import os
import asyncio
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
    print(f"[Bot Reply] {text}")
    await update.message.reply_text(text)


async def run_cursor_agent_stream(prompt: str, update: Update) -> None:
    """
    调用 Cursor Agent，并把 stdout 实时转发到 Telegram。
    """
    if update.message is None:
        return

    cmd = _build_cursor_cmd()
    cmd = [*cmd, *_max_permission_agent_args()]
    print(f"[Agent Exec] {' '.join(cmd)}")
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
            print(output)
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

    print(f"[Telegram /cursor] {prompt}")
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

    print(f"[Telegram text] {prompt}")
    await run_cursor_agent_stream(prompt, update)


def main() -> None:
    # 防止多开导致 Telegram 轮询冲突（Conflict: terminated by other getUpdates request）。
    # Windows 下用文件锁实现单实例。
    if os.name == "nt":
        import msvcrt

        lock_path = os.path.join(os.path.dirname(__file__), ".telegram_codex_bot.lock")
        lock_handle = open(lock_path, "w", encoding="utf-8")
        try:
            msvcrt.locking(lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            try:
                lock_handle.close()
            except Exception:
                pass
            raise SystemExit("检测到已有 telegram_codex_bot 实例在运行，请先停止旧实例后再启动。")

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


if __name__ == "__main__":
    main()