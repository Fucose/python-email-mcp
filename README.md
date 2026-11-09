# Python Email MCP

用于 Codex、Claude Code、DeepSeek Harness 和其他支持本地 stdio MCP 的助手的跨平台邮件工具。它通过 IMAP 查询邮件，通过 SMTP 发送和回复邮件，并提供一份共享的 Email Assistant Skill。

## 文档

- [安装、配置与更新](docs/installation.md)
- [Codex](docs/codex.md)
- [Claude Code](docs/claude-code.md)
- [DeepSeek Harness](docs/dsh.md)
- [架构与开发](docs/architecture.md)
- [共享 Skill](skills/email-assistant/SKILL.md)

## 功能

- 使用 IMAP 搜索、列出和读取邮件
- 下载单封邮件或搜索结果中的附件
- 使用 SMTP 发送邮件或回复邮件
- 通过 stdio MCP 与 CLI 使用同一份 Python 邮件核心
- 在插件缓存之外保存每个用户自己的配置
- 使用稳定的 JSON 结果和错误码

## 项目结构

仓库根目录是可移植插件的根目录。`plugin.json` 和 `mcp.json` 描述可移植插件，`skills/email-assistant/` 提供平台无关的共享 Skill。Codex 和 Claude Code 使用各自的适配配置，DeepSeek Harness 使用 `integrations/dsh/` 中的 bundle。详见[架构文档](docs/architecture.md)。

## 安装与配置

运行本地 MCP server 的主机需要安装 `uv`。项目使用 Python 3.12。不同主机上的插件、运行时与邮箱配置互相独立，例如 Windows 与 WSL 需要分别安装和配置。

