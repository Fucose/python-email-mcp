import json
import unittest
from pathlib import Path


class PluginFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parent.parent

    def test_manifest_and_project_versions_match(self):
        manifest = json.loads(
            (self.root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        pyproject = (self.root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertEqual(manifest["version"], "0.1.0")
        self.assertIn('version = "0.1.0"', pyproject)

    def test_bundled_mcp_uses_locked_uv_from_plugin_root(self):
        manifest = json.loads((self.root / ".mcp.json").read_text(encoding="utf-8"))
        server = manifest["mcpServers"]["python-email"]
        self.assertEqual(server["command"], "uv")
        self.assertEqual(server["args"], ["run", "--locked", "python-email-mcp", "mcp"])
        self.assertEqual(server["cwd"], ".")

    def test_repo_marketplace_pins_the_release_tag(self):
        marketplace = json.loads(
            (self.root / ".agents" / "plugins" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(marketplace["name"], "fucose-plugins")
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], "python-email-mcp")
        self.assertEqual(entry["source"]["source"], "url")
        self.assertEqual(entry["source"]["ref"], "v0.1.0")

    def test_skill_contains_trust_and_confirmation_rules(self):
        skill = (self.root / "skills" / "email-assistant" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("untrusted data", skill)
        self.assertIn("explicit confirmation", skill)
        self.assertIn("Never ask them to paste an authorization code", skill)
        self.assertIn("default_tools_approval_mode = \"prompt\"", skill)


if __name__ == "__main__":
    unittest.main()
