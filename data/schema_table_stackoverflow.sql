-- Stack Overflow crawler schema
-- Mục tiêu:
--   - Theo dõi câu hỏi mới được tạo trong vòng 24 giờ.
--   - Hỗ trợ source theo tag hoặc keyword.
--   - Xếp hạng độ thảo luận theo answer_count, score và view_count.
--   - Lưu tag riêng để tránh lặp dữ liệu.

PRAGMA foreign_keys = ON;

CREATE TABLE sources (
    id INTEGER PRIMARY KEY,

    source_type VARCHAR(20) NOT NULL
        CHECK (source_type IN ('tag', 'keyword', 'latest')),

    -- tag:     python
    -- keyword: memory leak
    -- latest:  latest
    identifier VARCHAR(300) NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT 1,
    is_accessible BOOLEAN NOT NULL DEFAULT 1,

    -- 1: lấy và lưu câu trả lời; 0: chỉ dùng answer_count từ question_metrics.
    include_answers BOOLEAN NOT NULL DEFAULT 0,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_scraped DATETIME,
    next_scrape DATETIME,

    schedule_tier INTEGER,
    schedule_override_minutes INTEGER,

    UNIQUE (source_type, identifier)
);

CREATE INDEX idx_sources_next_scrape
    ON sources (is_active, is_accessible, next_scrape);


CREATE TABLE questions (
    id INTEGER PRIMARY KEY,

    stackoverflow_question_id INTEGER NOT NULL,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,

    title TEXT NOT NULL,
    link TEXT NOT NULL,

    author_user_id INTEGER,
    author_display_name VARCHAR(200),
    author_link TEXT,

    is_answered BOOLEAN NOT NULL DEFAULT 0,

    last_activity_at DATETIME NOT NULL,
    question_created_at DATETIME NOT NULL,
    last_edited_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    is_tracked BOOLEAN NOT NULL DEFAULT 1,
    tracking_until DATETIME,
    is_deleted BOOLEAN NOT NULL DEFAULT 0,

    last_metric_update DATETIME,
    next_metric_update DATETIME,
    metric_tier VARCHAR(20) NOT NULL DEFAULT 'very_low'
        CHECK (metric_tier IN (
            'hot', 'high', 'medium', 'low', 'very_low'
        )),

    UNIQUE (stackoverflow_question_id),
    UNIQUE (link)
);

CREATE INDEX idx_questions_created
    ON questions (question_created_at);
CREATE INDEX idx_questions_metric_due
    ON questions (is_tracked, next_metric_update);
CREATE INDEX idx_questions_source
    ON questions (source_id);


-- Một question có thể được tìm thấy từ nhiều source, ví dụ tag + keyword.
CREATE TABLE source_questions (
    source_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,

    first_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (source_id, question_id),

    FOREIGN KEY (source_id)
        REFERENCES sources(id) ON DELETE CASCADE,
    FOREIGN KEY (question_id)
        REFERENCES questions(id) ON DELETE CASCADE
);

CREATE INDEX idx_source_questions_question
    ON source_questions (question_id);


CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    tag_name VARCHAR(100) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (tag_name)
);

CREATE INDEX idx_tags_name
    ON tags (tag_name);


-- Quan hệ nhiều-nhiều giữa question và tag.
CREATE TABLE question_tags (
    question_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,

    PRIMARY KEY (question_id, tag_id),

    FOREIGN KEY (question_id)
        REFERENCES questions(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)
        REFERENCES tags(id) ON DELETE CASCADE
);

CREATE INDEX idx_question_tags_tag
    ON question_tags (tag_id);


CREATE TABLE analytics_cache (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL,
    date DATE NOT NULL,

    total_questions INTEGER NOT NULL DEFAULT 0,
    total_answers INTEGER NOT NULL DEFAULT 0,
    total_views INTEGER NOT NULL DEFAULT 0,
    total_score INTEGER NOT NULL DEFAULT 0,
    avg_answers_per_question FLOAT NOT NULL DEFAULT 0,
    top_question_id INTEGER,
    growth_rate FLOAT NOT NULL DEFAULT 0,
    cached_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (source_id, date),

    FOREIGN KEY (source_id)
        REFERENCES sources(id) ON DELETE CASCADE,
    FOREIGN KEY (top_question_id)
        REFERENCES questions(id) ON DELETE SET NULL
);

CREATE INDEX idx_analytics_cache_source_date
    ON analytics_cache (source_id, date);


CREATE TABLE pipeline_jobs (
    id INTEGER PRIMARY KEY,

    job_type VARCHAR(30) NOT NULL DEFAULT 'scrape_questions'
        CHECK (job_type IN (
            'scrape_questions',
            'scrape_new_questions',
            'update_metrics',
            'scrape_answers'
        )),

    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,

    status VARCHAR(10) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'done', 'failed')),

    questions_found INTEGER NOT NULL DEFAULT 0,
    questions_new INTEGER NOT NULL DEFAULT 0,
    questions_updated INTEGER NOT NULL DEFAULT 0,
    items_failed INTEGER NOT NULL DEFAULT 0,

    error_message TEXT,
    started_at DATETIME,
    finished_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pipeline_jobs_source_time
    ON pipeline_jobs (source_id, started_at);
CREATE INDEX idx_pipeline_jobs_status
    ON pipeline_jobs (status, created_at);


-- Lưu lịch sử metric để theo dõi tốc độ tăng thảo luận.
CREATE TABLE question_metrics (
    id INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL,

    view_count INTEGER NOT NULL DEFAULT 0,
    answer_count INTEGER NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 0,

    recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    job_id INTEGER REFERENCES pipeline_jobs(id) ON DELETE SET NULL,

    FOREIGN KEY (question_id)
        REFERENCES questions(id) ON DELETE CASCADE
);

CREATE INDEX idx_question_metrics_question_time
    ON question_metrics (question_id, recorded_at);
CREATE INDEX idx_question_metrics_recorded_at
    ON question_metrics (recorded_at);
CREATE INDEX idx_question_metrics_hot
    ON question_metrics (answer_count DESC, score DESC, view_count DESC);


-- Chỉ ghi bảng này khi source tương ứng có include_answers = 1.
CREATE TABLE answers (
    id INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL,

    stackoverflow_answer_id INTEGER NOT NULL,
    author_user_id INTEGER,
    author_display_name VARCHAR(200),

    is_accepted BOOLEAN NOT NULL DEFAULT 0,
    score INTEGER NOT NULL DEFAULT 0,
    answer_body TEXT,

    answer_created_at DATETIME NOT NULL,
    last_activity_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (question_id)
        REFERENCES questions(id) ON DELETE CASCADE,

    UNIQUE (stackoverflow_answer_id)
);

CREATE INDEX idx_answers_question_time
    ON answers (question_id, answer_created_at);


CREATE TABLE pipeline_logs (
    id INTEGER PRIMARY KEY,

    job_id INTEGER REFERENCES pipeline_jobs(id) ON DELETE SET NULL,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,

    log_level VARCHAR(20) NOT NULL DEFAULT 'ERROR'
        CHECK (log_level IN ('ERROR', 'WARNING')),

    message TEXT NOT NULL,
    error_type VARCHAR(100),
    error_details TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pipeline_logs_job
    ON pipeline_logs (job_id, created_at);
CREATE INDEX idx_pipeline_logs_source
    ON pipeline_logs (source_id, created_at);
