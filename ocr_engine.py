from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import pytesseract

from evaluation_service import (
    DetectedResponse,
    ExamGradingConfig,
    QuestionRule,
    build_question_rules,
    evaluate_sheet,
)

BANGLA_TO_ASCII = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
OPTION_LABELS = ["ক", "খ", "গ", "ঘ"]


@dataclass
class OCRField:
    field_name: str
    text: str
    confidence: float
    review_required: bool


@dataclass
class OMRAnswer:
    question_no: int
    selected_option: Optional[str]
    confidence: float
    ink_ratios: List[float]
    status: str
    detected_options: List[str] | None = None
    fill_percentages: Dict[str, float] | None = None
    requires_manual_review: bool = False


@dataclass
class ProcessedPaper:
    record_id: str
    source_file: str
    page_number: int
    staging_original: str
    staging_aligned: str
    staging_marked: str
    class_name: str
    roll: str
    name: str
    section: str
    score: float
    total_questions: float
    percentage: float
    alignment_confidence: float
    review_required: bool
    fields: Dict[str, Dict[str, Any]]
    answers: Dict[str, Dict[str, Any]]
    evaluation: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalise_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\x0c", " ")
    return re.sub(r"\s+", " ", text).strip()


def bangla_digits_to_ascii(text: str) -> str:
    return normalise_text(text).translate(BANGLA_TO_ASCII)


def safe_component(value: str, fallback: str) -> str:
    value = normalise_text(value).replace("/", "-").replace("\\", "-")
    value = re.sub(r"[<>:\"|?*]", "-", value)
    value = re.sub(r"\s+", "_", value).strip("._-")
    return value or fallback


