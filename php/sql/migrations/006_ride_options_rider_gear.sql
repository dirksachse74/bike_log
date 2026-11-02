-- Round 5a: rides left out of the km, wheels used on one ride, CSV import identity.

-- A ride that stays in the list but gives no km to any part (e.g. a rented bike, a test ride logged twice).
ALTER TABLE rides
  ADD COLUMN excluded_reason VARCHAR(255) NULL AFTER conditions,
  ADD COLUMN source_kind VARCHAR(16) NULL AFTER notes,
  ADD COLUMN source_ref VARCHAR(64) NULL AFTER source_kind,
  ADD UNIQUE KEY ux_ride_source (user_id, source_kind, source_ref);

-- Which part a ride used in a position, overriding the fitting history for that ride only
-- (race wheels for one ride). component_id NULL = nothing in that position on that ride.
CREATE TABLE ride_equipment (
  id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id       INT UNSIGNED NOT NULL,
  ride_id       INT UNSIGNED NOT NULL,
  slot          VARCHAR(32) NOT NULL,
  component_id  INT UNSIGNED NULL,
  created_at    DATETIME NOT NULL,
  UNIQUE KEY ux_req_slot (ride_id, slot),
  KEY ix_req_comp (component_id),
  CONSTRAINT fk_req_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_req_ride FOREIGN KEY (ride_id) REFERENCES rides(id) ON DELETE CASCADE,
  CONSTRAINT fk_req_comp FOREIGN KEY (component_id) REFERENCES components(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
