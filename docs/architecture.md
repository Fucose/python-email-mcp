# 架构与开发

CLI 和 stdio MCP server 共用一套 Python 实现。Codex、Claude Code 和 DeepSeek Harness 使用各自的插件清单或 bundle 连接相同的 MCP server，并加载同一份 `email-assistant` Skill。

## 文件布局

| 路径 | 用途 |
| --- | --- |
| `plugin.json` | Agent Plugins 1.0 可移植清单和 OpenAI 界面扩展 |
| `mcp.json` | 可移植的本地 MCP server 启动配置 |
| `skills/email-assistant/` | 平台无关的邮件工作流和安全规则 |
| `.agents/plugins/marketplace.json` | Codex marketplace，插件 source 指向同一目录快照 |
| `.claude-plugin/plugin.json` | Claude Code 插件元数据 |
| `.claude-plugin/marketplace.json` | Claude Code marketplace 项目 |
| `.mcp.json` | Claude Code 插件的本地 MCP server 配置 |
| `integrations/dsh/` | DeepSeek Harness bundle：MCP client 与共享 Skill provider |
| `cli/`、`email_client/`、`mcp_server/` | 共用 CLI、邮件客户端、配置逻辑和 MCP server |

## MCP 配置分发

| 客户端 | 读取的插件和 MCP 配置 | 行为 |
| --- | --- | --- |
| Agent Plugins 1.0 与 Codex | 根目录 `plugin.json` 和 `mcp.json` | 从根目录可移植清单发现共享 Skill 和 `python-email` server |
| Claude Code | `.claude-plugin/plugin.json` 和 `.mcp.json` | 从原生 Claude Code 清单读取本地 MCP server，并加载根目录共享 Skill |
| DeepSeek Harness | `integrations/dsh/cordis.patch.yml` | 由 bundle 注册 `python-email` stdio server 和共享 Skill provider |

两个清单注册的 MCP server 名均为 `python-email`。客户端按其原生插件格式选择对应的一份配置，无需再手动添加同一 server。

隔离环境中的 Codex CLI `0.166.0-alpha.6` 插件读取检查报告一个 MCP server 和一份共享 Skill，并观察到根目录可移植清单提供组件。该行为也符合 [OpenAI Agent Plugin 打包文档](https://developers.openai.com/plugins/build/plugins) 中关于可移植清单的说明。

## 运行与配置边界

每次 MCP 工具调用都会重新加载用户配置、创建独立邮件客户端、执行一次操作并关闭连接。邮箱配置保存在插件目录之外。`get_configuration_status` 只读，不返回密码或授权码。

插件清单只保存启动路径和运行选项，不保存邮箱秘密。运行环境支持可写插件数据目录时，可用它管理 Python 虚拟环境。邮箱配置仍放在用户配置目录或受保护的进程环境中。

`uv --project` 用于选择项目和锁定依赖，不改变进程当前目录。相对附件路径和下载路径会按 MCP 主机设置的进程目录解析，因此优先使用绝对路径。

## 本地验证

安装锁定的测试依赖后，运行离线清单验证和单元测试。

```powershell
uv run --locked --group test python scripts/validate_manifests.py
uv run --locked --group test python -m unittest discover -s tests -v
```

清单验证默认使用 `scripts/schemas/` 中的官方 JSON Schema 副本。Claude Code 未安装在开发环境中，因此没有声明其实际运行时已通过验证。DeepSeek Harness bundle 已在 WSL 上的 Harness 中安装并验证：工具通过 `mcp__python-email__*` 注册，共享 Skill 由本仓库的 `skills/` 提供，`get_configuration_status` 与 `test_connection` 均成功。离线清单验证和单元测试不连接真实邮箱。

## 版本维护与发布检查

当前版本为 `0.2.0`。发布新版本时，同步 `pyproject.toml`、根插件清单、Claude Code 清单、DeepSeek Harness bundle 清单和锁文件中的版本。Codex marketplace 从本地预览目录读取同一份插件快照。发布后从对应 Git tag 添加 marketplace。

完成本地验证并确认发布已获授权后，创建 tag 并运行以下检查。

```powershell
uv run --locked --group test python scripts/validate_manifests.py --release-ref v0.2.0
```

`--release-ref` 检查目标 tag 是否存在、是否指向 `HEAD`，以及工作树是否干净。检查通过本身不代表发布已获授权。
