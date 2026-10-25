-- Fabric SQL database / Azure SQL (T-SQL).
-- The app writes rows into dispatch_request; only the dispatcher starts jobs.

CREATE TABLE dbo.dispatch_request (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    action           NVARCHAR(100)  NOT NULL,          -- key into the dispatcher's routes
    target           NVARCHAR(200)  NULL,              -- free-form, e.g. a portfolio code
    status           NVARCHAR(20)   NOT NULL DEFAULT 'pending',
                     -- pending -> claimed -> running -> succeeded | failed
    job_instance_url NVARCHAR(500)  NULL,
    message          NVARCHAR(1000) NULL,
    requested_by     NVARCHAR(200)  NULL,
    requested_at     DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at       DATETIME2      NULL
);

CREATE INDEX ix_dispatch_request_status ON dbo.dispatch_request (status, requested_at);

-- Settings the app wants (desired) vs what the dispatcher has applied (actual).
-- A mismatch counts as open work and keeps the chain alive.
CREATE TABLE dbo.dispatch_setting (
    name          NVARCHAR(100) PRIMARY KEY,
    desired_value NVARCHAR(400) NOT NULL,
    actual_value  NVARCHAR(400) NULL,
    updated_at    DATETIME2     NULL
);
