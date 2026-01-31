@echo off
REM 创建虚拟环境并安装依赖

echo 🔧 创建Python虚拟环境...

REM 使用uv创建虚拟环境
uv venv .venv

REM 激活虚拟环境
echo 📦 激活虚拟环境并安装依赖...
call .venv\Scripts\activate

REM 安装依赖
uv pip install -r requirements.txt

echo.
echo ✅ 虚拟环境设置完成！
echo.
echo 使用方法:
echo   激活虚拟环境: .venv\Scripts\activate
echo   退出虚拟环境: deactivate
echo.
echo 运行CLI工具:
echo   python main.py list --days 3
echo   python main.py search --subject "关键词"
echo   python main.py setup
echo.
echo 启动MCP服务器:
echo   python main.py mcp
