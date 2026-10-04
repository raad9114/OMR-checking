from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import cv2

from database import save_batch
from evaluation_service import ExamGradingConfig, QuestionRule, build_question_rules
from excel_export import export_marks_workbook
from file_utils import expand_upload_to_images, make_zip, unique_folder
from ocr_engine import (
    OPTION_LABELS,
    align_to_reference,
    bangla_digits_to_ascii,
    extract_omr_answers,
    load_gray,
    load_template,
    process_single_image,
    safe_component,
)


def normalise_answer_key(rows: Sequence[Sequence[Any]], number_of_questions: int) -> Dict[int, str]:
    allowed = set(OPTION_LABELS)
    result: Dict[int, str] = {}
    for index in range(1, number_of_questions + 1):
        value = ""
        if index - 1 < len(rows) and len(rows[index - 1]) >= 2:
            value = str(rows[index - 1][1] or "").strip()
        result[index] = value if value in allowed else ""
    return result


def normalise_question_rules(
    rows: Sequence[Sequence[Any]],
    answer_key: Dict[int, str],
    config: ExamGradingConfig,
) -> Dict[int, QuestionRule]:
    rules = build_question_rules(
        answer_key=answer_key,
        total_questions=config.total_questions,
        rows=rows,
    )
    for question_no, rule in list(rules.items()):
        if not rule.correct_option:
            rules[question_no] = QuestionRule.from_values(
                question_number=question_no,
                correct_option=answer_key.get(question_no, ""),
                points=rule.points,
                status=rule.status,
                custom_negative_mark=rule.custom_negative_mark,
                notes=rule.notes,
            )
    return rules


def _answer_sheet_preview(
    aligned_sheet,
    answers: Dict[int, Any],
    omr: Dict[str, Any],
    *,
    number_of_questions: int,
    selected_count: int,
):
    canvas = cv2.cvtColor(aligned_sheet, cv2.COLOR_GRAY2BGR)
    h, w = aligned_sheet.shape[:2]
    left_x = [x * w for x in omr["left_x"]]
    right_x = [x * w for x in omr["right_x"]]
    row_y = [y * h for y in omr["row_y"]]
    labels = omr.get("option_labels", OPTION_LABELS)
    radius = max(7, int(round(float(omr["bubble_radius_ratio"]) * w)))

    for row_index, y in enumerate(row_y):
        for columns, question_no in ((left_x, row_index + 1), (right_x, row_index + 16)):
            if question_no > number_of_questions:
                continue
            answer = answers.get(question_no)
            if not answer or answer.selected_option not in labels:
                continue
            option_index = labels.index(answer.selected_option)
            centre = (int(round(columns[option_index])), int(round(y)))
            cv2.circle(canvas, centre, radius + 6, (0, 105, 255), 3, cv2.LINE_AA)

    cv2.rectangle(canvas, (18, 15), (350, 68), (255, 255, 255), -1)
    cv2.rectangle(canvas, (18, 15), (350, 68), (0, 105, 255), 2)
    cv2.putText(
        canvas,
        f"Answer key: {selected_count}/{number_of_questions}",
        (30, 51),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (0, 105, 255),
        2,
        cv2.LINE_AA,
    )
    return canvas


