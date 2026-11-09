# DeepSeek Harness

`integrations/dsh/` 是一个 DeepSeek Harness（DSH）bundle。它不复制插件代码，只向 Harness 注册两行配置：

| 行 ID | 插件 | 作用 |
| --- | --- | --- |
| `python-email-mcp` | `@deepseek-ai/dsh-mcp-client` | 以 stdio 启动本 checkout 的 MCP server，server 名为 `python-email` |
| `python-email-mcp-skills` | `@deepseek-ai/dsh-skill-filesystem` | 把仓库的 `skills/` 目录提供给 Skill 目录 |

工具在 Harness 中以 `mcp__python-email__*` 出现，Skill 以 `email-assistant` 出现。

## 安装

用 Harness 的插件管理器安装该目录，`target` 指向 checkout 中的 `integrations/dsh`：

```text
plugin_manager install_bundle target = /path/to/python-email-mcp/integrations/dsh
```

安装完成后，插件管理器和设置页会按 `locale/en.json`、`locale/zh.json` 与 `icon.svg` 显示标题、描述和图标。修改 `cordis.patch.yml` 后需要重启 Harness，或重新加载该行，补丁才会生效。

Harness 从安装目录建立链接，更新 checkout 后会使用其中的 Python 代码与 Skill。更新后重启 Harness，或重新加载 MCP 与 Skill provider，让进程和工具目录读取新内容。若 `package.json` 或补丁本身变化，重新安装 bundle。

## checkout 路径

补丁在**加载时**解析 checkout 路径，顺序为：

1. 环境变量 `PYTHON_EMAIL_MCP_ROOT`
2. `$HOME/projects/python-email-mcp`
3. `HOME` 未设置时使用 `%USERPROFILE%/projects/python-email-mcp`

checkout 不在默认位置时，在启动 Harness 之前设置 `PYTHON_EMAIL_MCP_ROOT`。该变量由补丁读取，不经过 MCP client 的子进程环境清洗，因此不会被丢弃。

## 启动契约

MCP 行以 `uv run --project <checkout> --locked python-email-mcp mcp` 启动，并把 `cwd` 设为 checkout 根目录。`--project` 只选择 Python 项目，不改变相对路径的含义；`cwd` 让相对路径有确定基准。附件与下载目标仍建议使用绝对路径。

该行还设置：

- `failOnStartupError: true`：server 启动失败时在插件激活阶段直接报错，而不是静默地不注册工具
- `toolCallTimeoutMs: 120000`：为慢速邮箱的搜索与附件下载留出余量

Skill 行设置 `includeDefaultRoots: false`，只提供仓库中的 `skills/`，不会重复扫描用户级 Skill 目录。

## 邮箱配置

配置保存在 checkout 之外，Harness 主机需要先完成一次 setup：

```bash
cd /path/to/python-email-mcp
uv run --locked python-email-mcp cli setup
uv run --locked python-email-mcp cli test
```

Windows 与 WSL 是两个独立主机，各自需要 `uv`、setup 和插件安装。详见[安装指南](installation.md)。

## 验证

1. 调用 `get_configuration_status`，确认 `configured: true` 且没有缺失字段。
2. 调用 `test_connection`，确认 IMAP 与 SMTP 都成功。
3. 在 Skill 目录中确认 `email-assistant` 来自本仓库。
4. 确认工具目录包含 `preview_email` 和 `preview_reply`，发送和回复的参数包含必填 `preview_id`。

对 `download_attachments`、`batch_download_attachments`、`send_email` 和 `reply_email` 保留 Harness 的工具审批，并完成共享 [Skill](../skills/email-assistant/SKILL.md) 要求的明确确认。

## 手动合并

不使用插件管理器时，可以把 `integrations/dsh/cordis.patch.yml` 中的两行 `insert` 合并进 profile 的 `cordis.patch.yml`。保留 `!!js` 表达式，否则 checkout 路径会被写死；`python-email-mcp` 这个 id 不要与既有行重复，重复 id 会整行替换。

## 卸载

移除 `@fucose/dsh-python-email-mcp` bundle 即可；checkout、`~/.config/python-email-mcp/` 和 Python 虚拟环境都可独立保留或删除。
