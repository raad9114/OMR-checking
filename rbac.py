from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Set


PERMISSIONS = [
    "users.view",
    "users.create",
    "users.update",
    "users.disable",
    "roles.manage",
    "classes.manage",
    "students.manage",
    "exams.manage",
    "answer_keys.manage",
    "grading.configure",
    "omr.upload",
    "omr.process",
    "omr.review",
    "results.view",
    "results.edit",
    "results.publish",
    "results.export",
    "settings.manage",
    "audit_logs.view",
]

DEFAULT_ROLE_PERMISSIONS = {
    "Super Admin": set(PERMISSIONS),
    "Admin / Exam Manager": {
        "classes.manage",
        "students.manage",
        "exams.manage",
        "answer_keys.manage",
        "grading.configure",
        "omr.upload",
        "omr.process",
        "omr.review",
        "results.view",
        "results.edit",
        "results.publish",
        "results.export",
    },
    "Marker / Evaluator": {
        "omr.upload",
        "omr.process",
        "omr.review",
        "results.view",
    },
    "Result Viewer": {
        "results.view",
        "results.export",
    },
}


class AuthorizationError(PermissionError):
    pass


@dataclass(frozen=True)
class UserPrincipal:
    id: int
    name: str
    username: str
    email: str
    role_name: str
    permissions: Set[str]
    is_active: bool = True

    @classmethod
    def anonymous(cls) -> "UserPrincipal":
        return cls(0, "Anonymous", "", "", "Anonymous", set(), False)

    def has_permission(self, permission: str) -> bool:
        return self.is_active and permission in self.permissions


def has_permission(user: UserPrincipal | None, permission: str) -> bool:
    return bool(user and user.has_permission(permission))


def require_permission(user: UserPrincipal | None, permission: str) -> None:
    if not has_permission(user, permission):
        raise AuthorizationError(f"Permission required: {permission}")


def menu_allowed(user: UserPrincipal | None, permissions: Iterable[str]) -> bool:
    return any(has_permission(user, permission) for permission in permissions)
