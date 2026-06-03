"""Data provider backed by real MySQL queries."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.queries import (
    get_homework,
    get_student,
    list_classes,
    list_homeworks,
    list_students,
)
from app.models import HomeworkModel, StudentModel
from app.schemas.student import (
    AiAssistRequest,
    AiAssistResponse,
    ClassInfo,
    HomeworkDetail,
    HomeworkSummary,
    StudentDetail,
    StudentStats,
    StudentSummary,
)


def _to_class_info(model) -> ClassInfo:
    return ClassInfo(id=model.id, name=model.name, grade=model.grade)


def _to_student_summary(model: StudentModel) -> StudentSummary:
    return StudentSummary(id=model.id, name=model.name, status=model.status)


def _to_student_detail(model: StudentModel) -> StudentDetail:
    return StudentDetail(
        id=model.id,
        name=model.name,
        grade=model.grade,
        class_id=model.class_id,
        stats=StudentStats(
            homework_completed=model.homework_completed,
            homework_total=model.homework_total,
            accuracy_avg=model.accuracy_avg,
            last_active=str(model.last_active),
        ),
    )


def _to_homework_summary(model: HomeworkModel) -> HomeworkSummary:
    return HomeworkSummary(
        id=model.id,
        title=model.title,
        subject=model.subject,
        assigned_at=str(model.assigned_at),
        due_at=str(model.due_at),
        status=model.status,
        accuracy=model.accuracy,
    )


def _to_homework_detail(model: HomeworkModel) -> HomeworkDetail:
    detail = model.detail
    questions = [q.question_text for q in detail.questions] if detail else []
    return HomeworkDetail(
        id=model.id,
        title=model.title,
        subject=model.subject,
        assigned_at=str(model.assigned_at),
        due_at=str(model.due_at),
        status=model.status,
        accuracy=model.accuracy,
        wrong_count=detail.wrong_count if detail else 0,
        notes=detail.notes if detail else "",
        questions=questions,
    )


class StudentService:
    """Stateless service — all data comes from the database via the provided session."""

    async def get_classes(self, db: AsyncSession) -> list[ClassInfo]:
        return [_to_class_info(c) for c in await list_classes(db)]

    async def get_students(self, db: AsyncSession, class_id: str) -> list[StudentSummary]:
        return [_to_student_summary(s) for s in await list_students(db, class_id)]

    async def get_student_detail(self, db: AsyncSession, student_id: str) -> StudentDetail | None:
        s = await get_student(db, student_id)
        return _to_student_detail(s) if s else None

    async def get_homeworks(self, db: AsyncSession, student_id: str) -> list[HomeworkSummary]:
        return [_to_homework_summary(h) for h in await list_homeworks(db, student_id)]

    async def get_homework_detail(self, db: AsyncSession, homework_id: str) -> HomeworkDetail | None:
        h = await get_homework(db, homework_id)
        return _to_homework_detail(h) if h else None

    async def assist(self, db: AsyncSession, request: AiAssistRequest) -> AiAssistResponse:
        """Generate an AI-assisted reply draft based on real student/homework data."""
        student = await get_student(db, request.student_id)

        if student is None:
            return AiAssistResponse(
                request_id=f"ai_{uuid4().hex[:10]}",
                draft="未找到该学生的学习数据。",
                tips=["请检查学生 ID 是否正确。"],
            )

        homework = None
        if request.homework_id:
            homework = await get_homework(db, request.homework_id)

        # Build draft from real data
        draft_parts: list[str] = [f"家长您好，这是关于{student.name}近期的学习反馈。"]

        if homework:
            draft_parts.append(
                f"最近一次作业《{homework.title}》"
                f"状态为{homework.status}"
            )
            if homework.accuracy is not None:
                draft_parts.append(f"，正确率{round(homework.accuracy * 100)}%")
            if homework.detail and homework.detail.notes:
                draft_parts.append(f"。{homework.detail.notes}")
            else:
                draft_parts.append("。")

        draft_parts.append(
            f"孩子整体上基础题表现较稳，但建议课后固定时间复盘错题，"
            f"并把订正过程写完整。"
        )

        tips = [
            "先肯定基础表现，再提醒需要关注的点。",
            "避免使用绝对化表达。",
            "建议给出可执行的小动作。",
        ]

        if homework and homework.detail:
            if homework.detail.wrong_count > 3:
                tips.append(f"本次作业错题较多（{homework.detail.wrong_count}道），建议逐题分析。")
            else:
                tips.append(f"本次作业错题{homework.detail.wrong_count}道，继续保持。")

        return AiAssistResponse(
            request_id=f"ai_{uuid4().hex[:10]}",
            draft="".join(draft_parts),
            tips=tips,
        )