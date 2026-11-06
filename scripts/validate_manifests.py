"""Validate the repository's plugin adapters without network or mailbox access."""

from __future__ import annotations

import argparse
import json
import subprocess
import tomllib
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from jsonschema import Draft202012Validator
import yaml


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_BASE = "https://agent-plugins.org/schemas/1.0.0/"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def package_path(root: Path, value: str) -> Path:
    require(value.startswith("./"), f"Package path must start with ./: {value}")
    require(".." not in Path(value).parts, f"Package path contains ..: {value}")
    resolved = (root / value).resolve()
    require(resolved.is_relative_to(root.resolve()), f"Package path escapes root: {value}")
    require(resolved.exists(), f"Missing package path: {value}")
    return resolved


class _JsExpression:
    """Captured Loader `!!js` expression, kept as source instead of evaluated."""

    def __init__(self, expression: str) -> None:
        self.expression = expression


class _PatchLoader(yaml.SafeLoader):
    """SafeLoader variant that accepts the Loader's `!!js` tag."""


_PatchLoader.add_constructor(
    "tag:yaml.org,2002:js",
    lambda loader, node: _JsExpression(loader.construct_scalar(node)),
)


def js_expression(value: object, field: str) -> str:
    require(isinstance(value, _JsExpression), f"{field} must use a !!js expression")
    return value.expression


def validate_dsh_bundle(root: Path, project: dict) -> None:
    """Validate the DeepSeek Harness bundle that launches this checkout."""
    bundle = root / "integrations" / "dsh"
    manifest = load_json(bundle / "package.json")
    require(
        manifest["dsh"]["bundle"]["patch"] == "./cordis.patch.yml",
        "DSh bundle must load cordis.patch.yml",
    )
    require(manifest["version"] == project["version"], "DSh bundle version mismatch")
    for name in ("cordis.patch.yml", "icon.svg", "locale/en.json", "locale/zh.json"):
        require((bundle / name).is_file(), f"Missing DSh bundle file: {name}")
    require(
        {"cordis.patch.yml", "icon.svg", "locale/*.json"} <= set(manifest["files"]),
        "DSh bundle package.json must ship the patch, locales, and icon",
    )
    icon = ElementTree.parse(bundle / "icon.svg").getroot()
    require(
        icon.tag == "{http://www.w3.org/2000/svg}svg",
        "DSh bundle icon must be an SVG document",
    )
    for locale in ("en", "zh"):
        meta = load_json(bundle / "locale" / f"{locale}.json")["meta"]
        require(
            bool(meta.get("title")) and bool(meta.get("description")),
            f"DSh bundle metadata is incomplete in locale/{locale}.json",
        )

    patch = yaml.load(
        (bundle / "cordis.patch.yml").read_text(encoding="utf-8"),
        Loader=_PatchLoader,
    )
    require(
        isinstance(patch, list)
        and len(patch) == 1
        and isinstance(patch[0].get("insert"), list)
        and len(patch[0]["insert"]) == 2,
        "DSh patch must insert the MCP client and the Skill provider",
    )
    mcp_row, skill_row = patch[0]["insert"]
    require(mcp_row["name"] == "@deepseek-ai/dsh-mcp-client", "DSh MCP plugin mismatch")
    mcp = mcp_row["config"]
    require(mcp["serverName"] == "python-email", "DSh MCP server name mismatch")
    require(mcp["transport"] == "stdio", "DSh MCP transport must be stdio")
    require(mcp["command"] == "uv", "DSh MCP must launch through uv")
    require(mcp["failOnStartupError"] is True, "DSh MCP must fail loudly at startup")
    timeout = mcp.get("toolCallTimeoutMs")
    require(
        isinstance(timeout, int) and timeout >= 60000,
        "DSh MCP tool timeout must allow slow mailbox operations",
    )
    require(
        mcp["args"][:2] == ["run", "--project"]
        and mcp["args"][3:] == ["--locked", "python-email-mcp", "mcp"],
        "DSh MCP launch arguments mismatch",
    )
    checkout = js_expression(mcp["args"][2], "DSh MCP project path")
    require(
        "PYTHON_EMAIL_MCP_ROOT" in checkout and "HOME" in checkout,
        "DSh MCP project path must resolve the checkout when the patch loads",
    )
    require(
        js_expression(mcp["cwd"], "DSh MCP working directory") == checkout,
        "DSh MCP working directory must match --project",
    )

    require(
        skill_row["name"] == "@deepseek-ai/dsh-skill-filesystem",
        "DSh Skill provider mismatch",
    )
    skill = skill_row["config"]
    require(skill["providerName"] == "python-email", "DSh Skill provider name mismatch")
    require(
        skill["includeDefaultRoots"] is False,
        "DSh Skill provider must not rescan user Skill roots",
    )
    require(len(skill["customSkillDirs"]) == 1, "DSh Skill provider must use one directory")
    skills = js_expression(skill["customSkillDirs"][0], "DSh Skill directory")
    require(
        "PYTHON_EMAIL_MCP_ROOT" in skills and "/skills" in skills,
        "DSh Skill directory must resolve the checkout's shared Skills",
    )


