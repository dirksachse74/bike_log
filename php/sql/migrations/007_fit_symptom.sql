-- Round 5b: which products fit which bike, and the symptom / work done of a maintenance entry.

-- "This chain/tire/pad fits my Synapse": checked (verified) or only expected, with a note.
CREATE TABLE product_bike_fit (
  id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id     INT UNSIGNED NOT NULL,
  product_id  INT UNSIGNED NOT NULL,
  bike_id     INT UNSIGNED NOT NULL,
  verified    TINYINT(1) NOT NULL DEFAULT 0,
  note        VARCHAR(255) NULL,
  created_at  DATETIME NOT NULL,
  UNIQUE KEY ux_fit (product_id, bike_id),
  KEY ix_fit_bike (bike_id),
  CONSTRAINT fk_fit_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_fit_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
  CONSTRAINT fk_fit_bike FOREIGN KEY (bike_id) REFERENCES bikes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- What was wrong (spongy lever) and what was done (lever bleed, mineral oil), e.g. for a brake bleed.
ALTER TABLE maintenance_events
  ADD COLUMN symptom VARCHAR(500) NULL AFTER measurement_unit,
  ADD COLUMN work_done VARCHAR(500) NULL AFTER symptom;
