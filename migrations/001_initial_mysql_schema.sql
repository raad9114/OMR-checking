CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(80) PRIMARY KEY,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS roles (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(80) NOT NULL UNIQUE,
    description TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS permissions (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    code VARCHAR(120) NOT NULL UNIQUE,
    description TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id BIGINT UNSIGNED NOT NULL,
    permission_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (role_id, permission_id),
    CONSTRAINT fk_role_permissions_role FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    CONSTRAINT fk_role_permissions_permission FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS users (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    username VARCHAR(80) NOT NULL UNIQUE,
    email VARCHAR(190) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role_id BIGINT UNSIGNED NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    last_login_at TIMESTAMP NULL,
    failed_login_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL,
    INDEX ix_users_username (username),
    INDEX ix_users_email (email),
    CONSTRAINT fk_users_role FOREIGN KEY (role_id) REFERENCES roles(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS classes (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    class_name VARCHAR(80) NOT NULL,
    section VARCHAR(80) NOT NULL DEFAULT '',
    academic_year VARCHAR(20) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL,
    UNIQUE KEY uq_class_section_year (class_name, section, academic_year),
    INDEX ix_classes_year (academic_year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS students (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    student_name VARCHAR(180) NOT NULL,
    roll_number VARCHAR(50) NOT NULL,
    registration_number VARCHAR(80) NULL UNIQUE,
    class_id BIGINT UNSIGNED NOT NULL,
    section VARCHAR(80) NOT NULL DEFAULT '',
    guardian_name VARCHAR(180) NULL,
    guardian_phone VARCHAR(60) NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL,
    UNIQUE KEY uq_student_roll_class_section (class_id, section, roll_number),
    INDEX ix_students_registration (registration_number),
    INDEX ix_students_name (student_name),
    CONSTRAINT fk_students_class FOREIGN KEY (class_id) REFERENCES classes(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS grade_scales (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(120) NOT NULL,
    minimum_percentage DECIMAL(8,4) NOT NULL,
    maximum_percentage DECIMAL(8,4) NOT NULL,
    letter_grade VARCHAR(20) NOT NULL,
    grade_point DECIMAL(6,3) NULL,
    remarks VARCHAR(255) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL,
    INDEX ix_grade_scales_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS exams (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    exam_name VARCHAR(180) NOT NULL,
    exam_code VARCHAR(80) NOT NULL UNIQUE,
    class_id BIGINT UNSIGNED NULL,
    subject VARCHAR(120) NOT NULL DEFAULT '',
    exam_date DATE NULL,
    total_questions INT NOT NULL,
    default_question_points DECIMAL(10,4) NOT NULL DEFAULT 1.0000,
    negative_marking_enabled TINYINT(1) NOT NULL DEFAULT 0,
    negative_mark_value DECIMAL(10,4) NOT NULL DEFAULT 0.0000,
    bubble_fill_threshold DECIMAL(8,4) NOT NULL DEFAULT 40.0000,
    low_confidence_review_enabled TINYINT(1) NOT NULL DEFAULT 0,
    low_confidence_lower_bound DECIMAL(8,4) NOT NULL DEFAULT 30.0000,
    low_confidence_upper_bound DECIMAL(8,4) NOT NULL DEFAULT 39.9900,
    dropped_question_mode VARCHAR(40) NOT NULL DEFAULT 'TOTAL_SHIFT',
    allow_negative_total_score TINYINT(1) NOT NULL DEFAULT 1,
    grade_scale_id BIGINT UNSIGNED NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    created_by BIGINT UNSIGNED NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL,
    INDEX ix_exams_class_subject (class_id, subject),
    CONSTRAINT fk_exams_class FOREIGN KEY (class_id) REFERENCES classes(id),
    CONSTRAINT fk_exams_grade_scale FOREIGN KEY (grade_scale_id) REFERENCES grade_scales(id),
    CONSTRAINT fk_exams_created_by FOREIGN KEY (created_by) REFERENCES users(id),
    CONSTRAINT ck_exams_threshold CHECK (bubble_fill_threshold >= 0 AND bubble_fill_threshold <= 100),
    CONSTRAINT ck_exams_negative CHECK (negative_mark_value >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS exam_questions (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    exam_id BIGINT UNSIGNED NOT NULL,
    question_number INT NOT NULL,
    correct_option VARCHAR(20) NOT NULL DEFAULT '',
    points DECIMAL(10,4) NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'NORMAL',
    custom_negative_mark DECIMAL(10,4) NULL,
    notes TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL,
    UNIQUE KEY uq_exam_question_number (exam_id, question_number),
    INDEX ix_exam_questions_status (exam_id, status),
    CONSTRAINT fk_exam_questions_exam FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE,
    CONSTRAINT ck_exam_question_status CHECK (status IN ('NORMAL', 'FLAG_FAULTY', 'FLAG_DROPPED')),
    CONSTRAINT ck_exam_question_points CHECK (points IS NULL OR points >= 0),
    CONSTRAINT ck_exam_question_penalty CHECK (custom_negative_mark IS NULL OR custom_negative_mark >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS omr_upload_batches (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    exam_id BIGINT UNSIGNED NOT NULL,
    batch_name VARCHAR(180) NOT NULL,
    uploaded_by BIGINT UNSIGNED NULL,
    total_files INT NOT NULL DEFAULT 0,
    processed_files INT NOT NULL DEFAULT 0,
    failed_files INT NOT NULL DEFAULT 0,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    INDEX ix_batches_exam_status (exam_id, status),
    CONSTRAINT fk_batches_exam FOREIGN KEY (exam_id) REFERENCES exams(id),
    CONSTRAINT fk_batches_uploaded_by FOREIGN KEY (uploaded_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS omr_sheets (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    batch_id BIGINT UNSIGNED NOT NULL,
    exam_id BIGINT UNSIGNED NOT NULL,
    student_id BIGINT UNSIGNED NULL,
    source_image_path VARCHAR(500) NOT NULL,
    aligned_image_path VARCHAR(500) NULL,
    annotated_image_path VARCHAR(500) NULL,
    detected_roll_number VARCHAR(80) NULL,
    detection_confidence DECIMAL(8,4) NOT NULL DEFAULT 0.0000,
    processing_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    review_status VARCHAR(30) NOT NULL DEFAULT 'NOT_REQUIRED',
    processed_at TIMESTAMP NULL,
    INDEX ix_omr_sheets_exam_student (exam_id, student_id),
    CONSTRAINT fk_omr_sheets_batch FOREIGN KEY (batch_id) REFERENCES omr_upload_batches(id),
    CONSTRAINT fk_omr_sheets_exam FOREIGN KEY (exam_id) REFERENCES exams(id),
    CONSTRAINT fk_omr_sheets_student FOREIGN KEY (student_id) REFERENCES students(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS student_responses (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    omr_sheet_id BIGINT UNSIGNED NOT NULL,
    exam_id BIGINT UNSIGNED NOT NULL,
    student_id BIGINT UNSIGNED NULL,
    question_id BIGINT UNSIGNED NOT NULL,
    selected_option VARCHAR(20) NULL,
    detected_options JSON NULL,
    response_status VARCHAR(40) NOT NULL,
    fill_percentages JSON NULL,
    confidence_score DECIMAL(8,4) NOT NULL DEFAULT 0.0000,
    awarded_marks DECIMAL(10,4) NOT NULL DEFAULT 0.0000,
    penalty_marks DECIMAL(10,4) NOT NULL DEFAULT 0.0000,
    final_marks DECIMAL(10,4) NOT NULL DEFAULT 0.0000,
    requires_manual_review TINYINT(1) NOT NULL DEFAULT 0,
    reviewed_by BIGINT UNSIGNED NULL,
    reviewed_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL,
    UNIQUE KEY uq_response_sheet_question (omr_sheet_id, question_id),
    INDEX ix_responses_exam_student (exam_id, student_id),
    INDEX ix_responses_status (exam_id, response_status),
    CONSTRAINT fk_responses_sheet FOREIGN KEY (omr_sheet_id) REFERENCES omr_sheets(id) ON DELETE CASCADE,
    CONSTRAINT fk_responses_exam FOREIGN KEY (exam_id) REFERENCES exams(id),
    CONSTRAINT fk_responses_student FOREIGN KEY (student_id) REFERENCES students(id),
    CONSTRAINT fk_responses_question FOREIGN KEY (question_id) REFERENCES exam_questions(id),
    CONSTRAINT fk_responses_reviewed_by FOREIGN KEY (reviewed_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS results (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    exam_id BIGINT UNSIGNED NOT NULL,
    student_id BIGINT UNSIGNED NULL,
    omr_sheet_id BIGINT UNSIGNED NOT NULL,
    raw_positive_marks DECIMAL(10,4) NOT NULL DEFAULT 0.0000,
    total_negative_marks DECIMAL(10,4) NOT NULL DEFAULT 0.0000,
    bonus_marks DECIMAL(10,4) NOT NULL DEFAULT 0.0000,
    raw_calculated_score DECIMAL(10,4) NOT NULL DEFAULT 0.0000,
    final_score DECIMAL(10,4) NOT NULL DEFAULT 0.0000,
    maximum_score DECIMAL(10,4) NOT NULL DEFAULT 0.0000,
    percentage DECIMAL(8,4) NOT NULL DEFAULT 0.0000,
    grade VARCHAR(20) NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'UNPUBLISHED',
    evaluated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL,
    UNIQUE KEY uq_result_exam_student (exam_id, student_id),
    INDEX ix_results_exam_status (exam_id, status),
    CONSTRAINT fk_results_exam FOREIGN KEY (exam_id) REFERENCES exams(id),
    CONSTRAINT fk_results_student FOREIGN KEY (student_id) REFERENCES students(id),
    CONSTRAINT fk_results_sheet FOREIGN KEY (omr_sheet_id) REFERENCES omr_sheets(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NULL,
    action VARCHAR(120) NOT NULL,
    entity_type VARCHAR(80) NULL,
    entity_id VARCHAR(80) NULL,
    old_values JSON NULL,
    new_values JSON NULL,
    ip_address VARCHAR(80) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_audit_entity (entity_type, entity_id),
    INDEX ix_audit_user_action (user_id, action),
    CONSTRAINT fk_audit_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO schema_migrations(version) VALUES ('001_initial_mysql_schema');
