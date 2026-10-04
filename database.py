from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping

from mysql_repository import MySQLRepository


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def initialise() -> None:
    repository = MySQLRepository()
    repository.apply_migrations()
    repository.seed_roles_permissions()


def save_batch(
    database_path: str | Path | None = None,
    *,
    batch_id: str,
    exam_title: str,
    default_class: str,
    answer_key: Dict[int, str],
    records: List[Dict[str, Any]],
    exam_config: Mapping[str, Any] | None = None,
    question_rules: Mapping[int, Any] | None = None,
    acting_user_id: int | None = None,
) -> None:
    if database_path:
        # Kept for backward-compatible call sites. Persistence is now configured
        # by DB_* environment variables instead of a SQLite file path.
        _ = Path(database_path)
    repository = MySQLRepository()
    repository.save_legacy_batch(
        batch_id=batch_id,
        exam_title=exam_title,
        default_class=default_class,
        answer_key=answer_key,
        records=records,
        exam_config=exam_config,
        question_rules=question_rules,
        acting_user_id=acting_user_id,
    )
