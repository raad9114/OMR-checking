from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence

import gradio as gr

from auth import AuthenticationError, authenticate, change_password, hash_password
from batch_processor import (
    extract_answer_key_from_sheet,
    finalise_batch,
    normalise_answer_key,
    normalise_question_rules,
    process_uploads,
)
from evaluation_service import ExamGradingConfig, QUESTION_DROPPED, QUESTION_FAULTY, QUESTION_NORMAL
from mysql_repository import MySQLRepository
from rbac import AuthorizationError, UserPrincipal, require_permission


ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = ROOT / "template.json"
DEFAULT_REFERENCE = ROOT / "sample_images" / "reference_form.jpeg"
WORKSPACE_ROOT = ROOT / "workspace"
OUTPUT_ROOT = ROOT / "outputs"
DATABASE_PATH = None

ANSWER_CHOICES = ["", "à¦•", "à¦–", "à¦—", "à¦˜"]
MAX_QUESTIONS = 30
RESULT_HEADERS = [
    "Record ID", "Source File", "Class", "Roll", "Student Name", "Section",
    "Marks", "Total", "Percentage", "Review Required", "Correct", "Incorrect",
    "Multiple", "Blank", "Low Confidence", "Faulty Bonus", "Dropped Bonus", "Negative Marks",
]
QUESTION_HEADERS = ["Question", "Correct Answer", "Marks", "Status", "Custom Penalty", "Notes"]


def default_key_rows() -> List[List[Any]]:
    return [[q, ""] for q in range(1, MAX_QUESTIONS + 1)]


def default_question_rows(answer_key: Dict[int, str] | None = None) -> List[List[Any]]:
    answer_key = answer_key or {}
    return [[q, answer_key.get(q, ""), 1, QUESTION_NORMAL, "", ""] for q in range(1, MAX_QUESTIONS + 1)]


def table_rows(value: Any) -> List[List[Any]]:
    if value is None:
        return []
    if hasattr(value, "values") and hasattr(value.values, "tolist"):
        return value.values.tolist()
    if hasattr(value, "tolist"):
        return value.tolist()
    return list(value)


def answer_key_rows(answer_key: Dict[int, str]) -> List[List[Any]]:
    return [[q, answer_key.get(q, "")] for q in range(1, MAX_QUESTIONS + 1)]


def principal_to_state(user: UserPrincipal) -> Dict[str, Any]:
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "email": user.email,
        "role_name": user.role_name,
        "permissions": sorted(user.permissions),
        "is_active": user.is_active,
    }


def principal_from_state(value: Dict[str, Any] | None) -> UserPrincipal:
    if not value:
        return UserPrincipal.anonymous()
    return UserPrincipal(
        id=int(value.get("id") or 0),
        name=str(value.get("name") or ""),
        username=str(value.get("username") or ""),
        email=str(value.get("email") or ""),
        role_name=str(value.get("role_name") or ""),
        permissions=set(value.get("permissions") or []),
        is_active=bool(value.get("is_active")),
    )


def require_state_permission(auth_state: Dict[str, Any] | None, permission: str) -> UserPrincipal:
    user = principal_from_state(auth_state)
    try:
        require_permission(user, permission)
    except AuthorizationError as exc:
        raise gr.Error(str(exc))
    return user


def login_clicked(identity: str, password: str):
    try:
        result = authenticate((identity or "").strip(), password or "", MySQLRepository())
        return principal_to_state(result.user), f"Logged in as **{result.user.name}** ({result.user.role_name})."
    except (AuthenticationError, RuntimeError) as exc:
        raise gr.Error(str(exc))


def logout_clicked():
    return None, "Logged out."


def change_password_clicked(auth_state: Dict[str, Any] | None, current_password: str, new_password: str):
    user = require_state_permission(auth_state, "results.view")
    try:
        change_password(user.id, current_password or "", new_password or "", MySQLRepository())
    except (AuthenticationError, ValueError, RuntimeError) as exc:
        raise gr.Error(str(exc))
    return "Password changed."


