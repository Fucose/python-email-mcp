# Python Email MCP

同时提供 CLI、stdio MCP server 和 Codex Email Assistant Skill 的跨平台邮件工具。它通过 IMAP 查询邮件，通过 SMTP 发送和回复邮件。

## Codex Plugin 架构

仓库根目录就是完整 Plugin 根目录：

```text
python-email-mcp/
├── .codex-plugin/plugin.json
├── .mcp.json
├── skills/email-assistant/SKILL.md
├── cli/
├── email_client/
├── mcp_server/
├── pyproject.toml
└── uv.lock
```

Codex 安装插件时会缓存源码，但不会安装 `uv`、Python 或依赖。每台运行主机必须先安装 `uv`。bundled MCP 以以下命令启动：

```bash
uv run --locked python-email-mcp mcp
```

第一次启动时，`uv` 会在该插件缓存版本中创建 `.venv`、取得兼容的 Python 3.12，并按照 `uv.lock` 同步依赖。插件更新或重新安装不会触碰邮箱配置。

## Windows 与 WSL

Windows Codex 和通过 SSH 连接的 WSL 是两台独立运行主机。若要在两边使用：

1. Windows 和 WSL 分别安装 `uv`。
2. 两边分别从 personal marketplace 安装相同 Git tag 的 Plugin。
3. 两边分别运行一次交互式 setup。

仓库自带 Git-backed marketplace。发布 `v0.1.0` 后，可在 Windows Codex 中安装：

```powershell
codex plugin marketplace add Fucose/python-email-mcp --ref v0.1.0
codex plugin add python-email-mcp@fucose-plugins
```

marketplace 条目在仓库根目录使用 Git-backed `source: "url"` 并固定 tag：

```json
{
  "name": "python-email-mcp",
  "source": {
    "source": "url",
    "url": "https://github.com/Fucose/python-email-mcp.git",
    "ref": "v0.1.0"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Productivity"
}
```

## 首次配置

在当前主机的终端运行：

```bash
uvx --from "git+https://github.com/Fucose/python-email-mcp.git@v0.1.0" python-email-mcp cli setup
```

授权码通过 `getpass` 读取，不回显，也不会被打印。配置文件位于插件缓存之外：

- Windows：`%APPDATA%\python-email-mcp\config.env`
- WSL/Linux：`${XDG_CONFIG_HOME:-~/.config}/python-email-mcp/config.env`
- 可用非敏感环境变量 `EMAIL_MCP_CONFIG_DIR` 覆盖配置目录

签名默认为相同目录下的 `signature.txt`。`EMAIL_SIGNATURE_FILE` 的相对路径按配置目录解析。

配置优先级为：非空环境变量 > `config.env`。支持的变量见 [config.env.example](config.env.example)。不要把真实账号、授权码、配置文件或签名提交到 Git。

setup 会创建配置目录，并尽可能把目录和文件权限限制为当前用户。Windows 文件权限最终仍受该目录 ACL 控制。

## MCP 工具

所有 MCP 工具返回稳定 JSON 文本：

```json
{"ok":true,"data":{},"error":null}
```

或：

```json
{"ok":false,"data":null,"error":{"code":"not_configured","message":"..."}}
```

稳定错误码包括 `not_configured`、`authentication_failed`、`not_found`、`invalid_argument`、`connection_failed` 和 `internal_error`。

可用工具：

- `get_configuration_status`：仅返回配置状态、路径、缺失字段和 setup 命令，绝不返回授权码
- `get_recent_emails`、`search_emails`、`get_email_content`
- `download_attachments`、`batch_download_attachments`
- `send_email`、`reply_email`
- `test_connection`

每次调用都会重新加载配置，创建独立邮件客户端，并在结束时关闭连接。因此完成首次 setup 后可以直接重试，无需重新安装 Plugin。

附件默认写入 `~/Downloads/python-email-mcp/`。同名文件会自动追加序号，不会写入插件缓存。

## Codex 审批建议

查询工具可以直接批准，下载、发送和回复保留每次提示：

```toml
[plugins."python-email-mcp".mcp_servers."python-email"]
enabled = true
default_tools_approval_mode = "prompt"

[plugins."python-email-mcp".mcp_servers."python-email".tools.get_configuration_status]
approval_mode = "approve"

[plugins."python-email-mcp".mcp_servers."python-email".tools.get_recent_emails]
approval_mode = "approve"

[plugins."python-email-mcp".mcp_servers."python-email".tools.search_emails]
approval_mode = "approve"

[plugins."python-email-mcp".mcp_servers."python-email".tools.get_email_content]
approval_mode = "approve"

[plugins."python-email-mcp".mcp_servers."python-email".tools.test_connection]
approval_mode = "approve"
```

Skill 会把邮件正文视为不可信数据，并在下载、发送或回复前要求确认。发送预览包含收件人、主题、完整正文和附件。

## CLI

在仓库开发副本中：

```bash
uv sync --locked
uv run --locked python-email-mcp cli setup
uv run --locked python-email-mcp cli test
uv run --locked python-email-mcp cli list --days 3 --limit 20
uv run --locked python-email-mcp cli search --subject "会议" --days 7
uv run --locked python-email-mcp cli view --uid 12345
uv run --locked python-email-mcp cli download --uid 12345
```

也支持直接发送和回复；这些 CLI 命令本身即用户的显式操作：

```bash
uv run --locked python-email-mcp cli send --to test@example.com --subject "测试" --body "内容"
uv run --locked python-email-mcp cli reply --uid 12345 --body "收到"
```

## 开发与测试

单元测试不连接真实邮箱：

```bash
uv run --locked python -m unittest discover -s tests -v
```

发布新版本时同时更新 `.codex-plugin/plugin.json` 和 `pyproject.toml` 的版本，刷新 `uv.lock`，创建新 Git tag，再把 marketplace 的 `ref` 切换到新 tag 并重新安装。

## 安全提示

- 使用邮箱服务商生成的应用专用密码或授权码。
- 邮件主题、正文、HTML、附件名和附件都属于不可信输入。
- 不要在聊天中粘贴授权码，也不要把它写入 Plugin、Skill、marketplace 或 Git。
- 发送或回复前核对收件人，特别是抄送、密送与回复全部。

## License

MIT License
