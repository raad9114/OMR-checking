from __future__ import annotations

import unittest

from auth import hash_password, verify_password
from rbac import DEFAULT_ROLE_PERMISSIONS, UserPrincipal, has_permission, require_permission


class RbacAuthTests(unittest.TestCase):
    def test_user_without_permission_cannot_change_grading_settings(self):
        user = UserPrincipal(1, "Viewer", "viewer", "viewer@example.com", "Result Viewer", {"results.view"}, True)
        with self.assertRaises(PermissionError):
            require_permission(user, "grading.configure")

    def test_marker_cannot_access_user_management(self):
        marker = UserPrincipal(
            2,
            "Marker",
            "marker",
            "marker@example.com",
            "Marker / Evaluator",
            DEFAULT_ROLE_PERMISSIONS["Marker / Evaluator"],
            True,
        )
        self.assertFalse(has_permission(marker, "users.view"))

    def test_super_admin_can_access_all_modules(self):
        admin = UserPrincipal(
            3,
            "Admin",
            "admin",
            "admin@example.com",
            "Super Admin",
            DEFAULT_ROLE_PERMISSIONS["Super Admin"],
            True,
        )
        for permission in DEFAULT_ROLE_PERMISSIONS["Super Admin"]:
            self.assertTrue(has_permission(admin, permission))

    def test_password_hash_is_not_plain_text_and_verifies(self):
        hashed = hash_password("secure-password")
        self.assertNotEqual(hashed, "secure-password")
        self.assertTrue(verify_password("secure-password", hashed))
        self.assertFalse(verify_password("wrong-password", hashed))


if __name__ == "__main__":
    unittest.main()
