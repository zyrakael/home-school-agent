"""SQLAlchemy ORM models for home-school agent."""

from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ClassModel(Base):
    __tablename__ = "classes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    grade: Mapped[str] = mapped_column(String(32))

    students: Mapped[list["StudentModel"]] = relationship(back_populates="cls")


class StudentModel(Base):
    __tablename__ = "students"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    class_id: Mapped[str] = mapped_column(String(32), ForeignKey("classes.id"))
    status: Mapped[str] = mapped_column(String(16), default="active")
    grade: Mapped[str] = mapped_column(String(32))
    homework_completed: Mapped[int] = mapped_column(Integer, default=0)
    homework_total: Mapped[int] = mapped_column(Integer, default=0)
    accuracy_avg: Mapped[float] = mapped_column(Float, default=0)
    last_active: Mapped[date] = mapped_column(Date)

    cls: Mapped[ClassModel] = relationship(back_populates="students")
    homeworks: Mapped[list["HomeworkModel"]] = relationship(back_populates="student")
    wrong_questions: Mapped[list["WrongQuestionModel"]] = relationship(
        back_populates="student"
    )


class HomeworkModel(Base):
    __tablename__ = "homeworks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    student_id: Mapped[str] = mapped_column(String(32), ForeignKey("students.id"))
    title: Mapped[str] = mapped_column(String(128))
    subject: Mapped[str] = mapped_column(String(32))
    assigned_at: Mapped[date] = mapped_column(Date)
    due_at: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)

    student: Mapped[StudentModel] = relationship(back_populates="homeworks")
    detail: Mapped["HomeworkDetailModel | None"] = relationship(
        back_populates="homework",
        uselist=False,
    )
    wrong_questions: Mapped[list["WrongQuestionModel"]] = relationship(
        back_populates="homework"
    )


class HomeworkDetailModel(Base):
    __tablename__ = "homework_details"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    homework_id: Mapped[str] = mapped_column(String(32), ForeignKey("homeworks.id"))
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(String(512), default="")

    homework: Mapped[HomeworkModel] = relationship(back_populates="detail")
    questions: Mapped[list["HomeworkQuestionModel"]] = relationship(back_populates="detail")


class HomeworkQuestionModel(Base):
    __tablename__ = "homework_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    homework_detail_id: Mapped[str] = mapped_column(String(32), ForeignKey("homework_details.id"))
    question_text: Mapped[str] = mapped_column(String(512))

    detail: Mapped[HomeworkDetailModel] = relationship(back_populates="questions")


class LessonPerformanceModel(Base):
    __tablename__ = "lesson_performances"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    student_id: Mapped[str] = mapped_column(String(32), ForeignKey("students.id"))
    lesson_id: Mapped[str] = mapped_column(String(32))
    lesson_title: Mapped[str] = mapped_column(String(128), default="")
    attendance: Mapped[str] = mapped_column(String(16), default="present")
    interaction_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_correct_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    advanced_correct_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(String(512), default="")


class WrongQuestionModel(Base):
    __tablename__ = "wrong_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(String(32), ForeignKey("students.id"))
    homework_id: Mapped[str] = mapped_column(String(32), ForeignKey("homeworks.id"))
    knowledge_point: Mapped[str] = mapped_column(String(128))
    question_type: Mapped[str] = mapped_column(String(32), default="")
    reason_tag: Mapped[str] = mapped_column(String(64), default="")
    difficulty: Mapped[str] = mapped_column(String(16), default="medium")
    is_corrected: Mapped[bool] = mapped_column(default=False)

    student: Mapped[StudentModel] = relationship(back_populates="wrong_questions")
    homework: Mapped[HomeworkModel] = relationship(back_populates="wrong_questions")