def validate(root: Path = ROOT) -> None:
    project = tomllib.loads(
        (root / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    manifests = {
        path: load_json(root / path)
        for path in ("plugin.json", ".claude-plugin/plugin.json")
    }
    portable = manifests["plugin.json"]
    for path, manifest in manifests.items():
        require(manifest["name"] == project["name"], f"Name mismatch in {path}")
        require(manifest["version"] == project["version"], f"Version mismatch in {path}")

    for filename in ("plugin", "mcp"):
        document = load_json(root / f"{filename}.json")
        schema = load_json(root / "scripts" / "schemas" / f"{filename}.schema.json")
        require(
            document["$schema"] == SCHEMA_BASE + f"{filename}.schema.json",
            "Schema version mismatch",
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(document)

    interface = portable["extensions"]["com.openai"]["interface"]
    require(interface["displayName"] == "Python Email MCP", "Missing OpenAI interface metadata")
    skill_dir = package_path(root, manifests[".claude-plugin/plugin.json"]["skills"])
    require(skill_dir == (root / "skills").resolve(), "Claude must use the shared Skill directory")

    for path, root_variable, data_variable in (
        ("mcp.json", "PLUGIN_ROOT", "PLUGIN_DATA"),
        (".mcp.json", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DATA"),
    ):
        servers = load_json(root / path)["mcpServers"]
        require(set(servers) == {"python-email"}, f"Unexpected MCP servers in {path}")
        server = servers["python-email"]
        require(server["command"] == "uv", f"Expected uv command in {path}")
        require(
            server["args"] == [
                "run", "--project", "${" + root_variable + "}",
                "--locked", "python-email-mcp", "mcp",
            ],
            f"Launch arguments mismatch in {path}",
        )
        require(
            server["env"] == {"UV_PROJECT_ENVIRONMENT": "${" + data_variable + "}/venv"},
            f"Runtime data path mismatch in {path}",
        )
        require("cwd" not in server, f"Launch must use --project in {path}")

    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    locked_project = next(item for item in lock["package"] if item["name"] == project["name"])
    require(locked_project["version"] == project["version"], "Lockfile project version mismatch")
    marketplace = load_json(root / ".agents/plugins/marketplace.json")
    require(marketplace["name"] == "fucose-plugins", "Codex marketplace identity changed")
    require(len(marketplace["plugins"]) == 1, "Expected one Codex marketplace plugin")
    entry = marketplace["plugins"][0]
    require(entry["name"] == project["name"], "Codex marketplace plugin name mismatch")
    require(
        entry["source"] == {"source": "local", "path": "./"},
        "Codex marketplace must use the plugin in the same repository snapshot",
    )
    package_path(root, entry["source"]["path"])
    claude_marketplace = load_json(root / ".claude-plugin/marketplace.json")
    require(claude_marketplace["name"] == marketplace["name"], "Marketplace identities differ")
    require(
        claude_marketplace["owner"]["name"] == portable["author"]["name"],
        "Claude marketplace owner mismatch",
    )
    require(
        claude_marketplace["plugins"] == [{"name": project["name"], "source": "./"}],
        "Claude marketplace must use the shared plugin root",
    )
    validate_dsh_bundle(root, project)


def validate_release(root: Path, ref: str) -> None:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    require(ref == "v" + project["version"], "Release ref must match the project version")
    tag_commit = subprocess.check_output(
        ["git", "rev-parse", "--verify", f"refs/tags/{ref}^{{commit}}"], cwd=root, text=True,
    ).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(tag_commit == head, "Release tag must point to HEAD")
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True)
    require(not status.strip(), "Release validation requires a clean working tree")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-ref", help="Also verify an existing local release tag and clean tree")
    args = parser.parse_args()
    validate()
    if args.release_ref:
        validate_release(ROOT, args.release_ref)
    print("Plugin manifests, schemas, adapter paths, and versions are consistent.")


if __name__ == "__main__":
    main()
