"""Agent service backed by real database queries.

Replaces MockAgentService — all data comes from the database via the
provided AsyncSession. The response narrative text is templated from
real student / homework / lesson-performance / wrong-question data.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.queries import (
    get_lesson_performance,
    get_lesson_performances,
    get_recent_homeworks,
    get_student,
    get_wrong_question_stats,
    list_homeworks,
)
from app.schemas.agent import AgentChatRequest
from app.schemas.response import AgentChatResponse, AgentSection


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{round(value * 100)}%"


class AgentService:
    """Stateless service — all data comes from the database via the provided session."""

    async def generate(
        self, db: AsyncSession, request: AgentChatRequest
    ) -> AgentChatResponse:
        """Dispatch by requested intent."""

        intent = request.params.intent
        if intent == "HOMEWORK_DIAGNOSIS":
            return await self._homework_diagnosis(db, request)
        if intent == "LESSON_FEEDBACK":
            return await self._lesson_feedback(db, request)
        if intent == "PARENT_REPLY":
            return await self._parent_reply(db, request)
        return await self._recent_summary(db, request)

    # ------------------------------------------------------------------
    # Shared response builder
    # ------------------------------------------------------------------

    @staticmethod
    def _base_response(
        *,
        intent: str,
        title: str,
        content: str,
        sections: list[AgentSection],
        evidence: list[str],
        warnings: list[str] | None = None,
    ) -> AgentChatResponse:
        return AgentChatResponse(
            request_id=f"req_{uuid4().hex[:12]}",
            intent=intent,
            status="success",
            title=title,
            content=content,
            sections=sections,
            evidence=evidence,
            warnings=warnings or [],
            available_actions=["copy", "edit", "regenerate", "shorten", "change_tone"],
        )

    # ------------------------------------------------------------------
    # RECENT_SUMMARY
    # ------------------------------------------------------------------

    async def _recent_summary(
        self, db: AsyncSession, request: AgentChatRequest
    ) -> AgentChatResponse:
        student_id = request.student_id
        days = int(request.params.time_range.replace("d", "")) if request.params.time_range else 7

        student = await get_student(db, student_id)
        homeworks = await get_recent_homeworks(db, student_id, days=days)
        wrong_stats = await get_wrong_question_stats(db, student_id, days=days)

        if student is None:
            return self._base_response(
                intent="RECENT_SUMMARY",
                title=f"近{days}天学习情况总结",
                content="未找到该学生的学习数据。",
                sections=[AgentSection(name="提示", items=["请检查学生 ID 是否正确。"])],
                evidence=[],
            )

        # ── compute real metrics ──
        total_hw = len(homeworks)
        completed_hw = sum(1 for h in homeworks if h.status in ("submitted", "late"))
        completion_rate = f"{completed_hw}/{total_hw}" if total_hw > 0 else "0/0"

        accuracies = [h.accuracy for h in homeworks if h.accuracy is not None]
        avg_acc = sum(accuracies) / len(accuracies) if accuracies else None

        top_wrong = [f"{kp}({cnt}次)" for kp, cnt in wrong_stats[:3] if cnt > 0]

        # ── build sections ──
        highlights: list[str] = []
        concerns: list[str] = []
        talk_points: list[str] = []
        evidence: list[str] = []

        if total_hw > 0:
            highlights.append(f"近{days}天{total_hw}次作业提交{completed_hw}次")
            evidence.append(f"近{days}天{total_hw}次作业提交{completed_hw}次")
        if avg_acc is not None:
            highlights.append(f"平均正确率{_fmt_pct(avg_acc)}")
            evidence.append(f"平均正确率{_fmt_pct(avg_acc)}")
        if student.status == "active":
            highlights.append("出勤稳定")

        if total_hw > 0 and completed_hw < total_hw:
            concerns.append(f"作业完成连续性需关注（{completion_rate}）")
        if avg_acc is not None and avg_acc < 0.75:
            concerns.append("正确率仍有提升空间")
        if top_wrong:
            concerns.append(f"错题集中在：{'、'.join(top_wrong)}")
            evidence.append(f"错题集中在：{'、'.join(top_wrong)}")

        if highlights:
            talk_points.append("先肯定基础表现")
        if concerns:
            talk_points.append("再提醒需要关注的点")
        talk_points.append("建议课后固定时间复盘错题")

        sections = []
        if highlights:
            sections.append(AgentSection(name="主要表现", items=highlights))
        if concerns:
            sections.append(AgentSection(name="需要关注", items=concerns))
        if talk_points:
            sections.append(AgentSection(name="沟通重点", items=talk_points))

        content = (
            f"{student.name}近期整体学习状态"
            f"{'基本稳定' if avg_acc and avg_acc >= 0.7 else '需要关注'}。"
            f"近{days}天共{total_hw}次作业，提交{completed_hw}次。"
        )
        if avg_acc is not None:
            content += f"平均正确率{_fmt_pct(avg_acc)}。"
        if top_wrong:
            content += f"薄弱知识点：{'、'.join(top_wrong)}。"

        return self._base_response(
            intent="RECENT_SUMMARY",
            title=f"近{days}天学习情况总结",
            content=content,
            sections=sections,
            evidence=evidence,
        )

    # ------------------------------------------------------------------
    # HOMEWORK_DIAGNOSIS
    # ------------------------------------------------------------------

    async def _homework_diagnosis(
        self, db: AsyncSession, request: AgentChatRequest
    ) -> AgentChatResponse:
        student_id = request.student_id
        days = 14

        student = await get_student(db, student_id)
        homeworks = await get_recent_homeworks(db, student_id, days=days)
        wrong_stats = await get_wrong_question_stats(db, student_id, days=days)

        if student is None:
            return self._base_response(
                intent="HOMEWORK_DIAGNOSIS",
                title="作业与错题诊断",
                content="未找到该学生的学习数据。",
                sections=[AgentSection(name="提示", items=["请检查学生 ID 是否正确。"])],
                evidence=[],
            )

        total_hw = len(homeworks)
        submitted = sum(1 for h in homeworks if h.status in ("submitted", "late"))
        accuracies = [h.accuracy for h in homeworks if h.accuracy is not None]
        avg_acc = sum(accuracies) / len(accuracies) if accuracies else None

        # wrong details from each homework
        total_wrong = sum(
            (h.detail.wrong_count if h.detail else 0) for h in homeworks
        )

        sections: list[AgentSection] = []
        evidence: list[str] = []

        # homework overview
        hw_items = [
            f"近{days}天{total_hw}次作业提交{submitted}次",
            f"平均正确率{_fmt_pct(avg_acc)}",
            f"累计错题{total_wrong}道",
        ]
        sections.append(AgentSection(name="作业情况", items=hw_items))
        evidence.extend(hw_items)

        # weak points from wrong_question stats
        weak_items = [
            f"{kp}错误{cnt}次" for kp, cnt in wrong_stats[:5] if cnt > 0
        ] or ["暂无薄弱点数据"]
        sections.append(AgentSection(name="薄弱点", items=weak_items))
        if weak_items:
            evidence.append(f"薄弱点：{'、'.join(weak_items)}")

        # suggestions
        suggestions = ["订正时写出每一步依据", "圈出题干关键词再列式"]
        if avg_acc is not None and avg_acc < 0.75:
            suggestions.append("建议每天完成2-3道同类巩固题")
        sections.append(AgentSection(name="建议动作", items=suggestions))

        content = (
            f"{student.name}作业完成率"
            f"{'尚可' if submitted >= total_hw * 0.7 else '需要提升'}"
            f"（{submitted}/{total_hw}），"
        )
        if avg_acc is not None:
            content += f"平均正确率{_fmt_pct(avg_acc)}。"
        if weak_items and weak_items[0] != "暂无薄弱点数据":
            content += f"错题集中在：{'、'.join(weak_items[:3])}。"
        content += "建议加强审题和分步骤列式训练。"

        return self._base_response(
            intent="HOMEWORK_DIAGNOSIS",
            title="作业与错题诊断",
            content=content,
            sections=sections,
            evidence=evidence,
        )

    # ------------------------------------------------------------------
    # LESSON_FEEDBACK
    # ------------------------------------------------------------------

    async def _lesson_feedback(
        self, db: AsyncSession, request: AgentChatRequest
    ) -> AgentChatResponse:
        student_id = request.student_id
        lesson_id = request.params.lesson_id
        warnings: list[str] = []

        student = await get_student(db, student_id)
        if student is None:
            return self._base_response(
                intent="LESSON_FEEDBACK",
                title="课后反馈草稿",
                content="未找到该学生的学习数据。",
                sections=[AgentSection(name="提示", items=["请检查学生 ID 是否正确。"])],
                evidence=[],
            )

        if lesson_id:
            perf = await get_lesson_performance(db, student_id, lesson_id)
        else:
            # No lesson_id provided — use the most recent one
            recent_perfs = await get_lesson_performances(db, student_id, limit=1)
            perf = recent_perfs[0] if recent_perfs else None
            if perf:
                warnings.append(f"未指定 lesson_id，已自动使用最近课次：{perf.lesson_title or perf.lesson_id}。")

        if perf is None:
            return self._base_response(
                intent="LESSON_FEEDBACK",
                title="课后反馈草稿",
                content="暂无该课次的学习表现数据，可能尚未录入。",
                sections=[
                    AgentSection(name="提示", items=["该课次暂无数据，请确认 lesson_id 或等待数据录入。"]),
                ],
                evidence=[],
                warnings=warnings,
            )

        # ── build from real lesson performance ──
        sections: list[AgentSection] = []
        evidence: list[str] = []

        course_items = [perf.lesson_title or f"课次 {perf.lesson_id}"]
        if perf.attendance:
            course_items.append(f"出勤：{perf.attendance}")
        sections.append(AgentSection(name="课程内容", items=course_items))

        highlights: list[str] = []
        if perf.base_correct_rate is not None:
            highlights.append(f"基础题正确率 {_fmt_pct(perf.base_correct_rate)}")
            evidence.append(f"基础题正确率 {_fmt_pct(perf.base_correct_rate)}")
        if perf.interaction_score is not None:
            highlights.append(f"课堂互动评分 {perf.interaction_score}")
            evidence.append(f"课堂互动评分 {perf.interaction_score}")
        highlights = highlights or ["暂无详细评分"]
        sections.append(AgentSection(name="课堂亮点", items=highlights))

        suggestions: list[str] = []
        if perf.advanced_correct_rate is not None and perf.advanced_correct_rate < 0.8:
            suggestions.append("综合题建议课后巩固")
        if perf.notes:
            suggestions.append(perf.notes)
        suggestions = suggestions or ["继续保持当前节奏"]
        sections.append(AgentSection(name="课后建议", items=suggestions))

        content = (
            f"家长您好，{student.name}本节课主要学习了"
            f"{perf.lesson_title or '本课次内容'}。"
        )
        if perf.base_correct_rate is not None:
            content += f"基础题正确率{_fmt_pct(perf.base_correct_rate)}"
            content += "，表现较好。" if perf.base_correct_rate >= 0.8 else "，还需加强。"
        if perf.notes:
            content += f"备注：{perf.notes}"

        return self._base_response(
            intent="LESSON_FEEDBACK",
            title="课后反馈草稿",
            content=content,
            sections=sections,
            evidence=evidence,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # PARENT_REPLY
    # ------------------------------------------------------------------

    async def _parent_reply(
        self, db: AsyncSession, request: AgentChatRequest
    ) -> AgentChatResponse:
        student_id = request.student_id
        question = request.params.parent_question or request.message or "孩子最近有没有进步？"

        # high-risk keywords check
        high_risk_keywords = ["退费", "投诉", "举报", "换老师", "不想上"]
        if any(keyword in question for keyword in high_risk_keywords):
            return self._base_response(
                intent="PARENT_REPLY",
                title="高风险家长问题处理建议",
                content=(
                    "该问题涉及退费、投诉或强烈不满倾向，"
                    "建议先由老师了解具体原因，并同步主管后再统一回复。"
                ),
                sections=[
                    AgentSection(
                        name="内部处理建议",
                        items=["先了解具体不满点", "不承诺退款或补偿", "同步主管处理"],
                    )
                ],
                evidence=[f"家长原话：{question}"],
                warnings=["高风险场景不生成直接发送给家长的话术。"],
            )

        # ── query real data for the reply context ──
        student = await get_student(db, student_id)
        homeworks = await list_homeworks(db, student_id)
        wrong_stats = await get_wrong_question_stats(db, student_id, days=30)

        if student is None:
            return self._base_response(
                intent="PARENT_REPLY",
                title="家长问题回复草稿",
                content="未找到该学生的学习数据，无法生成回复建议。",
                sections=[AgentSection(name="提示", items=["请检查学生 ID 是否正确。"])],
                evidence=[],
            )

        # compute metrics
        total_hw = len(homeworks)
        submitted = sum(1 for h in homeworks if h.status in ("submitted", "late"))
        accuracies = [h.accuracy for h in homeworks if h.accuracy is not None]
        avg_acc = sum(accuracies) / len(accuracies) if accuracies else None
        top_wrong = [kp for kp, cnt in wrong_stats[:3] if cnt > 0]

        # build response
        reply_strategy: list[str] = ["先回应家长关心的问题"]
        evidence: list[str] = []

        if avg_acc is not None:
            reply_strategy.append("用近期正确率数据说明整体状态")
            evidence.append(f"平均正确率{_fmt_pct(avg_acc)}")
        if total_hw > 0:
            reply_strategy.append(f"用作业完成情况（{submitted}/{total_hw}）说明努力程度")
            evidence.append(f"近期{total_hw}次作业提交{submitted}次")
        if top_wrong:
            reply_strategy.append(f"指出薄弱环节：{'、'.join(top_wrong)}，并给出具体建议")
            evidence.append(f"薄弱知识点：{'、'.join(top_wrong)}")

        reply_strategy.append("给出下一步具体可行的建议")
        sections = [
            AgentSection(name="回复策略", items=reply_strategy),
            AgentSection(name="不建议表达", items=["孩子不认真", "基础太差", "很快就能提分"]),
        ]

        content = (
            f"家长您好，{student.name}近期"
            f"{'表现稳定' if avg_acc and avg_acc >= 0.7 else '在持续进步中'}。"
        )
        if avg_acc is not None:
            content += f"平均正确率{_fmt_pct(avg_acc)}，"
        if total_hw > 0:
            content += f"近{total_hw}次作业提交{submitted}次。"
        if top_wrong:
            content += f"目前需要重点关注{'、'.join(top_wrong[:2])}的巩固练习。"
        content += "建议课后固定时间复盘当天的错题，把订正过程写完整。"

        return self._base_response(
            intent="PARENT_REPLY",
            title="家长问题回复草稿",
            content=content,
            sections=sections,
            evidence=evidence,
        )