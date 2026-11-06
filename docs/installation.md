# 安装与配置

Python Email MCP 可以作为插件安装，也可以作为本地 stdio MCP server 连接。运行环境和邮箱配置位于启动 MCP 进程的主机上。

## 运行要求

- MCP 主机需要安装 `uv`
- 项目使用 Python 3.12，`uv` 可以为项目管理 Python
- 邮箱需要提供可用的 IMAP 和 SMTP 设置

## 准备本地插件目录

预览当前未提交的工作树时，把公开插件文件复制到新的临时目录，再从该目录安装。Codex 会一起复制本地 source 中被 Git 忽略的文件，因此应先准备公开文件目录。下面的 allowlist 不包含仓库根目录的 `.env`、`config.env`、`signature.txt`、`.git`、`.venv`、`env` 或 `venv`。

从仓库根目录在 PowerShell 中运行以下命令。保留同一个 PowerShell 会话，以便平台指南使用生成的 `$staging` 路径。

```powershell
$source = (Resolve-Path .).Path
$staging = Join-Path $env:TEMP ("python-email-mcp-preview-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $staging | Out-Null
$items = @(
    ".agents", "plugin.json", "mcp.json", ".mcp.json", ".claude-plugin",
    "skills", "cli", "email_client", "mcp_server", "main.py", "pyproject.toml",
    "uv.lock", ".python-version", "README.md", "LICENSE", "config.env.example",
    "signature.txt.example", "docs"
)
foreach ($item in $items) {
    Copy-Item -LiteralPath (Join-Path $source $item) -Destination $staging -Recurse
}
```

该列表只复制列出的顶层文件和目录，不会复制仓库根目录的本地配置、Git 元数据或虚拟环境。复制完成后按对应平台指南从 `$staging` 安装插件。

## 配置邮箱

首次邮箱操作前调用 `get_configuration_status`。若结果列出缺失字段，请复制其中完整的 `setup_command`，并在运行 MCP server 的同一主机终端执行。命令使用当前 MCP server 进程的 Python 解释器和已安装包中 `main.py` 的绝对路径，无需下载另一个包或依赖发布 tag。Windows 与 POSIX shell 的命令行引用格式由状态结果提供，原样复制即可。

不要在聊天中粘贴密码或授权码。交互式 setup 会通过不回显的终端提示读取密码或授权码。完成后再次调用 `get_configuration_status`，再继续邮箱操作。

开发者也可以从本地源码 checkout 执行 setup。

```powershell
uv run --project "D:\path\to\python-email-mcp" --locked python-email-mcp cli setup
```

把示例替换为仓库的绝对路径。即使从其他当前目录运行，命令也会定位指定项目。

MCP 主机启动进程时，`uv --project` 只用于定位项目，不会改变进程当前目录。因此相对附件路径和下载目标会相对于主机选定的当前目录解析。优先使用绝对路径。

## 配置位置

配置文件默认写在插件安装和缓存目录之外。

- Windows 默认使用 `%APPDATA%\python-email-mcp\config.env`
- Linux 和 WSL 默认使用 `${XDG_CONFIG_HOME:-~/.config}/python-email-mcp/config.env`
- 可设置 `EMAIL_MCP_CONFIG_DIR` 来指定其他目录
- 签名默认使用配置目录中的 `signature.txt`
- 附件默认下载到 `~/Downloads/python-email-mcp/`

环境中的非空值优先于 `config.env` 中的值。支持的配置键见仓库根目录的 [`config.env.example`](../config.env.example)。`EMAIL_SIGNATURE_FILE` 的相对路径按配置目录解析。

Windows 和 WSL 是两个不同的运行主机。若两边都要运行 MCP，需要分别配置。安装或更新插件不会迁移邮箱设置。

## 验证配置

再次调用 `get_configuration_status`，确认账号已配置且没有缺失字段。然后调用 `test_connection` 或运行以下 CLI 命令，确认邮箱服务器可连接。

```powershell
uv run --project "D:\path\to\python-email-mcp" --locked python-email-mcp cli test
```

只有状态或连接测试结果明确成功时，才报告配置或连接已成功。

## 平台指南

- [Codex](codex.md)
- [Claude Code](claude-code.md)
