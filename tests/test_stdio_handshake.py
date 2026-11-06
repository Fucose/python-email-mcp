import asyncio
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ModuleNotFoundError as exc:
    if exc.name == "mcp":
        ClientSession = None
        StdioServerParameters = None
        stdio_client = None
    else:
        raise


EXPECTED_TOOLS = {
    "get_configuration_status",
    "get_recent_emails",
    "search_emails",
    "get_email_content",
    "download_attachments",
    "batch_download_attachments",
    "send_email",
    "reply_email",
    "test_connection",
}
UV = shutil.which("uv")


@unittest.skipIf(
    ClientSession is None,
    "mcp must be installed in this interpreter",
)
@unittest.skipIf(UV is None, "uv must be on PATH to exercise plugin launch configurations")
class StdioHandshakeTests(unittest.IsolatedAsyncioTestCase):
    async def _handshake(self, command, args, cwd, environment):
        parameters = StdioServerParameters(
            command=command,
            args=args,
            env=environment,
            cwd=str(cwd),
        )
        async with asyncio.timeout(90):
            async with stdio_client(parameters) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    result = await session.call_tool("get_configuration_status", {})

        self.assertEqual({tool.name for tool in listed.tools}, EXPECTED_TOOLS)
        payload = json.loads(result.content[0].text)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["data"]["configured"])
        self.assertNotIn("EMAIL_PASSWORD=", result.content[0].text)

    @staticmethod
    def _safe_environment(config_dir: Path) -> dict[str, str]:
        environment = os.environ.copy()
        for key in tuple(environment):
            if key.startswith(("EMAIL_", "IMAP_", "SMTP_")) or key in {
                "UV_NO_SYNC",
                "UV_PROJECT_ENVIRONMENT",
            }:
                environment.pop(key)
        environment["EMAIL_MCP_CONFIG_DIR"] = str(config_dir)
        return environment

    @staticmethod
    def _expand(value: str, substitutions: dict[str, str]) -> str:
        for variable, replacement in substitutions.items():
            value = value.replace("${" + variable + "}", replacement)
        return value

    async def test_native_plugin_launch_descriptions_handshake_from_external_cwd(self):
        repo_root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory(prefix="python email plugin 测试 ") as temporary:
            temp_root = Path(temporary)
            unrelated_cwd = temp_root / "unrelated 工作目录 with spaces"
            unrelated_cwd.mkdir()
            config_root = temp_root / "external user config"
            config_root.mkdir()
            data_root = temp_root / "plugin runtime data"
            data_root.mkdir()

            # Agent Plugins and Claude expand their respective root and data variables
            # before launching the MCP process.
            for label, config_path, root_variable, data_variable in (
                ("portable", repo_root / "mcp.json", "PLUGIN_ROOT", "PLUGIN_DATA"),
                ("claude", repo_root / ".mcp.json", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DATA"),
            ):
                with self.subTest(adapter=label):
                    document = json.loads(config_path.read_text(encoding="utf-8"))
                    server = document["mcpServers"]["python-email"]
                    substitutions = {
                        root_variable: str(repo_root),
                        data_variable: str(data_root),
                    }
                    args = [self._expand(argument, substitutions) for argument in server["args"]]
                    environment = self._safe_environment(config_root / label)
                    environment.update(
                        {
                            name: self._expand(value, substitutions)
                            for name, value in server.get("env", {}).items()
                        }
                    )
                    expected_runtime = data_root / "venv"
                    self.assertEqual(
                        Path(environment["UV_PROJECT_ENVIRONMENT"]), expected_runtime
                    )
                    await self._handshake(UV, args, unrelated_cwd, environment)
                    self.assertTrue(expected_runtime.is_dir())


if __name__ == "__main__":
    unittest.main()
