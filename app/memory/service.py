"""Lightweight work-context memory for the Agent.

This module stores reusable teaching-assistant context. It is intentionally not
a parent chat archive and not a parent profiling system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.agent_contracts import AgentChatRequest, AgentExecutionPlan, AgentIntent
from app.schemas.response import AgentChatResponse

MemoryType = Literal[
    "student_learning_pattern",
    "teacher_reply_style",
    "teacher_case_handling",
    "internal_reply_policy",
]


class EphemeralContext(BaseModel):
    """Context that may be used for this turn only and must not be stored."""

    items: list[str] = Field(default_factory=list)


class MemoryRecord(BaseModel):
    """One reusable work-context memory item."""

    id: str = Field(default_factory=lambda: f"mem_{uuid4().hex[:12]}")
    owner_key: str
    memory_type: MemoryType
    content: str
    source: str = "agent"
    intent: AgentIntent | None = None
    confidence: float = 0.8
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MemoryPack(BaseModel):
    """Memory recalled for one Agent run."""

    student_learning_patterns: list[str] = Field(default_factory=list)
    teacher_reply_styles: list[str] = Field(default_factory=list)
    teacher_case_handlings: list[str] = Field(default_factory=list)
    internal_reply_policies: list[str] = Field(default_factory=list)
    ephemeral_turn_context: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def has_content(self) -> bool:
        """Return whether this pack contains usable context."""

        return any(
            (
                self.student_learning_patterns,
                self.teacher_reply_styles,
                self.teacher_case_handlings,
                self.internal_reply_policies,
                self.ephemeral_turn_context,
            )
        )


class InMemoryMemoryStore:
    """Process-local memory store used by the first implementation."""

    def __init__(self, records: list[MemoryRecord] | None = None) -> None:
        self._records: list[MemoryRecord] = list(records or [])

    def add(self, record: MemoryRecord) -> None:
        """Add a memory record, avoiding exact duplicates."""

        for existing in self._records:
            if (
                existing.owner_key == record.owner_key
                and existing.memory_type == record.memory_type
                and existing.content == record.content
            ):
                return
        self._records.append(record)

    def list(
        self,
        *,
        owner_key: str | None = None,
        memory_type: MemoryType | None = None,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        """List newest matching records."""

        records = self._records
        if owner_key is not None:
            records = [record for record in records if record.owner_key == owner_key]
        if memory_type is not None:
            records = [record for record in records if record.memory_type == memory_type]
        return sorted(records, key=lambda record: record.created_at, reverse=True)[:limit]


@dataclass
class MemoryRetriever:
    """Retrieve reusable long-term work context."""

    store: InMemoryMemoryStore

    def recall(
        self,
        request: AgentChatRequest,
        plan: AgentExecutionPlan,
        ephemeral_context: EphemeralContext,
    ) -> MemoryPack:
        """Recall long-term memory for one request."""

        pack = MemoryPack()
        student_key = MemoryService._student_key(request.student_id)
        teacher_key = MemoryService._teacher_key(request.teacher_id)

        if request.student_id:
            pack.student_learning_patterns = [
                record.content
                for record in self.store.list(
                    owner_key=student_key,
                    memory_type="student_learning_pattern",
                )
            ]
        if request.teacher_id:
            pack.teacher_reply_styles = [
                record.content
                for record in self.store.list(
                    owner_key=teacher_key,
                    memory_type="teacher_reply_style",
                )
            ]
            if plan.intent == "PARENT_REPLY":
                pack.teacher_case_handlings = [
                    record.content
                    for record in self.store.list(
                        owner_key=teacher_key,
                        memory_type="teacher_case_handling",
                    )
                ]

        pack.internal_reply_policies = MemoryService._internal_policies(request, plan.intent)
        pack.ephemeral_turn_context = ephemeral_context.items
        return pack


@dataclass
class MemoryExtractor:
    """Extract conservative long-term memory candidates."""

    def extract(
        self,
        request: AgentChatRequest,
        plan: AgentExecutionPlan,
        response: AgentChatResponse,
    ) -> list[MemoryRecord]:
        """Extract candidate records from a successful response."""

        candidates: list[MemoryRecord] = []
        for content in MemoryService._safe_student_patterns(plan, response):
            candidates.append(
                MemoryRecord(
                    owner_key=MemoryService._student_key(request.student_id),
                    memory_type="student_learning_pattern",
                    content=content,
                    intent=plan.intent,
                    source="agent_response_summary",
                    confidence=0.7,
                )
            )

        for memory_type, content in MemoryService._safe_teacher_work_context(
            request,
            plan,
            response,
        ):
            candidates.append(
                MemoryRecord(
                    owner_key=MemoryService._teacher_key(request.teacher_id),
                    memory_type=memory_type,
                    content=content,
                    intent=plan.intent,
                    source="agent_response_summary",
                    confidence=0.7,
                )
            )
        return candidates


@dataclass
class MemoryValidator:
    """Validate whether a candidate may become long-term memory."""

    def can_store(self, record: MemoryRecord, response: AgentChatResponse) -> bool:
        """Return whether the record is safe to store."""

        if not record.content or record.owner_key.endswith(":unknown"):
            return False
        if MemoryService._looks_data_insufficient(response):
            return False
        return MemoryService._is_safe_long_term_item(record.content)


@dataclass
class MemoryUpdater:
    """Apply validated long-term memory changes."""

    store: InMemoryMemoryStore

    def update(self, records: list[MemoryRecord]) -> None:
        """Add records with store-level de-duplication."""

        for record in records:
            self.store.add(record)


@dataclass
class MemoryService:
    """Recall and commit reusable work context for the Agent."""

    store: InMemoryMemoryStore = field(default_factory=InMemoryMemoryStore)
    retriever: MemoryRetriever | None = None
    extractor: MemoryExtractor | None = None
    validator: MemoryValidator | None = None
    updater: MemoryUpdater | None = None

    def __post_init__(self) -> None:
        self.retriever = self.retriever or MemoryRetriever(self.store)
        self.extractor = self.extractor or MemoryExtractor()
        self.validator = self.validator or MemoryValidator()
        self.updater = self.updater or MemoryUpdater(self.store)

    async def recall(
        self,
        request: AgentChatRequest,
        plan: AgentExecutionPlan,
    ) -> MemoryPack:
        """Recall reusable memory and this-turn ephemeral context."""

        return self.retriever.recall(  # type: ignore[union-attr]
            request,
            plan,
            self.extract_ephemeral_context(request),
        )

    async def commit(
        self,
        request: AgentChatRequest,
        plan: AgentExecutionPlan,
        run_result: Any,
        response: AgentChatResponse,
    ) -> None:
        """Persist only safe, reusable summaries from a successful run."""

        if getattr(run_result, "error", None) or response.status != "success":
            return
        candidates = self.extractor.extract(request, plan, response)  # type: ignore[union-attr]
        valid_records = [
            record
            for record in candidates
            if self.validator.can_store(record, response)  # type: ignore[union-attr]
        ]
        self.updater.update(valid_records)  # type: ignore[union-attr]

    def extract_ephemeral_context(self, request: AgentChatRequest) -> EphemeralContext:
        """Extract this-turn-only context from request.context."""

        items: list[str] = []
        for key in (
            "pasted_chat",
            "chat_record",
            "chat_history",
            "parent_chat",
            "temporary_context",
            "teacher_note",
        ):
            value = request.context.get(key)
            items.extend(self._coerce_context_items(value))

        if request.params.parent_question:
            items.append(f"家长本轮问题：{request.params.parent_question}")

        return EphemeralContext(items=self._dedupe(items, limit=8))

    @staticmethod
    def _student_key(student_id: str) -> str:
        return f"student:{student_id or 'unknown'}"

    @staticmethod
    def _teacher_key(teacher_id: str) -> str:
        return f"teacher:{teacher_id or 'unknown'}"

    @staticmethod
    def _internal_policies(request: AgentChatRequest, intent: AgentIntent) -> list[str]:
        policies: list[str] = []
        if intent == "PARENT_REPLY":
            policies.append("家长回复必须先回应关切，再基于事实说明情况，最后给出可执行的下一步。")
            policies.append("投诉、退费、师资争议类问题只输出内部处理建议，不生成可直接发送承诺话术。")

        text = f"{request.message}\n{request.params.parent_question or ''}"
        if any(keyword in text for keyword in ("投诉", "退费", "退款", "不满", "师资", "换老师")):
            policies.append("当前请求疑似敏感家校问题，应按内部处理流程回复，避免承诺赔付、退费、处罚或更换老师。")
        return policies

    @staticmethod
    def _coerce_context_items(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            items: list[str] = []
            for item in value:
                if isinstance(item, str) and item.strip():
                    items.append(item.strip())
                elif isinstance(item, dict):
                    text = item.get("content") or item.get("text") or item.get("message")
                    if isinstance(text, str) and text.strip():
                        items.append(text.strip())
            return items
        if isinstance(value, dict):
            text = value.get("content") or value.get("text") or value.get("message")
            return [text.strip()] if isinstance(text, str) and text.strip() else []
        return []

    @staticmethod
    def _dedupe(items: list[str], *, limit: int) -> list[str]:
        deduped: list[str] = []
        for item in items:
            if item not in deduped:
                deduped.append(item)
            if len(deduped) >= limit:
                break
        return deduped

    def _add_record(
        self,
        *,
        owner_key: str,
        memory_type: MemoryType,
        content: str,
        intent: AgentIntent,
        source: str,
    ) -> None:
        if not content or owner_key.endswith(":unknown"):
            return
        self.store.add(
            MemoryRecord(
                owner_key=owner_key,
                memory_type=memory_type,
                content=content,
                source=source,
                intent=intent,
                confidence=0.7,
            )
        )

    @staticmethod
    def _looks_data_insufficient(response: AgentChatResponse) -> bool:
        text = f"{response.title}\n{response.content}\n{' '.join(response.warnings)}"
        return any(keyword in text for keyword in ("数据不足", "没有查到", "补充或确认"))

    @staticmethod
    def _safe_student_patterns(
        plan: AgentExecutionPlan,
        response: AgentChatResponse,
    ) -> list[str]:
        if plan.intent not in ("RECENT_SUMMARY", "HOMEWORK_DIAGNOSIS", "LESSON_FEEDBACK"):
            return []
        candidates = MemoryService._section_items(
            response,
            names=("学习", "表现", "薄弱", "错题", "课堂", "作业", "建议"),
        )
        return [
            MemoryService._as_summary("学生稳定学习特征", item)
            for item in candidates
            if MemoryService._is_safe_long_term_item(item)
        ][:3]

    @staticmethod
    def _safe_teacher_work_context(
        request: AgentChatRequest,
        plan: AgentExecutionPlan,
        response: AgentChatResponse,
    ) -> list[tuple[MemoryType, str]]:
        items: list[tuple[MemoryType, str]] = []
        if request.params.tone:
            items.append(
                (
                    "teacher_reply_style",
                    f"班主任常用回复语气偏好：{request.params.tone}",
                )
            )
        if plan.intent == "PARENT_REPLY":
            section_items = MemoryService._section_items(response, names=("处理", "建议", "回复"))
            for item in section_items:
                if MemoryService._is_safe_long_term_item(item):
                    items.append(
                        (
                            "teacher_case_handling",
                            MemoryService._as_summary("同类问题处理方式", item),
                        )
                    )
                    break
        return items[:2]

    @staticmethod
    def _section_items(
        response: AgentChatResponse,
        *,
        names: tuple[str, ...],
    ) -> list[str]:
        items: list[str] = []
        for section in response.sections:
            if any(name in section.name for name in names):
                items.extend(section.items)
        return items

    @staticmethod
    def _is_safe_long_term_item(item: str) -> bool:
        unsafe_keywords = (
            "家长说",
            "家长表示",
            "聊天记录",
            "原话",
            "隐私",
            "情绪",
            "生气",
            "焦虑",
            "不满",
            "投诉",
        )
        return bool(item.strip()) and not any(keyword in item for keyword in unsafe_keywords)

    @staticmethod
    def _as_summary(prefix: str, item: str) -> str:
        item = item.strip()
        if len(item) > 120:
            item = f"{item[:117]}..."
        return f"{prefix}：{item}"
