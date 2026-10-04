from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from mysql_repository import MySQLRepository


def load_legacy_batches(sqlite_path: Path) -> List[Dict[str, Any]]:
    connection = sqlite3.connect(sqlite_path)
    connection.row_factory = sqlite3.Row
    try:
        batches = []
        for batch in connection.execute("SELECT * FROM exam_batches ORDER BY created_at"):
            records = []
            for row in connection.execute(
                "SELECT * FROM submissions WHERE batch_id=? ORDER BY record_id",
                (batch["batch_id"],),
            ):
                records.append(
                    {
                        "record_id": row["record_id"],
                        "source_file": row["source_file"],
                        "page_number": row["page_number"],
                        "class_name": row["class_name"],
                        "roll": row["roll"],
                        "name": row["student_name"],
                        "section": row["section"],
                        "score": row["score"],
                        "total_questions": row["total_questions"],
                        "percentage": row["percentage"],
                        "alignment_confidence": row["alignment_confidence"],
                        "review_required": bool(row["review_required"]),
                        "output_folder": row["output_folder"],
                        "original_image": row["original_image"],
                        "marked_image": row["marked_image"],
                        "staging_aligned": "",
                        "fields": json.loads(row["fields_json"] or "{}"),
                        "answers": json.loads(row["answers_json"] or "{}"),
                    }
                )
            batches.append(
                {
                    "batch_id": batch["batch_id"],
                    "exam_title": batch["exam_title"],
                    "default_class": batch["default_class"] or "",
                    "answer_key": {int(k): v for k, v in json.loads(batch["answer_key_json"]).items()},
                    "records": records,
                }
            )
        return batches
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy legacy SQLite OMR results into MySQL.")
    parser.add_argument("--sqlite", default="data/exam_results.sqlite", help="Path to the legacy SQLite database.")
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")

    repository = MySQLRepository()
    repository.apply_migrations()
    repository.seed_roles_permissions()
    batches = load_legacy_batches(sqlite_path)
    for batch in batches:
        repository.save_legacy_batch(**batch)
    print(f"Migrated {len(batches)} batch(es) from {sqlite_path} to MySQL.")


if __name__ == "__main__":
    main()
