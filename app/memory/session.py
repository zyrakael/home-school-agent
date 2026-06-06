"""Short-lived session memory for multi-turn Agent work state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from app.schemas.agent_contracts import AgentChatRequest, AgentExecutionPlan, AgentIntent
from app.schemas.response import AgentChatResponse


class SessionState(BaseModel):
    """Short-lived state for one conversation."""

    conversation_id: str = ""
    student_id: str = ""
    subject: str = ""
    scene: str = ""
    last_intent: AgentIntent | None = None
    last_user_message: str = ""
    called_tools: list[str] = Field(default_factory=list)
    tool_evidence: list[str] = Field(default_factory=list)
    key_data_summary: list[str] = Field(default_factory=list)
    last_draft_title: str = ""
    last_draft_content: str = ""
    last_revision_instruction: str = ""
    suggested_next_step: str = ""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def has_content(self) -> bool:
        """Return whether this state has context worth injecting."""

        return any(
            (
                self.student_id,
                self.subject,
                self.last_intent,
                self.called_tools,
                self.key_data_summary,
                self.last_draft_content,
                self.last_revision_instruction,
                self.suggested_next_step,
            )
        )


@dataclass
class SessionMemoryStore:
    """Process-local session store with a TTL."""

    ttl_seconds: int = 2 * 60 * 60
    _states: dict[str, tuple[SessionState, datetime]] = field(default_factory=dict)

    def get(self, conversation_id: str) -> SessionState:
        """Return a non-expired session state or an empty one."""

        if not conversation_id:
            return SessionState()
        state_entry = self._states.get(conversation_id)
        if state_entry is None:
            return SessionState(conversation_id=conversation_id)
        state, expires_at = state_entry
        if expires_at <= datetime.now(UTC):
            self._states.pop(conversation_id, None)
            return SessionState(conversation_id=conversation_id)
        return state

    def set(self, state: SessionState) -> None:
        """Persist a state until the configured TTL expires."""

        if not state.conversation_id:
            return
        expires_at = datetime.now(UTC) + timedelta(seconds=self.ttl_seconds)
        state.updated_at = datetime.now(UTC)
        self._states[state.conversation_id] = (state, expires_at)


@dataclass
class SessionMemoryService:
    """Recall, resolve, and commit short-lived conversation state."""

    store: SessionMemoryStore = field(default_factory=SessionMemoryStore)

    async def recall(self, request: AgentChatRequest) -> SessionState:
        """Recall state for the current conversation."""

        if not request.conversation_id:
            return SessionState()
        return self.store.get(request.conversation_id)

    def resolve_request(
        self,
        request: AgentChatRequest,
        session_state: SessionState,
    ) -> AgentChatRequest:
        """Fill obvious omitted context from session state."""

        if not request.conversation_id or not session_state.has_content():
            return request
        if not self._is_followup(request.message):
            return request

        params_updates: dict[str, object] = {}
        request_updates: dict[str, object] = {}
        if not request.student_id and session_state.student_id:
            request_updates["student_id"] = session_state.student_id
        if not request.scene and session_state.scene:
            request_updates["scene"] = session_state.scene
        if not request.params.subject and session_state.subject:
            params_updates["subject"] = session_state.subject
        if (
            session_state.last_intent
            and request.params.intent == "RECENT_SUMMARY"
            and not self._mentions_new_intent(request.message)
        ):
            params_updates["intent"] = session_state.last_intent

        if params_updates:
            request_updates["params"] = request.params.model_copy(update=params_updates)
        if not request_updates:
            return request
        return request.model_copy(update=request_updates)

    async def commit(
        self,
        request: AgentChatRequest,
        plan: AgentExecutionPlan,
        run_result: object,
        response: AgentChatResponse,
    ) -> None:
        """Store short-lived work state after one Agent run."""

        if not request.conversation_id:
            return

        state = self.store.get(request.conversation_id)
        state.conversation_id = request.conversation_id
        state.student_id = request.student_id or state.student_id
        state.subject = request.params.subject or state.subject
        state.scene = request.scene or state.scene
        state.last_intent = plan.intent
        state.last_user_message = request.message
        tool_results = getattr(run_result, "tool_results", {}) or {}
        evidence = getattr(run_result, "evidence", []) or []
        state.called_tools = self._dedupe([*state.called_tools, *tool_results.keys()], limit=12)
        state.tool_evidence = self._dedupe([*state.tool_evidence, *evidence], limit=12)
        state.key_data_summary = self._key_data_summary(response, run_result)
        state.last_draft_title = response.title if response.status == "success" else state.last_draft_title
        state.last_draft_content = (
            self._trim(response.content, 800)
            if response.status == "success"
            else state.last_draft_content
        )
        revision = self._revision_instruction(request.message)
        if revision:
            state.last_revision_instruction = revision
        state.suggested_next_step = self._suggested_next_step(plan.intent)
        self.store.set(state)

    @staticmethod
    def _is_followup(message: str) -> bool:
        markers = ("那", "继续", "再", "刚才", "上面", "这个", "改", "换成", "帮我生成")
        return any(marker in message for marker in markers)

    @staticmethod
    def _mentions_new_intent(message: str) -> bool:
        markers = ("错题", "诊断", "课后", "反馈", "家长", "回复", "总结")
        return any(marker in message for marker in markers)

    @staticmethod
    def _revision_instruction(message: str) -> str:
        markers = ("改短", "短一点", "温和", "正式", "口语", "再改", "换成", "润色")
        if any(marker in message for marker in markers):
            return message.strip()
        return ""

    @staticmethod
    def _key_data_summary(
        response: AgentChatResponse,
        run_result: object,
    ) -> list[str]:
        items: list[str] = []
        for section in response.sections:
            if any(name in section.name for name in ("学习", "表现", "薄弱", "错题", "作业", "课堂")):
                items.extend(section.items)
        if not items:
            items.extend(getattr(run_result, "evidence", []) or [])
        return [SessionMemoryService._trim(item, 160) for item in items[:6]]

    @staticmethod
    def _suggested_next_step(intent: AgentIntent) -> str:
        suggestions = {
            "RECENT_SUMMARY": "generate_parent_reply",
            "HOMEWORK_DIAGNOSIS": "generate_parent_reply",
            "LESSON_FEEDBACK": "revise_or_send_feedback",
            "PARENT_REPLY": "revise_draft",
        }
        return suggestions[intent]

    @staticmethod
    def _dedupe(items: list[str], *, limit: int) -> list[str]:
        deduped: list[str] = []
        for item in items:
            if item and item not in deduped:
                deduped.append(item)
            if len(deduped) >= limit:
                break
        return deduped

    @staticmethod
    def _trim(value: str, limit: int) -> str:
        value = value.strip()
        if len(value) <= limit:
            return value
        return f"{value[: limit - 3]}..."
