"""Tool policy mapping abstract data needs to MCP tools."""

from app.schemas.agent_contracts import AgentDataNeed


class ToolPolicy:
    """Static allow-list mapping for MCP tools."""

    DATA_NEED_TOOLS: dict[AgentDataNeed, tuple[str, ...]] = {
        "student_profile": ("user.get_student_profile",),
        "recent_homeworks": ("learning.get_recent_homeworks",),
        "homework_detail": ("learning.get_homework_detail",),
        "wrong_question_stats": ("wrong_question.get_stats",),
        "recent_wrong_questions": ("wrong_question.list_recent",),
        "lesson_performance": ("lesson.get_performance",),
        "recent_lesson_performances": ("lesson.list_recent_performances",),
        "class_students": ("user.list_students",),
    }

    def tools_for_need(self, data_need: str) -> tuple[str, ...]:
        """Return allowed MCP tools for one data need."""

        return self.DATA_NEED_TOOLS.get(data_need, ())
