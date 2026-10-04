from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Mapping, Optional


DECIMAL_PLACES = Decimal("0.0001")

QUESTION_NORMAL = "NORMAL"
QUESTION_FAULTY = "FLAG_FAULTY"
QUESTION_DROPPED = "FLAG_DROPPED"

DROPPED_TOTAL_SHIFT = "TOTAL_SHIFT"
DROPPED_UNIVERSAL_BONUS = "UNIVERSAL_BONUS"

RESPONSE_BLANK = "BLANK"
RESPONSE_CORRECT = "CORRECT"
RESPONSE_INCORRECT = "INCORRECT"
RESPONSE_MULTIPLE = "MULTIPLE"
RESPONSE_LOW_CONFIDENCE = "LOW_CONFIDENCE"
RESPONSE_FAULTY_BONUS = "FAULTY_BONUS"
RESPONSE_DROPPED_EXCLUDED = "DROPPED_EXCLUDED"
RESPONSE_DROPPED_BONUS = "DROPPED_BONUS"


def to_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))


def money(value: Decimal) -> Decimal:
    return value.quantize(DECIMAL_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ExamGradingConfig:
    total_questions: int
    default_question_points: Decimal = Decimal("1")
    negative_marking_enabled: bool = False
    negative_mark_value: Decimal = Decimal("0")
    bubble_fill_threshold: Decimal = Decimal("40")
    low_confidence_review_enabled: bool = False
    low_confidence_lower_bound: Decimal = Decimal("30")
    low_confidence_upper_bound: Decimal = Decimal("39.99")
    dropped_question_mode: str = DROPPED_TOTAL_SHIFT
    allow_negative_total_score: bool = True

    @classmethod
    def from_values(
        cls,
        *,
        total_questions: int,
        default_question_points: Any = "1",
        negative_marking_enabled: bool = False,
        negative_mark_value: Any = "0",
        bubble_fill_threshold: Any = "40",
        low_confidence_review_enabled: bool = False,
        low_confidence_lower_bound: Any = "30",
        low_confidence_upper_bound: Any = "39.99",
        dropped_question_mode: str = DROPPED_TOTAL_SHIFT,
        allow_negative_total_score: bool = True,
    ) -> "ExamGradingConfig":
        config = cls(
            total_questions=int(total_questions),
            default_question_points=to_decimal(default_question_points, "1"),
            negative_marking_enabled=bool(negative_marking_enabled),
            negative_mark_value=to_decimal(negative_mark_value),
            bubble_fill_threshold=to_decimal(bubble_fill_threshold, "40"),
            low_confidence_review_enabled=bool(low_confidence_review_enabled),
            low_confidence_lower_bound=to_decimal(low_confidence_lower_bound, "30"),
            low_confidence_upper_bound=to_decimal(low_confidence_upper_bound, "39.99"),
            dropped_question_mode=dropped_question_mode or DROPPED_TOTAL_SHIFT,
            allow_negative_total_score=bool(allow_negative_total_score),
        )
        validate_exam_config(config)
        return config


@dataclass(frozen=True)
class QuestionRule:
    question_number: int
    correct_option: str = ""
    points: Optional[Decimal] = None
    status: str = QUESTION_NORMAL
    custom_negative_mark: Optional[Decimal] = None
    notes: str = ""

    @classmethod
    def from_values(
        cls,
        *,
        question_number: int,
        correct_option: str = "",
        points: Any = None,
        status: str = QUESTION_NORMAL,
        custom_negative_mark: Any = None,
        notes: str = "",
    ) -> "QuestionRule":
        return cls(
            question_number=int(question_number),
            correct_option=str(correct_option or "").strip(),
            points=to_decimal(points) if points not in (None, "") else None,
            status=str(status or QUESTION_NORMAL).strip() or QUESTION_NORMAL,
            custom_negative_mark=(
                to_decimal(custom_negative_mark)
                if custom_negative_mark not in (None, "")
                else None
            ),
            notes=str(notes or "").strip(),
        )


@dataclass(frozen=True)
class DetectedResponse:
    question_number: int
    fill_percentages: Mapping[str, Decimal]
    selected_option_hint: str = ""
    confidence_score: Decimal = Decimal("0")

    @classmethod
    def from_omr_answer(
        cls,
        question_number: int,
        option_labels: Iterable[str],
        answer: Any,
    ) -> "DetectedResponse":
        ratios = list(getattr(answer, "ink_ratios", []) or [])
        percentages = normalise_fill_percentages(dict(zip(option_labels, ratios)))
        return cls(
            question_number=question_number,
            fill_percentages=percentages,
            selected_option_hint=getattr(answer, "selected_option", "") or "",
            confidence_score=to_decimal(getattr(answer, "confidence", 0)),
        )


@dataclass
class ResponseEvaluation:
    question_number: int
    question_status: str
    selected_option: str
    detected_options: List[str]
    response_status: str
    fill_percentages: Dict[str, Decimal]
    confidence_score: Decimal
    awarded_marks: Decimal
    penalty_marks: Decimal
    final_marks: Decimal
    maximum_marks: Decimal
    requires_manual_review: bool = False
    correct_option: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_number": self.question_number,
            "question_status": self.question_status,
            "selected_option": self.selected_option,
            "detected_options": self.detected_options,
            "response_status": self.response_status,
            "fill_percentages": {k: float(v) for k, v in self.fill_percentages.items()},
            "confidence_score": float(self.confidence_score),
            "awarded_marks": float(self.awarded_marks),
            "penalty_marks": float(self.penalty_marks),
            "final_marks": float(self.final_marks),
            "maximum_marks": float(self.maximum_marks),
            "requires_manual_review": self.requires_manual_review,
            "correct_option": self.correct_option,
        }


