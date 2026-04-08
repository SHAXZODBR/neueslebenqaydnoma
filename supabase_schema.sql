-- SQL to initialize tables in Supabase (PostgreSQL)

-- Groups table
CREATE TABLE IF NOT EXISTS groups (
    group_id BIGINT PRIMARY KEY,
    group_name TEXT NOT NULL DEFAULT '',
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Workers table
CREATE TABLE IF NOT EXISTS workers (
    user_id BIGINT PRIMARY KEY,
    username TEXT DEFAULT '',
    first_name TEXT DEFAULT '',
    last_name TEXT DEFAULT '',
    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Check-ins table
CREATE TABLE IF NOT EXISTS checkins (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES workers(user_id) ON DELETE CASCADE,
    group_id BIGINT NOT NULL REFERENCES groups(group_id) ON DELETE CASCADE,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    media_file_id TEXT,
    media_type TEXT, -- 'photo' or 'video'
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    date DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE INDEX IF NOT EXISTS idx_checkins_date ON checkins(date);
CREATE INDEX IF NOT EXISTS idx_checkins_user_date ON checkins(user_id, date);

-- Admins table
CREATE TABLE IF NOT EXISTS admins (
    user_id BIGINT PRIMARY KEY
);

-- Settings table
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Note: BIGINT is used for Telegram IDs because they can exceed the range of standard INTEGER.
