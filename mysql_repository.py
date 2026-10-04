from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Sequence

from db_config import DatabaseConfig
from rbac import DEFAULT_ROLE_PERMISSIONS, PERMISSIONS


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def load_env_file(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    import os

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class MySQLRepository:
    def __init__(self, config: DatabaseConfig | None = None):
        load_env_file()
        self.config = config or DatabaseConfig.from_env()

    def connect(self):
        import pymysql
        import pymysql.cursors

        kwargs = self.config.pymysql_kwargs.copy()
        kwargs["cursorclass"] = pymysql.cursors.DictCursor
        return pymysql.connect(**kwargs)

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def apply_migrations(self, migrations_dir: str | Path = "migrations") -> List[str]:
        applied: List[str] = []
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version VARCHAR(80) PRIMARY KEY,
                        applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
                cursor.execute("SELECT version FROM schema_migrations")
                existing = {row["version"] for row in cursor.fetchall()}
                for path in sorted(Path(migrations_dir).glob("*.sql")):
                    version = path.stem
                    if version in existing:
                        continue
                    for statement in _split_sql(path.read_text(encoding="utf-8")):
                        cursor.execute(statement)
                    cursor.execute("INSERT IGNORE INTO schema_migrations(version) VALUES (%s)", (version,))
                    applied.append(version)
        return applied

    def seed_roles_permissions(self) -> None:
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                for code in PERMISSIONS:
                    cursor.execute(
                        "INSERT IGNORE INTO permissions(code, description) VALUES (%s, %s)",
                        (code, code.replace(".", " ").title()),
                    )
                for role_name, permissions in DEFAULT_ROLE_PERMISSIONS.items():
                    cursor.execute(
                        "INSERT IGNORE INTO roles(name, description) VALUES (%s, %s)",
                        (role_name, f"Default {role_name} role"),
                    )
                    cursor.execute("SELECT id FROM roles WHERE name=%s", (role_name,))
                    role_id = cursor.fetchone()["id"]
                    for code in permissions:
                        cursor.execute("SELECT id FROM permissions WHERE code=%s", (code,))
                        permission_id = cursor.fetchone()["id"]
                        cursor.execute(
                            "INSERT IGNORE INTO role_permissions(role_id, permission_id) VALUES (%s, %s)",
                            (role_id, permission_id),
                        )

    def create_super_admin(self, *, name: str, username: str, email: str, password_hash: str) -> int:
        self.seed_roles_permissions()
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM roles WHERE name=%s", ("Super Admin",))
                role_id = cursor.fetchone()["id"]
                cursor.execute("SELECT id FROM users WHERE username=%s OR email=%s", (username, email))
                existing = cursor.fetchone()
                if existing:
                    return int(existing["id"])
                cursor.execute(
                    """
                    INSERT INTO users(name, username, email, password_hash, role_id, is_active)
                    VALUES (%s, %s, %s, %s, %s, 1)
                    """,
                    (name, username, email, password_hash, role_id),
                )
                user_id = int(cursor.lastrowid)
                self._audit(cursor, user_id, "users.create_super_admin", "users", user_id, None, {"email": email}, "")
                return user_id

    def find_user_for_login(self, identity: str) -> Dict[str, Any] | None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT u.*, r.name AS role_name
                    FROM users u
                    JOIN roles r ON r.id = u.role_id
                    WHERE (u.email = %s OR u.username = %s) AND u.deleted_at IS NULL
                    LIMIT 1
                    """,
                    (identity, identity),
                )
                return cursor.fetchone()

    def get_user_with_permissions(self, user_id: int) -> Dict[str, Any]:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT u.*, r.name AS role_name
                    FROM users u
                    JOIN roles r ON r.id = u.role_id
                    WHERE u.id = %s AND u.deleted_at IS NULL
                    """,
                    (user_id,),
                )
                user = cursor.fetchone()
                if not user:
                    raise LookupError("User not found.")
                cursor.execute(
                    """
                    SELECT p.code
                    FROM role_permissions rp
                    JOIN permissions p ON p.id = rp.permission_id
                    WHERE rp.role_id = %s
                    ORDER BY p.code
                    """,
                    (user["role_id"],),
                )
                user["permissions"] = [row["code"] for row in cursor.fetchall()]
                return user

    def record_failed_login(self, identity: str, ip_address: str = "", user_id: int | None = None) -> None:
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                if user_id:
                    cursor.execute(
                        "UPDATE users SET failed_login_count = failed_login_count + 1 WHERE id=%s",
                        (user_id,),
                    )
                self._audit(
                    cursor,
                    user_id,
                    "login.failed",
                    "users",
                    user_id,
                    None,
                    {"identity": identity},
                    ip_address,
                )

    def record_successful_login(self, user_id: int, ip_address: str = "") -> None:
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET last_login_at=%s, failed_login_count=0 WHERE id=%s",
                    (utc_now(), user_id),
                )
                self._audit(cursor, user_id, "login.success", "users", user_id, None, None, ip_address)

    def update_user_password(self, user_id: int, password_hash: str, acting_user_id: int | None = None) -> None:
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE users SET password_hash=%s WHERE id=%s", (password_hash, user_id))
                self._audit(
                    cursor,
                    acting_user_id or user_id,
                    "users.password_update",
                    "users",
                    user_id,
                    None,
                    {"password_hash": "updated"},
                    "",
                )

    def list_roles(self) -> List[Dict[str, Any]]:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, name, description FROM roles ORDER BY name")
                return list(cursor.fetchall())

    def create_user(
        self,
        *,
        name: str,
        username: str,
        email: str,
        password_hash: str,
        role_name: str,
        is_active: bool,
        acting_user_id: int | None,
    ) -> int:
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM roles WHERE name=%s", (role_name,))
                role = cursor.fetchone()
                if not role:
                    raise LookupError(f"Role not found: {role_name}")
                cursor.execute(
                    """
                    INSERT INTO users(name, username, email, password_hash, role_id, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (name, username, email, password_hash, role["id"], int(bool(is_active))),
                )
                user_id = int(cursor.lastrowid)
                self._audit(
                    cursor,
                    acting_user_id,
                    "users.create",
                    "users",
                    user_id,
                    None,
                    {"name": name, "username": username, "email": email, "role": role_name, "is_active": is_active},
                    "",
                )
                return user_id

    def list_users(self) -> List[Dict[str, Any]]:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT u.id, u.name, u.username, u.email, r.name AS role_name,
                           u.is_active, u.last_login_at, u.failed_login_count
                    FROM users u
                    JOIN roles r ON r.id = u.role_id
                    WHERE u.deleted_at IS NULL
                    ORDER BY u.id DESC
                    """
                )
                return list(cursor.fetchall())

    def list_manual_review_queue(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT sr.id, e.exam_name, e.exam_code, s.student_name, s.roll_number,
                           eq.question_number, eq.correct_option, sr.selected_option,
                           sr.detected_options, sr.response_status, sr.fill_percentages,
                           sr.confidence_score, os.annotated_image_path
                    FROM student_responses sr
                    JOIN exams e ON e.id = sr.exam_id
                    JOIN exam_questions eq ON eq.id = sr.question_id
                    LEFT JOIN students s ON s.id = sr.student_id
                    JOIN omr_sheets os ON os.id = sr.omr_sheet_id
                    WHERE sr.requires_manual_review = 1 AND sr.deleted_at IS NULL
                    ORDER BY sr.created_at DESC
                    LIMIT %s
                    """,
                    (int(limit),),
                )
                return list(cursor.fetchall())

    def class_wise_results(self, *, class_name: str = "", section: str = "", exam_code: str = "") -> List[Dict[str, Any]]:
        where = ["r.deleted_at IS NULL"]
        params: List[Any] = []
        if class_name:
            where.append("c.class_name = %s")
            params.append(class_name)
        if section:
            where.append("c.section = %s")
            params.append(section)
        if exam_code:
            where.append("e.exam_code = %s")
            params.append(exam_code)
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT c.academic_year, c.class_name, c.section, e.exam_name, e.subject,
                           s.roll_number, s.student_name, r.final_score, r.maximum_score,
                           r.percentage, r.grade, r.status, r.total_negative_marks, r.bonus_marks
                    FROM results r
                    JOIN exams e ON e.id = r.exam_id
                    LEFT JOIN students s ON s.id = r.student_id
                    LEFT JOIN classes c ON c.id = s.class_id
                    WHERE {' AND '.join(where)}
                    ORDER BY c.academic_year DESC, c.class_name, c.section, s.roll_number
                    """,
                    params,
                )
                return list(cursor.fetchall())

    def student_wise_results(self, *, search: str = "") -> List[Dict[str, Any]]:
        like = f"%{search}%"
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.student_name, s.roll_number, s.registration_number,
                           c.class_name, c.section, e.exam_name, e.subject,
                           r.final_score, r.maximum_score, r.percentage, r.grade, r.status,
                           os.source_image_path, os.annotated_image_path
                    FROM results r
                    JOIN exams e ON e.id = r.exam_id
                    LEFT JOIN students s ON s.id = r.student_id
                    LEFT JOIN classes c ON c.id = s.class_id
                    JOIN omr_sheets os ON os.id = r.omr_sheet_id
                    WHERE r.deleted_at IS NULL
                      AND (%s = '' OR s.student_name LIKE %s OR s.roll_number LIKE %s OR s.registration_number LIKE %s)
                    ORDER BY s.student_name, e.exam_date DESC, e.exam_name
                    LIMIT 500
                    """,
                    (search, like, like, like),
                )
                return list(cursor.fetchall())

    def exam_summary(self, *, exam_code: str = "") -> List[Dict[str, Any]]:
        where = ["r.deleted_at IS NULL"]
        params: List[Any] = []
        if exam_code:
            where.append("e.exam_code = %s")
            params.append(exam_code)
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT e.exam_name, e.exam_code, e.subject,
                           COUNT(r.id) AS total_students,
                           AVG(r.percentage) AS average_percentage,
                           MAX(r.final_score) AS highest_score,
                           MIN(r.final_score) AS lowest_score,
                           SUM(CASE WHEN r.percentage >= 33 THEN 1 ELSE 0 END) AS passed_students
                    FROM results r
                    JOIN exams e ON e.id = r.exam_id
                    WHERE {' AND '.join(where)}
                    GROUP BY e.id, e.exam_name, e.exam_code, e.subject
                    ORDER BY e.created_at DESC
                    """,
                    params,
                )
                return list(cursor.fetchall())

    def audit_log(
        self,
        user_id: int | None,
        action: str,
        entity_type: str | None,
        entity_id: Any,
        old_values: Any,
        new_values: Any,
        ip_address: str = "",
    ) -> None:
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                self._audit(cursor, user_id, action, entity_type, entity_id, old_values, new_values, ip_address)

    def save_legacy_batch(
        self,
        *,
        batch_id: str,
        exam_title: str,
        default_class: str,
        answer_key: Mapping[int, str],
        records: Sequence[Mapping[str, Any]],
        exam_config: Mapping[str, Any] | None = None,
        question_rules: Mapping[int, Any] | None = None,
        acting_user_id: int | None = None,
    ) -> None:
        config = exam_config or {}
        with self.transaction() as connection:
            with connection.cursor() as cursor:
                class_id = self._ensure_class(cursor, default_class or "unknown_class", "", datetime.now().year)
                exam_id = self._ensure_exam(cursor, batch_id, exam_title, class_id, answer_key, config, acting_user_id)
                question_ids = self._ensure_questions(cursor, exam_id, answer_key, question_rules or {})
                cursor.execute(
                    """
                    INSERT INTO omr_upload_batches(
                        exam_id, batch_name, uploaded_by, total_files, processed_files, failed_files, status, completed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'COMPLETED', %s)
                    """,
                    (exam_id, batch_id, acting_user_id, len(records), len(records), 0, utc_now()),
                )
                batch_pk = int(cursor.lastrowid)
                for row in records:
                    row_class = str(row.get("class_name") or default_class or "unknown_class")
                    row_section = str(row.get("section") or "")
                    row_class_id = self._ensure_class(cursor, row_class, row_section, datetime.now().year)
                    student_id = self._ensure_student(
                        cursor,
                        row_class_id,
                        row_section,
                        str(row.get("roll") or row.get("record_id") or ""),
                        str(row.get("name") or "Unknown Student"),
                    )
                    cursor.execute(
                        """
                        INSERT INTO omr_sheets(
                            batch_id, exam_id, student_id, source_image_path, aligned_image_path,
                            annotated_image_path, detected_roll_number, detection_confidence,
                            processing_status, review_status, processed_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PROCESSED', %s, %s)
                        """,
                        (
                            batch_pk,
                            exam_id,
                            student_id,
                            row.get("original_image") or row.get("staging_original") or "",
                            row.get("staging_aligned") or "",
                            row.get("marked_image") or row.get("staging_marked") or "",
                            row.get("roll") or "",
                            Decimal(str(row.get("alignment_confidence") or 0)),
                            "REQUIRED" if row.get("review_required") else "NOT_REQUIRED",
                            utc_now(),
                        ),
                    )
                    sheet_id = int(cursor.lastrowid)
                    evaluation = row.get("evaluation") or {}
                    responses = evaluation.get("responses") or row.get("answers") or {}
                    for question_no, response in responses.items():
                        q_no = int(question_no)
                        if q_no not in question_ids:
                            continue
                        self._insert_response(cursor, sheet_id, exam_id, student_id, question_ids[q_no], response)
                    cursor.execute(
                        """
                        INSERT INTO results(
                            exam_id, student_id, omr_sheet_id, raw_positive_marks, total_negative_marks,
                            bonus_marks, raw_calculated_score, final_score, maximum_score, percentage,
                            grade, status, evaluated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'UNPUBLISHED', %s)
                        ON DUPLICATE KEY UPDATE
                            omr_sheet_id=VALUES(omr_sheet_id),
                            raw_positive_marks=VALUES(raw_positive_marks),
                            total_negative_marks=VALUES(total_negative_marks),
                            bonus_marks=VALUES(bonus_marks),
                            raw_calculated_score=VALUES(raw_calculated_score),
                            final_score=VALUES(final_score),
                            maximum_score=VALUES(maximum_score),
                            percentage=VALUES(percentage),
                            updated_at=CURRENT_TIMESTAMP
                        """,
                        (
                            exam_id,
                            student_id,
                            sheet_id,
                            evaluation.get("raw_positive_marks", row.get("score", 0)),
                            evaluation.get("total_negative_marks", 0),
                            evaluation.get("bonus_marks", 0),
                            evaluation.get("raw_calculated_score", row.get("score", 0)),
                            evaluation.get("final_score", row.get("score", 0)),
                            evaluation.get("maximum_score", row.get("total_questions", 0)),
                            evaluation.get("percentage", row.get("percentage", 0)),
                            row.get("grade"),
                            utc_now(),
                        ),
                    )
                self._audit(cursor, acting_user_id, "omr.batch_finalised", "omr_upload_batches", batch_pk, None, {"batch_id": batch_id}, "")

    def _ensure_class(self, cursor: Any, class_name: str, section: str, academic_year: Any) -> int:
        cursor.execute(
            """
            INSERT INTO classes(class_name, section, academic_year, status)
            VALUES (%s, %s, %s, 'ACTIVE')
            ON DUPLICATE KEY UPDATE updated_at=CURRENT_TIMESTAMP
            """,
            (class_name, section or "", str(academic_year)),
        )
        cursor.execute(
            "SELECT id FROM classes WHERE class_name=%s AND section=%s AND academic_year=%s",
            (class_name, section or "", str(academic_year)),
        )
        return int(cursor.fetchone()["id"])

    def _ensure_student(self, cursor: Any, class_id: int, section: str, roll: str, name: str) -> int:
        cursor.execute(
            """
            INSERT INTO students(student_name, roll_number, class_id, section, status)
            VALUES (%s, %s, %s, %s, 'ACTIVE')
            ON DUPLICATE KEY UPDATE student_name=VALUES(student_name), updated_at=CURRENT_TIMESTAMP
            """,
            (name or "Unknown Student", roll or "unknown", class_id, section or ""),
        )
        cursor.execute(
            "SELECT id FROM students WHERE class_id=%s AND section=%s AND roll_number=%s",
            (class_id, section or "", roll or "unknown"),
        )
        return int(cursor.fetchone()["id"])

    def _ensure_exam(
        self,
        cursor: Any,
        batch_id: str,
        exam_title: str,
        class_id: int,
        answer_key: Mapping[int, str],
        config: Mapping[str, Any],
        acting_user_id: int | None,
    ) -> int:
        exam_code = str(config.get("exam_code") or batch_id)
        cursor.execute(
            """
            INSERT INTO exams(
                exam_name, exam_code, class_id, subject, total_questions, default_question_points,
                negative_marking_enabled, negative_mark_value, bubble_fill_threshold,
                low_confidence_review_enabled, low_confidence_lower_bound, low_confidence_upper_bound,
                dropped_question_mode, allow_negative_total_score, status, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'DRAFT', %s)
            ON DUPLICATE KEY UPDATE
                exam_name=VALUES(exam_name),
                total_questions=VALUES(total_questions),
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                exam_title or "Exam Results",
                exam_code,
                class_id,
                config.get("subject", ""),
                int(config.get("total_questions") or len(answer_key)),
                config.get("default_question_points", 1),
                int(bool(config.get("negative_marking_enabled", False))),
                config.get("negative_mark_value", 0),
                config.get("bubble_fill_threshold", 40),
                int(bool(config.get("low_confidence_review_enabled", False))),
                config.get("low_confidence_lower_bound", 30),
                config.get("low_confidence_upper_bound", 39.99),
                config.get("dropped_question_mode", "TOTAL_SHIFT"),
                int(bool(config.get("allow_negative_total_score", True))),
                acting_user_id,
            ),
        )
        cursor.execute("SELECT id FROM exams WHERE exam_code=%s", (exam_code,))
        return int(cursor.fetchone()["id"])

    def _ensure_questions(self, cursor: Any, exam_id: int, answer_key: Mapping[int, str], question_rules: Mapping[int, Any]) -> Dict[int, int]:
        question_ids: Dict[int, int] = {}
        for question_no, answer in answer_key.items():
            rule = question_rules.get(int(question_no))
            points = _rule_value(rule, "points", None)
            status = _rule_value(rule, "status", "NORMAL")
            custom_negative = _rule_value(rule, "custom_negative_mark", None)
            notes = _rule_value(rule, "notes", "")
            correct_option = _rule_value(rule, "correct_option", answer)
            cursor.execute(
                """
                INSERT INTO exam_questions(exam_id, question_number, correct_option, points, status, custom_negative_mark, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    correct_option=VALUES(correct_option),
                    points=VALUES(points),
                    status=VALUES(status),
                    custom_negative_mark=VALUES(custom_negative_mark),
                    notes=VALUES(notes),
                    updated_at=CURRENT_TIMESTAMP
                """,
                (exam_id, int(question_no), correct_option or "", points, status, custom_negative, notes),
            )
            cursor.execute(
                "SELECT id FROM exam_questions WHERE exam_id=%s AND question_number=%s",
                (exam_id, int(question_no)),
            )
            question_ids[int(question_no)] = int(cursor.fetchone()["id"])
        return question_ids

    def _insert_response(self, cursor: Any, sheet_id: int, exam_id: int, student_id: int, question_id: int, response: Mapping[str, Any]) -> None:
        cursor.execute(
            """
            INSERT INTO student_responses(
                omr_sheet_id, exam_id, student_id, question_id, selected_option, detected_options,
                response_status, fill_percentages, confidence_score, awarded_marks, penalty_marks,
                final_marks, requires_manual_review
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                sheet_id,
                exam_id,
                student_id,
                question_id,
                response.get("selected_option") or None,
                json.dumps(response.get("detected_options") or [], ensure_ascii=False),
                response.get("response_status") or response.get("status") or "UNKNOWN",
                json.dumps(response.get("fill_percentages") or response.get("ink_ratios") or {}, ensure_ascii=False),
                response.get("confidence_score", response.get("confidence", 0)),
                response.get("awarded_marks", 0),
                response.get("penalty_marks", 0),
                response.get("final_marks", 0),
                int(bool(response.get("requires_manual_review", False))),
            ),
        )

    def _audit(
        self,
        cursor: Any,
        user_id: int | None,
        action: str,
        entity_type: str | None,
        entity_id: Any,
        old_values: Any,
        new_values: Any,
        ip_address: str,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO audit_logs(user_id, action, entity_type, entity_id, old_values, new_values, ip_address)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                action,
                entity_type,
                str(entity_id) if entity_id is not None else None,
                json.dumps(old_values, ensure_ascii=False) if old_values is not None else None,
                json.dumps(new_values, ensure_ascii=False) if new_values is not None else None,
                ip_address or None,
            ),
        )


def _split_sql(sql: str) -> List[str]:
    statements: List[str] = []
    current: List[str] = []
    in_string: str | None = None
    previous = ""
    for char in sql:
        if char in {"'", '"'} and previous != "\\":
            in_string = None if in_string == char else char if in_string is None else in_string
        if char == ";" and in_string is None:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        previous = char
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _rule_value(rule: Any, name: str, default: Any) -> Any:
    if not rule:
        return default
    if isinstance(rule, Mapping):
        return rule.get(name, default)
    return getattr(rule, name, default)
