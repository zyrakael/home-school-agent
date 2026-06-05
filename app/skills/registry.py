"""In-memory Skill registry."""

from functools import lru_cache

from app.skills.loader import Skill, SkillLoader


class SkillRegistry:
    """Cache and expose local skills."""

    def __init__(self, loader: SkillLoader | None = None) -> None:
        self.loader = loader or SkillLoader()
        self._skills: dict[str, Skill] | None = None

    def all(self) -> dict[str, Skill]:
        """Return all skills keyed by name."""

        if self._skills is None:
            self._skills = self.loader.load_all()
        return self._skills

    def get(self, name: str) -> Skill | None:
        """Return one skill by name."""

        return self.all().get(name)


@lru_cache
def get_skill_registry() -> SkillRegistry:
    """Return shared registry."""

    return SkillRegistry()