@dataclass
class SheetEvaluation:
    responses: Dict[int, ResponseEvaluation]
    raw_positive_marks: Decimal
    total_negative_marks: Decimal
    bonus_marks: Decimal
    raw_calculated_score: Decimal
    final_score: Decimal
    maximum_score: Decimal
    percentage: Decimal
    counts: Dict[str, int] = field(default_factory=dict)
    requires_manual_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "responses": {str(k): v.to_dict() for k, v in self.responses.items()},
            "raw_positive_marks": float(self.raw_positive_marks),
            "total_negative_marks": float(self.total_negative_marks),
            "bonus_marks": float(self.bonus_marks),
            "raw_calculated_score": float(self.raw_calculated_score),
            "final_score": float(self.final_score),
            "maximum_score": float(self.maximum_score),
            "percentage": float(self.percentage),
            "counts": self.counts,
            "requires_manual_review": self.requires_manual_review,
        }


def normalise_fill_percentages(values: Mapping[str, Any]) -> Dict[str, Decimal]:
    decimals = {str(k): to_decimal(v) for k, v in values.items()}
    if decimals and all(v <= Decimal("1") for v in decimals.values()):
        return {k: money(v * Decimal("100")) for k, v in decimals.items()}
    return {k: money(v) for k, v in decimals.items()}


def validate_exam_config(config: ExamGradingConfig) -> None:
    if config.total_questions < 1:
        raise ValueError("Total questions must be at least 1.")
    if config.default_question_points < 0:
        raise ValueError("Default question points must be zero or greater.")
    if config.negative_mark_value < 0:
        raise ValueError("Negative mark value must be zero or greater.")
    if not Decimal("0") <= config.bubble_fill_threshold <= Decimal("100"):
        raise ValueError("Bubble threshold must be between 0 and 100.")
    if config.low_confidence_lower_bound < 0:
        raise ValueError("Low-confidence lower bound must be zero or greater.")
    if config.low_confidence_lower_bound >= config.bubble_fill_threshold:
        raise ValueError("Low-confidence lower bound must be lower than the main threshold.")
    if config.low_confidence_upper_bound >= config.bubble_fill_threshold:
        raise ValueError("Low-confidence upper bound must be lower than the main threshold.")
    if config.low_confidence_upper_bound < config.low_confidence_lower_bound:
        raise ValueError("Low-confidence upper bound must be greater than or equal to the lower bound.")
    if config.dropped_question_mode not in {DROPPED_TOTAL_SHIFT, DROPPED_UNIVERSAL_BONUS}:
        raise ValueError("Dropped-question mode must be TOTAL_SHIFT or UNIVERSAL_BONUS.")


