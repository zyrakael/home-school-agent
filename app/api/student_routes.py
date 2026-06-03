"""API endpoints for classes, students, and homework — backed by MySQL."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.schemas.student import (
    AiAssistRequest,
    AiAssistResponse,
    ClassInfo,
    HomeworkDetail,
    HomeworkSummary,
    StudentDetail,
    StudentSummary,
)
from app.services.student_service import StudentService

router = APIRouter(prefix="/api", tags=["data"])
service = StudentService()


@router.get("/classes", response_model=list[ClassInfo])
async def list_classes(db: AsyncSession = Depends(get_db)) -> list[ClassInfo]:
    return await service.get_classes(db)


@router.get("/classes/{class_id}/students", response_model=list[StudentSummary])
async def list_students(class_id: str, db: AsyncSession = Depends(get_db)) -> list[StudentSummary]:
    return await service.get_students(db, class_id)


@router.get("/students/{student_id}", response_model=StudentDetail)
async def get_student(student_id: str, db: AsyncSession = Depends(get_db)) -> StudentDetail:
    student = await service.get_student_detail(db, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@router.get("/students/{student_id}/homeworks", response_model=list[HomeworkSummary])
async def list_homeworks(student_id: str, db: AsyncSession = Depends(get_db)) -> list[HomeworkSummary]:
    return await service.get_homeworks(db, student_id)


@router.get("/homeworks/{homework_id}", response_model=HomeworkDetail)
async def get_homework(homework_id: str, db: AsyncSession = Depends(get_db)) -> HomeworkDetail:
    homework = await service.get_homework_detail(db, homework_id)
    if not homework:
        raise HTTPException(status_code=404, detail="Homework not found")
    return homework


@router.post("/ai/assist", response_model=AiAssistResponse)
async def assist(request: AiAssistRequest, db: AsyncSession = Depends(get_db)) -> AiAssistResponse:
    return await service.assist(db, request)
