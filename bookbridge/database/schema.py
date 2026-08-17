"""SQLite Schema Definitions with Migrations."""

SCHEMA_V1 = """
-- Books Table
CREATE TABLE IF NOT EXISTS books (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT,
    language TEXT DEFAULT 'en',
    publisher TEXT,
    identifier TEXT,
    description TEXT,
    source_format TEXT NOT NULL DEFAULT 'epub',
    source_file_path TEXT NOT NULL,
    cover_image_id TEXT,
    metadata_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Chapters Table
CREATE TABLE IF NOT EXISTS chapters (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL,
    title TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    source_file_path TEXT,
    metadata_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chapters_book ON chapters(book_id, order_index);

-- Blocks Table
CREATE TABLE IF NOT EXISTS blocks (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL,
    type TEXT NOT NULL,
    source_text TEXT NOT NULL,
    translated_text TEXT,
    order_index INTEGER NOT NULL,
    is_translatable INTEGER NOT NULL DEFAULT 1,
    style_json TEXT,
    source_location_json TEXT,
    resource_id TEXT,
    tag_attributes_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_blocks_chapter ON blocks(chapter_id, order_index);

-- Resources Table
CREATE TABLE IF NOT EXISTS resources (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    media_type TEXT NOT NULL,
    relative_path TEXT,
    data BLOB,
    width INTEGER,
    height INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
);

-- Translation Jobs Table
CREATE TABLE IF NOT EXISTS translation_jobs (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL,
    book_title TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    source_language TEXT NOT NULL DEFAULT 'en',
    target_language TEXT NOT NULL DEFAULT 'ar',
    style TEXT NOT NULL DEFAULT 'natural',
    glossary_profile_id TEXT,
    output_format TEXT NOT NULL DEFAULT 'epub',
    total_chapters INTEGER DEFAULT 0,
    completed_chapters INTEGER DEFAULT 0,
    current_chapter_title TEXT,
    total_segments INTEGER DEFAULT 0,
    completed_segments INTEGER DEFAULT 0,
    cached_segments INTEGER DEFAULT 0,
    failed_segments INTEGER DEFAULT 0,
    retried_segments INTEGER DEFAULT 0,
    total_tokens_used INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    custom_settings_json TEXT,
    FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON translation_jobs(status);

-- Translation Segments Table
CREATE TABLE IF NOT EXISTS segments (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    chapter_id TEXT NOT NULL,
    block_ids_json TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    source_text TEXT NOT NULL,
    translated_text TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    cache_key TEXT,
    source_hash TEXT,
    provider_used TEXT,
    model_used TEXT,
    credential_id_used TEXT,
    tokens_used INTEGER DEFAULT 0,
    retries_count INTEGER DEFAULT 0,
    error_message TEXT,
    validation_notes TEXT,
    translated_at TIMESTAMP,
    FOREIGN KEY(job_id) REFERENCES translation_jobs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_segments_job ON segments(job_id, order_index);
CREATE INDEX IF NOT EXISTS idx_segments_cache ON segments(cache_key);
CREATE INDEX IF NOT EXISTS idx_segments_source_hash ON segments(source_hash);

-- Translation Memory Table (Global reusable translations)
CREATE TABLE IF NOT EXISTS translation_memory (
    id TEXT PRIMARY KEY,
    source_hash TEXT NOT NULL,
    source_text TEXT NOT NULL,
    translated_text TEXT NOT NULL,
    source_language TEXT NOT NULL DEFAULT 'en',
    target_language TEXT NOT NULL DEFAULT 'ar',
    glossary_version INTEGER DEFAULT 1,
    style_type TEXT DEFAULT 'natural',
    provider TEXT,
    model TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tm_hash ON translation_memory(source_hash, source_language, target_language);

-- Translation Cache Table (Exact deterministic request cache)
CREATE TABLE IF NOT EXISTS translation_cache (
    cache_key TEXT PRIMARY KEY,
    translated_text TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    tokens_used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Glossaries Table
CREATE TABLE IF NOT EXISTS glossaries (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    genre TEXT DEFAULT 'General',
    enabled_categories_json TEXT,
    custom_rules_json TEXT,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Glossary Terms Table
CREATE TABLE IF NOT EXISTS glossary_terms (
    id TEXT PRIMARY KEY,
    glossary_id TEXT NOT NULL,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'General terminology',
    priority INTEGER NOT NULL DEFAULT 100,
    match_type TEXT NOT NULL DEFAULT 'exact',
    case_sensitive INTEGER NOT NULL DEFAULT 0,
    locked INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(glossary_id) REFERENCES glossaries(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_terms_glossary ON glossary_terms(glossary_id, priority DESC);

-- Provider Credentials Metadata (NO plaintext secrets)
CREATE TABLE IF NOT EXISTS credentials_metadata (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    name TEXT NOT NULL,
    model TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    state TEXT NOT NULL DEFAULT 'available',
    cooldown_until TIMESTAMP,
    consecutive_failures INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    total_tokens_used INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    last_success_at TIMESTAMP,
    last_error_at TIMESTAMP,
    last_error_message TEXT,
    rate_limit_rpm INTEGER,
    rate_limit_tpm INTEGER,
    extra_config_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Usage Records Table
CREATE TABLE IF NOT EXISTS usage_records (
    id TEXT PRIMARY KEY,
    credential_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    job_id TEXT,
    segment_id TEXT,
    tokens_prompt INTEGER DEFAULT 0,
    tokens_completion INTEGER DEFAULT 0,
    tokens_total INTEGER DEFAULT 0,
    cost_estimate_usd REAL DEFAULT 0.0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_usage_time ON usage_records(timestamp);

-- Settings Table (Key-Value)
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Migrations tracking table
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""
