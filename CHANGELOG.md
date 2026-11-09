# Changelog

## 0.2.0 - 2026-11-09

- Package a portable Agent Plugin with Codex and Claude Code integrations and a DeepSeek Harness bundle, while keeping one shared Python CLI and MCP server.
- Add a shared, platform-independent Email Assistant Skill and move host-specific installation and approval guidance into platform documentation.
- Add Windows, Linux, and WSL setup guidance and clarify per-host configuration and relative-path behavior.
- Add offline manifest validation and document local development and release checks.
- Add an MIT license.
- Add repository-level `AGENTS.md` instructions for collaboration, implementation constraints, verification, and releases.
- Require verified TLS for IMAP and SMTP connections, including STARTTLS before authentication. IMAP selects `INBOX` read-only and uses `BODY.PEEK` when fetching messages.
- Add MCP `preview_email` and `preview_reply` tools. Sending or replying through MCP now requires the matching `preview_id`, computed from the prepared message and attachment content snapshots. This changes the MCP send and reply API.
- Prefer `Reply-To` when preparing replies and preserve `In-Reply-To` and `References` headers. Missing or invalid dates now have consistent internal and user-facing representations.
- Report SMTP delivery outcomes per recipient, including accepted, rejected, and unknown recipients. Validate IMAP UIDs and encode UTF-8 search terms as IMAP literals.
- Add UTF-8 mode to the generated terminal setup command for reliable Windows setup output.

The existing `v0.2.0` tag was created on 2026-11-06 and pointed to `fb9dc73`. This dated entry is for the first GitHub Release of `v0.2.0`.

## 0.1.0 - 2026-09-01

- Package the repository as a Git-distributed Codex Plugin with an Email Assistant Skill and bundled MCP server.
- Add Windows and WSL per-user configuration outside the plugin cache, with non-echoing CLI setup.
- Add locked `uv` runtime management on Python 3.12.
- Return stable structured MCP results and create a fresh email connection for every call.
- Add explicit confirmation guidance for downloads, sends, and replies, plus untrusted-email-content handling.
- Add cross-platform configuration, attachment, SMTP, MCP, Plugin, Skill, and stdio handshake tests.
