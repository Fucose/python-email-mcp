#!/usr/bin/env python3
"""Console entry point for MCP and CLI modes."""

import sys
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))


def print_usage(file=None):
    """打印使用说明"""
    print("""
Python Email MCP - 邮件客户端

使用方法:
  python-email-mcp mcp              启动 MCP 服务器模式
  python-email-mcp cli <command>    使用命令行工具模式

命令行工具命令:
  list                          列出最近邮件
  search --subject <关键词>      搜索邮件
  view --uid <邮件UID>          查看邮件详情
  download --uid <邮件UID>      下载附件
  batch-download --subject <关键词>  批量下载附件
  send --to <收件人> --subject <主题> --body <内容>  发送邮件
  reply --uid <邮件UID> --body <内容>  回复邮件
  setup                         配置邮箱
  test                          测试连接

示例:
  python-email-mcp cli list --days 3
  python-email-mcp cli search --subject "会议通知"
  python-email-mcp cli setup

配置:
  首次使用请运行 python-email-mcp cli setup。
  配置保存在插件缓存外的每用户配置目录。

文档:
  详细使用说明请查看 README.md
""", file=file or sys.stdout)


def main():
    """主函数"""
    if len(sys.argv) == 2 and sys.argv[1] in {"-h", "--help"}:
        print_usage()
        return
    if len(sys.argv) < 2:
        print_usage(sys.stderr)
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == 'mcp':
        from mcp_server.server import main as mcp_main
        import asyncio
        asyncio.run(mcp_main())

    elif mode == 'cli':
        from cli.main import main as cli_main
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        cli_main()

    else:
        print(f"未知模式: {mode}", file=sys.stderr)
        print_usage(sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n操作已取消", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"启动失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
