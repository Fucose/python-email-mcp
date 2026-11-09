# Configuration and setup

## Start with status

Call `get_configuration_status` before the first mailbox action. If the result lists missing fields, relay its exact `config_file`, `missing_fields`, and `setup_command`. The status call does not reveal the password or authorization code.

Run setup in a terminal on the same host that runs the MCP server. The interactive setup reads the password or authorization code without echoing it. Do not ask the user to paste it into chat. After setup, call `get_configuration_status` again and then retry the requested mailbox action.

The returned command uses the running server's Python interpreter, `-X utf8`, and its installed `main.py` absolute path. If that installation path is unavailable, use the installation instructions for the same host to repair the installation, then request configuration status again.

## Separate hosts have separate configuration

Windows, WSL, Linux, and another remote host keep their own runtime and per-user configuration. Configure each host on which the MCP server will run. Installing or updating the package does not copy mailbox credentials between hosts.

## Paths and precedence

Configuration is stored outside the installed plugin and its cache by default.

- **Windows** uses `%APPDATA%\python-email-mcp\config.env`.
- **Linux and WSL** use `${XDG_CONFIG_HOME:-~/.config}/python-email-mcp/config.env`.
- **Downloads** go to `~/Downloads/python-email-mcp/` by default.

Set `EMAIL_MCP_CONFIG_DIR` to use another configuration directory. Non-empty environment variables override values from `config.env`. `EMAIL_SIGNATURE_FILE` may name an absolute path or a path relative to the configuration directory. Its default is `signature.txt` beside `config.env`.

The supported keys are `EMAIL_USER`, `EMAIL_PASSWORD`, `EMAIL_IMAP_HOST`, `EMAIL_IMAP_PORT`, `EMAIL_IMAP_SSL`, `EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT`, `EMAIL_SMTP_SSL`, and `EMAIL_SIGNATURE_FILE`. Keep actual credentials and signatures private and outside version control.

## TLS settings

Both IMAP and SMTP verify the server certificate and hostname. Setting the corresponding `*_SSL` key to `true` uses implicit TLS. Setting it to `false` requires a verified STARTTLS upgrade before login. Use the server's documented port for the chosen mode. Failed TLS negotiation or certificate validation returns `connection_failed`.
