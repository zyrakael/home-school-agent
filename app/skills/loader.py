"""Load local Markdown skills from the skills directory."""

from dataclasses import dataclass
from pathlib import Path

from app.core.config import PROJECT_ROOT


@dataclass(frozen=True)
class Skill:
    """A local skill definition."""

    name: str
    description: str
    instructions: str
    path: Path


class SkillLoader:
    """Scan `skills/*/SKILL.md` and parse simple Markdown sections."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or PROJECT_ROOT / "skills"

    def load_all(self) -> dict[str, Skill]:
        """Load all available skills keyed by directory name."""

        skills: dict[str, Skill] = {}
        if not self.root.exists():
            return skills
        for skill_file in sorted(self.root.glob("*/SKILL.md")):
            skill_name = skill_file.parent.name
            text = skill_file.read_text(encoding="utf-8")
            skills[skill_name] = Skill(
                name=skill_name,
                description=self._section(text, "Description"),
                instructions=self._section(text, "Instructions"),
                path=skill_file,
            )
        return skills

    @staticmethod
    def _section(text: str, heading: str) -> str:
        marker = f"## {heading}"
        if marker not in text:
            return ""
        tail = text.split(marker, 1)[1]
        if "\n## " in tail:
            tail = tail.split("\n## ", 1)[0]
        return tail.strip()