def load_gray(path: str | Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    return image


def load_colour(path: str | Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    return image


def align_to_reference(student: np.ndarray, reference: np.ndarray) -> Tuple[np.ndarray, float]:
    orb = cv2.ORB_create(nfeatures=6000)
    kp_s, des_s = orb.detectAndCompute(student, None)
    kp_r, des_r = orb.detectAndCompute(reference, None)
    if des_s is None or des_r is None:
        raise RuntimeError("Not enough visual features for page alignment.")

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs = matcher.knnMatch(des_s, des_r, k=2)
    good = [m for m, n in pairs if m.distance < 0.74 * n.distance]
    if len(good) < 18:
        raise RuntimeError(f"Only {len(good)} reliable matches were found.")

    source = np.float32([kp_s[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    target = np.float32([kp_r[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    matrix, mask = cv2.findHomography(source, target, cv2.RANSAC, 3.5)
    if matrix is None or mask is None:
        raise RuntimeError("Page alignment failed.")

    aligned = cv2.warpPerspective(
        student,
        matrix,
        (reference.shape[1], reference.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderValue=255,
    )
    return aligned, float(mask.sum()) / max(1.0, float(len(good)))


def roi_from_normalised(image: np.ndarray, roi: List[float]) -> np.ndarray:
    h, w = image.shape[:2]
    x1, y1, x2, y2 = roi
    xa, ya = max(0, int(x1 * w)), max(0, int(y1 * h))
    xb, yb = min(w, int(x2 * w)), min(h, int(y2 * h))
    if xb <= xa or yb <= ya:
        raise ValueError(f"Invalid ROI: {roi}")
    return image[ya:yb, xa:xb]


def _ocr_variant(crop: np.ndarray, field_name: str, threshold_mode: int) -> Tuple[str, float]:
    crop = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    crop = cv2.GaussianBlur(crop, (3, 3), 0)
    if threshold_mode == 0:
        processed = crop
    elif threshold_mode == 1:
        processed = cv2.adaptiveThreshold(
            crop, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
        )
    else:
        _, processed = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    extra = ""
    if field_name in {"roll", "exam_year", "exam_date"}:
        extra = " -c tessedit_char_whitelist=0123456789০১২৩৪৫৬৭৮৯./-"
    config = f"--oem 1 --psm 7{extra}"
    data = pytesseract.image_to_data(
        processed,
        lang="ben+eng",
        config=config,
        output_type=pytesseract.Output.DICT,
    )
    words: List[str] = []
    confidences: List[float] = []
    for word, conf in zip(data.get("text", []), data.get("conf", [])):
        word = normalise_text(word)
        try:
            conf_value = float(conf)
        except (TypeError, ValueError):
            conf_value = -1.0
        if word:
            words.append(word)
        if conf_value >= 0:
            confidences.append(conf_value)
    return normalise_text(" ".join(words)), float(np.mean(confidences)) if confidences else 0.0


def read_field(image: np.ndarray, field_name: str, roi: List[float]) -> OCRField:
    crop = roi_from_normalised(image, roi)
    candidates = [_ocr_variant(crop, field_name, mode) for mode in (0, 1, 2)]
    text, confidence = max(candidates, key=lambda item: (bool(item[0]), item[1]))
    return OCRField(
        field_name=field_name,
        text=text,
        confidence=round(confidence, 2),
        review_required=(not text) or confidence < 55.0,
    )


def extract_roll(text: str, filename: str = "") -> str:
    text_ascii = bangla_digits_to_ascii(text)
    matches = re.findall(r"\d{1,8}", text_ascii)
    if matches:
        return matches[-1].lstrip("0") or "0"
    filename_matches = re.findall(r"\d{1,8}", Path(filename).stem)
    return (filename_matches[-1].lstrip("0") or "0") if filename_matches else ""


def disk_ink_ratio(
    image: np.ndarray,
    x: float,
    y: float,
    radius: float,
    dark_threshold: int,
) -> float:
    h, w = image.shape[:2]
    x0, y0 = int(round(x)), int(round(y))
    r = max(3, int(round(radius)))
    xa, xb = max(0, x0 - r), min(w, x0 + r + 1)
    ya, yb = max(0, y0 - r), min(h, y0 + r + 1)
    patch = image[ya:yb, xa:xb]
    yy, xx = np.ogrid[ya:yb, xa:xb]
    mask = (xx - x0) ** 2 + (yy - y0) ** 2 <= r**2
    values = patch[mask]
    return float(np.mean(values < dark_threshold)) if values.size else 0.0


def _threshold_ratio(value: Any, default_percent: float = 40.0) -> float:
    if value is None or value == "":
        return default_percent / 100.0
    numeric = float(value)
    return numeric / 100.0 if numeric > 1.0 else numeric


def extract_omr_answers(
    image: np.ndarray,
    omr: Dict[str, Any],
    *,
    bubble_fill_threshold: Any | None = None,
    low_confidence_review_enabled: bool = False,
    low_confidence_lower_bound: Any = 30,
    low_confidence_upper_bound: Any = 39.99,
) -> Dict[int, OMRAnswer]:
    h, w = image.shape[:2]
    left_x = [x * w for x in omr["left_x"]]
    right_x = [x * w for x in omr["right_x"]]
    row_y = [y * h for y in omr["row_y"]]
    labels = omr.get("option_labels", OPTION_LABELS)
    radius = float(omr["bubble_radius_ratio"]) * w
    absolute_threshold = _threshold_ratio(
        bubble_fill_threshold if bubble_fill_threshold is not None else omr.get("filled_ratio_threshold"),
        40.0,
    )
    low_lower = _threshold_ratio(low_confidence_lower_bound, 30.0)
    low_upper = _threshold_ratio(low_confidence_upper_bound, 39.99)
    dark_threshold = int(omr["dark_pixel_threshold"])

    answers: Dict[int, OMRAnswer] = {}
    for row_index, y in enumerate(row_y):
        for columns, question_no in ((left_x, row_index + 1), (right_x, row_index + 16)):
            ratios = [disk_ink_ratio(image, x, y, radius, dark_threshold) for x in columns]
            selected_indexes = [index for index, ratio in enumerate(ratios) if ratio >= absolute_threshold]
            detected_options = [labels[index] for index in selected_indexes]
            order = np.argsort(ratios)[::-1]
            best_index, second_index = int(order[0]), int(order[1])
            best, second = float(ratios[best_index]), float(ratios[second_index])
            margin = best - second
            selected: Optional[str] = None
            requires_manual_review = False
            if len(selected_indexes) == 0:
                if low_confidence_review_enabled and low_lower <= best <= low_upper:
                    status = "low_confidence"
                    requires_manual_review = True
                else:
                    status = "blank"
            elif len(selected_indexes) == 1:
                selected = labels[selected_indexes[0]]
                status = "selected"
            else:
                status = "multiple"
                requires_manual_review = True
            confidence = max(0.0, min(1.0, best if status != "multiple" else margin))
            answers[question_no] = OMRAnswer(
                question_no=question_no,
                selected_option=selected,
                confidence=round(confidence, 4),
                ink_ratios=[round(v, 4) for v in ratios],
                status=status,
                detected_options=detected_options,
                fill_percentages={labels[index]: round(ratio * 100.0, 4) for index, ratio in enumerate(ratios)},
                requires_manual_review=requires_manual_review,
            )
    return answers


def grade_answers(
    student_answers: Dict[int, OMRAnswer], answer_key: Dict[int, str]
) -> Tuple[int, int, Dict[int, bool]]:
    valid_key = {q: a for q, a in answer_key.items() if a in OPTION_LABELS}
    correctness = {
        q: student_answers.get(q, OMRAnswer(q, None, 0.0, [], "missing")).selected_option == answer
        for q, answer in valid_key.items()
    }
    return sum(correctness.values()), len(valid_key), correctness


def annotate_correct_answers_red(
    aligned_student: np.ndarray,
    student_answers: Dict[int, OMRAnswer],
    answer_key: Dict[int, str],
    omr: Dict[str, Any],
    score: int,
    total: int,
) -> np.ndarray:
    """Circle the student's correct selections in red, as requested."""
    canvas = cv2.cvtColor(aligned_student, cv2.COLOR_GRAY2BGR)
    h, w = aligned_student.shape[:2]
    left_x = [x * w for x in omr["left_x"]]
    right_x = [x * w for x in omr["right_x"]]
    row_y = [y * h for y in omr["row_y"]]
    labels = omr.get("option_labels", OPTION_LABELS)
    radius = max(7, int(round(float(omr["bubble_radius_ratio"]) * w)))

    for row_index, y in enumerate(row_y):
        for columns, q in ((left_x, row_index + 1), (right_x, row_index + 16)):
            key_option = answer_key.get(q)
            selected = student_answers.get(q)
            if not selected or selected.selected_option != key_option or key_option not in labels:
                continue
            option_index = labels.index(key_option)
            centre = (int(round(columns[option_index])), int(round(y)))
            cv2.circle(canvas, centre, radius + 6, (0, 0, 230), 3, cv2.LINE_AA)
            cv2.putText(
                canvas,
                "OK",
                (centre[0] + radius + 5, centre[1] + 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.36,
                (0, 0, 230),
                1,
                cv2.LINE_AA,
            )

    cv2.rectangle(canvas, (18, 15), (275, 68), (255, 255, 255), -1)
    cv2.rectangle(canvas, (18, 15), (275, 68), (0, 0, 230), 2)
    cv2.putText(
        canvas,
        f"Score: {score}/{total}",
        (30, 51),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.85,
        (0, 0, 230),
        2,
        cv2.LINE_AA,
    )
    return canvas


def process_single_image(
    *,
    image_path: str | Path,
    reference_path: str | Path,
    template: Dict[str, Any],
    answer_key: Dict[int, str],
    staging_dir: str | Path,
    record_id: str,
    page_number: int = 1,
    fallback_class: str = "",
    exam_config: ExamGradingConfig | None = None,
    question_rules: Dict[int, QuestionRule] | None = None,
) -> ProcessedPaper:
    staging = Path(staging_dir)
    staging.mkdir(parents=True, exist_ok=True)
    source_path = Path(image_path)
    reference = load_gray(reference_path)
    student = load_gray(source_path)
    aligned, alignment_confidence = align_to_reference(student, reference)

    fields = {
        name: read_field(aligned, name, roi)
        for name, roi in template["field_rois"].items()
    }
    template_threshold = float(template["omr"].get("filled_ratio_threshold", 0.40))
    config = exam_config or ExamGradingConfig.from_values(
        total_questions=len(answer_key),
        bubble_fill_threshold=template_threshold * 100.0 if template_threshold <= 1.0 else template_threshold,
    )
    rules = question_rules or build_question_rules(
        answer_key=answer_key,
        total_questions=config.total_questions,
        default_points=config.default_question_points,
    )
    answers = extract_omr_answers(
        aligned,
        template["omr"],
        bubble_fill_threshold=config.bubble_fill_threshold,
        low_confidence_review_enabled=config.low_confidence_review_enabled,
        low_confidence_lower_bound=config.low_confidence_lower_bound,
        low_confidence_upper_bound=config.low_confidence_upper_bound,
    )
    labels = template["omr"].get("option_labels", OPTION_LABELS)
    detections = {
        q: DetectedResponse.from_omr_answer(q, labels, answer)
        for q, answer in answers.items()
        if q <= config.total_questions
    }
    evaluation = evaluate_sheet(
        detections=detections,
        question_rules=rules,
        config=config,
        option_labels=labels,
    )
    score = float(evaluation.final_score)
    total = float(evaluation.maximum_score)

    class_ocr = normalise_text(fields.get("class_name", OCRField("", "", 0, True)).text)
    class_name = class_ocr if class_ocr and not fields["class_name"].review_required else normalise_text(fallback_class)
    roll = extract_roll(fields.get("roll", OCRField("", "", 0, True)).text, source_path.name)
    name = normalise_text(fields.get("name", OCRField("", "", 0, True)).text)
    section = normalise_text(fields.get("section", OCRField("", "", 0, True)).text)

    original_path = staging / f"{record_id}_original{source_path.suffix.lower() or '.jpg'}"
    aligned_path = staging / f"{record_id}_aligned.jpg"
    marked_path = staging / f"{record_id}_marked.jpg"

    colour_source = load_colour(source_path)
    cv2.imwrite(str(original_path), colour_source)
    cv2.imwrite(str(aligned_path), aligned)
    marked = annotate_correct_answers_red(aligned, answers, answer_key, template["omr"], score, total)
    cv2.imwrite(str(marked_path), marked)

    review_required = (
        not class_name
        or not roll
        or alignment_confidence < 0.45
        or fields.get("roll", OCRField("", "", 0, True)).review_required
        or fields.get("class_name", OCRField("", "", 0, True)).review_required
        or evaluation.requires_manual_review
    )

    return ProcessedPaper(
        record_id=record_id,
        source_file=source_path.name,
        page_number=page_number,
        staging_original=str(original_path),
        staging_aligned=str(aligned_path),
        staging_marked=str(marked_path),
        class_name=class_name,
        roll=roll,
        name=name,
        section=section,
        score=score,
        total_questions=total,
        percentage=round(float(evaluation.percentage), 2),
        alignment_confidence=round(alignment_confidence, 4),
        review_required=review_required,
        fields={k: asdict(v) for k, v in fields.items()},
        answers={str(k): asdict(v) for k, v in answers.items()},
        evaluation=evaluation.to_dict(),
    )


def load_template(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
