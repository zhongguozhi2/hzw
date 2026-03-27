"""
发送文件到飞书群聊/私聊。

用法：
    # 列出机器人所在的群聊（获取 chat_id）
    python send_file_to_feishu.py --list-chats

    # 发送文件到指定群聊
    python send_file_to_feishu.py --chat-id oc_xxx --file path/to/file.pdf

    # 发送文件时附带一条文本说明
    python send_file_to_feishu.py --chat-id oc_xxx --file report.xlsx --text "这是本周报告"

环境变量（可选，脚本已内置默认值）：
    FEISHU_APP_ID      飞书应用 App ID
    FEISHU_APP_SECRET  飞书应用 App Secret
"""

import os
import sys
import json
import argparse
import mimetypes
from pathlib import Path

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateFileRequest,
    CreateFileRequestBody,
    CreateMessageRequest,
    CreateMessageRequestBody,
    ListChatRequest,
)

APP_ID = os.getenv("FEISHU_APP_ID", "cli_a94a6b06cdf81bc8").strip()
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "n9diR85BeOoAZqsmZvhTJc4ZmQGlQ1gH").strip()

FILE_TYPE_MAP = {
    ".opus": "opus",
    ".mp4": "mp4",
    ".pdf": "pdf",
    ".doc": "doc",
    ".docx": "doc",
    ".xls": "xls",
    ".xlsx": "xls",
    ".ppt": "ppt",
    ".pptx": "ppt",
}

def guess_msg_type(file_path: Path) -> str:
    """
    Feishu IM message type mapping for uploaded file.

    Error 230055 happens when `msg_type` does not match the uploaded file type.
    In particular, video files (mp4) should use msg_type="video", not "file".
    """
    ext = file_path.suffix.lower()
    if ext in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
        # Feishu uses `media` as the msg_type for video.
        return "media"
    if ext in {".opus", ".mp3", ".wav", ".aac"}:
        return "audio"
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return "image"
    return "file"


def build_client() -> lark.Client:
    return (
        lark.Client.builder()
        .app_id(APP_ID)
        .app_secret(APP_SECRET)
        .log_level(lark.LogLevel.INFO)
        .build()
    )


def guess_file_type(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    return FILE_TYPE_MAP.get(ext, "stream")


def upload_file(client: lark.Client, file_path: Path) -> str:
    """上传文件到飞书，返回 file_key。"""
    file_type = guess_file_type(file_path)
    file_name = file_path.name

    with open(file_path, "rb") as f:
        req = (
            CreateFileRequest.builder()
            .request_body(
                CreateFileRequestBody.builder()
                .file_type(file_type)
                .file_name(file_name)
                .file(f)
                .build()
            )
            .build()
        )
        resp = client.im.v1.file.create(req)

    if not resp.success():
        print(f"[ERROR] 上传文件失败: code={resp.code}, msg={resp.msg}, log_id={resp.get_log_id()}")
        sys.exit(1)

    file_key = resp.data.file_key
    print(f"[OK] 文件已上传, file_key={file_key}")
    return file_key


def send_file_message(client: lark.Client, chat_id: str, file_key: str, file_path: Path) -> None:
    """发送文件消息到指定会话。"""
    msg_type = guess_msg_type(file_path)
    content = json.dumps({"file_key": file_key})
    req = (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type(msg_type)
            .content(content)
            .build()
        )
        .build()
    )
    resp = client.im.v1.message.create(req)

    if not resp.success():
        print(f"[ERROR] 发送文件消息失败: code={resp.code}, msg={resp.msg}, log_id={resp.get_log_id()}")
        sys.exit(1)

    print(f"[OK] 文件消息已发送到 chat_id={chat_id}")


def send_text_message(client: lark.Client, chat_id: str, text: str) -> None:
    """发送纯文本消息。"""
    content = json.dumps({"text": text}, ensure_ascii=False)
    req = (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content(content)
            .build()
        )
        .build()
    )
    resp = client.im.v1.message.create(req)

    if not resp.success():
        print(f"[ERROR] 发送文本消息失败: code={resp.code}, msg={resp.msg}, log_id={resp.get_log_id()}")
        sys.exit(1)

    print(f"[OK] 文本消息已发送")


def list_chats(client: lark.Client) -> None:
    """列出机器人所在的群聊。"""
    req = ListChatRequest.builder().page_size(50).build()
    resp = client.im.v1.chat.list(req)

    if not resp.success():
        print(f"[ERROR] 获取群列表失败: code={resp.code}, msg={resp.msg}, log_id={resp.get_log_id()}")
        sys.exit(1)

    items = resp.data.items or []
    if not items:
        print("机器人当前不在任何群聊中。请先把机器人加入一个群。")
        return

    print(f"共找到 {len(items)} 个群聊:\n")
    print(f"{'#':<4} {'chat_id':<30} {'名称'}")
    print("-" * 70)
    for i, chat in enumerate(items, 1):
        name = getattr(chat, "name", "") or "(无名称)"
        cid = getattr(chat, "chat_id", "") or "N/A"
        print(f"{i:<4} {cid:<30} {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="发送文件到飞书")
    parser.add_argument("--file", "-f", help="要发送的文件路径")
    parser.add_argument("--chat-id", "-c", help="目标会话 chat_id (使用 --list-chats 获取)")
    parser.add_argument("--text", "-t", help="随文件一起发送的文本说明（可选）")
    parser.add_argument("--list-chats", action="store_true", help="列出机器人所在的群聊")
    args = parser.parse_args()

    client = build_client()

    if args.list_chats:
        list_chats(client)
        return

    if not args.file:
        parser.error("请指定 --file 或使用 --list-chats 查看群列表")

    file_path = Path(args.file).resolve()
    if not file_path.is_file():
        print(f"[ERROR] 文件不存在: {file_path}")
        sys.exit(1)

    if not args.chat_id:
        parser.error("请指定 --chat-id，可先用 --list-chats 查看可用群聊")

    print(f"文件: {file_path} ({file_path.stat().st_size / 1024:.1f} KB)")
    print(f"目标: chat_id={args.chat_id}")
    print()

    if args.text:
        send_text_message(client, args.chat_id, args.text)

    file_key = upload_file(client, file_path)
    send_file_message(client, args.chat_id, file_key, file_path)

    print("\n完成!")


if __name__ == "__main__":
    main()
