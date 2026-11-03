-- Round 3b: purchase bundles, links for stock-drawn parts (costs), sending a part away for repair.

-- Parts bought together at one price (a groupset): the bundle price is the only price of its parts.
CREATE TABLE purchase_bundles (
  id               INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id          INT UNSIGNED NOT NULL,
  name             VARCHAR(160) NOT NULL,
  merchant         VARCHAR(160) NULL,
  purchased_on     DATE NULL,
  price_cents      INT NULL,
  notes            TEXT NULL,
  work_session_id  INT UNSIGNED NULL,
  voided_at        DATETIME NULL,
  void_reason      VARCHAR(255) NULL,
  created_at       DATETIME NOT NULL,
  KEY ix_bundle_user (user_id),
  CONSTRAINT fk_bundle_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE components
  ADD COLUMN bundle_id INT UNSIGNED NULL AFTER product_id,
  ADD COLUMN from_stock_txn_id INT UNSIGNED NULL AFTER bundle_id,
  ADD CONSTRAINT fk_comp_bundle FOREIGN KEY (bundle_id) REFERENCES purchase_bundles(id) ON DELETE SET NULL;

-- A part sent away for service or repair, and what came back.
CREATE TABLE service_orders (
  id                 INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id            INT UNSIGNED NOT NULL,
  component_id       INT UNSIGNED NOT NULL,
  bike_id            INT UNSIGNED NULL,
  from_bike_id       INT UNSIGNED NULL,
  from_parent_id     INT UNSIGNED NULL,
  from_slot          VARCHAR(32) NULL,
  sent_on            DATE NOT NULL,
  shop               VARCHAR(160) NULL,
  reason             VARCHAR(500) NULL,
  incident_group     CHAR(32) NULL,
  send_session_id    INT UNSIGNED NULL,
  status             ENUM('OUT','BACK','VOIDED') NOT NULL DEFAULT 'OUT',
  returned_on        DATE NULL,
  outcome            VARCHAR(24) NULL,
  cost_cents         INT NULL,
  receipt_ref        VARCHAR(120) NULL,
  return_notes       VARCHAR(500) NULL,
  return_session_id  INT UNSIGNED NULL,
  event_id           INT UNSIGNED NULL,
  replacement_id     INT UNSIGNED NULL,
  created_at         DATETIME NOT NULL,
  KEY ix_so_user (user_id, status),
  KEY ix_so_comp (component_id),
  CONSTRAINT fk_so_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_so_comp FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
