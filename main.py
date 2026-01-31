#!/usr/bin/env python3
"""
Python Email MCP - 主入口文件
支持MCP服务器模式和命令行工具模式
"""

import sys
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))


def print_usage():
    """打印使用说明"""
    print("""
Python Email MCP - 邮件客户端

使用方法:
  python main.py mcp              启动MCP服务器模式
  python main.py cli <command>    使用命令行工具模式

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
  # MCP模式
  python main.py mcp

  # CLI模式
  python main.py cli list --days 3
  python main.py cli search --subject "会议通知"
  python main.py cli download --uid 12345 --folder downloads
  python main.py cli send --to test@example.com --subject "测试" --body "内容"
  python main.py cli setup

配置:
  首次使用请运行: python main.py cli setup
  或手动创建 .env 文件（参考 .env.example）

文档:
  详细使用说明请查看 README.md
""")


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == 'mcp':
        # MCP服务器模式
        from mcp_server.server import main as mcp_main
        import asyncio
        asyncio.run(mcp_main())

    elif mode == 'cli':
        # 命令行工具模式
        from cli.main import main as cli_main
        # 移除 'cli' 参数
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        cli_main()

    else:
        # 未知模式
        print(f"✗ 未知模式: {mode}")
        print()
        print_usage()
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n操作已取消")
        sys.exit(0)
    except Exception as e:
        print(f"✗ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
