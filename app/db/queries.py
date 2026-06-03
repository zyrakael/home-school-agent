"""Read-only database queries for student and homework data."""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ClassModel,
    HomeworkDetailModel,
    HomeworkModel,
    LessonPerformanceModel,
    StudentModel,
    WrongQuestionModel,
)


async def list_classes(db: AsyncSession) -> list[ClassModel]:
    result = await db.execute(select(ClassModel).order_by(ClassModel.id))
    return list(result.scalars().all())


async def list_students(db: AsyncSession, class_id: str) -> list[StudentModel]:
    result = await db.execute(
        select(StudentModel)
        .where(StudentModel.class_id == class_id)
        .order_by(StudentModel.id)
    )
    return list(result.scalars().all())


async def get_student(db: AsyncSession, student_id: str) -> StudentModel | None:
    result = await db.execute(
        select(StudentModel).where(StudentModel.id == student_id)
    )
    return result.scalar_one_or_none()


async def list_homeworks(db: AsyncSession, student_id: str) -> list[HomeworkModel]:
    result = await db.execute(
        select(HomeworkModel)
        .where(HomeworkModel.student_id == student_id)
        .order_by(HomeworkModel.assigned_at.desc(), HomeworkModel.id.desc())
    )
    return list(result.scalars().all())


async def get_homework(db: AsyncSession, homework_id: str) -> HomeworkModel | None:
    detail_loader = selectinload(HomeworkModel.detail).selectinload(
        HomeworkDetailModel.questions
    )
    result = await db.execute(
        select(HomeworkModel)
        .where(HomeworkModel.id == homework_id)
        .options(detail_loader)
    )
    return result.scalar_one_or_none()


async def get_recent_homeworks(
    db: AsyncSession, student_id: str, days: int = 14
) -> list[HomeworkModel]:
    """Get homeworks from the last N days."""
    cutoff = date.today() - timedelta(days=days)
    result = await db.execute(
        select(HomeworkModel)
        .where(
            HomeworkModel.student_id == student_id,
            HomeworkModel.assigned_at >= cutoff,
        )
        .options(selectinload(HomeworkModel.detail))
        .order_by(HomeworkModel.assigned_at.desc(), HomeworkModel.id.desc())
    )
    return list(result.scalars().all())


async def get_wrong_questions(
    db: AsyncSession, student_id: str, limit: int = 20
) -> list[WrongQuestionModel]:
    """Get recent wrong questions for a student."""
    result = await db.execute(
        select(WrongQuestionModel)
        .where(WrongQuestionModel.student_id == student_id)
        .order_by(WrongQuestionModel.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_lesson_performances(
    db: AsyncSession, student_id: str, limit: int = 10
) -> list[LessonPerformanceModel]:
    """Get recent lesson performances for a student."""
    result = await db.execute(
        select(LessonPerformanceModel)
        .where(LessonPerformanceModel.student_id == student_id)
        .order_by(LessonPerformanceModel.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_lesson_performance(
    db: AsyncSession, student_id: str, lesson_id: str
) -> LessonPerformanceModel | None:
    """Get a specific lesson performance record."""
    result = await db.execute(
        select(LessonPerformanceModel)
        .where(
            LessonPerformanceModel.student_id == student_id,
            LessonPerformanceModel.lesson_id == lesson_id,
        )
    )
    return result.scalar_one_or_none()


async def get_wrong_question_stats(
    db: AsyncSession, student_id: str, days: int = 30
) -> list[tuple[str, int]]:
    """Get wrong-question counts grouped by knowledge point."""
    cutoff = date.today() - timedelta(days=days)
    count_wrong_questions = func.count(WrongQuestionModel.id)
    result = await db.execute(
        select(
            WrongQuestionModel.knowledge_point,
            count_wrong_questions.label("cnt"),
        )
        .where(
            WrongQuestionModel.student_id == student_id,
            WrongQuestionModel.homework.has(HomeworkModel.assigned_at >= cutoff),
        )
        .group_by(WrongQuestionModel.knowledge_point)
        .order_by(count_wrong_questions.desc())
    )
    return [(row.knowledge_point, row.cnt) for row in result.all()]
