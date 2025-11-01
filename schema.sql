-- Onboarding PRs table
CREATE TABLE IF NOT EXISTS onboarding_prs (
    pr_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    pr_link TEXT NOT NULL,
    onboarding_type TEXT CHECK (onboarding_type in ('Firmware', 'GS')),
    notion_email TEXT NOT NULL,
    status TEXT CHECK (status in ('Pending', 'Approved')) DEFAULT 'Pending',
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    approver_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_onboarding_prs_status ON onboarding_prs (status);
CREATE INDEX IF NOT EXISTS idx_onboarding_prs_type ON onboarding_prs (onboarding_type);

-- OBC-firmware PRs table
CREATE TABLE IF NOT EXISTS obc_firmware_prs (
    pr_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    pr_link TEXT NOT NULL,
    status TEXT CHECK (status in ('Pending', 'Approved')) DEFAULT 'Pending',
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    approver_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_obc_firmware_prs_status ON obc_firmware_prs (status);
