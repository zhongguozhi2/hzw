"""
Open a leave-request email draft in the Outlook desktop client.

The script creates a new mail item via COM, injects the body *before* the
default signature that Outlook inserts on Display(), so the user's business-
card signature is preserved automatically.

Usage examples
--------------
# 休假一天（默认）
python send_leave_email_outlook_client.py --date "3/19"

# 休假两天
python send_leave_email_outlook_client.py --date "3/19-3/20" --days 2

# 自定义原因 + 收件人
python send_leave_email_outlook_client.py --date "3/19" --reason "身体不适" --to "someone@cbctech.com"

# 完全自定义（非请假场景）
python send_leave_email_outlook_client.py --subject "周报" --body "<b>本周完成…</b>" --to "team@cbctech.com"
"""

import argparse
import sys

import win32com.client as win32


def build_leave_body(date_str: str, days: int, reason: str) -> str:
    day_text = f"{days}天" if days >= 1 else "半天"
    return (
        f'<div style="font-family: Calibri, sans-serif; font-size: 11pt;">'
        f"Hi 宋总 Charlie<br><br>"
        f"本人因{reason}， {date_str}休假{day_text}。<br>"
        f"如有事宜需要找我确认，可以微信联系。<br><br>"
        f"</div>"
    )


def build_leave_subject(date_str: str, days: int) -> str:
    day_text = f"{days}天" if days >= 1 else "半天"
    date_display = date_str.replace("-", "~")
    return f"{date_display}休假{day_text}-黄志文"


def create_mail(to: str, subject: str, html_body: str, send: bool = False):
    outlook = win32.Dispatch("outlook.application")
    mail = outlook.CreateItem(0)
    mail.To = to
    mail.Subject = subject

    # Display() triggers Outlook to insert the default signature into HTMLBody
    mail.Display()
    signature = mail.HTMLBody

    mail.HTMLBody = html_body + signature

    if send:
        mail.Send()
        print(f"Email sent to {to}")
    else:
        print(f"Email draft displayed in Outlook  →  {subject}")


def main():
    parser = argparse.ArgumentParser(description="Outlook leave-email helper")
    parser.add_argument("--date", help="休假日期，如 '3/19' 或 '3/19-3/20'")
    parser.add_argument("--days", type=float, default=1, help="休假天数，默认 1")
    parser.add_argument("--reason", default="个人有事", help="请假原因，默认「个人有事」")
    parser.add_argument("--to", default="zhiwen.huang@cbctech.com", help="收件人")
    parser.add_argument("--cc", default="", help="抄送")
    parser.add_argument("--subject", help="自定义邮件主题（覆盖自动生成）")
    parser.add_argument("--body", help="自定义 HTML 正文（覆盖请假模板）")
    parser.add_argument("--send", action="store_true", help="直接发送而非打开草稿")

    args = parser.parse_args()

    if args.body:
        html_body = args.body
    elif args.date:
        html_body = build_leave_body(args.date, args.days, args.reason)
    else:
        parser.error("必须提供 --date（请假日期）或 --body（自定义正文）")

    subject = args.subject or (
        build_leave_subject(args.date, args.days) if args.date else "邮件"
    )

    try:
        create_mail(to=args.to, subject=subject, html_body=html_body, send=args.send)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        print("请确保 Outlook 桌面客户端已启动。", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
