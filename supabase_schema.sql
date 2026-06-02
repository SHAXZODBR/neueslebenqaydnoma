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

-- Group membership table — tracks who currently belongs to each group.
-- A worker is shown in reports unless they are explicitly marked inactive here
-- (i.e. they left/were removed from every group they were known to be in).
CREATE TABLE IF NOT EXISTS group_members (
    group_id  BIGINT NOT NULL,
    user_id   BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    left_at   TIMESTAMPTZ,
    PRIMARY KEY (group_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_group_members_active ON group_members(user_id, is_active);

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
