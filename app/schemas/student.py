"""Student, class, and homework schemas."""

from typing import Literal

from pydantic import BaseModel, Field


HomeworkStatus = Literal["pending", "submitted", "late", "missing"]


class ClassInfo(BaseModel):
    """Class summary used in dropdown selectors."""

    id: str
    name: str
    grade: str


class StudentSummary(BaseModel):
    """Student summary used in list views."""

    id: str
    name: str
    status: str = Field(default="active")


class StudentStats(BaseModel):
    """Aggregated learning stats for a student."""

    homework_completed: int
    homework_total: int
    accuracy_avg: float
    last_active: str


class StudentDetail(BaseModel):
    """Student detail for the profile panel."""

    id: str
    name: str
    grade: str
    class_id: str
    stats: StudentStats


class HomeworkSummary(BaseModel):
    """Homework summary for list views."""

    id: str
    title: str
    subject: str
    assigned_at: str
    due_at: str
    status: HomeworkStatus
    accuracy: float | None = None


class HomeworkDetail(BaseModel):
    """Homework detail for the detail panel."""

    id: str
    title: str
    subject: str
    assigned_at: str
    due_at: str
    status: HomeworkStatus
    accuracy: float | None = None
    wrong_count: int
    notes: str
    questions: list[str] = Field(default_factory=list)


class AiAssistRequest(BaseModel):
    """Request payload for AI assist endpoint."""

    student_id: str
    homework_id: str | None = None
    prompt: str


class AiAssistResponse(BaseModel):
    """Response payload for AI assist endpoint."""

    request_id: str
    draft: str
    tips: list[str] = Field(default_factory=list)