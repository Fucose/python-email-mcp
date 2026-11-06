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

`v0.2.0` 已发布，可将 marketplace 固定到该 Git ref，再安装插件。

```powershell
claude plugin marketplace add Fucose/python-email-mcp#v0.2.0
claude plugin install python-email-mcp@fucose-plugins
```

Claude Code 支持通过 `#ref` 将 GitHub marketplace 固定到分支或 tag。当前 CLI 命令和 marketplace 用法见 [Claude Code marketplace 文档](https://code.claude.com/docs/en/plugin-marketplaces) 与[插件安装文档](https://code.claude.com/docs/en/plugins/install)。

## 邮箱配置和工具授权

按[安装指南](installation.md)在 MCP server 所在主机配置邮箱。Claude Code 可能会给 MCP 工具名添加平台前缀。请按[共享 Skill](../skills/email-assistant/SKILL.md) 中的功能名称选择工具。

执行附件下载或发送邮件时，先检查 Claude Code 的工具审批提示。客户端提示和 Skill 的操作确认是两层要求。即使将客户端策略设置为允许调用，也必须保留文件写入、发送和回复前的用户确认。
