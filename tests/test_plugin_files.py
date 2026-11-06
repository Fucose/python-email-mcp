import importlib.util
import json
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path


class PluginFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parent.parent
        validator_path = cls.root / "scripts" / "validate_manifests.py"
        spec = importlib.util.spec_from_file_location("validate_manifests_test", validator_path)
        cls.validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.validator)

    def _copy_validation_fixture(self, destination: Path) -> Path:
        """Copy only public packaging files needed by validate()."""
        files = (
            "plugin.json",
            "mcp.json",
            ".mcp.json",
            "pyproject.toml",
            "uv.lock",
        )
        directories = (
            ".agents",
            ".claude-plugin",
            "scripts",
            "skills",
        )
        for filename in files:
            shutil.copy2(self.root / filename, destination / filename)
        for directory in directories:
            shutil.copytree(self.root / directory, destination / directory)
        return destination

    def _mutated_root(self, mutate):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = self._copy_validation_fixture(Path(temporary.name))
        mutate(root)
        return root

    @staticmethod
    def _write_json(path: Path, document: dict) -> None:
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    def test_manifests_schemas_paths_and_release_metadata_validate(self):
        self.validator.validate(root=self.root)

        project = tomllib.loads((self.root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        for relative in ("plugin.json", ".claude-plugin/plugin.json"):
            with self.subTest(manifest=relative):
                manifest = json.loads((self.root / relative).read_text(encoding="utf-8"))
                self.assertEqual(manifest["name"], project["name"])
                self.assertEqual(manifest["version"], project["version"])

        marketplace = json.loads(
            (self.root / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
        )
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], project["name"])
        self.assertEqual(entry["source"], {"source": "local", "path": "./"})

    def test_marketplace_cannot_reference_an_unpublished_release_tag(self):
        def mutate(root):
            path = root / ".agents" / "plugins" / "marketplace.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            document["plugins"][0]["source"] = {
                "source": "url",
                "url": "https://github.com/Fucose/python-email-mcp.git",
                "ref": "v999.0.0",
            }
            self._write_json(path, document)

        with self.assertRaises(ValueError):
            self.validator.validate(root=self._mutated_root(mutate))

    def test_codex_metadata_is_in_the_portable_manifest(self):
        manifest = json.loads((self.root / "plugin.json").read_text(encoding="utf-8"))
        interface = manifest["extensions"]["com.openai"]["interface"]
        self.assertEqual(interface["displayName"], "Python Email MCP")
        self.assertEqual(interface["capabilities"], ["Read", "Write"])
        self.assertFalse((self.root / ".codex-plugin").exists())
        self.assertFalse((self.root / "integrations").exists())

    def test_wrong_manifest_version_fails_validation(self):
        def mutate(root):
            path = root / ".claude-plugin" / "plugin.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            document["version"] = f"{document['version']}-test"
            self._write_json(path, document)

        with self.assertRaises(ValueError):
            self.validator.validate(root=self._mutated_root(mutate))

    def test_wrong_portable_schema_fails_validation(self):
        def mutate(root):
            path = root / "plugin.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            document["$schema"] = "https://agent-plugins.org/schemas/0.9.0/plugin.schema.json"
            self._write_json(path, document)

        with self.assertRaises(ValueError):
            self.validator.validate(root=self._mutated_root(mutate))

    def test_escaping_skill_package_path_fails_validation(self):
        def mutate(root):
            path = root / ".claude-plugin" / "plugin.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            document["skills"] = "../outside-skills/"
            self._write_json(path, document)

        with self.assertRaises(ValueError):
            self.validator.validate(root=self._mutated_root(mutate))

    def test_wrong_adapter_variable_fails_validation(self):
        mutations = (
            ("mcp.json", "args", "PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT"),
            (".mcp.json", "env", "CLAUDE_PLUGIN_DATA", "PLUGIN_DATA"),
        )
        for relative, location, expected, wrong in mutations:
            with self.subTest(adapter=relative):
                def mutate(root):
                    path = root / relative
                    document = json.loads(path.read_text(encoding="utf-8"))
                    server = document["mcpServers"]["python-email"]
                    if location == "args":
                        server["args"] = [arg.replace(expected, wrong) for arg in server["args"]]
                    else:
                        server["env"]["UV_PROJECT_ENVIRONMENT"] = server["env"][
                            "UV_PROJECT_ENVIRONMENT"
                        ].replace(expected, wrong)
                    self._write_json(path, document)

                with self.assertRaises(ValueError):
                    self.validator.validate(root=self._mutated_root(mutate))


if __name__ == "__main__":
    unittest.main()
