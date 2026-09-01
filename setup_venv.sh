#!/bin/bash
# 使用锁文件创建项目虚拟环境并安装依赖

set -eu
echo "使用 uv 同步锁定依赖..."
uv sync --locked

echo ""
echo "✅ 虚拟环境设置完成！"
echo ""
echo "使用方法:"
echo "  uv run --locked python-email-mcp cli list --days 3"
echo "  uv run --locked python-email-mcp cli setup"
echo ""
echo "启动MCP服务器:"
echo "  uv run --locked python-email-mcp mcp"
