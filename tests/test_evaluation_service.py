from __future__ import annotations

import unittest
from decimal import Decimal

from evaluation_service import (
    DROPPED_TOTAL_SHIFT,
    DROPPED_UNIVERSAL_BONUS,
    QUESTION_DROPPED,
    QUESTION_FAULTY,
    QUESTION_NORMAL,
    RESPONSE_BLANK,
    RESPONSE_CORRECT,
    RESPONSE_DROPPED_BONUS,
    RESPONSE_DROPPED_EXCLUDED,
    RESPONSE_FAULTY_BONUS,
    RESPONSE_INCORRECT,
    RESPONSE_LOW_CONFIDENCE,
    RESPONSE_MULTIPLE,
    DetectedResponse,
    ExamGradingConfig,
    QuestionRule,
    evaluate_sheet,
)


OPTIONS = ["A", "B", "C", "D"]


def config(**overrides):
    values = {
        "total_questions": 1,
        "default_question_points": "1",
        "negative_marking_enabled": True,
        "negative_mark_value": "0.25",
        "bubble_fill_threshold": "40",
        "low_confidence_review_enabled": False,
        "low_confidence_lower_bound": "30",
        "low_confidence_upper_bound": "39.99",
        "dropped_question_mode": DROPPED_TOTAL_SHIFT,
        "allow_negative_total_score": True,
    }
    values.update(overrides)
    return ExamGradingConfig.from_values(**values)


def rule(**overrides):
    values = {
        "question_number": 1,
        "correct_option": "A",
        "points": "1",
        "status": QUESTION_NORMAL,
    }
    values.update(overrides)
    return QuestionRule.from_values(**values)


def detected(**fills):
    values = {"A": 0, "B": 0, "C": 0, "D": 0}
    values.update(fills)
    return DetectedResponse(1, values)


def evaluate(det, cfg=None, qrule=None):
    return evaluate_sheet(
        detections={1: det},
        question_rules={1: qrule or rule()},
        config=cfg or config(),
        option_labels=OPTIONS,
    )


class EvaluationServiceTests(unittest.TestCase):
    def test_correct_response_receives_full_points(self):
        result = evaluate(detected(A=45))
        self.assertEqual(result.responses[1].response_status, RESPONSE_CORRECT)
        self.assertEqual(result.final_score, Decimal("1.0000"))

    def test_incorrect_response_receives_penalty(self):
        result = evaluate(detected(B=45))
        self.assertEqual(result.responses[1].response_status, RESPONSE_INCORRECT)
        self.assertEqual(result.total_negative_marks, Decimal("0.2500"))
        self.assertEqual(result.final_score, Decimal("-0.2500"))

    def test_blank_response_receives_zero_and_no_penalty(self):
        result = evaluate(detected(A=10, B=12))
        self.assertEqual(result.responses[1].response_status, RESPONSE_BLANK)
        self.assertEqual(result.total_negative_marks, Decimal("0.0000"))

    def test_multiple_bubbles_are_incorrect_and_penalized(self):
        result = evaluate(detected(A=45, B=44))
        self.assertEqual(result.responses[1].response_status, RESPONSE_MULTIPLE)
        self.assertEqual(result.total_negative_marks, Decimal("0.2500"))

    def test_faint_marks_below_threshold_are_blank(self):
        result = evaluate(detected(A=29))
        self.assertEqual(result.responses[1].response_status, RESPONSE_BLANK)
        self.assertFalse(result.responses[1].requires_manual_review)

    def test_low_confidence_marks_are_queued_for_manual_review(self):
        result = evaluate(
            detected(A=35),
            cfg=config(low_confidence_review_enabled=True),
        )
        self.assertEqual(result.responses[1].response_status, RESPONSE_LOW_CONFIDENCE)
        self.assertTrue(result.responses[1].requires_manual_review)
        self.assertEqual(result.total_negative_marks, Decimal("0.0000"))

    def test_faulty_question_awards_full_points_to_every_response_type(self):
        result = evaluate(detected(B=45), qrule=rule(status=QUESTION_FAULTY, points="2"))
        self.assertEqual(result.responses[1].response_status, RESPONSE_FAULTY_BONUS)
        self.assertEqual(result.bonus_marks, Decimal("2.0000"))
        self.assertEqual(result.final_score, Decimal("2.0000"))

    def test_faulty_question_never_receives_penalty(self):
        result = evaluate(detected(B=45, C=44), qrule=rule(status=QUESTION_FAULTY))
        self.assertEqual(result.total_negative_marks, Decimal("0.0000"))

    def test_dropped_total_shift_reduces_maximum_score(self):
        result = evaluate(detected(A=45), qrule=rule(status=QUESTION_DROPPED))
        self.assertEqual(result.responses[1].response_status, RESPONSE_DROPPED_EXCLUDED)
        self.assertEqual(result.maximum_score, Decimal("0.0000"))

    def test_dropped_universal_bonus_awards_full_points(self):
        result = evaluate(
            detected(B=45),
            cfg=config(dropped_question_mode=DROPPED_UNIVERSAL_BONUS),
            qrule=rule(status=QUESTION_DROPPED),
        )
        self.assertEqual(result.responses[1].response_status, RESPONSE_DROPPED_BONUS)
        self.assertEqual(result.final_score, Decimal("1.0000"))

    def test_negative_marking_disabled_produces_no_penalty(self):
        result = evaluate(detected(B=45), cfg=config(negative_marking_enabled=False))
        self.assertEqual(result.total_negative_marks, Decimal("0.0000"))

    def test_question_specific_penalty_overrides_exam_penalty(self):
        result = evaluate(detected(B=45), qrule=rule(custom_negative_mark="0.50"))
        self.assertEqual(result.total_negative_marks, Decimal("0.5000"))

    def test_decimal_marks_and_penalties_are_exact(self):
        result = evaluate(
            detected(B=45),
            cfg=config(default_question_points="1.25", negative_mark_value="0.33"),
            qrule=rule(points="1.25"),
        )
        self.assertEqual(result.final_score, Decimal("-0.3300"))

    def test_blank_answers_never_receive_negative_marks(self):
        result = evaluate(detected())
        self.assertEqual(result.responses[1].penalty_marks, Decimal("0.0000"))

    def test_multiple_answers_receive_negative_only_when_enabled(self):
        enabled = evaluate(detected(A=50, B=50))
        disabled = evaluate(detected(A=50, B=50), cfg=config(negative_marking_enabled=False))
        self.assertEqual(enabled.total_negative_marks, Decimal("0.2500"))
        self.assertEqual(disabled.total_negative_marks, Decimal("0.0000"))

    def test_final_score_can_be_clamped_to_zero(self):
        result = evaluate(detected(B=45), cfg=config(allow_negative_total_score=False))
        self.assertEqual(result.raw_calculated_score, Decimal("-0.2500"))
        self.assertEqual(result.final_score, Decimal("0.0000"))

    def test_re_running_unchanged_inputs_is_deterministic(self):
        first = evaluate(detected(A=45)).to_dict()
        second = evaluate(detected(A=45)).to_dict()
        self.assertEqual(first, second)

    def test_re_evaluation_updates_results_with_new_rules(self):
        before = evaluate(detected(B=45))
        after = evaluate(detected(B=45), qrule=rule(status=QUESTION_FAULTY))
        self.assertEqual(before.final_score, Decimal("-0.2500"))
        self.assertEqual(after.final_score, Decimal("1.0000"))


if __name__ == "__main__":
    unittest.main()
