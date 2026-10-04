# MySQL Setup And Migration

## Configure MySQL

Create the database and user in MySQL:

```sql
CREATE DATABASE omr_management CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'omr_user'@'localhost' IDENTIFIED BY 'use-a-strong-password';
GRANT ALL PRIVILEGES ON omr_management.* TO 'omr_user'@'localhost';
FLUSH PRIVILEGES;
```

Copy `.env.example` to `.env` and set:

```env
DB_HOST=localhost
DB_PORT=3306
DB_NAME=omr_management
DB_USER=omr_user
DB_PASSWORD=use-a-strong-password
```

## Run Migrations

```bash
python scripts/migrate_mysql.py
```

This applies SQL files in `migrations/` and seeds default roles and permissions.

## Create First Super Admin

Set these values in `.env` or the shell:

```env
SUPER_ADMIN_NAME=System Super Admin
SUPER_ADMIN_USERNAME=superadmin
SUPER_ADMIN_EMAIL=admin@example.com
SUPER_ADMIN_PASSWORD=change-this-secure-password
```

Then run:

```bash
python scripts/seed_super_admin.py
```

The password is hashed with PBKDF2 before storage. Do not commit real `.env` files.

## Backup Before Migration

Keep the existing SQLite file unchanged:

```bash
copy data\exam_results.sqlite data\exam_results.sqlite.backup
```

For MySQL rollback points:

```bash
mysqldump -u omr_user -p omr_management > omr_management_backup.sql
```

## Copy Legacy SQLite Results To MySQL

After migrations:

```bash
python scripts/migrate_sqlite_to_mysql.py --sqlite data/exam_results.sqlite
```

This script reads `exam_batches` and `submissions` from SQLite and writes normalized MySQL rows for exams, classes, students, OMR batches, sheets, responses, and results. It does not delete the SQLite file.

## Rollback

To restore a MySQL backup:

```bash
mysql -u omr_user -p omr_management < omr_management_backup.sql
```

To return temporarily to the old code path, restore the previous source version and the SQLite backup. The current implementation intentionally uses MySQL for final persistence.

## Legacy Field Mapping

| SQLite field | MySQL table/field |
| --- | --- |
| `exam_batches.batch_id` | `omr_upload_batches.batch_name`, `exams.exam_code` when no code exists |
| `exam_batches.exam_title` | `exams.exam_name` |
| `exam_batches.default_class` | `classes.class_name` |
| `exam_batches.answer_key_json` | `exam_questions.correct_option` |
| `submissions.roll` | `students.roll_number`, `omr_sheets.detected_roll_number` |
| `submissions.student_name` | `students.student_name` |
| `submissions.score` | `results.final_score` |
| `submissions.total_questions` | `results.maximum_score` |
| `submissions.percentage` | `results.percentage` |
| `submissions.answers_json` | `student_responses.fill_percentages` and status fields where available |
| `submissions.original_image` | `omr_sheets.source_image_path` |
| `submissions.marked_image` | `omr_sheets.annotated_image_path` |
