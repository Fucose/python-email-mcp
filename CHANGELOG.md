# Changelog

## 0.2.0 - Unreleased

- Package a portable Agent Plugin with Codex and Claude Code integrations while keeping one shared Python CLI and MCP server.
- Add a shared, platform-independent Email Assistant Skill and move host-specific installation and approval guidance into platform documentation.
- Add Windows, Linux, and WSL setup guidance and clarify per-host configuration and relative-path behavior.
- Add offline manifest validation and document local development and release checks.
- Add an MIT license.

## 0.1.0 - 2026-09-01

- Package the repository as a Git-distributed Codex Plugin with an Email Assistant Skill and bundled MCP server.
- Add Windows and WSL per-user configuration outside the plugin cache, with non-echoing CLI setup.
- Add locked `uv` runtime management on Python 3.12.
- Return stable structured MCP results and create a fresh email connection for every call.
- Add explicit confirmation guidance for downloads, sends, and replies, plus untrusted-email-content handling.
- Add cross-platform configuration, attachment, SMTP, MCP, Plugin, Skill, and stdio handshake tests.