def config_to_dict(config: ExamGradingConfig, *, exam_code: str, subject: str) -> Dict[str, Any]:
    return {
        "exam_code": exam_code,
        "subject": subject,
        "total_questions": config.total_questions,
        "default_question_points": str(config.default_question_points),
        "negative_marking_enabled": config.negative_marking_enabled,
        "negative_mark_value": str(config.negative_mark_value),
        "bubble_fill_threshold": str(config.bubble_fill_threshold),
        "low_confidence_review_enabled": config.low_confidence_review_enabled,
        "low_confidence_lower_bound": str(config.low_confidence_lower_bound),
        "low_confidence_upper_bound": str(config.low_confidence_upper_bound),
        "dropped_question_mode": config.dropped_question_mode,
        "allow_negative_total_score": config.allow_negative_total_score,
    }


def sync_question_rows(question_count: int, key_rows: Sequence[Sequence[Any]], existing_rows: Sequence[Sequence[Any]] | None):
    count = int(question_count or MAX_QUESTIONS)
    answer_key = normalise_answer_key(table_rows(key_rows), count)
    existing = {int(row[0]): row for row in table_rows(existing_rows) if row and row[0] not in (None, "")}
    rows = []
    for question_no in range(1, MAX_QUESTIONS + 1):
        row = list(existing.get(question_no, [question_no, "", 1, QUESTION_NORMAL, "", ""]))
        row += [""] * max(0, 6 - len(row))
        row[1] = answer_key.get(question_no, row[1])
        if question_no > count:
            row[1] = ""
            row[3] = QUESTION_NORMAL
        rows.append(row[:6])
    return rows


def read_answer_sheet_clicked(
    auth_state: Dict[str, Any] | None,
    question_count: int,
    reference_file: str | None,
    answer_sheet_file: str | None,
):
    require_state_permission(auth_state, "answer_keys.manage")
    if not answer_sheet_file:
        return gr.update(), [], "Upload an answer sheet first.", gr.update()
    reference = reference_file or str(DEFAULT_REFERENCE)
    count = int(question_count or MAX_QUESTIONS)
    answer_key, preview_path, missing, confidence = extract_answer_key_from_sheet(
        answer_sheet_path=answer_sheet_file,
        reference_path=reference,
        template_path=str(TEMPLATE_PATH),
        number_of_questions=count,
        workspace_root=WORKSPACE_ROOT,
    )
    message = f"Read **{count - len(missing)} / {count}** answers from the answer sheet. Alignment confidence: **{confidence}**."
    if missing:
        message += " Review blank/ambiguous questions in the table: " + ", ".join(str(q) for q in missing[:12])
        if len(missing) > 12:
            message += f", and {len(missing) - 12} more"
    return answer_key_rows(answer_key), [preview_path], message, default_question_rows(answer_key)