def validate_question_rules(
    rules: Mapping[int, QuestionRule],
    *,
    total_questions: int,
    option_labels: Iterable[str],
) -> None:
    valid_statuses = {QUESTION_NORMAL, QUESTION_FAULTY, QUESTION_DROPPED}
    labels = set(option_labels)
    for question_no, rule in rules.items():
        if question_no < 1 or question_no > total_questions:
            raise ValueError(f"Question {question_no} is outside the exam range.")
        if rule.status not in valid_statuses:
            raise ValueError(f"Question {question_no} has an invalid status.")
        if rule.status == QUESTION_NORMAL and rule.correct_option not in labels:
            raise ValueError(f"Question {question_no} needs a valid correct option.")
        if rule.points is not None and rule.points < 0:
            raise ValueError(f"Question {question_no} points must be zero or greater.")
        if rule.custom_negative_mark is not None and rule.custom_negative_mark < 0:
            raise ValueError(f"Question {question_no} penalty must be zero or greater.")


def build_question_rules(
    *,
    answer_key: Mapping[int, str],
    total_questions: int,
    default_points: Any = None,
    rows: Iterable[Iterable[Any]] | None = None,
) -> Dict[int, QuestionRule]:
    rules = {
        q: QuestionRule.from_values(
            question_number=q,
            correct_option=answer_key.get(q, ""),
            points=default_points,
        )
        for q in range(1, total_questions + 1)
    }
    if rows:
        for row in rows:
            cells = list(row)
            if not cells or cells[0] in (None, ""):
                continue
            question_no = int(cells[0])
            if question_no < 1 or question_no > total_questions:
                continue
            rules[question_no] = QuestionRule.from_values(
                question_number=question_no,
                correct_option=cells[1] if len(cells) > 1 else answer_key.get(question_no, ""),
                points=cells[2] if len(cells) > 2 else default_points,
                status=cells[3] if len(cells) > 3 else QUESTION_NORMAL,
                custom_negative_mark=cells[4] if len(cells) > 4 else None,
                notes=cells[5] if len(cells) > 5 else "",
            )
    return rules


def classify_detected_response(
    detected: DetectedResponse,
    config: ExamGradingConfig,
) -> tuple[str, str, List[str], bool, Decimal]:
    fills = normalise_fill_percentages(detected.fill_percentages)
    selected_options = [
        option
        for option, percentage in fills.items()
        if percentage >= config.bubble_fill_threshold
    ]
    selected_options.sort()
    max_fill = max(fills.values(), default=Decimal("0"))
    if not selected_options:
        review = (
            config.low_confidence_review_enabled
            and config.low_confidence_lower_bound <= max_fill <= config.low_confidence_upper_bound
        )
        if review:
            darkest = max(fills.items(), key=lambda item: item[1])[0] if fills else ""
            return RESPONSE_LOW_CONFIDENCE, darkest, [], True, money(max_fill / Decimal("100"))
        return RESPONSE_BLANK, "", [], False, money(max_fill / Decimal("100"))
    if len(selected_options) > 1:
        return RESPONSE_MULTIPLE, "", selected_options, True, money(max_fill / Decimal("100"))
    return "SELECTED", selected_options[0], selected_options, False, money(max_fill / Decimal("100"))


def configured_penalty(config: ExamGradingConfig, rule: QuestionRule) -> Decimal:
    if not config.negative_marking_enabled:
        return Decimal("0")
    if rule.custom_negative_mark is not None:
        return rule.custom_negative_mark
    return config.negative_mark_value


