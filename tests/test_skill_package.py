import re
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml


class SkillPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parent.parent
        cls.skill_root = cls.repo_root / "skills" / "email-assistant"
        cls.skill_file = cls.skill_root / "SKILL.md"

    @staticmethod
    def _frontmatter(skill_file: Path) -> tuple[dict, str]:
        content = skill_file.read_text(encoding="utf-8")
        if not content.startswith("---\n"):
            raise AssertionError("SKILL.md must begin with YAML frontmatter")
        _, frontmatter, body = content.split("---\n", 2)
        metadata = yaml.safe_load(frontmatter)
        if not isinstance(metadata, dict):
            raise AssertionError("SKILL.md frontmatter must be a YAML mapping")
        return metadata, body

    @staticmethod
    def _local_references(skill_root: Path) -> list[tuple[Path, Path]]:
        skill_root = skill_root.resolve()
        references = []
        for markdown_file in sorted(skill_root.rglob("*.md")):
            body = markdown_file.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", body):
                target = target.split(maxsplit=1)[0].strip("<>")
                if ":" in target or target.startswith("#"):
                    continue
                relative_path = target.split("#", maxsplit=1)[0]
                if not relative_path:
                    continue
                resolved = (markdown_file.parent / relative_path).resolve()
                if not resolved.is_relative_to(skill_root):
                    raise AssertionError(f"Skill reference escapes its folder: {target}")
                if not resolved.is_file():
                    raise AssertionError(f"Skill reference does not exist: {target}")
                references.append(
                    (markdown_file.relative_to(skill_root), resolved.relative_to(skill_root))
                )
        return references

    def test_shared_skill_has_standard_frontmatter_and_is_the_only_skill(self):
        skill_files = sorted((self.repo_root / "skills").rglob("SKILL.md"))
        self.assertEqual(skill_files, [self.skill_file])

        metadata, _ = self._frontmatter(self.skill_file)
        self.assertTrue(metadata.get("name"))
        self.assertIsInstance(metadata.get("name"), str)
        self.assertTrue(metadata.get("description"))
        self.assertIsInstance(metadata.get("description"), str)

    def test_references_stay_inside_the_skill_and_survive_a_standalone_copy(self):
        references = self._local_references(self.skill_root)
        self.assertTrue(references, "The shared Skill should exercise its bundled references")

        with tempfile.TemporaryDirectory(prefix="standalone email skill ") as temporary:
            copied_skill = Path(temporary) / "email assistant"
            shutil.copytree(self.skill_root, copied_skill)
            copied_skill_file = copied_skill / "SKILL.md"
            self.assertTrue(copied_skill_file.is_file())
            copied_references = self._local_references(copied_skill)
            self.assertEqual(set(references), set(copied_references))

    def test_core_email_safety_rules_remain_in_the_shared_skill(self):
        _, body = self._frontmatter(self.skill_file)
        normalized = " ".join(body.split()).casefold()
        for safety_anchor in (
            "untrusted data",
            "explicit, action-specific approval",
            "never ask them to share a password, authorization code",
            "confirmation for those exact details",
            "get_configuration_status",
        ):
            with self.subTest(anchor=safety_anchor):
                self.assertIn(safety_anchor.casefold(), normalized)


if __name__ == "__main__":
    unittest.main()
