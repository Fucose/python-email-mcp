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
| `AGENTS.md` | 仓库协作方式、实现约束、验证要求和发布流程 |
| `cli/`、`email_client/`、`mcp_server/` | 共用 CLI、邮件客户端、配置逻辑和 MCP server |

## MCP 配置分发

| 客户端 | 读取的插件和 MCP 配置 | 行为 |
| --- | --- | --- |
| Agent Plugins 1.0 与 Codex | 根目录 `plugin.json` 和 `mcp.json` | 从根目录可移植清单发现共享 Skill 和 `python-email` server |
| Claude Code | `.claude-plugin/plugin.json` 和 `.mcp.json` | 从原生 Claude Code 清单读取本地 MCP server，并加载根目录共享 Skill |
| DeepSeek Harness | `integrations/dsh/cordis.patch.yml` | 由 bundle 注册 `python-email` stdio server 和共享 Skill provider |

两个清单注册的 MCP server 名均为 `python-email`。客户端按其原生插件格式选择对应的一份配置，无需再手动添加同一 server。

此前的隔离环境检查记录了 Codex CLI `0.166.0-alpha.6` 插件读取一个 MCP server 和一份共享 Skill，并观察到根目录可移植清单提供组件。此前也曾在 WSL 上验证 DeepSeek Harness 的工具注册和共享 Skill 加载。这些是既有的宿主集成验证记录。Codex 的检查结果也符合 [OpenAI Agent Plugin 打包文档](https://developers.openai.com/plugins/build/plugins) 中关于可移植清单的说明。

## 运行与配置边界

每个邮件操作的 MCP 调用都会重新加载用户配置、创建独立邮件客户端、执行操作并在结束时关闭已打开的连接。邮件客户端按需创建 IMAP 或 SMTP 客户端，且只在实际执行协议操作时建立网络连接。`get_configuration_status` 读取配置状态并返回非敏感信息，不会建立协议连接，也不返回密码或授权码。

插件清单只保存启动路径和运行选项，不保存邮箱秘密。运行环境支持可写插件数据目录时，可用它管理 Python 虚拟环境。邮箱配置仍放在用户配置目录或受保护的进程环境中。

`uv --project` 用于选择项目和锁定依赖，不改变进程当前目录。相对附件路径和下载路径会按 MCP 主机设置的进程目录解析，因此优先使用绝对路径。

`get_configuration_status` 返回的 `setup_command` 使用当前 Python 解释器、安装中的 `main.py` 绝对路径和 `-X utf8` 选项，以便 Windows 终端配置流程使用 UTF-8。源码 checkout 也可以使用 README 中的 `uv` 命令运行配置流程。

## 邮件连接与读取

IMAP 和 SMTP 默认使用经过证书校验的隐式 TLS。关闭隐式 TLS 时，客户端仍要求先完成并验证 STARTTLS，再提交登录凭据。IMAP 只选择只读的 `INBOX`，读取邮件正文和邮件头时使用 `BODY.PEEK`，退出时执行 logout。IMAP UID 会在发送到服务器前按正十进制数和协议范围校验。主题搜索将 UTF-8 搜索词作为 IMAP literal 发送，避免把搜索词当作协议命令的一部分。

邮件头缺少有效日期时，内部 `Email.date` 使用 `datetime.min` 哨兵值。MCP 邮件摘要把日期序列化为 `null`，CLI 和回复引用文本显示“日期不详”。

## 出站邮件和 MCP 预览

出站邮件先准备为不可变的 `PreparedEmail`。准备过程校验邮件头和收件人，并将附件字节读入快照。预览包含收件人、正文、附件路径、大小和 SHA-256。`preview_id` 是发件人、收件人、主题、正文、附件快照及回复线程头等发送相关值的确定性 SHA-256 摘要。

MCP 的 `preview_email` 在本地准备邮件和附件快照。`preview_reply` 通过 IMAP 读取原邮件后准备回复。调用 `send_email` 或 `reply_email` 必须携带对应预览返回的 `preview_id`，并重复相同参数。服务器重新准备邮件并比较摘要，内容或附件变化时拒绝发送并要求重新预览。SMTP 连接在发送或回复时按需建立。CLI 的 `send` 和 `reply` 命令直接准备并发送邮件。

回复优先发送到原邮件的 `Reply-To`，缺少该字段时使用 `From`。`reply_all` 会去重并排除自己的地址。回复保留 `In-Reply-To` 和 `References` 线程头。

SMTP 成功时表示所有收件人均被服务器接受。部分或全部拒收以及无法确认结果时，`DeliveryError.details` 提供 `status`、`accepted`、`rejected` 和 `unknown` 字段。`status` 用 `partial`、`rejected` 或 `unknown` 描述失败结果。传输中断导致接受状态无法确定时，相关收件人会列在 `unknown` 中。

## 本地验证

安装锁定的测试依赖后，运行离线清单验证和单元测试。

```powershell
uv run --locked --group test python scripts/validate_manifests.py
uv run --locked --group test python -m unittest discover -s tests -v
```

清单验证默认使用 `scripts/schemas/` 中的官方 JSON Schema 副本。

| 验证范围 | 结果 |
| --- | --- |
| Linux 本地单元测试 | 85 项通过，另有离线清单验证 |
| 本地协议检查 | 真实 `imaplib` socketpair UTF-8 literal；IMAP 隐式 TLS、SMTP 隐式 TLS 和 SMTP STARTTLS 均拒绝自签证书 |
| GitHub Actions | 对代码提交 `a01b334` 的 run `42506694684` 通过 Linux 和 Windows 矩阵 |
| 待验收 | Windows 原生宿主集成、真实邮箱联调、Claude Code 运行时及当前 MCP API 的 DeepSeek Harness 重验 |

此前 DeepSeek Harness 的工具注册和共享 Skill 验证是早期集成记录。

## 版本维护与发布检查

本次版本为 `0.2.0`。包、插件清单和 `email_client.__version__` 使用同一版本号。现有 `v0.2.0` tag 创建于 2026-11-06，原目标为 `fb9dc73`。本次发行日期为 2026-11-09。发布时将该 tag 更新到通过验证的 `HEAD`，并在 GitHub 创建首个 `v0.2.0` Release。之后发布新版本时，同步 `pyproject.toml`、`email_client.__version__`、根插件清单、Claude Code 清单、DeepSeek Harness bundle 清单和锁文件中的版本。Codex marketplace 从本地预览目录读取同一份插件快照。发布后从对应 Git tag 添加 marketplace。

完成本地验证后，将 tag 指向本次 `HEAD` 并运行以下检查。

```powershell
uv run --locked --group test python scripts/validate_manifests.py --release-ref v0.2.0
```

`--release-ref` 检查目标 tag 是否存在、是否指向 `HEAD`，以及工作树是否干净。
