from __future__ import annotations

import os
import unittest

from auth import hash_password
from mysql_repository import MySQLRepository


MYSQL_ENABLED = os.getenv("RUN_MYSQL_TESTS") == "1"


@unittest.skipUnless(MYSQL_ENABLED, "Set RUN_MYSQL_TESTS=1 and DB_* variables to run MySQL integration tests.")
class MySQLIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.repository = MySQLRepository()
        self.repository.apply_migrations()
        self.repository.seed_roles_permissions()

    def test_roles_permissions_and_super_admin_seed(self):
        user_id = self.repository.create_super_admin(
            name="Integration Super Admin",
            username="integration_admin",
            email="integration_admin@example.com",
            password_hash=hash_password("integration-password"),
        )
        user = self.repository.get_user_with_permissions(user_id)
        self.assertEqual(user["role_name"], "Super Admin")
        self.assertIn("users.view", user["permissions"])
        self.assertIn("omr.process", user["permissions"])

    def test_exam_batch_result_relationships(self):
        self.repository.save_legacy_batch(
            batch_id="integration_batch_001",
            exam_title="Integration Exam",
            default_class="2",
            answer_key={1: "A"},
            records=[
                {
                    "record_id": "paper_0001",
                    "source_file": "student_1.png",
                    "page_number": 1,
                    "class_name": "2",
                    "roll": "1",
                    "name": "Integration Student",
                    "section": "A",
                    "score": 1,
                    "total_questions": 1,
                    "percentage": 100,
                    "alignment_confidence": 1,
                    "review_required": False,
                    "original_image": "storage/omr/2/integration/student_1.png",
                    "marked_image": "storage/omr/2/integration/student_1_marked.jpg",
                    "staging_aligned": "storage/omr/2/integration/student_1_aligned.jpg",
                    "evaluation": {
                        "responses": {
                            "1": {
                                "selected_option": "A",
                                "detected_options": ["A"],
                                "response_status": "CORRECT",
                                "fill_percentages": {"A": 50, "B": 0, "C": 0, "D": 0},
                                "confidence_score": 0.5,
                                "awarded_marks": 1,
                                "penalty_marks": 0,
                                "final_marks": 1,
                                "requires_manual_review": False,
                            }
                        },
                        "raw_positive_marks": 1,
                        "total_negative_marks": 0,
                        "bonus_marks": 0,
                        "raw_calculated_score": 1,
                        "final_score": 1,
                        "maximum_score": 1,
                        "percentage": 100,
                    },
                }
            ],
            exam_config={"exam_code": "integration_exam_001", "total_questions": 1},
        )


if __name__ == "__main__":
    unittest.main()