当前版本为 `0.2.0`，对应 tag 为 `v0.2.0`。该 tag 于 2026-11-09 重新发布，包含 TLS、IMAP 和发送预览修复，详见 [Changelog](CHANGELOG.md)。已有安装需要刷新原 tag 或插件快照，操作见[安装指南](docs/installation.md#选择安装来源与更新)。

首次执行邮箱操作前先调用 `get_configuration_status`。若结果列出缺失字段，在运行 MCP server 的同一主机终端执行其中的完整 `setup_command`。

`setup_command` 使用当前 MCP 进程的 Python 解释器和该安装包中 `main.py` 的绝对路径。Windows 和 POSIX 命令会按对应 shell 格式引用路径。本地源码 checkout 可以使用以下命令，并将项目路径替换为仓库绝对路径。

```powershell
uv run --project "D:\path\to\python-email-mcp" --locked python-email-mcp cli setup
```

Setup 通过不回显的终端提示读取密码或授权码，不要在聊天中粘贴秘密。配置默认写到插件缓存之外的用户目录。

- Windows 使用 `%APPDATA%\python-email-mcp\config.env`
- Linux 和 WSL 使用 `${XDG_CONFIG_HOME:-~/.config}/python-email-mcp/config.env`
- `EMAIL_MCP_CONFIG_DIR` 可以覆盖配置目录
- 签名默认使用配置目录中的 `signature.txt`
- `EMAIL_SIGNATURE_FILE` 的相对路径按配置目录解析
- 环境中的非空变量优先于 `config.env`

可用变量见 [`config.env.example`](config.env.example)。Setup 会尽可能限制文件权限。Windows 上的最终访问权限仍取决于目录 ACL。

安装说明见[通用安装文档](docs/installation.md)和[平台指南](#平台指南)。

## MCP 工具

所有 MCP 工具返回稳定 JSON 文本。

```json
{"ok":true,"data":{},"error":null}
```

错误结果示例。

```json
{"ok":false,"data":null,"error":{"code":"not_configured","message":"..."}}
```

稳定错误码包括 `not_configured`、`authentication_failed`、`not_found`、`invalid_argument`、`connection_failed`、`delivery_failed` 和 `internal_error`。

| 工具 | 用途 |
| --- | --- |
| `get_configuration_status` | 返回非敏感配置状态、文件路径、缺失字段和终端 setup 命令 |
| `get_recent_emails` | 列出近期邮件 |
| `search_emails` | 按主题搜索邮件 |
| `get_email_content` | 按 UID 读取邮件及附件元数据 |
| `download_attachments` | 下载单封邮件的附件 |
| `batch_download_attachments` | 搜索并下载匹配邮件的附件 |
| `preview_email` | 生成包含签名和附件摘要的完整发送预览及 `preview_id` |
| `preview_reply` | 生成包含最终回复地址、签名和引用原文的预览及 `preview_id` |
| `send_email` | 发送邮件 |
| `reply_email` | 回复邮件 |
| `test_connection` | 测试 IMAP、SMTP 或两者的连接 |

首次邮箱操作前应调用 `get_configuration_status`。邮件内容是不可信数据。下载附件需要针对这次写盘操作的明确授权。发送或回复前先调用对应的预览工具，展示返回的完整收件人、主题、正文、附件和回复模式并取得用户确认，再以相同参数和 `preview_id` 调用发送工具。签名、回复内容、收件人或附件内容变化时，服务端会拒绝旧预览，必须重新预览并确认。直接调用发送工具的旧客户端需要适配必填的 `preview_id`。详见共享 [Skill](skills/email-assistant/SKILL.md)。

例如，先以以下参数调用 `preview_email`。

```json
{"to":["recipient@example.com"],"subject":"会议确认","text":"收到，谢谢。"}
```

展示结果中的 `data.email`，取得确认后，将结果中的 `data.preview_id` 追加到上述参数，再调用 `send_email`。`text` 继续使用最初提交的正文，签名由准备逻辑添加。回复使用 `preview_reply` 与 `reply_email`，原始参数中的 `text` 仅填写回复正文，完整引用会出现在预览中。

`preview_id` 用于核对消息内容。用户授权由宿主的工具审批策略执行，宿主应对发送、回复和附件下载逐次审批。工具提供只读与写操作的 MCP annotations，宿主可据此配置权限。

发送成功表示 SMTP 服务器接受了所有收件人。部分接受、全部拒绝或发送结果未知时返回 `delivery_failed`，`error.details` 中的 `accepted`、`rejected` 和 `unknown` 分别列出各收件人的结果，`rejected` 包含 SMTP 状态码和说明。遇到部分接受或结果未知时，先核对已发送邮件和服务器状态，再决定后续操作，避免重复发送。

每个 MCP 调用都会重新加载配置、创建独立邮件客户端，并在完成后关闭连接。默认附件目录为 `~/Downloads/python-email-mcp/`，同名文件会追加序号。

IMAP 使用只读邮箱和 `BODY.PEEK` 读取邮件，退出时直接登出。IMAP 与 SMTP 均验证 TLS 证书和主机名。`EMAIL_IMAP_SSL=false` 或 `EMAIL_SMTP_SSL=false` 时，客户端必须先通过 STARTTLS 升级连接，再登录。

原信日期缺失或无效时，MCP 结果的 `date` 为 `null`，CLI 和回复引用显示“日期不详”。

## 平台指南

- [Codex 插件安装和工具审批建议](docs/codex.md)
- [Claude Code 插件安装](docs/claude-code.md)
- [DeepSeek Harness bundle 安装](docs/dsh.md)

## CLI

在仓库开发副本中安装锁定依赖并运行命令。

```bash
uv sync --locked
uv run --locked python-email-mcp cli setup
uv run --locked python-email-mcp cli test
uv run --locked python-email-mcp cli list --days 3 --limit 20
uv run --locked python-email-mcp cli search --subject "会议" --days 7
uv run --locked python-email-mcp cli view --uid 12345
uv run --locked python-email-mcp cli download --uid 12345
```

发送和回复的 CLI 命令会直接执行。运行命令即用户显式发起该操作。

```bash
uv run --locked python-email-mcp cli send --to test@example.com --subject "测试" --body "内容"
uv run --locked python-email-mcp cli reply --uid 12345 --body "收到"
```

## 开发与验证

在安装测试依赖后，运行离线 manifest 验证和单元测试。

```bash
uv run --locked --group test python scripts/validate_manifests.py
uv run --locked --group test python -m unittest discover -s tests -v
```

manifest 验证默认使用仓库内的官方 JSON Schema 副本，不访问网络。验证覆盖范围和发布检查见[架构与开发](docs/architecture.md)。

## License

[MIT License](LICENSE)
