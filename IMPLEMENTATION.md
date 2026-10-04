# Implementation Summary

## Existing Project Analysis

- Backend framework: Gradio Blocks in `app.py`.
- Frontend framework: Gradio components rendered by the Python app.
- OMR module: `ocr_engine.py`.
- Existing grading function: `ocr_engine.grade_answers()`, now superseded for processing by `evaluation_service.evaluate_sheet()`.
- Existing database configuration: SQLite file `data/exam_results.sqlite` through the old `database.py`; now replaced by MySQL environment variables.
- Authentication before upgrade: none.
- Existing student/exam/result models before upgrade: no model layer; dictionaries were exported to JSON/XLSX and saved in two SQLite tables.
- Bubble darkness/fill calculation: `ocr_engine.disk_ink_ratio()` calculates the ratio of dark pixels in each bubble disk.

## Reused Modules

- `ocr_engine.py`: alignment, OCR field extraction, bubble ROI scanning, image annotation.
- `batch_processor.py`: upload expansion, batch staging, answer-sheet reading, output folder organization.
- `file_utils.py`: PDF expansion, unique folders, ZIP creation.
- `excel_export.py`: XLSX writer, expanded with new grading columns.

## Added Or Updated Modules

- `evaluation_service.py`: centralized Decimal-safe grading and response classification.
- `auth.py`: PBKDF2 password hashing, login, password change/reset helpers.
- `rbac.py`: permissions, default role permission sets, backend permission checks.
- `db_config.py`: environment-driven MySQL configuration.
- `mysql_repository.py`: MySQL migrations, seeds, auth queries, user management, batch persistence, reports.
- `models.py`: SQLAlchemy ORM model definitions matching the MySQL schema.
- `database.py`: compatibility adapter that now writes to MySQL.
- `migrations/001_initial_mysql_schema.sql`: normalized MySQL schema.
- `scripts/migrate_mysql.py`: applies migrations and seeds roles/permissions.
- `scripts/seed_super_admin.py`: creates the first Super Admin from environment variables.
- `scripts/migrate_sqlite_to_mysql.py`: optional legacy SQLite data migration.
- `tests/`: grading, RBAC/auth, and optional MySQL integration tests.

## Database Tables

Added MySQL tables:

- `schema_migrations`
- `roles`
- `permissions`
- `role_permissions`
- `users`
- `classes`
- `students`
- `grade_scales`
- `exams`
- `exam_questions`
- `omr_upload_batches`
- `omr_sheets`
- `student_responses`
- `results`
- `audit_logs`

The previous SQLite tables `exam_batches` and `submissions` are deprecated and can be migrated with `scripts/migrate_sqlite_to_mysql.py`.

## Grading Behavior

- `NORMAL`: threshold-based blank/correct/incorrect/multiple/low-confidence scoring.
- `FLAG_FAULTY`: awards full configured points to every student and never applies penalties.
- `FLAG_DROPPED` with `TOTAL_SHIFT`: excludes the question from scoring and maximum score.
- `FLAG_DROPPED` with `UNIVERSAL_BONUS`: awards full configured points to every student.
- Negative marking applies only to `INCORRECT` and `MULTIPLE`.
- Question-specific penalties override exam-level penalties.
- Decimal arithmetic is used for marks and penalties.
- Re-running the same detections with the same config is deterministic.

## Verification

```bash
python -m py_compile app.py batch_processor.py ocr_engine.py evaluation_service.py auth.py rbac.py db_config.py mysql_repository.py models.py scripts\migrate_mysql.py scripts\seed_super_admin.py scripts\migrate_sqlite_to_mysql.py
python -c "import app; print('app import ok')"
python -m unittest discover -s tests
```

Current test result: 24 tests passing, with 2 MySQL integration tests skipped unless `RUN_MYSQL_TESTS=1`.
