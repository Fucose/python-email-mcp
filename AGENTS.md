# 项目协作指南

## 范围与入口

本仓库为 Codex、Claude Code、DeepSeek Harness 和其他 stdio MCP 客户端提供同一套邮件核心。使用 Python 3.12 和锁定的 `uv` 依赖。

- `email_client/` 实现配置、模型、IMAP、SMTP 和出站邮件准备逻辑。
- `cli/main.py` 提供终端命令，`mcp_server/server.py` 提供结构化 MCP 工具，`main.py` 选择运行模式。
- 根目录 `plugin.json`、`mcp.json` 提供可移植插件，`.claude-plugin/` 与 `.mcp.json` 提供 Claude Code 适配。
- `integrations/dsh/` 注册同一 checkout 中的 MCP server 和共享 Skill。
- `skills/email-assistant/` 是各宿主共用的唯一邮件 Skill。

协议和消息准备逻辑放在 `email_client/`，各入口复用这些实现。修改公共契约时，核对 CLI、MCP 和共享 Skill 的调用链。

## 邮件安全与状态约束

- IMAP 和 SMTP 必须验证 TLS 证书及主机名。SSL 标志为 `false` 时，先完成 STARTTLS，再提交凭据。
- 查询使用只读 `INBOX` 和 `BODY.PEEK`。断开 IMAP 时使用 logout，避免引入清除已删除邮件的副作用。
- 发出 IMAP 命令前校验单个 UID，范围为 `1` 至 `4294967295`。Unicode 搜索词使用 UTF-8 literal，拒绝命令控制字符。
- 邮件、地址、主题、正文和附件名称均为外部数据。保留有效的邮件头折行处理，并校验新建邮件头。
- `PreparedEmail` 统一驱动预览与发送，保存最终收件人、正文、线程头和附件字节快照。摘要涵盖所有发送相关内容。
- MCP 发送和回复必须核对 `preview_id`。用户确认后继续使用原始参数，消息变化时重新预览和确认。
- 用户授权由宿主审批落实。附件下载、发送和回复保留针对本次操作的确认流程。CLI 的显式发送命令直接执行。
- 回复优先使用 `Reply-To`，处理回复全部的去重和自身地址排除，并维护 `In-Reply-To` 与 `References`。
- SMTP 成功表示服务器接受全部收件人。部分拒收或结果未知时保留逐收件人结果，避免自动重发造成重复邮件。
- 日期无法解析时，内部使用 `datetime.min`，MCP 输出 `null`，CLI 和回复引用显示“日期不详”。

## 配置与测试数据

用户配置保存在插件缓存外的用户目录，可由 `EMAIL_MCP_CONFIG_DIR` 指定。环境中的非空配置优先于配置文件。相对签名路径按配置目录解析，相对附件路径按 MCP 进程工作目录解析。

测试使用临时目录、模拟连接或本地测试服务器。真实邮箱访问、发送邮件和下载真实附件需要对应的用户授权。仓库中的示例配置使用占位值，凭据和私人签名留在外部用户配置中。

## 验证命令

安装开发与测试依赖。

```bash
uv sync --locked --group test
```

修改后按影响范围运行对应的 `unittest` 测试。文档或 Skill 改动核对相对链接、示例参数、平台安装步骤和发布状态。发布前运行完整测试、离线清单验证和差异检查。

```bash
uv run --locked --group test python -m unittest discover -s tests -v
uv run --locked --group test python scripts/validate_manifests.py
git diff --check
```

跨平台或邮箱行为的验证报告应区分单元测试、本地模拟服务器、宿主运行验证与真实邮箱联调。推送发布提交后核对 CI 结果。

## 文档与版本维护

README 介绍当前版本与公共调用流程。`docs/installation.md` 维护配置和更新步骤，平台指南维护各宿主适配，`docs/architecture.md` 维护内部边界和验证范围，`CHANGELOG.md` 记录版本变更。

版本调整时同步以下位置。

- `pyproject.toml` 和 `uv.lock` 中的项目版本。
- `email_client/__init__.py` 中的 `__version__`。
- `plugin.json`、`.claude-plugin/plugin.json` 和 `integrations/dsh/package.json`。
- README、Changelog、安装与平台指南中的版本和 tag 示例。

## 提交与发布

沿用用户和全局协作规则中的授权范围。主代理接受实际差异和验证结果后，将精确暂存与提交操作交给 `git_operator`。已有明确授权时继续完成对应操作。

发布 tag 使用 `v` 加项目版本。创建或更新 tag 后，在干净工作树中运行发布检查，并核对远端 tag 指向的提交。

```bash
uv run --locked --group test python scripts/validate_manifests.py --release-ref v0.2.0
```

发布说明记录接口变更和验证范围。用户明确要求移动已有 tag 时，核对旧目标并将远端更新限制到该 tag，发布完成后验证 Release 与目标提交一致。
