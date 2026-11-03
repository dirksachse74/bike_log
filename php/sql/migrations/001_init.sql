-- Bike Log (PHP, multi-user) first schema. MySQL 5.7.8+/8.x or MariaDB 10.3+. InnoDB, utf8mb4.
-- Every table with bike data carries user_id; the app only ever reads rows of the signed-in user.
-- Dates are DATE (local calendar days, no invented times). Timestamps are UTC DATETIME.

CREATE TABLE users (
  id               INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  email            VARCHAR(190) NOT NULL,
  display_name     VARCHAR(100) NOT NULL,
  password_hash    VARCHAR(255) NOT NULL,
  role             ENUM('USER','ADMIN') NOT NULL DEFAULT 'USER',
  status           ENUM('ACTIVE','BLOCKED') NOT NULL DEFAULT 'ACTIVE',
  email_verified_at DATETIME NULL,
  session_version  INT UNSIGNED NOT NULL DEFAULT 1,   -- raising it logs the user out everywhere
  timezone         VARCHAR(64) NOT NULL DEFAULT 'Europe/Berlin',
  blocked_reason   VARCHAR(255) NULL,
  created_at       DATETIME NOT NULL,
  updated_at       DATETIME NOT NULL,
  last_login_at    DATETIME NULL,
  UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- One-time links: email verification, password reset, invitations, email change.
-- Only the SHA-256 of the token is stored; the token itself exists only in the email.
CREATE TABLE user_tokens (
  id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id     INT UNSIGNED NULL,
  purpose     ENUM('VERIFY','RESET','INVITE','EMAIL_CHANGE') NOT NULL,
  token_hash  CHAR(64) NOT NULL,
  email       VARCHAR(190) NULL,        -- invite target / new email address
  created_by  INT UNSIGNED NULL,
  created_at  DATETIME NOT NULL,
  expires_at  DATETIME NOT NULL,
  used_at     DATETIME NULL,
  UNIQUE KEY uq_token_hash (token_hash),
  KEY ix_token_user (user_id, purpose),
  CONSTRAINT fk_token_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Rate limiting: one row per attempt in a bucket (login-email, login-ip, register-ip, reset-ip ...).
CREATE TABLE rate_events (
  id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  bucket      VARCHAR(32) NOT NULL,
  key_hash    CHAR(64) NOT NULL,
  created_at  DATETIME NOT NULL,
  KEY ix_rate (bucket, key_hash, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Security and admin audit trail. actor = who did it, subject = whose account it concerns.
CREATE TABLE audit_log (
  id               BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  created_at       DATETIME NOT NULL,
  actor_user_id    INT UNSIGNED NULL,
  subject_user_id  INT UNSIGNED NULL,
  event            VARCHAR(48) NOT NULL,
  detail           VARCHAR(500) NULL,
  ip               VARCHAR(45) NULL,
  KEY ix_audit_time (created_at),
  KEY ix_audit_subject (subject_user_id),
  KEY ix_audit_event (event)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE site_settings (
  name   VARCHAR(64) PRIMARY KEY,
  value  TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------- bike data (per user)

CREATE TABLE bikes (
  id                    INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id               INT UNSIGNED NOT NULL,
  name                  VARCHAR(120) NOT NULL,
  maker                 VARCHAR(120) NULL,
  model                 VARCHAR(120) NULL,
  year                  SMALLINT NULL,
  shifting              ENUM('ELECTRONIC','MECHANICAL') NULL,
  status                ENUM('ACTIVE','RETIRED') NOT NULL DEFAULT 'ACTIVE',
  retired_on            DATE NULL,
  purchase_date         DATE NULL,
  purchase_price_cents  INT NULL,
  notes                 TEXT NULL,
  created_at            DATETIME NOT NULL,
  updated_at            DATETIME NOT NULL,
  UNIQUE KEY uq_bike_name (user_id, name),
  CONSTRAINT fk_bike_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- One physical part you own. Identity never changes, whatever bike it is on.
CREATE TABLE components (
  id                 INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id            INT UNSIGNED NOT NULL,
  component_type     VARCHAR(32) NOT NULL,
  label              VARCHAR(160) NOT NULL,
  maker              VARCHAR(120) NULL,
  model              VARCHAR(160) NULL,
  mark               VARCHAR(80) NULL,          -- how to tell identical parts apart ("1 punch dot")
  serial_number      VARCHAR(120) NULL,         -- private
  prior_usage        ENUM('NEW','RECORDED','UNKNOWN') NOT NULL DEFAULT 'UNKNOWN',
  starting_km        DECIMAL(10,1) NULL,        -- km before tracking began (RECORDED)
  starting_km_estimate TINYINT(1) NOT NULL DEFAULT 0,
  tire_setup         ENUM('TUBE','TUBELESS','TUBULAR') NULL,  -- wheels only
  purchase_date      DATE NULL,
  price_cents        INT NULL,
  shop               VARCHAR(120) NULL,
  status             ENUM('ACTIVE','RETIRED') NOT NULL DEFAULT 'ACTIVE',
  retired_on         DATE NULL,
  retire_reason      VARCHAR(255) NULL,
  notes              TEXT NULL,
  created_at         DATETIME NOT NULL,
  updated_at         DATETIME NOT NULL,
  KEY ix_comp_user_type (user_id, component_type),
  CONSTRAINT fk_comp_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Fitment history, on a bike or on another part (tire on wheel). Start-inclusive, end-exclusive (dates).
-- A wrong record is voided (kept, hidden from totals), never deleted.
CREATE TABLE installations (
  id                   INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id              INT UNSIGNED NOT NULL,
  component_id         INT UNSIGNED NOT NULL,
  bike_id              INT UNSIGNED NULL,
  parent_component_id  INT UNSIGNED NULL,
  slot                 VARCHAR(32) NOT NULL,
  installed_on         DATE NOT NULL,
  removed_on           DATE NULL,
  removal_reason       VARCHAR(255) NULL,
  note                 VARCHAR(255) NULL,
  voided_at            DATETIME NULL,
  void_reason          VARCHAR(255) NULL,
  created_at           DATETIME NOT NULL,
  KEY ix_inst_comp (component_id),
  KEY ix_inst_bike (bike_id),
  KEY ix_inst_parent (parent_component_id),
  KEY ix_inst_user (user_id),
  CONSTRAINT fk_inst_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_inst_comp FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE,
  CONSTRAINT fk_inst_bike FOREIGN KEY (bike_id) REFERENCES bikes(id) ON DELETE CASCADE,
  CONSTRAINT fk_inst_parent FOREIGN KEY (parent_component_id) REFERENCES components(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Explicit km for a part: a correction (+/-) on a date. Voided, never deleted.
CREATE TABLE usage_adjustments (
  id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id       INT UNSIGNED NOT NULL,
  component_id  INT UNSIGNED NOT NULL,
  effective_on  DATE NOT NULL,
  km            DECIMAL(10,1) NOT NULL,
  is_estimate   TINYINT(1) NOT NULL DEFAULT 0,
  note          VARCHAR(255) NULL,
  voided_at     DATETIME NULL,
  created_at    DATETIME NOT NULL,
  KEY ix_adj_comp (component_id),
  CONSTRAINT fk_adj_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_adj_comp FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Rides entered by hand. distance NULL = missing (not zero). Removed rides are kept (removed_at).
CREATE TABLE rides (
  id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id       INT UNSIGNED NOT NULL,
  bike_id       INT UNSIGNED NULL,
  ride_date     DATE NOT NULL,
  start_time    TIME NULL,                     -- optional, local time
  name          VARCHAR(200) NULL,
  distance_km   DECIMAL(8,2) NULL,
  duration_s    INT UNSIGNED NULL,
  elevation_m   INT UNSIGNED NULL,
  kind          ENUM('OUTDOOR','INDOOR') NOT NULL DEFAULT 'OUTDOOR',
  conditions    ENUM('DRY','WET') NULL,
  notes         TEXT NULL,
  removed_at    DATETIME NULL,
  created_at    DATETIME NOT NULL,
  updated_at    DATETIME NOT NULL,
  KEY ix_ride_user_date (user_id, ride_date),
  KEY ix_ride_bike_date (bike_id, ride_date),
  CONSTRAINT fk_ride_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_ride_bike FOREIGN KEY (bike_id) REFERENCES bikes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE consumables (
  id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id     INT UNSIGNED NOT NULL,
  kind        VARCHAR(24) NOT NULL,           -- WAX, LUBE, SEALANT, BRAKE_FLUID, GREASE, OTHER
  name        VARCHAR(160) NOT NULL,
  maker       VARCHAR(120) NULL,
  unit        VARCHAR(16) NOT NULL DEFAULT 'ml',
  track_stock TINYINT(1) NOT NULL DEFAULT 1,
  archived_at DATETIME NULL,
  notes       TEXT NULL,
  created_at  DATETIME NOT NULL,
  UNIQUE KEY uq_cons_name (user_id, name),
  CONSTRAINT fk_cons_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE maintenance_events (
  id                 INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id            INT UNSIGNED NOT NULL,
  action_code        VARCHAR(32) NOT NULL,
  component_id       INT UNSIGNED NULL,
  bike_id            INT UNSIGNED NULL,       -- bike-level work (torque check) or the bike the part was on
  performed_on       DATE NOT NULL,
  outcome            VARCHAR(32) NULL,
  measurement_value  DECIMAL(8,3) NULL,
  measurement_unit   VARCHAR(16) NULL,
  consumable_id      INT UNSIGNED NULL,
  consumable_qty     DECIMAL(10,2) NULL,
  cost_cents         INT NULL,
  shop               VARCHAR(120) NULL,
  notes              TEXT NULL,
  voided_at          DATETIME NULL,
  void_reason        VARCHAR(255) NULL,
  created_at         DATETIME NOT NULL,
  KEY ix_ev_comp (component_id, action_code, performed_on),
  KEY ix_ev_bike (bike_id, action_code, performed_on),
  KEY ix_ev_user (user_id, performed_on),
  CONSTRAINT fk_ev_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_ev_comp FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE,
  CONSTRAINT fk_ev_bike FOREIGN KEY (bike_id) REFERENCES bikes(id) ON DELETE CASCADE,
  CONSTRAINT fk_ev_cons FOREIGN KEY (consumable_id) REFERENCES consumables(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Stock movements: BUY adds, USE subtracts, ADJUST sets a correction (+/-).
CREATE TABLE consumable_txns (
  id                    INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id               INT UNSIGNED NOT NULL,
  consumable_id         INT UNSIGNED NOT NULL,
  kind                  ENUM('BUY','USE','ADJUST') NOT NULL,
  qty                   DECIMAL(10,2) NOT NULL,
  happened_on           DATE NOT NULL,
  cost_cents            INT NULL,
  maintenance_event_id  INT UNSIGNED NULL,
  note                  VARCHAR(255) NULL,
  voided_at             DATETIME NULL,
  created_at            DATETIME NOT NULL,
  KEY ix_txn_cons (consumable_id),
  CONSTRAINT fk_txn_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_txn_cons FOREIGN KEY (consumable_id) REFERENCES consumables(id) ON DELETE CASCADE,
  CONSTRAINT fk_txn_event FOREIGN KEY (maintenance_event_id) REFERENCES maintenance_events(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Service rules. A user's type-level rules are copied from the catalog defaults at sign-up so they can be
-- changed; a part-level rule with the same rule_code replaces the type rule for that part.
CREATE TABLE service_rules (
  id               INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id          INT UNSIGNED NOT NULL,
  rule_code        VARCHAR(48) NOT NULL,
  name             VARCHAR(160) NOT NULL,
  component_type   VARCHAR(32) NULL,          -- 'BIKE' for bike-level rules
  component_id     INT UNSIGNED NULL,
  action_code      VARCHAR(32) NOT NULL,
  reset_actions    VARCHAR(255) NOT NULL DEFAULT '',   -- comma list; empty = action_code
  trigger_kind     ENUM('INTERVAL','ONCE_AFTER_INSTALL') NOT NULL DEFAULT 'INTERVAL',
  interval_km      DECIMAL(10,1) NULL,
  interval_months  SMALLINT NULL,
  interval_hours   DECIMAL(8,1) NULL,
  warn_km          DECIMAL(10,1) NULL,
  warn_days        SMALLINT NULL,
  warn_hours       DECIMAL(8,1) NULL,
  requires_setup   VARCHAR(12) NULL,          -- TUBELESS / MECHANICAL
  origin           ENUM('DEFAULT','MANUFACTURER','PERSONAL') NOT NULL DEFAULT 'PERSONAL',
  active           TINYINT(1) NOT NULL DEFAULT 1,
  notes            VARCHAR(500) NULL,
  created_at       DATETIME NOT NULL,
  updated_at       DATETIME NOT NULL,
  UNIQUE KEY uq_rule_type (user_id, component_type, rule_code),
  UNIQUE KEY uq_rule_comp (user_id, component_id, rule_code),
  CONSTRAINT fk_rule_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_rule_comp FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Hide a reminder until a date and/or until more km. Records no maintenance.
CREATE TABLE reminder_snoozes (
  id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id       INT UNSIGNED NOT NULL,
  component_id  INT UNSIGNED NULL,
  bike_id       INT UNSIGNED NULL,
  rule_code     VARCHAR(48) NOT NULL,
  until_date    DATE NULL,
  until_km      DECIMAL(10,1) NULL,           -- km-since-reset at which it shows again
  note          VARCHAR(255) NULL,
  created_at    DATETIME NOT NULL,
  cleared_at    DATETIME NULL,
  KEY ix_snooze (user_id, rule_code),
  CONSTRAINT fk_snooze_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_snooze_comp FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE,
  CONSTRAINT fk_snooze_bike FOREIGN KEY (bike_id) REFERENCES bikes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
