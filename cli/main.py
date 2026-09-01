"""Command-line interface for python-email-mcp."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from email_client import Config, EmailClient, EmailClientError, get_default_download_dir


def _with_client(operation):
    client = EmailClient()
    try:
        return operation(client)
    finally:
        client.disconnect()


def cmd_list(args):
    def run(client):
        messages = client.get_recent_emails(days=args.days, limit=args.limit)
        print(f"最近 {args.days} 天的邮件：{len(messages)} 封")
        for message in messages:
            print(f"UID: {message.uid}")
            print(f"日期: {message.date.strftime('%Y-%m-%d %H:%M')}")
            print(f"发件人: {message.from_}")
            print(f"主题: {message.subject}")
            print("-" * 50)

    _with_client(run)


def cmd_search(args):
    def run(client):
        messages = client.search_emails(subject=args.subject, days=args.days)
        print(f"搜索结果：{len(messages)} 封")
        for message in messages:
            print(f"UID: {message.uid}")
            print(f"日期: {message.date.strftime('%Y-%m-%d %H:%M')}")
            print(f"发件人: {message.from_}")
            print(f"主题: {message.subject}")
            print("-" * 50)

    _with_client(run)


def cmd_view(args):
    def run(client):
        message = client.get_email(args.uid)
        if not message:
            print(f"未找到 UID 为 {args.uid} 的邮件")
            return
        print(f"UID: {message.uid}")
        print(f"日期: {message.date.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"发件人: {message.from_}")
        print(f"收件人: {message.to}")
        if message.cc:
            print(f"抄送: {message.cc}")
        print(f"主题: {message.subject}")
        print("-" * 50)
        if message.body:
            print(message.body)
        if message.attachments:
            print("\n附件：")
            for attachment in message.attachments:
                print(f"- {attachment.filename} ({attachment.size} bytes)")

    _with_client(run)


def _download_folder(value: str | None) -> Path:
    return Path(value).expanduser() if value else get_default_download_dir()


def cmd_download(args):
    folder = _download_folder(args.folder)

    def run(client):
        files = client.download_attachments(args.uid, folder)
        print(f"已下载 {len(files)} 个附件到 {folder.resolve()}")
        for path in files:
            print(f"- {path.name}")

    _with_client(run)


def cmd_batch_download(args):
    folder = _download_folder(args.folder)

    def run(client):
        files = client.batch_download_attachments(args.subject, args.days, folder)
        print(f"已下载 {len(files)} 个附件到 {folder.resolve()}")
        for path in files:
            print(f"- {path.name}")

    _with_client(run)


def _split_addresses(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def cmd_send(args):
    def run(client):
        client.send_email(
            to=_split_addresses(args.to) or [],
            subject=args.subject,
            body=args.body,
            attachments=[Path(item).expanduser() for item in args.attach] if args.attach else None,
            cc=_split_addresses(args.cc),
            bcc=_split_addresses(args.bcc),
        )
        print("邮件发送成功")

    _with_client(run)


def cmd_reply(args):
    def run(client):
        client.reply(
            uid=args.uid,
            body=args.body,
            attachments=[Path(item).expanduser() for item in args.attach] if args.attach else None,
            reply_all=args.reply_all,
        )
        print("回复发送成功")

    _with_client(run)


def _prompt_value(label: str, supplied: str | None, default: str | None = None) -> str:
    if supplied:
        return supplied.strip()
    suffix = f"（默认 {default}）" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or (default or "")


def cmd_setup(args):
    """Collect the authorization code only through a non-echoing terminal prompt."""
    config = Config()
    if config.env_file.exists() and not args.force:
        overwrite = input(f"配置文件 {config.env_file} 已存在，是否覆盖？(y/N): ").strip().lower()
        if overwrite not in {"y", "yes"}:
            print("操作已取消")
            return

    email = _prompt_value("邮箱地址", args.email)
    password = getpass.getpass("邮箱密码或授权码（输入不会显示）: ")
    imap_host = _prompt_value("IMAP 服务器", args.imap_host, "mail.cstnet.cn")
    smtp_host = _prompt_value("SMTP 服务器", args.smtp_host, "mail.cstnet.cn")
    if not email or not password:
        raise ValueError("邮箱地址和授权码不能为空")

    saved = config.save_config(
        email=email,
        password=password,
        imap_host=imap_host,
        imap_port=args.imap_port,
        imap_ssl=args.imap_ssl,
        smtp_host=smtp_host,
        smtp_port=args.smtp_port,
        smtp_ssl=args.smtp_ssl,
    )
    if not saved:
        raise OSError(f"无法写入配置文件 {config.env_file}")

    print(f"配置已保存到 {config.env_file}")
    print(f"邮箱: {email}")
    print(f"IMAP: {imap_host}:{args.imap_port} (SSL: {args.imap_ssl})")
    print(f"SMTP: {smtp_host}:{args.smtp_port} (SSL: {args.smtp_ssl})")
    print("运行 `python-email-mcp cli test` 验证连接。")


def cmd_test(args):
    def run(client):
        results = client.test_connection(args.type)
        for protocol, result in results.items():
            state = "成功" if result["ok"] else "失败"
            print(f"{protocol.upper()}: {state} - {result['message']}")

    _with_client(run)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Python Email MCP 命令行工具")
    parser.add_argument("--verbose", action="store_true", help="显示异常堆栈")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出最近邮件")
    list_parser.add_argument("--days", type=int, default=3)
    list_parser.add_argument("--limit", type=int, default=20)

    search_parser = subparsers.add_parser("search", help="按主题搜索邮件")
    search_parser.add_argument("--subject", required=True)
    search_parser.add_argument("--days", type=int, default=7)

    view_parser = subparsers.add_parser("view", help="查看邮件详情")
    view_parser.add_argument("--uid", required=True)

    download_parser = subparsers.add_parser("download", help="下载附件")
    download_parser.add_argument("--uid", required=True)
    download_parser.add_argument("--folder", help="默认 ~/Downloads/python-email-mcp")

    batch_parser = subparsers.add_parser("batch-download", help="批量下载附件")
    batch_parser.add_argument("--subject", required=True)
    batch_parser.add_argument("--days", type=int, default=7)
    batch_parser.add_argument("--folder", help="默认 ~/Downloads/python-email-mcp")

    send_parser = subparsers.add_parser("send", help="发送邮件")
    send_parser.add_argument("--to", required=True)
    send_parser.add_argument("--subject", required=True)
    send_parser.add_argument("--body", required=True)
    send_parser.add_argument("--attach", nargs="*")
    send_parser.add_argument("--cc")
    send_parser.add_argument("--bcc")

    reply_parser = subparsers.add_parser("reply", help="回复邮件")
    reply_parser.add_argument("--uid", required=True)
    reply_parser.add_argument("--body", required=True)
    reply_parser.add_argument("--attach", nargs="*")
    reply_parser.add_argument("--reply-all", action="store_true")

    setup_parser = subparsers.add_parser("setup", help="交互式配置邮箱")
    setup_parser.add_argument("--email")
    setup_parser.add_argument("--imap-host")
    setup_parser.add_argument("--imap-port", type=int, default=993)
    setup_parser.add_argument(
        "--imap-ssl", action=argparse.BooleanOptionalAction, default=True
    )
    setup_parser.add_argument("--smtp-host")
    setup_parser.add_argument("--smtp-port", type=int, default=465)
    setup_parser.add_argument(
        "--smtp-ssl", action=argparse.BooleanOptionalAction, default=True
    )
    setup_parser.add_argument("--force", action="store_true", help="不询问直接覆盖")

    test_parser = subparsers.add_parser("test", help="测试邮箱连接")
    test_parser.add_argument("--type", choices=["imap", "smtp", "both"], default="both")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    command_func = {
        "list": cmd_list,
        "search": cmd_search,
        "view": cmd_view,
        "download": cmd_download,
        "batch-download": cmd_batch_download,
        "send": cmd_send,
        "reply": cmd_reply,
        "setup": cmd_setup,
        "test": cmd_test,
    }[args.command]
    try:
        command_func(args)
    except KeyboardInterrupt:
        print("\n操作已取消", file=sys.stderr)
        raise SystemExit(130)
    except (EmailClientError, OSError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        if args.verbose:
            raise
        raise SystemExit(1)


if __name__ == "__main__":
    main()
