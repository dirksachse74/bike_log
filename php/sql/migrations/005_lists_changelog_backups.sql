-- Round 4: shop pick list, change log, per-user backups (fresh start, restore).

-- Names you pick instead of typing again (list SHOP: where you buy and where parts go for repair).
-- Records keep the name as text; the list holds the names on offer. Nothing is deleted:
-- a merged entry points to the name it went into, a hidden one is left out of the dropdowns.
CREATE TABLE pick_list_items (
  id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id         INT UNSIGNED NOT NULL,
  list_code       VARCHAR(16) NOT NULL,
  name            VARCHAR(160) NOT NULL,
  hidden_at       DATETIME NULL,
  merged_into_id  INT UNSIGNED NULL,
  created_at      DATETIME NOT NULL,
  UNIQUE KEY ux_pick_name (user_id, list_code, name),
  CONSTRAINT fk_pick_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- What changed, field by field (edits, new records, parts fitted). Written by the app, never edited.
CREATE TABLE change_log (
  id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id       INT UNSIGNED NOT NULL,
  changed_at    DATETIME NOT NULL,
  entity        VARCHAR(32) NOT NULL,
  entity_id     INT UNSIGNED NULL,
  bike_id       INT UNSIGNED NULL,
  component_id  INT UNSIGNED NULL,
  action        VARCHAR(16) NOT NULL,          -- CREATED | CHANGED | NOTE
  field         VARCHAR(64) NULL,
  old_value     VARCHAR(500) NULL,
  new_value     VARCHAR(500) NULL,
  source        VARCHAR(32) NULL,              -- FORM, PRODUCT_IMPORT, RESTORE ...
  KEY ix_cl_user (user_id, id),
  KEY ix_cl_bike (user_id, bike_id),
  KEY ix_cl_comp (user_id, component_id),
  CONSTRAINT fk_cl_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Copies of one user's data (gzipped JSON in the export format), written before a fresh start or a restore.
CREATE TABLE user_backups (
  id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id     INT UNSIGNED NOT NULL,
  created_at  DATETIME NOT NULL,
  reason      VARCHAR(32) NOT NULL,            -- BEFORE_RESET | BEFORE_RESTORE | MANUAL
  summary     VARCHAR(255) NULL,
  size_bytes  INT UNSIGNED NOT NULL,
  content     LONGBLOB NOT NULL,
  KEY ix_ub_user (user_id, id),
  CONSTRAINT fk_ub_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