def evaluate_sheet(
    *,
    detections: Mapping[int, DetectedResponse],
    question_rules: Mapping[int, QuestionRule],
    config: ExamGradingConfig,
    option_labels: Iterable[str],
) -> SheetEvaluation:
    validate_exam_config(config)
    validate_question_rules(question_rules, total_questions=config.total_questions, option_labels=option_labels)

    responses: Dict[int, ResponseEvaluation] = {}
    positive_marks = Decimal("0")
    negative_marks = Decimal("0")
    bonus_marks = Decimal("0")
    maximum_score = Decimal("0")
    counts: Dict[str, int] = {}
    requires_review = False

    labels = list(option_labels)
    empty_detection = DetectedResponse(0, {label: Decimal("0") for label in labels})

    for question_no in range(1, config.total_questions + 1):
        rule = question_rules[question_no]
        points = rule.points if rule.points is not None else config.default_question_points
        points = money(points)
        detected = detections.get(question_no, empty_detection)
        fills = normalise_fill_percentages(detected.fill_percentages)

        if rule.status == QUESTION_FAULTY:
            maximum_score += points
            bonus_marks += points
            response = ResponseEvaluation(
                question_number=question_no,
                question_status=rule.status,
                selected_option="",
                detected_options=[],
                response_status=RESPONSE_FAULTY_BONUS,
                fill_percentages=fills,
                confidence_score=Decimal("1"),
                awarded_marks=points,
                penalty_marks=Decimal("0"),
                final_marks=points,
                maximum_marks=points,
                correct_option=rule.correct_option,
            )
            responses[question_no] = response
            counts[response.response_status] = counts.get(response.response_status, 0) + 1
            continue

        if rule.status == QUESTION_DROPPED:
            if config.dropped_question_mode == DROPPED_TOTAL_SHIFT:
                response = ResponseEvaluation(
                    question_number=question_no,
                    question_status=rule.status,
                    selected_option="",
                    detected_options=[],
                    response_status=RESPONSE_DROPPED_EXCLUDED,
                    fill_percentages=fills,
                    confidence_score=Decimal("1"),
                    awarded_marks=Decimal("0"),
                    penalty_marks=Decimal("0"),
                    final_marks=Decimal("0"),
                    maximum_marks=Decimal("0"),
                    correct_option=rule.correct_option,
                )
                responses[question_no] = response
                counts[response.response_status] = counts.get(response.response_status, 0) + 1
                continue
            maximum_score += points
            bonus_marks += points
            response = ResponseEvaluation(
                question_number=question_no,
                question_status=rule.status,
                selected_option="",
                detected_options=[],
                response_status=RESPONSE_DROPPED_BONUS,
                fill_percentages=fills,
                confidence_score=Decimal("1"),
                awarded_marks=points,
                penalty_marks=Decimal("0"),
                final_marks=points,
                maximum_marks=points,
                correct_option=rule.correct_option,
            )
            responses[question_no] = response
            counts[response.response_status] = counts.get(response.response_status, 0) + 1
            continue

        maximum_score += points
        status, selected_option, detected_options, manual_review, confidence = classify_detected_response(detected, config)
        awarded = Decimal("0")
        penalty = Decimal("0")

        if status == "SELECTED":
            if selected_option == rule.correct_option:
                status = RESPONSE_CORRECT
                awarded = points
                positive_marks += awarded
            else:
                status = RESPONSE_INCORRECT
                penalty = configured_penalty(config, rule)
                negative_marks += penalty
        elif status == RESPONSE_MULTIPLE:
            penalty = configured_penalty(config, rule)
            negative_marks += penalty

        if manual_review:
            requires_review = True
        response = ResponseEvaluation(
            question_number=question_no,
            question_status=rule.status,
            selected_option=selected_option,
            detected_options=detected_options,
            response_status=status,
            fill_percentages=fills,
            confidence_score=confidence,
            awarded_marks=money(awarded),
            penalty_marks=money(penalty),
            final_marks=money(awarded - penalty),
            maximum_marks=points,
            requires_manual_review=manual_review,
            correct_option=rule.correct_option,
        )
        responses[question_no] = response
        counts[status] = counts.get(status, 0) + 1

    raw_score = money(positive_marks + bonus_marks - negative_marks)
    final_score = raw_score if config.allow_negative_total_score else max(Decimal("0"), raw_score)
    percentage = money((final_score / maximum_score * Decimal("100")) if maximum_score else Decimal("0"))
    return SheetEvaluation(
        responses=responses,
        raw_positive_marks=money(positive_marks),
        total_negative_marks=money(negative_marks),
        bonus_marks=money(bonus_marks),
        raw_calculated_score=raw_score,
        final_score=money(final_score),
        maximum_score=money(maximum_score),
        percentage=percentage,
        counts=counts,
        requires_manual_review=requires_review,
    )
