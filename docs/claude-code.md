# Claude Code

仓库包含 Claude Code 插件清单和 MCP 启动配置。运行 Claude Code 本地 MCP server 的主机需要安装 `uv`。

## 从当前工作树安装

先按[安装指南](installation.md)中的“准备本地插件目录”步骤生成 `$staging`，并保持同一个 PowerShell 会话。验证 staging 目录中的插件，添加该目录作为本地 marketplace，然后安装插件。

```powershell
claude plugin validate "$staging"
claude plugin marketplace add "$staging"
claude plugin install python-email-mcp@fucose-plugins
```

运行 `claude plugin list` 检查插件是否启用。若当前会话尚未显示 Skill 或工具，重启会话或重新加载插件。

## 安装已发布版本

`v0.2.0` 于 2026-11-09 重新发布，可将 marketplace 固定到该 Git ref，再安装插件。已有旧版 tag 或插件快照时，先按[更新说明](installation.md#选择安装来源与更新)刷新安装来源。

```powershell
claude plugin marketplace add Fucose/python-email-mcp#v0.2.0
claude plugin install python-email-mcp@fucose-plugins
```

Claude Code 支持通过 `#ref` 将 GitHub marketplace 固定到分支或 tag。当前 CLI 命令和 marketplace 用法见 [Claude Code marketplace 文档](https://code.claude.com/docs/en/plugin-marketplaces) 与[插件安装文档](https://code.claude.com/docs/en/plugins/install)。

## 邮箱配置和工具授权

按[安装指南](installation.md)在 MCP server 所在主机配置邮箱。Claude Code 可能会给 MCP 工具名添加平台前缀。请按[共享 Skill](../skills/email-assistant/SKILL.md) 中的功能名称选择工具。

对 `download_attachments`、`batch_download_attachments`、`send_email` 和 `reply_email` 保留宿主工具审批，并完成共享 Skill 中针对本次操作的用户确认。更新后重新加载插件，确认工具目录包含 `preview_email` 和 `preview_reply`，发送和回复按共享工作流携带 `preview_id`。
