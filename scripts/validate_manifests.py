"""Validate the repository's plugin adapters without network or mailbox access."""

from __future__ import annotations

import argparse
import json
import subprocess
import tomllib
from pathlib import Path

from jsonschema import Draft202012Validator


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
