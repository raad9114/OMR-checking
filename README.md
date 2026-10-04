# Bangla OCR Exam Grading Panel

A Gradio-based OMR examination panel for fixed-layout Bangla MCQ sheets. The application now uses MySQL for production persistence, secure login, permission-based access control, configurable grading rules, threshold-based bubble classification, manual-review flags, and result reports.

## Current Architecture

- Backend/UI framework: Python with Gradio in `app.py`.
- Frontend framework: Gradio Blocks components.
- OMR image processing: `ocr_engine.py`.
- Batch workflow: `batch_processor.py`.
- Central grading engine: `evaluation_service.py`.
- MySQL persistence: `mysql_repository.py`, `database.py`, `models.py`, `migrations/001_initial_mysql_schema.sql`.
- Authentication/RBAC: `auth.py`, `rbac.py`.
- Export: `excel_export.py`.
- Legacy SQLite migration: `scripts/migrate_sqlite_to_mysql.py`.

The original OpenCV alignment, Tesseract OCR field extraction, upload expansion, image staging, marked-image export, ZIP export, and Excel workbook generation are preserved.

## Key Features

- Login with username/email and password.
- PBKDF2 password hashing; no plain-text passwords.
- Default roles and permission checks for Super Admin, Admin / Exam Manager, Marker / Evaluator, and Result Viewer.
- Configurable exam settings: question count, default points, negative marking, bubble threshold, low-confidence bounds, dropped-question mode, and negative total-score behavior.
- Question-level rules: `NORMAL`, `FLAG_FAULTY`, `FLAG_DROPPED`.
- Dropped-question modes: `TOTAL_SHIFT` and `UNIVERSAL_BONUS`.
- Multiple-bubble detection; the engine no longer picks only the darkest option when multiple bubbles pass threshold.
- Low-confidence review flagging.
- Decimal-safe scoring.
- MySQL tables for users, roles, permissions, classes, students, exams, questions, OMR batches, sheets, responses, results, grade scales, and audit logs.
- Class-wise, student-wise, and exam-wise result query screens.
- Manual-review queue screen for stored low-confidence and multiple responses.
- Excel export with negative marks, bonus marks, response counts, and question-level scoring details.

## Install

Install Tesseract OCR and Bengali language support. Verify that `ben` appears in:

```bash
tesseract --list-langs
```

Install Python packages:

```bash
pip install -r requirements.txt
```

## Configure MySQL

Create a MySQL database and user, then copy `.env.example` to `.env` and set:

```env
DB_HOST=localhost
DB_PORT=3306
DB_NAME=omr_management
DB_USER=omr_user
DB_PASSWORD=secure_password
```

Run migrations and seed roles/permissions:

```bash
python scripts/migrate_mysql.py
```

Create the first Super Admin. The password must come from `.env` or the shell:

```env
SUPER_ADMIN_NAME=System Super Admin
SUPER_ADMIN_USERNAME=superadmin
SUPER_ADMIN_EMAIL=admin@example.com
SUPER_ADMIN_PASSWORD=change-this-secure-password
```

```bash
python scripts/seed_super_admin.py
```

Full migration and rollback notes are in `docs/MYSQL_MIGRATION.md`.

## Run

```bash
python app.py
```

Then open the local Gradio URL, log in, configure the exam/question rules, upload sheets, process, review, and finalise/export.

## Tests

Run unit tests:

```bash
python -m unittest discover -s tests
```

Run MySQL integration tests only when a disposable test database is configured:

```bash
set RUN_MYSQL_TESTS=1
python -m unittest tests.test_mysql_integration
```

## Legacy SQLite Migration

Back up the old database:

```bash
copy data\exam_results.sqlite data\exam_results.sqlite.backup
```

Copy legacy rows into MySQL:

```bash
python scripts/migrate_sqlite_to_mysql.py --sqlite data/exam_results.sqlite
```

## OMR Template

The supplied template is calibrated for the bundled Bandarban Cantonment form. Bubble coordinates and field ROIs are in `template.json`. The default fill threshold is now 40%, and authorized users can override it per exam in the app.

## Security Notes

- Credentials are loaded from environment variables or `.env`; they are not hardcoded.
- Backend callbacks enforce permissions.
- Inactive users cannot authenticate.
- Login success/failure and important user/result actions are written to audit logs.
- The Gradio interface uses session state for the current user. For internet-facing deployments, put it behind HTTPS and a trusted reverse proxy with secure cookies and request-size limits.

## Remaining Boundaries

The project remains a Gradio application, not a REST/SPA framework. The admin interface is implemented as Gradio tabs and callbacks rather than separate HTTP route controllers. Manual-review listing is implemented; final per-response correction should be expanded with reviewer decision forms if your operating workflow requires browser-based correction of every response.