def process_clicked(
    auth_state: Dict[str, Any] | None,
    exam_title: str,
    exam_code: str,
    subject: str,
    default_class: str,
    question_count: int,
    default_question_points: float,
    negative_marking_enabled: bool,
    negative_mark_value: float,
    bubble_fill_threshold: float,
    low_confidence_review_enabled: bool,
    low_confidence_lower_bound: float,
    low_confidence_upper_bound: float,
    dropped_question_mode: str,
    allow_negative_total_score: bool,
    answer_sheet_file: str | None,
    key_rows: Sequence[Sequence[Any]],
    question_rule_rows: Sequence[Sequence[Any]],
    reference_file: str | None,
    student_files: Sequence[str] | None,
):
    user = require_state_permission(auth_state, "omr.process")
    if not student_files:
        raise gr.Error("Upload at least one student paper.")
    reference = reference_file or str(DEFAULT_REFERENCE)
    count = int(question_count or MAX_QUESTIONS)
    try:
        config = ExamGradingConfig.from_values(
            total_questions=count,
            default_question_points=default_question_points,
            negative_marking_enabled=negative_marking_enabled,
            negative_mark_value=negative_mark_value,
            bubble_fill_threshold=bubble_fill_threshold,
            low_confidence_review_enabled=low_confidence_review_enabled,
            low_confidence_lower_bound=low_confidence_lower_bound,
            low_confidence_upper_bound=low_confidence_upper_bound,
            dropped_question_mode=dropped_question_mode,
            allow_negative_total_score=allow_negative_total_score,
        )
    except ValueError as exc:
        raise gr.Error(str(exc))
    answer_key = normalise_answer_key(table_rows(key_rows), count)
    if answer_sheet_file and not all(answer_key.values()):
        sheet_key, _, _, _ = extract_answer_key_from_sheet(
            answer_sheet_path=answer_sheet_file,
            reference_path=reference,
            template_path=str(TEMPLATE_PATH),
            number_of_questions=count,
            workspace_root=WORKSPACE_ROOT,
        )
        answer_key = {
            question_no: answer_key.get(question_no) or sheet_key.get(question_no, "")
            for question_no in range(1, count + 1)
        }
    if not any(answer_key.values()):
        raise gr.Error("Enter answers in the answer-key table or upload an answer sheet.")
    question_rules = normalise_question_rules(table_rows(question_rule_rows), answer_key, config)

    batch_id, records, errors = process_uploads(
        uploads=list(student_files),
        reference_path=reference,
        template_path=str(TEMPLATE_PATH),
        answer_key=answer_key,
        fallback_class=default_class,
        workspace_root=WORKSPACE_ROOT,
        exam_config=config,
        question_rules=question_rules,
    )
    if not records:
        raise gr.Error("No papers could be processed. " + ("; ".join(errors[:3]) if errors else ""))

    result_rows = []
    previews = []
    for record in records:
        evaluation = record.get("evaluation") or {}
        counts = evaluation.get("counts") or {}
        result_rows.append([
            record["record_id"], record["source_file"], record["class_name"], record["roll"],
            record["name"], record["section"], record["score"], record["total_questions"],
            record["percentage"], "Yes" if record["review_required"] else "No",
            counts.get("CORRECT", 0), counts.get("INCORRECT", 0), counts.get("MULTIPLE", 0),
            counts.get("BLANK", 0), counts.get("LOW_CONFIDENCE", 0),
            counts.get("FAULTY_BONUS", 0), counts.get("DROPPED_BONUS", 0),
            evaluation.get("total_negative_marks", 0),
        ])
        previews.append(record["staging_marked"])

    state = {
        "batch_id": batch_id,
        "records": records,
        "answer_key": answer_key,
        "exam_title": exam_title or "Exam Results",
        "default_class": default_class or "",
        "exam_config": config_to_dict(config, exam_code=exam_code or batch_id, subject=subject or ""),
        "question_rules": {
            question_no: {
                "question_number": rule.question_number,
                "correct_option": rule.correct_option,
                "points": str(rule.points) if rule.points is not None else "",
                "status": rule.status,
                "custom_negative_mark": str(rule.custom_negative_mark) if rule.custom_negative_mark is not None else "",
                "notes": rule.notes,
            }
            for question_no, rule in question_rules.items()
        },
        "acting_user_id": user.id,
    }
    message = f"Processed **{len(records)}** paper(s). Review Class/Roll/Name, then click Finalise & Export."
    if errors:
        message += f"  \nWarning: {len(errors)} file/page error(s): " + "; ".join(errors[:4])
    return state, result_rows, previews, message, answer_key_rows(answer_key)


