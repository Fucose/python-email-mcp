# Codex

仓库使用 Agent Plugins 1.0 可移植组件。Codex 从根目录读取插件清单、MCP server 配置和共享 Skill。运行本地 MCP server 的主机需要安装 `uv`。

## 预览当前工作树

先按[安装指南](installation.md)中的“准备本地插件目录”步骤生成 `$staging`。不要将原始工作树直接注册为本地 marketplace。

```powershell
codex plugin marketplace add "$staging" --json
codex plugin add python-email-mcp@fucose-plugins --json
```

## 安装已发布版本

`v0.2.0` 已发布，可从该 Git ref 安装 marketplace。

```powershell
codex plugin marketplace add Fucose/python-email-mcp --ref v0.2.0
codex plugin add python-email-mcp@fucose-plugins
```

## 邮箱配置与 MCP

首次邮箱操作前调用 `get_configuration_status`。若配置缺失，请在运行 Codex MCP server 的主机终端执行结果中的完整 `setup_command`。该命令调用当前 MCP server 进程的 Python 解释器和已安装包中 `main.py` 的绝对路径，不依赖另一个 Git tag。详细路径见[安装指南](installation.md)。

根目录 `mcp.json` 注册名为 `python-email` 的 server。使用插件时不要再将同一 server 手动添加到 Codex 配置。功能名称及流程见[共享工作流](../skills/email-assistant/references/workflows.md)。

## 工具审批建议

以下 Codex 设置允许只读工具，并让文件写入和外发邮件在每次调用时提示确认。

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

保留 `download_attachments`、`batch_download_attachments`、`send_email` 和 `reply_email` 的 `prompt` 策略。Codex 审批提示不替代共享 Skill 要求的明确用户授权。Codex 插件打包和组件发现规则见 [OpenAI 插件文档](https://developers.openai.com/plugins/build/plugins)。
