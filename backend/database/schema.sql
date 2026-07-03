-- AI File Manager 2.0 schema

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    extension TEXT NOT NULL DEFAULT '',
    created_at REAL,
    modified_at REAL,
    content_hash TEXT NOT NULL DEFAULT '',
    scanned_at TEXT
);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL UNIQUE REFERENCES files(id) ON DELETE CASCADE,
    summary TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    subcategory TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    project TEXT NOT NULL DEFAULT '',
    importance INTEGER NOT NULL DEFAULT 5,
    sentimental_value INTEGER NOT NULL DEFAULT 1,
    confidence INTEGER NOT NULL DEFAULT 50,
    lifecycle TEXT NOT NULL DEFAULT 'Unknown',
    action TEXT NOT NULL DEFAULT 'Review',
    reasoning TEXT NOT NULL DEFAULT '',
    requires_review INTEGER NOT NULL DEFAULT 0,
    prefiltered INTEGER NOT NULL DEFAULT 0,
    model_used TEXT NOT NULL DEFAULT '',
    analyzed_at TEXT
);

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT '',
    root_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    progress REAL NOT NULL DEFAULT 0,
    files_found INTEGER NOT NULL DEFAULT 0,
    files_processed INTEGER NOT NULL DEFAULT 0,
    total_bytes INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT '',
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS scan_files (
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    PRIMARY KEY (scan_id, file_id)
);

CREATE TABLE IF NOT EXISTS duplicate_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL UNIQUE,
    file_count INTEGER NOT NULL DEFAULT 0,
    total_bytes INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS duplicate_members (
    group_id INTEGER NOT NULL REFERENCES duplicate_groups(id) ON DELETE CASCADE,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, file_id)
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS file_projects (
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    PRIMARY KEY (file_id, project_id)
);

CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rec_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    savings_bytes INTEGER NOT NULL DEFAULT 0,
    file_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    description TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS file_cache (
    path_hash TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    filename TEXT NOT NULL,
    modified_time REAL NOT NULL,
    size_bytes INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    model_used TEXT NOT NULL,
    analysis_json TEXT NOT NULL,
    analyzed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
CREATE INDEX IF NOT EXISTS idx_files_content_hash ON files(content_hash);
CREATE INDEX IF NOT EXISTS idx_analyses_category ON analyses(category);
CREATE INDEX IF NOT EXISTS idx_analyses_action ON analyses(action);
CREATE INDEX IF NOT EXISTS idx_scans_started_at ON scans(started_at);
CREATE INDEX IF NOT EXISTS idx_activity_created_at ON activity_log(created_at);
