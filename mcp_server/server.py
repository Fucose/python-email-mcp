"""MCP服务器实现"""

import sys
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server import Server
from mcp.types import Tool, TextContent
from email_client import EmailClient, Config
import json


# 创建MCP服务器
server = Server("python-email-server")

# 全局客户端实例
_client = None


def get_client():
    """获取邮件客户端实例"""
    global _client
    if _client is None:
        _client = EmailClient()
    return _client


@server.list_tools()
async def list_tools() -> list[Tool]:
    """列出所有可用工具"""
    return [
        Tool(
            name="get_recent_emails",
            description="获取最近的邮件列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "number",
                        "description": "最近几天（默认3）",
                        "default": 3
                    },
                    "limit": {
                        "type": "number",
                        "description": "最大返回数量（默认20）",
                        "default": 20
                    }
                }
            }
        ),
        Tool(
            name="search_emails",
            description="按主题搜索邮件",
            inputSchema={
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "主题关键词"
                    },
                    "days": {
                        "type": "number",
                        "description": "搜索最近几天（默认7）",
                        "default": 7
                    }
                },
                "required": ["subject"]
            }
        ),
        Tool(
            name="get_email_content",
            description="获取邮件详细内容",
            inputSchema={
                "type": "object",
                "properties": {
                    "uid": {
                        "type": "string",
                        "description": "邮件UID"
                    }
                },
                "required": ["uid"]
            }
        ),
        Tool(
            name="download_attachments",
            description="下载邮件附件",
            inputSchema={
                "type": "object",
                "properties": {
                    "uid": {
                        "type": "string",
                        "description": "邮件UID"
                    },
                    "folder": {
                        "type": "string",
                        "description": "下载文件夹（默认downloads）",
                        "default": "downloads"
                    }
                },
                "required": ["uid"]
            }
        ),
        Tool(
            name="batch_download_attachments",
            description="批量下载附件（基于搜索结果）",
            inputSchema={
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "主题关键词"
                    },
                    "days": {
                        "type": "number",
                        "description": "搜索最近几天（默认7）",
                        "default": 7
                    },
                    "folder": {
                        "type": "string",
                        "description": "下载文件夹（默认downloads）",
                        "default": "downloads"
                    }
                },
                "required": ["subject"]
            }
        ),
        Tool(
            name="send_email",
            description="发送邮件",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "收件人列表"
                    },
                    "subject": {
                        "type": "string",
                        "description": "邮件主题"
                    },
                    "text": {
                        "type": "string",
                        "description": "邮件正文"
                    },
                    "attachments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "附件文件路径列表"
                    },
                    "cc": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "抄送列表"
                    },
                    "bcc": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "密送列表"
                    }
                },
                "required": ["to", "subject", "text"]
            }
        ),
        Tool(
            name="reply_email",
            description="回复邮件",
            inputSchema={
                "type": "object",
                "properties": {
                    "uid": {
                        "type": "string",
                        "description": "原邮件UID"
                    },
                    "text": {
                        "type": "string",
                        "description": "回复正文"
                    },
                    "attachments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "附件文件路径列表"
                    },
                    "reply_all": {
                        "type": "boolean",
                        "description": "是否回复全部",
                        "default": False
                    }
                },
                "required": ["uid", "text"]
            }
        ),
        Tool(
            name="setup_email_account",
            description="配置邮箱账号",
            inputSchema={
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "邮箱地址"
                    },
                    "password": {
                        "type": "string",
                        "description": "邮箱密码或授权码"
                    },
                    "imap_host": {
                        "type": "string",
                        "description": "IMAP服务器地址"
                    },
                    "imap_port": {
                        "type": "number",
                        "description": "IMAP端口"
                    },
                    "imap_ssl": {
                        "type": "boolean",
                        "description": "IMAP是否使用SSL"
                    },
                    "smtp_host": {
                        "type": "string",
                        "description": "SMTP服务器地址"
                    },
                    "smtp_port": {
                        "type": "number",
                        "description": "SMTP端口"
                    },
                    "smtp_ssl": {
                        "type": "boolean",
                        "description": "SMTP是否使用SSL"
                    }
                },
                "required": ["email", "password", "imap_host", "imap_port", "imap_ssl", "smtp_host", "smtp_port", "smtp_ssl"]
            }
        ),
        Tool(
            name="test_connection",
            description="测试邮箱连接",
            inputSchema={
                "type": "object",
                "properties": {
                    "test_type": {
                        "type": "string",
                        "enum": ["imap", "smtp", "both"],
                        "description": "测试类型",
                        "default": "both"
                    }
                }
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """调用工具"""

    try:
        if name == "get_recent_emails":
            client = get_client()
            days = arguments.get("days", 3)
            limit = arguments.get("limit", 20)

            emails = client.get_recent_emails(days, limit)

            if not emails:
                return [TextContent(
                    type="text",
                    text=f"最近{days}天内没有找到邮件。"
                )]

            result = f"📬 最近{days}天的邮件列表 (共{len(emails)}封):\n\n"
            for email in emails:
                result += f"📧 UID: {email.uid}\n"
                result += f"📅 日期: {email.date.strftime('%Y-%m-%d %H:%M')}\n"
                result += f"👤 发件人: {email.from_}\n"
                result += f"📝 主题: {email.subject}\n"
                result += "─" * 50 + "\n"

            return [TextContent(type="text", text=result)]

        elif name == "search_emails":
            client = get_client()
            subject = arguments["subject"]
            days = arguments.get("days", 7)

            emails = client.search_emails(subject, days)

            if not emails:
                return [TextContent(
                    type="text",
                    text=f"未找到主题包含'{subject}'的邮件。"
                )]

            result = f"📬 搜索结果 (共{len(emails)}封):\n\n"
            for email in emails:
                result += f"📧 UID: {email.uid}\n"
                result += f"📅 日期: {email.date.strftime('%Y-%m-%d %H:%M')}\n"
                result += f"👤 发件人: {email.from_}\n"
                result += f"📝 主题: {email.subject}\n"
                result += "─" * 50 + "\n"

            return [TextContent(type="text", text=result)]

        elif name == "get_email_content":
            client = get_client()
            uid = arguments["uid"]

            email = client.get_email(uid)

            if not email:
                return [TextContent(
                    type="text",
                    text=f"✗ 未找到UID为{uid}的邮件"
                )]

            result = f"📧 邮件详情 (UID: {email.uid})\n"
            result += "─" * 50 + "\n"
            result += f"📅 日期: {email.date.strftime('%Y-%m-%d %H:%M:%S')}\n"
            result += f"👤 发件人: {email.from_}\n"
            result += f"👥 收件人: {email.to}\n"
            if email.cc:
                result += f"📋 抄送: {email.cc}\n"
            result += f"📝 主题: {email.subject}\n"
            result += "─" * 50 + "\n"

            if email.body:
                result += f"📄 文本内容:\n{email.body}\n"

            if email.attachments:
                result += f"\n📎 附件列表:\n"
                for i, att in enumerate(email.attachments, 1):
                    result += f"  {i}. {att.filename} ({att.size:,} bytes)\n"

            return [TextContent(type="text", text=result)]

        elif name == "download_attachments":
            client = get_client()
            uid = arguments["uid"]
            folder = Path(arguments.get("folder", "downloads"))

            files = client.download_attachments(uid, folder)

            if not files:
                return [TextContent(
                    type="text",
                    text="✗ 未找到附件或下载失败"
                )]

            result = f"✓ 下载完成！共下载{len(files)}个文件\n"
            result += f"✓ 保存位置: {folder.absolute()}\n\n"
            for file_path in files:
                result += f"  • {file_path.name}\n"

            return [TextContent(type="text", text=result)]

        elif name == "batch_download_attachments":
            client = get_client()
            subject = arguments["subject"]
            days = arguments.get("days", 7)
            folder = Path(arguments.get("folder", "downloads"))

            files = client.batch_download_attachments(subject, days, folder)

            if not files:
                return [TextContent(
                    type="text",
                    text="✗ 未找到附件或下载失败"
                )]

            result = f"✓ 批量下载完成！共下载{len(files)}个文件\n"
            result += f"✓ 保存位置: {folder.absolute()}\n\n"
            for file_path in files:
                result += f"  • {file_path.name}\n"

            return [TextContent(type="text", text=result)]

        elif name == "send_email":
            client = get_client()
            to = arguments["to"]
            subject = arguments["subject"]
            body = arguments["text"]
            attachments = arguments.get("attachments")
            cc = arguments.get("cc")
            bcc = arguments.get("bcc")

            # 转换附件路径
            attachment_paths = None
            if attachments:
                attachment_paths = [Path(f) for f in attachments]

            success = client.send_email(to, subject, body, attachment_paths, cc, bcc)

            if success:
                result = f"✓ 邮件发送成功！\n"
                result += f"  收件人: {', '.join(to)}\n"
                result += f"  主题: {subject}"
            else:
                result = "✗ 邮件发送失败"

            return [TextContent(type="text", text=result)]

        elif name == "reply_email":
            client = get_client()
            uid = arguments["uid"]
            body = arguments["text"]
            attachments = arguments.get("attachments")
            reply_all = arguments.get("reply_all", False)

            # 转换附件路径
            attachment_paths = None
            if attachments:
                attachment_paths = [Path(f) for f in attachments]

            success = client.reply(uid, body, attachment_paths, reply_all)

            if success:
                result = "✓ 回复发送成功！"
            else:
                result = "✗ 回复发送失败"

            return [TextContent(type="text", text=result)]

        elif name == "setup_email_account":
            email = arguments["email"]
            password = arguments["password"]
            imap_host = arguments["imap_host"]
            imap_port = arguments["imap_port"]
            imap_ssl = arguments["imap_ssl"]
            smtp_host = arguments["smtp_host"]
            smtp_port = arguments["smtp_port"]
            smtp_ssl = arguments["smtp_ssl"]

            config = Config()
            success = config.save_config(email, password, imap_host, imap_port, imap_ssl, smtp_host, smtp_port, smtp_ssl)

            if success:
                result = f"✓ 邮箱账号设置成功！\n\n"
                result += f"📧 邮箱地址: {email}\n"
                result += f"📥 IMAP服务器: {imap_host}:{imap_port} (SSL: {'是' if imap_ssl else '否'})\n"
                result += f"📤 SMTP服务器: {smtp_host}:{smtp_port} (SSL: {'是' if smtp_ssl else '否'})\n"
                result += f"\n💡 提示: 配置已保存，您现在可以使用邮件功能了！"
            else:
                result = "✗ 邮箱设置失败"

            return [TextContent(type="text", text=result)]

        elif name == "test_connection":
            client = get_client()
            test_type = arguments.get("test_type", "both")

            results = client.test_connection(test_type)

            result = "\n".join(results.values())

            return [TextContent(type="text", text=result)]

        else:
            return [TextContent(
                type="text",
                text=f"✗ 未知的工具: {name}"
            )]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"✗ 执行工具时出错: {e}"
        )]


async def main():
    """启动MCP服务器"""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
