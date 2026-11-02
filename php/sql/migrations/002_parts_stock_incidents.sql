-- Round 2 of the full port: products, what happened to removed parts, work sessions (undo),
-- counted spare stock, journal with ride incidents, spare minimums.

-- What you can buy (maker + model + specs with their source). Per user, like everything else.
CREATE TABLE products (
  id                INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id           INT UNSIGNED NOT NULL,
  component_type    VARCHAR(32) NOT NULL,
  maker             VARCHAR(120) NULL,
  model             VARCHAR(200) NOT NULL,
  specs_json        TEXT NULL,
  spec_source       VARCHAR(500) NULL,
  spec_version      VARCHAR(200) NULL,
  list_price_cents  INT NULL,
  notes             TEXT NULL,
  created_at        DATETIME NOT NULL,
  KEY ix_prod_user_type (user_id, component_type),
  CONSTRAINT fk_prod_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- A group of changes made in one go (groupset import, a fix); undoing it reverts all of them.
CREATE TABLE work_sessions (
  id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id     INT UNSIGNED NOT NULL,
  kind        VARCHAR(24) NOT NULL,
  title       VARCHAR(200) NOT NULL,
  happened_on DATE NOT NULL,
  created_at  DATETIME NOT NULL,
  undone_at   DATETIME NULL,
  KEY ix_ws_user (user_id),
  CONSTRAINT fk_ws_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE components
  ADD COLUMN product_id INT UNSIGNED NULL AFTER label,
  ADD COLUMN specs_json TEXT NULL AFTER product_id,
  ADD COLUMN disposition VARCHAR(20) NOT NULL DEFAULT 'STORED' AFTER status,
  ADD COLUMN disposition_on DATE NULL AFTER disposition,
  ADD COLUMN storage_location VARCHAR(160) NULL AFTER disposition_on,
  ADD COLUMN pressure_note VARCHAR(80) NULL AFTER tire_setup,
  ADD COLUMN warranty_until DATE NULL AFTER price_cents,
  ADD COLUMN work_session_id INT UNSIGNED NULL,
  ADD CONSTRAINT fk_comp_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL;

ALTER TABLE installations
  ADD COLUMN removal_outcome VARCHAR(20) NULL AFTER removal_reason,
  ADD COLUMN work_session_id INT UNSIGNED NULL,
  ADD COLUMN removal_session_id INT UNSIGNED NULL;

ALTER TABLE maintenance_events ADD COLUMN work_session_id INT UNSIGNED NULL;
ALTER TABLE consumable_txns ADD COLUMN work_session_id INT UNSIGNED NULL;
ALTER TABLE consumable_txns MODIFY kind ENUM('BUY','USE','ADJUST','RETURN') NOT NULL;

-- History of what happened to a part while not on a bike: stored, awaiting service, sold, discarded ...
CREATE TABLE component_dispositions (
  id                    INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id               INT UNSIGNED NOT NULL,
  component_id          INT UNSIGNED NOT NULL,
  disposition           VARCHAR(20) NOT NULL,
  previous_disposition  VARCHAR(20) NULL,
  effective_on          DATE NOT NULL,
  note                  VARCHAR(255) NULL,
  work_session_id       INT UNSIGNED NULL,
  created_at            DATETIME NOT NULL,
  KEY ix_disp_comp (component_id),
  CONSTRAINT fk_disp_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_disp_comp FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Counted spare parts (tubes, pad sets, quick links) are stock lines too: tracking_mode COUNTED with the
-- part type (and product). Taking one out creates an individual part in the same transaction.
ALTER TABLE consumables
  ADD COLUMN tracking_mode ENUM('BULK','COUNTED') NOT NULL DEFAULT 'BULK' AFTER kind,
  ADD COLUMN component_type VARCHAR(32) NULL AFTER tracking_mode,
  ADD COLUMN product_id INT UNSIGNED NULL AFTER component_type,
  ADD COLUMN min_stock DECIMAL(10,2) NULL AFTER track_stock,
  ADD COLUMN storage_location VARCHAR(160) NULL AFTER min_stock,
  ADD CONSTRAINT fk_cons_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL;

-- Dated notes and issues on a bike or a part; ride incidents are issues with an incident type, one entry per
-- affected thing sharing incident_group. Never deleted: voided (and restorable).
CREATE TABLE journal_entries (
  id                 INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id            INT UNSIGNED NOT NULL,
  bike_id            INT UNSIGNED NULL,
  component_id       INT UNSIGNED NULL,
  ride_id            INT UNSIGNED NULL,
  entry_on           DATE NOT NULL,
  kind               ENUM('NOTE','ISSUE') NOT NULL DEFAULT 'NOTE',
  text               TEXT NOT NULL,
  resolved_on        DATE NULL,
  incident_type      VARCHAR(16) NULL,
  incident_group     CHAR(32) NULL,
  affected           VARCHAR(160) NULL,
  repair             VARCHAR(12) NULL,          -- REPLACED / REPAIRED / NONE
  repair_text        VARCHAR(255) NULL,
  repaired_on        DATE NULL,
  repair_session_id  INT UNSIGNED NULL,
  created_at         DATETIME NOT NULL,
  updated_at         DATETIME NULL,
  voided_at          DATETIME NULL,
  void_reason        VARCHAR(255) NULL,
  KEY ix_j_user (user_id, entry_on),
  KEY ix_j_bike (bike_id),
  KEY ix_j_comp (component_id),
  KEY ix_j_ride (ride_id),
  KEY ix_j_group (incident_group),
  CONSTRAINT fk_j_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_j_bike FOREIGN KEY (bike_id) REFERENCES bikes(id) ON DELETE CASCADE,
  CONSTRAINT fk_j_comp FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE,
  CONSTRAINT fk_j_ride FOREIGN KEY (ride_id) REFERENCES rides(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Per-user settings (spare minimums, spoke limit, default tire setup ...), name -> value.
CREATE TABLE user_settings (
  user_id  INT UNSIGNED NOT NULL,
  name     VARCHAR(64) NOT NULL,
  value    TEXT NOT NULL,
  PRIMARY KEY (user_id, name),
  CONSTRAINT fk_us_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
