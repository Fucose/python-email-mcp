# DeepSeek Harness bundle

This directory is a DeepSeek Harness bundle for the repository's MCP server and
shared Skill. It is not a copy of the plugin: it only adds Harness rows that
launch the checkout's `python-email-mcp` stdio server and expose
`skills/email-assistant/` to the agent.

## What it registers

| Row | Plugin | Purpose |
| --- | --- | --- |
| `python-email-mcp` | `@deepseek-ai/dsh-mcp-client` | stdio MCP server named `python-email`, tools exposed as `mcp__python-email__*` |
| `python-email-mcp-skills` | `@deepseek-ai/dsh-skill-filesystem` | Skill provider for the repository's `skills/` directory |

The MCP row sets `failOnStartupError: true` and a 120-second tool timeout. The
Skill row sets `includeDefaultRoots: false`, so it contributes only the
repository Skill and does not re-scan user Skill directories.

## Install

Install the bundle with the Harness plugin manager, pointing at this directory:

```text
plugin_manager install_bundle target = /path/to/python-email-mcp/integrations/dsh
```

The plugin manager links the directory into the profile and loads
`cordis.patch.yml`. Restart the Harness, or reload the plugin row, to apply
changes to the patch.

## Checkout path

The patch resolves the checkout path when it loads, in this order:

1. `PYTHON_EMAIL_MCP_ROOT` from the Harness environment, when set
2. `$HOME/projects/python-email-mcp`
3. `%USERPROFILE%/projects/python-email-mcp` when `HOME` is unset

Set `PYTHON_EMAIL_MCP_ROOT` before starting the Harness when the checkout lives
elsewhere. The environment variable is read by the patch, not by the MCP server,
so it is not affected by the MCP client's environment scrubbing.

## Requirements

- `uv` on the Harness host's `PATH`
- Python 3.12; `uv` installs and pins it from `.python-version`
- `uv sync --locked` run once in the checkout, or network access for the first
  launch

## Verify

1. `get_configuration_status` returns `configured: true` and no missing fields.
2. `test_connection` succeeds for IMAP and SMTP.
3. The Skill catalog lists `email-assistant` from this repository.

Mailbox configuration lives outside the checkout. See
[installation.md](../../docs/installation.md) and [dsh.md](../../docs/dsh.md).
