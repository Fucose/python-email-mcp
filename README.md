# Python Email MCP

Python 邮件 MCP 服务器，支持多种邮箱系统，提供 MCP 服务器和命令行工具两种使用模式。

## 功能特性

- 📧 **邮件接收**：获取邮件列表、按主题搜索、查看详情
- 📎 **附件处理**：下载单个或批量下载附件
- ✉️ **邮件发送**：发送新邮件、回复邮件（支持附件、抄送、密送）
- ⚙️ **配置管理**：自动配置、手动配置、连接测试

## 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
# 推荐使用 uv（快速）
uv venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows
uv pip install -r requirements.txt

# 或使用标准方式
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows
pip install -r requirements.txt
```

### 2. 配置邮箱

**方式选择：**
- **MCP 模式**：在项目根目录创建 `.mcp.json` 文件并配置环境变量，无需 `.env` 文件
- **CLI 模式**：运行 `python main.py cli setup` 交互式配置

### 3. 测试连接

```bash
# 确保虚拟环境已激活
python main.py cli test
```

## 使用方式

### MCP 服务器模式

在 Claude Code 项目中使用 MCP 服务器（**推荐**）：

**步骤 1：在项目根目录创建 `.mcp.json` 文件**
```bash
# 在您的 Claude 工作项目根目录下创建
touch .mcp.json
```

**步骤 2：添加以下配置到 `.mcp.json`**
```json
{
  "mcpServers": {
    "py_email": {
      "command": "/path/to/python-email-mcp/.venv/bin/python",
      "args": ["/path/to/python-email-mcp/main.py", "mcp"],
      "env": {
        "EMAIL_USER": "your@email.com",
        "EMAIL_PASSWORD": "your_password_or_app_password",
        "EMAIL_IMAP_HOST": "imap.example.com",
        "EMAIL_IMAP_PORT": "993",
        "EMAIL_IMAP_SSL": "true",
        "EMAIL_SMTP_HOST": "smtp.example.com",
        "EMAIL_SMTP_PORT": "465",
        "EMAIL_SMTP_SSL": "true"
      }
    }
  }
}
```

**配置说明：**
- `command`：如果使用虚拟环境，指向 `.venv/bin/python`（Linux/Mac）或 `.venv\Scripts\python.exe`（Windows）；如果未使用虚拟环境，使用 `python`
- 将 `/path/to/python-email-mcp` 替换为实际的项目路径
- 配置完成后重启 Claude Code 使其生效

**在 Claude Code 中使用：**
- 查看最近邮件：`获取最近3天的邮件`
- 搜索邮件：`搜索主题包含"会议"的邮件`
- 下载附件：`下载邮件 UID 为 xxx 的附件`
- 发送邮件：`发送邮件给 xxx，主题是 xxx`

### 命令行工具模式

```bash
# 列出最近邮件
python main.py cli list --days 3 --limit 20

# 搜索邮件
python main.py cli search --subject "会议通知" --days 7

# 查看邮件详情
python main.py cli view --uid 1441524521

# 下载附件
python main.py cli download --uid 1441524521 --folder downloads

# 批量下载附件
python main.py cli batch-download --subject "会议通知" --days 3 --folder downloads

# 发送邮件
python main.py cli send \
  --to "test@example.com" \
  --subject "测试邮件" \
  --body "邮件内容" \
  --attach "file.pdf"

# 回复邮件
python main.py cli reply --uid 1441524521 --body "好的，收到" --reply-all
```

## 配置说明

### 环境变量

**配置优先级：** 环境变量 > .env 文件

**MCP 模式：** 在项目根目录的 `.mcp.json` 文件中配置
**CLI 模式：** 在 `.env` 文件中配置或运行 `python main.py cli setup`

**必需配置：**
```bash
EMAIL_USER=your@email.com
EMAIL_PASSWORD=your_password_or_app_password
```

**可选配置（常见邮箱默认值）：**
```bash
# IMAP 配置
EMAIL_IMAP_HOST=imap.example.com
EMAIL_IMAP_PORT=993

# SMTP 配置
EMAIL_SMTP_HOST=smtp.example.com
EMAIL_SMTP_PORT=465

# 邮件签名（可选）
EMAIL_SIGNATURE_FILE=signature.txt
```

**常见邮箱服务器：**
- **Gmail**: `imap.gmail.com:993`, `smtp.gmail.com:465`（需应用专用密码）
- **QQ 邮箱**: `imap.qq.com:993`, `smtp.qq.com:465`（需授权码）
- **163 邮箱**: `imap.163.com:993`, `smtp.163.com:465`（需授权码）
- **Outlook**: `outlook.office365.com:993`, `smtp-mail.outlook.com:587`

### 邮件签名

创建 `signature.txt` 文件（可选）：
```
您的姓名
职位
公司/组织
Email: your@email.com
```

## 项目结构

```
python-email-mcp/
├── email_client/          # 核心邮件客户端库
│   ├── client.py          # 核心客户端
│   ├── config.py          # 配置管理
│   ├── imap_client.py     # IMAP 操作
│   ├── smtp_client.py     # SMTP 操作
│   └── models.py          # 数据模型
├── mcp_server/           # MCP 服务器
├── cli/                  # 命令行工具
├── main.py               # 主入口
└── requirements.txt      # Python 依赖
```

## 注意事项

1. **授权码**：Gmail、QQ、163 等邮箱需使用授权码而非登录密码
2. **IMAP/SMTP 服务**：确保邮箱已开启 IMAP/SMTP 服务
3. **网络连接**：确保能访问邮箱服务器
4. **UID 稳定性**：使用 IMAP 原始 UID，删除其他邮件不会影响现有 UID

## 故障排除

**连接失败：**
- 检查网络连接和邮箱配置
- 确认使用授权码而非登录密码
- 检查 IMAP/SMTP 服务是否已开启

**认证失败：**
- 确认使用授权码而非登录密码
- 重新生成授权码
- 检查邮箱地址是否正确

**找不到邮件：**
- 检查搜索关键词和搜索天数
- 确认邮件在收件箱中

## 许可证

MIT License