def extract_answer_key_from_sheet(
    *,
    answer_sheet_path: str,
    reference_path: str,
    template_path: str,
    number_of_questions: int,
    workspace_root: str | Path,
) -> Tuple[Dict[int, str], str, List[int], float]:
    key_id = datetime.now().strftime("answer_key_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    key_workspace = Path(workspace_root) / key_id
    expanded = key_workspace / "expanded"
    staging = key_workspace / "staging"
    staging.mkdir(parents=True, exist_ok=True)

    pages = expand_upload_to_images(answer_sheet_path, expanded)
    if not pages:
        raise RuntimeError("No page was found in the answer sheet upload.")

    first_page, _ = pages[0]
    template = load_template(template_path)
    reference = load_gray(reference_path)
    key_sheet = load_gray(first_page)
    aligned, alignment_confidence = align_to_reference(key_sheet, reference)
    answers = extract_omr_answers(aligned, template["omr"])

    answer_key: Dict[int, str] = {}
    missing_questions: List[int] = []
    for question_no in range(1, number_of_questions + 1):
        answer = answers.get(question_no)
        selected = answer.selected_option if answer else None
        if selected in OPTION_LABELS:
            answer_key[question_no] = selected
        else:
            answer_key[question_no] = ""
            missing_questions.append(question_no)

    selected_count = number_of_questions - len(missing_questions)
    preview = _answer_sheet_preview(
        aligned,
        answers,
        template["omr"],
        number_of_questions=number_of_questions,
        selected_count=selected_count,
    )
    preview_path = staging / "answer_key_preview.jpg"
    cv2.imwrite(str(preview_path), preview)
    return answer_key, str(preview_path), missing_questions, round(alignment_confidence, 4)


def process_uploads(
    *,
    uploads: Sequence[str],
    reference_path: str,
    template_path: str,
    answer_key: Dict[int, str],
    fallback_class: str,
    workspace_root: str | Path,
    exam_config: ExamGradingConfig | None = None,
    question_rules: Dict[int, QuestionRule] | None = None,
) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    batch_workspace = Path(workspace_root) / batch_id
    staging = batch_workspace / "staging"
    expanded = batch_workspace / "expanded"
    staging.mkdir(parents=True, exist_ok=True)

    template = load_template(template_path)
    config = exam_config or ExamGradingConfig.from_values(total_questions=len(answer_key))
    rules = question_rules or build_question_rules(
        answer_key=answer_key,
        total_questions=config.total_questions,
        default_points=config.default_question_points,
    )
    records: List[Dict[str, Any]] = []
    errors: List[str] = []
    counter = 0
    for upload in uploads:
        try:
            pages = expand_upload_to_images(upload, expanded)
        except Exception as exc:
            errors.append(f"{Path(upload).name}: could not open file ({exc})")
            continue
        for image_path, page_number in pages:
            counter += 1
            record_id = f"paper_{counter:04d}"
            try:
                paper = process_single_image(
                    image_path=image_path,
                    reference_path=reference_path,
                    template=template,
                    answer_key=answer_key,
                    staging_dir=staging,
                    record_id=record_id,
                    page_number=page_number,
                    fallback_class=fallback_class,
                    exam_config=config,
                    question_rules=rules,
                )
                records.append(paper.to_dict())
            except Exception as exc:
                errors.append(f"{Path(upload).name}, page {page_number}: {exc}")
    state_path = batch_workspace / "state.json"
    state_path.write_text(
        json.dumps({"batch_id": batch_id, "records": records, "answer_key": answer_key}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return batch_id, records, errors


def finalise_batch(
    *,
    batch_id: str,
    records: List[Dict[str, Any]],
    edited_rows: Sequence[Sequence[Any]],
    exam_title: str,
    default_class: str,
    answer_key: Dict[int, str],
    output_root: str | Path,
    database_path: str | Path,
    exam_config: Dict[str, Any] | None = None,
    question_rules: Dict[int, QuestionRule] | None = None,
    acting_user_id: int | None = None,
) -> Tuple[Path, Path, List[str], List[Dict[str, Any]]]:
    edits: Dict[str, Sequence[Any]] = {}
    for row in edited_rows:
        if row:
            edits[str(row[0])] = row

    batch_output = Path(output_root) / f"{safe_component(exam_title, 'exam')}_{batch_id}"
    batch_output.mkdir(parents=True, exist_ok=True)
    final_records: List[Dict[str, Any]] = []
    gallery: List[str] = []

    for record in records:
        row = edits.get(record["record_id"])
        if row:
            # record_id, source, class, roll, name, section, score, total, percentage, review
            record["class_name"] = str(row[2] or "").strip()
            record["roll"] = str(row[3] or "").strip()
            record["name"] = str(row[4] or "").strip()
            record["section"] = str(row[5] or "").strip()
            review_cell = str(row[9] or "").strip().lower()
            record["review_required"] = review_cell in {"yes", "true", "1"}

        class_value = bangla_digits_to_ascii(record.get("class_name", ""))
        roll_value = bangla_digits_to_ascii(record.get("roll", ""))
        class_safe = safe_component(class_value, "unknown_class")
        roll_safe = safe_component(roll_value, record["record_id"])
        folder_name = f"{roll_safe}_{class_safe}"
        student_folder = unique_folder(batch_output / class_safe / folder_name)
        student_folder.mkdir(parents=True, exist_ok=True)

        original_src = Path(record["staging_original"])
        marked_src = Path(record["staging_marked"])
        aligned_src = Path(record["staging_aligned"])
        original_dest = student_folder / f"{folder_name}_original{original_src.suffix.lower()}"
        marked_dest = student_folder / f"{folder_name}_marked.jpg"
        aligned_dest = student_folder / f"{folder_name}_aligned.jpg"
        shutil.copy2(original_src, original_dest)
        shutil.copy2(marked_src, marked_dest)
        shutil.copy2(aligned_src, aligned_dest)

        record["output_folder"] = str(student_folder)
        record["original_image"] = str(original_dest)
        record["marked_image"] = str(marked_dest)
        final_records.append(record)
        gallery.append(str(marked_dest))

    excel_path = batch_output / "marks.xlsx"
    export_marks_workbook(
        excel_path,
        exam_title=exam_title,
        batch_id=batch_id,
        answer_key=answer_key,
        records=final_records,
    )
    save_batch(
        database_path,
        batch_id=batch_id,
        exam_title=exam_title,
        default_class=default_class,
        answer_key=answer_key,
        records=final_records,
        exam_config=exam_config,
        question_rules=question_rules,
        acting_user_id=acting_user_id,
    )
    (batch_output / "results.json").write_text(
        json.dumps(final_records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    zip_path = batch_output.with_suffix(".zip")
    make_zip(batch_output, zip_path)
    return excel_path, zip_path, gallery, final_records