def finalise_clicked(auth_state: Dict[str, Any] | None, state: Dict[str, Any] | None, edited_rows: Sequence[Sequence[Any]]):
    user = require_state_permission(auth_state, "results.export")
    if not state:
        raise gr.Error("Process the student papers first.")
    excel_path, zip_path, gallery, final_records = finalise_batch(
        batch_id=state["batch_id"],
        records=state["records"],
        edited_rows=table_rows(edited_rows),
        exam_title=state["exam_title"],
        default_class=state["default_class"],
        answer_key={int(k): v for k, v in state["answer_key"].items()},
        output_root=OUTPUT_ROOT,
        database_path=DATABASE_PATH,
        exam_config=state.get("exam_config") or {},
        question_rules={int(k): v for k, v in (state.get("question_rules") or {}).items()},
        acting_user_id=user.id,
    )
    message = (
        f"Completed **{len(final_records)}** student paper(s). "
        f"The Excel file and organised image ZIP are ready."
    )
    return str(excel_path), str(zip_path), gallery, message


def permission_note(auth_state: Dict[str, Any] | None, permission: str) -> str:
    user = principal_from_state(auth_state)
    allowed = permission in user.permissions and user.is_active
    return "Access granted." if allowed else f"Permission required: {permission}"


def list_manual_reviews_clicked(auth_state: Dict[str, Any] | None):
    require_state_permission(auth_state, "omr.review")
    rows = MySQLRepository().list_manual_review_queue()
    return [
        [
            row.get("id"),
            row.get("exam_code"),
            row.get("exam_name"),
            row.get("student_name"),
            row.get("roll_number"),
            row.get("question_number"),
            row.get("correct_option"),
            row.get("selected_option"),
            row.get("response_status"),
            row.get("confidence_score"),
            row.get("fill_percentages"),
            row.get("annotated_image_path"),
        ]
        for row in rows
    ]


def class_results_clicked(auth_state: Dict[str, Any] | None, class_name: str, section: str, exam_code: str):
    require_state_permission(auth_state, "results.view")
    rows = MySQLRepository().class_wise_results(class_name=class_name or "", section=section or "", exam_code=exam_code or "")
    return [
        [
            row.get("academic_year"), row.get("class_name"), row.get("section"), row.get("exam_name"),
            row.get("subject"), row.get("roll_number"), row.get("student_name"), row.get("final_score"),
            row.get("maximum_score"), row.get("percentage"), row.get("grade"), row.get("status"),
            row.get("total_negative_marks"), row.get("bonus_marks"),
        ]
        for row in rows
    ]


def student_results_clicked(auth_state: Dict[str, Any] | None, search: str):
    require_state_permission(auth_state, "results.view")
    rows = MySQLRepository().student_wise_results(search=search or "")
    return [
        [
            row.get("student_name"), row.get("roll_number"), row.get("registration_number"),
            row.get("class_name"), row.get("section"), row.get("exam_name"), row.get("subject"),
            row.get("final_score"), row.get("maximum_score"), row.get("percentage"), row.get("grade"),
            row.get("status"), row.get("source_image_path"), row.get("annotated_image_path"),
        ]
        for row in rows
    ]


def exam_summary_clicked(auth_state: Dict[str, Any] | None, exam_code: str):
    require_state_permission(auth_state, "results.view")
    rows = MySQLRepository().exam_summary(exam_code=exam_code or "")
    return [
        [
            row.get("exam_code"), row.get("exam_name"), row.get("subject"), row.get("total_students"),
            row.get("average_percentage"), row.get("highest_score"), row.get("lowest_score"),
            row.get("passed_students"),
        ]
        for row in rows
    ]


def create_user_clicked(
    auth_state: Dict[str, Any] | None,
    name: str,
    username: str,
    email: str,
    password: str,
    role_name: str,
    is_active: bool,
):
    user = require_state_permission(auth_state, "users.create")
    if not all([name, username, email, password, role_name]):
        raise gr.Error("Name, username, email, password, and role are required.")
    repository = MySQLRepository()
    user_id = repository.create_user(
        name=name.strip(),
        username=username.strip(),
        email=email.strip(),
        password_hash=hash_password(password),
        role_name=role_name,
        is_active=is_active,
        acting_user_id=user.id,
    )
    return f"Created user id {user_id}.", list_users_clicked(auth_state)


