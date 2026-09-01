import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ModuleNotFoundError as exc:
    if exc.name == "mcp":
        ClientSession = None
    else:
        raise


@unittest.skipIf(ClientSession is None, "mcp dependency is not installed in this interpreter")
class StdioHandshakeTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_list_tools_and_configuration_status(self):
        repo_root = Path(__file__).resolve().parent.parent
        test_deps = repo_root / ".codex-test-deps"
        bootstrap_parts = ["import sys"]
        if test_deps.is_dir():
            bootstrap_parts.extend(
                ["import site", f"site.addsitedir({str(test_deps)!r})"]
            )
        bootstrap_parts.extend(
            [
                "sys.argv = ['main.py', 'mcp']",
                "import main",
                "main.main()",
            ]
        )
        bootstrap = "; ".join(bootstrap_parts)

        with tempfile.TemporaryDirectory() as config_dir:
            environment = os.environ.copy()
            environment["EMAIL_MCP_CONFIG_DIR"] = config_dir
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-X", "utf8", "-c", bootstrap],
                env=environment,
                cwd=str(repo_root),
            )
            async with stdio_client(parameters) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    result = await session.call_tool("get_configuration_status", {})

        names = {tool.name for tool in listed.tools}
        self.assertEqual(len(names), 9)
        self.assertNotIn("setup_email_account", names)
        self.assertIn("get_configuration_status", names)
        payload = json.loads(result.content[0].text)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["data"]["configured"])
        self.assertNotIn("EMAIL_PASSWORD=", result.content[0].text)


if __name__ == "__main__":
    unittest.main()
