CREATE TABLE IF NOT EXISTS prs (
    pr_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    pr_link TEXT NOT NULL,
    onboarding_type TEXT CHECK (onboarding_type in ('Firmware', 'GS')),
    status TEXT CHECK (status in ('Pending', 'Reviewed')) DEFAULT 'Pending',
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    reviewer_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_prs_status ON prs (status);
CREATE INDEX IF NOT EXISTS idx_prs_type ON prs (onboarding_type);