def list_users_clicked(auth_state: Dict[str, Any] | None):
    require_state_permission(auth_state, "users.view")
    rows = MySQLRepository().list_users()
    return [
        [
            row.get("id"), row.get("name"), row.get("username"), row.get("email"),
            row.get("role_name"), "Active" if row.get("is_active") else "Inactive",
            row.get("last_login_at"), row.get("failed_login_count"),
        ]
        for row in rows
    ]


css = """
.gradio-container {max-width: 1240px !important;}
#hero {background: linear-gradient(135deg, #111111, #2b2416); border: 1px solid #a97a1f; border-radius: 18px; padding: 22px;}
#hero h1, #hero p {color: #f4d27b !important;}
.primary {background: #b78727 !important; color: #111 !important; border: none !important;}
"""

theme = gr.themes.Soft(primary_hue="amber", neutral_hue="slate")

with gr.Blocks(title="Bangla OCR Exam Grading Panel") as demo:
    state = gr.State()
    auth_state = gr.State()
    gr.Markdown(
        "# Bangla OCR Exam Grading Panel\nSecure OMR processing, configurable grading, manual review, and MySQL result storage.",
        elem_id="hero",
    )

    with gr.Accordion("Login and account", open=True):
        with gr.Row():
            login_identity = gr.Textbox(label="Email or username")
            login_password = gr.Textbox(label="Password", type="password")
            login_button = gr.Button("Login", variant="primary", elem_classes=["primary"])
            logout_button = gr.Button("Logout")
        login_status = gr.Markdown("Log in with a permitted account before processing.")
        with gr.Row():
            current_password = gr.Textbox(label="Current password", type="password")
            new_password = gr.Textbox(label="New password", type="password")
            change_password_button = gr.Button("Change password")
        password_status = gr.Markdown()

    with gr.Tabs():
        with gr.Tab("OMR Processing"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### Exam setup")
                    exam_title = gr.Textbox(label="Exam title", value="Annual MCQ Examination")
                    exam_code = gr.Textbox(label="Exam code", placeholder="Example: ANNUAL-MCQ-2026")
                    subject = gr.Textbox(label="Subject")
                    default_class = gr.Textbox(label="Default class", placeholder="Example: 2")
                    question_count = gr.Slider(1, MAX_QUESTIONS, value=30, step=1, label="Number of questions")
                    default_question_points = gr.Number(label="Default marks per question", value=1, minimum=0)
                    negative_marking_enabled = gr.Checkbox(label="Enable negative marking", value=False)
                    negative_mark_value = gr.Number(label="Negative mark deduction", value=0.25, minimum=0)
                    bubble_fill_threshold = gr.Slider(0, 100, value=40, step=0.1, label="Bubble fill threshold (%)")
                    low_confidence_review_enabled = gr.Checkbox(label="Enable low-confidence manual review", value=True)
                    with gr.Row():
                        low_confidence_lower_bound = gr.Number(label="Review lower bound (%)", value=30, minimum=0, maximum=100)
                        low_confidence_upper_bound = gr.Number(label="Review upper bound (%)", value=39.99, minimum=0, maximum=100)
                    dropped_question_mode = gr.Dropdown(["TOTAL_SHIFT", "UNIVERSAL_BONUS"], value="TOTAL_SHIFT", label="Dropped-question mode")
                    allow_negative_total_score = gr.Checkbox(label="Allow negative final total", value=True)
                    reference_file = gr.Image(label="Reference/blank form image (optional)", type="filepath", sources=["upload"])
                    gr.Markdown("Leave the reference image empty to use the supplied sample form template.")
                with gr.Column(scale=2):
                    gr.Markdown("### Answer key and question rules")
                    answer_sheet_file = gr.File(
                        label="Master answer sheet / answer key paper (optional)",
                        file_count="single",
                        file_types=[".jpg", ".jpeg", ".png", ".pdf"],
                        type="filepath",
                    )
                    read_answer_button = gr.Button("Read Answer Sheet")
                    answer_key_status = gr.Markdown()
                    answer_sheet_preview = gr.Gallery(label="Detected answer key preview", columns=1, height="auto")
                    answer_key = gr.Dataframe(
                        headers=["Question", "Correct Answer"],
                        value=default_key_rows(),
                        datatype=["number", "str"],
                        row_count=(MAX_QUESTIONS, "fixed"),
                        column_count=(2, "fixed"),
                        interactive=True,
                        label="Use only à¦•, à¦–, à¦—, or à¦˜",
                    )
                    sync_question_button = gr.Button("Sync Question Rules From Answer Key")
                    question_rules = gr.Dataframe(
                        headers=QUESTION_HEADERS,
                        value=default_question_rows(),
                        datatype=["number", "str", "number", "str", "number", "str"],
                        row_count=(MAX_QUESTIONS, "fixed"),
                        column_count=(6, "fixed"),
                        interactive=True,
                        label="Question status: NORMAL, FLAG_FAULTY, or FLAG_DROPPED",
                    )

            gr.Markdown("### Upload student papers")
            student_files = gr.File(
                label="Upload JPG, JPEG, PNG, or PDF files",
                file_count="multiple",
                file_types=[".jpg", ".jpeg", ".png", ".pdf"],
                type="filepath",
            )
            process_button = gr.Button("Run OCR and Mark Papers", variant="primary", elem_classes=["primary"])
            process_status = gr.Markdown()

            gr.Markdown("### Review OCR results")
            result_table = gr.Dataframe(
                headers=RESULT_HEADERS,
                datatype=[
                    "str", "str", "str", "str", "str", "str", "number", "number", "number", "str",
                    "number", "number", "number", "number", "number", "number", "number", "number",
                ],
                interactive=True,
                wrap=True,
                label="Correct Class, Roll, Name, or Section before export",
            )
            preview_gallery = gr.Gallery(label="Marked previews - correct selections are circled in red", columns=3, height="auto")

            finalise_button = gr.Button("Finalise, Save Images, and Create Excel", variant="primary", elem_classes=["primary"])
            final_status = gr.Markdown()
            with gr.Row():
                excel_download = gr.File(label="Download marks Excel file")
                zip_download = gr.File(label="Download all output folders as ZIP")
            final_gallery = gr.Gallery(label="Final marked sheets", columns=3, height="auto")

        with gr.Tab("Manual Review"):
            gr.Markdown("Manual review queue uses LOW_CONFIDENCE and MULTIPLE responses stored in MySQL.")
            load_review_button = gr.Button("Load Manual Review Queue")
            manual_review_table = gr.Dataframe(
                headers=[
                    "Response ID", "Exam Code", "Exam", "Student", "Roll", "Question",
                    "Correct", "Selected", "Status", "Confidence", "Fill Percentages", "Annotated Image",
                ],
                datatype=["number", "str", "str", "str", "str", "number", "str", "str", "str", "number", "str", "str"],
                interactive=False,
            )

        with gr.Tab("Results"):
            gr.Markdown("Class-wise, student-wise, and exam-wise reports are generated from MySQL results and student response tables.")
            with gr.Row():
                report_class = gr.Textbox(label="Class filter")
                report_section = gr.Textbox(label="Section filter")
                report_exam_code = gr.Textbox(label="Exam code filter")
                class_results_button = gr.Button("Class-wise Results")
            class_results_table = gr.Dataframe(
                headers=[
                    "Academic Year", "Class", "Section", "Exam", "Subject", "Roll",
                    "Student", "Final Score", "Maximum", "Percentage", "Grade",
                    "Status", "Negative Marks", "Bonus Marks",
                ],
                interactive=False,
            )
            with gr.Row():
                student_search = gr.Textbox(label="Student search")
                student_results_button = gr.Button("Student-wise Results")
                exam_summary_button = gr.Button("Exam-wise Summary")
            student_results_table = gr.Dataframe(
                headers=[
                    "Student", "Roll", "Registration", "Class", "Section", "Exam",
                    "Subject", "Final Score", "Maximum", "Percentage", "Grade",
                    "Status", "Original Image", "Annotated Image",
                ],
                interactive=False,
            )
            exam_summary_table = gr.Dataframe(
                headers=[
                    "Exam Code", "Exam", "Subject", "Total Students", "Average %",
                    "Highest", "Lowest", "Passed",
                ],
                interactive=False,
            )

        with gr.Tab("Admin"):
            gr.Markdown("User, role, permission, class, student, grade-scale, threshold, and audit-log management are backed by MySQL.")
            with gr.Row():
                new_user_name = gr.Textbox(label="Name")
                new_user_username = gr.Textbox(label="Username")
                new_user_email = gr.Textbox(label="Email")
            with gr.Row():
                new_user_password = gr.Textbox(label="Initial password", type="password")
                new_user_role = gr.Dropdown(
                    ["Super Admin", "Admin / Exam Manager", "Marker / Evaluator", "Result Viewer"],
                    value="Result Viewer",
                    label="Role",
                )
                new_user_active = gr.Checkbox(label="Active", value=True)
                create_user_button = gr.Button("Create User")
                list_users_button = gr.Button("List Users")
            admin_status = gr.Markdown()
            users_table = gr.Dataframe(
                headers=["ID", "Name", "Username", "Email", "Role", "Status", "Last Login", "Failed Logins"],
                interactive=False,
            )

    login_button.click(login_clicked, inputs=[login_identity, login_password], outputs=[auth_state, login_status])
    logout_button.click(logout_clicked, outputs=[auth_state, login_status])
    change_password_button.click(change_password_clicked, inputs=[auth_state, current_password, new_password], outputs=[password_status])
    sync_question_button.click(sync_question_rows, inputs=[question_count, answer_key, question_rules], outputs=[question_rules])
    process_button.click(
        process_clicked,
        inputs=[
            auth_state, exam_title, exam_code, subject, default_class, question_count,
            default_question_points, negative_marking_enabled, negative_mark_value,
            bubble_fill_threshold, low_confidence_review_enabled,
            low_confidence_lower_bound, low_confidence_upper_bound,
            dropped_question_mode, allow_negative_total_score,
            answer_sheet_file, answer_key, question_rules, reference_file, student_files,
        ],
        outputs=[state, result_table, preview_gallery, process_status, answer_key],
    )
    read_answer_button.click(
        read_answer_sheet_clicked,
        inputs=[auth_state, question_count, reference_file, answer_sheet_file],
        outputs=[answer_key, answer_sheet_preview, answer_key_status, question_rules],
    )
    finalise_button.click(finalise_clicked, inputs=[auth_state, state, result_table], outputs=[excel_download, zip_download, final_gallery, final_status])
    load_review_button.click(list_manual_reviews_clicked, inputs=[auth_state], outputs=[manual_review_table])
    class_results_button.click(
        class_results_clicked,
        inputs=[auth_state, report_class, report_section, report_exam_code],
        outputs=[class_results_table],
    )
    student_results_button.click(student_results_clicked, inputs=[auth_state, student_search], outputs=[student_results_table])
    exam_summary_button.click(exam_summary_clicked, inputs=[auth_state, report_exam_code], outputs=[exam_summary_table])
    create_user_button.click(
        create_user_clicked,
        inputs=[
            auth_state, new_user_name, new_user_username, new_user_email,
            new_user_password, new_user_role, new_user_active,
        ],
        outputs=[admin_status, users_table],
    )
    list_users_button.click(list_users_clicked, inputs=[auth_state], outputs=[users_table])


if __name__ == "__main__":
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    demo.launch(inbrowser=True, theme=theme, css=css)
