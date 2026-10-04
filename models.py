from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    DECIMAL,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    permissions: Mapped[list["RolePermission"]] = relationship(back_populates="role", cascade="all, delete-orphan")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    roles: Mapped[list["RolePermission"]] = relationship(back_populates="permission", cascade="all, delete-orphan")


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[Role] = relationship(back_populates="permissions")
    permission: Mapped[Permission] = relationship(back_populates="roles")


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_username", "username"),
        Index("ix_users_email", "email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(190), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[DateTime | None] = mapped_column(DateTime)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    role: Mapped[Role] = relationship()


class AcademicClass(Base, TimestampMixin):
    __tablename__ = "classes"
    __table_args__ = (
        UniqueConstraint("class_name", "section", "academic_year", name="uq_class_section_year"),
        Index("ix_classes_year", "academic_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_name: Mapped[str] = mapped_column(String(80), nullable=False)
    section: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    academic_year: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)


class Student(Base, TimestampMixin):
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("class_id", "section", "roll_number", name="uq_student_roll_class_section"),
        Index("ix_students_registration", "registration_number"),
        Index("ix_students_name", "student_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_name: Mapped[str] = mapped_column(String(180), nullable=False)
    roll_number: Mapped[str] = mapped_column(String(50), nullable=False)
    registration_number: Mapped[str | None] = mapped_column(String(80), unique=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False)
    section: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    guardian_name: Mapped[str | None] = mapped_column(String(180))
    guardian_phone: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)
    academic_class: Mapped[AcademicClass] = relationship()


class GradeScale(Base, TimestampMixin):
    __tablename__ = "grade_scales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    minimum_percentage: Mapped[DECIMAL] = mapped_column(DECIMAL(8, 4), nullable=False)
    maximum_percentage: Mapped[DECIMAL] = mapped_column(DECIMAL(8, 4), nullable=False)
    letter_grade: Mapped[str] = mapped_column(String(20), nullable=False)
    grade_point: Mapped[DECIMAL | None] = mapped_column(DECIMAL(6, 3))
    remarks: Mapped[str | None] = mapped_column(String(255))


class Exam(Base, TimestampMixin):
    __tablename__ = "exams"
    __table_args__ = (
        UniqueConstraint("exam_code", name="uq_exam_code"),
        Index("ix_exams_class_subject", "class_id", "subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_name: Mapped[str] = mapped_column(String(180), nullable=False)
    exam_code: Mapped[str] = mapped_column(String(80), nullable=False)
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id"))
    subject: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    exam_date: Mapped[Date | None] = mapped_column(Date)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    default_question_points: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 4), default=1, nullable=False)
    negative_marking_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    negative_mark_value: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 4), default=0, nullable=False)
    bubble_fill_threshold: Mapped[DECIMAL] = mapped_column(DECIMAL(8, 4), default=40, nullable=False)
    low_confidence_review_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    low_confidence_lower_bound: Mapped[DECIMAL] = mapped_column(DECIMAL(8, 4), default=30, nullable=False)
    low_confidence_upper_bound: Mapped[DECIMAL] = mapped_column(DECIMAL(8, 4), default=39.99, nullable=False)
    dropped_question_mode: Mapped[str] = mapped_column(String(40), default="TOTAL_SHIFT", nullable=False)
    allow_negative_total_score: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    grade_scale_id: Mapped[int | None] = mapped_column(ForeignKey("grade_scales.id"))
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    class_: Mapped[AcademicClass | None] = relationship()
    questions: Mapped[list["ExamQuestion"]] = relationship(back_populates="exam", cascade="all, delete-orphan")


class ExamQuestion(Base, TimestampMixin):
    __tablename__ = "exam_questions"
    __table_args__ = (UniqueConstraint("exam_id", "question_number", name="uq_exam_question_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    question_number: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_option: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    points: Mapped[DECIMAL | None] = mapped_column(DECIMAL(10, 4))
    status: Mapped[str] = mapped_column(String(30), default="NORMAL", nullable=False)
    custom_negative_mark: Mapped[DECIMAL | None] = mapped_column(DECIMAL(10, 4))
    notes: Mapped[str | None] = mapped_column(Text)
    exam: Mapped[Exam] = relationship(back_populates="questions")


class OmrUploadBatch(Base):
    __tablename__ = "omr_upload_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"), nullable=False)
    batch_name: Mapped[str] = mapped_column(String(180), nullable=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    total_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime)


class OmrSheet(Base):
    __tablename__ = "omr_sheets"
    __table_args__ = (Index("ix_omr_sheets_exam_student", "exam_id", "student_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("omr_upload_batches.id"), nullable=False)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"), nullable=False)
    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id"))
    source_image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    aligned_image_path: Mapped[str | None] = mapped_column(String(500))
    annotated_image_path: Mapped[str | None] = mapped_column(String(500))
    detected_roll_number: Mapped[str | None] = mapped_column(String(80))
    detection_confidence: Mapped[DECIMAL] = mapped_column(DECIMAL(8, 4), default=0, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    review_status: Mapped[str] = mapped_column(String(30), default="NOT_REQUIRED", nullable=False)
    processed_at: Mapped[DateTime | None] = mapped_column(DateTime)


class StudentResponse(Base, TimestampMixin):
    __tablename__ = "student_responses"
    __table_args__ = (
        UniqueConstraint("omr_sheet_id", "question_id", name="uq_response_sheet_question"),
        Index("ix_responses_exam_student", "exam_id", "student_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    omr_sheet_id: Mapped[int] = mapped_column(ForeignKey("omr_sheets.id", ondelete="CASCADE"), nullable=False)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"), nullable=False)
    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id"))
    question_id: Mapped[int] = mapped_column(ForeignKey("exam_questions.id"), nullable=False)
    selected_option: Mapped[str | None] = mapped_column(String(20))
    detected_options: Mapped[dict | None] = mapped_column(JSON)
    response_status: Mapped[str] = mapped_column(String(40), nullable=False)
    fill_percentages: Mapped[dict | None] = mapped_column(JSON)
    confidence_score: Mapped[DECIMAL] = mapped_column(DECIMAL(8, 4), default=0, nullable=False)
    awarded_marks: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 4), default=0, nullable=False)
    penalty_marks: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 4), default=0, nullable=False)
    final_marks: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 4), default=0, nullable=False)
    requires_manual_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[DateTime | None] = mapped_column(DateTime)


class Result(Base, TimestampMixin):
    __tablename__ = "results"
    __table_args__ = (
        UniqueConstraint("exam_id", "student_id", name="uq_result_exam_student"),
        Index("ix_results_exam_status", "exam_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"), nullable=False)
    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id"))
    omr_sheet_id: Mapped[int] = mapped_column(ForeignKey("omr_sheets.id"), nullable=False)
    raw_positive_marks: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 4), default=0, nullable=False)
    total_negative_marks: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 4), default=0, nullable=False)
    bonus_marks: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 4), default=0, nullable=False)
    raw_calculated_score: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 4), default=0, nullable=False)
    final_score: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 4), default=0, nullable=False)
    maximum_score: Mapped[DECIMAL] = mapped_column(DECIMAL(10, 4), default=0, nullable=False)
    percentage: Mapped[DECIMAL] = mapped_column(DECIMAL(8, 4), default=0, nullable=False)
    grade: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="UNPUBLISHED", nullable=False)
    evaluated_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    published_at: Mapped[DateTime | None] = mapped_column(DateTime)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(80))
    old_values: Mapped[dict | None] = mapped_column(JSON)
    new_values: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
