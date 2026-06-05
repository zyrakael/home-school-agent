"""Select local skills for an execution plan."""

from dataclasses import dataclass, field

from app.schemas.agent import AgentIntent
from app.skills.loader import Skill
from app.skills.registry import SkillRegistry, get_skill_registry


@dataclass
class SkillSelectionResult:
    """Selected skills and non-fatal warnings."""

    skills: list[Skill] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SkillSelector:
    """Choose one primary skill and one communication skill for each intent."""

    INTENT_PRIMARY_SKILL: dict[AgentIntent, str] = {
        "RECENT_SUMMARY": "recent-summary",
        "HOMEWORK_DIAGNOSIS": "learning-diagnosis",
        "LESSON_FEEDBACK": "lesson-feedback",
        "PARENT_REPLY": "parent-reply",
    }
    SUPPORT_SKILL = "home-school-communication"

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self.registry = registry or get_skill_registry()

    def select(self, intent: AgentIntent) -> SkillSelectionResult:
        """Select skills for the intent."""

        result = SkillSelectionResult()
        for skill_name in (self.INTENT_PRIMARY_SKILL[intent], self.SUPPORT_SKILL):
            skill = self.registry.get(skill_name)
            if skill is None:
                result.warnings.append(f"Skill 文件缺失：{skill_name}")
                continue
            result.skills.append(skill)
        return result
