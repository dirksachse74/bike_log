-- Round 3a: the liquid-wax window as its own rule kind, hot wax after a top-up, quick link per chain
-- (PARENT_COUNT), and chain rotation per bike.

ALTER TABLE service_rules
  MODIFY trigger_kind ENUM('INTERVAL','ONCE_AFTER_INSTALL','CYCLE_WINDOW','PARENT_COUNT') NOT NULL DEFAULT 'INTERVAL',
  ADD COLUMN window_min_km DECIMAL(10,1) NULL AFTER warn_hours,
  ADD COLUMN window_max_km DECIMAL(10,1) NULL AFTER window_min_km,
  ADD COLUMN after_top_up_km DECIMAL(10,1) NULL AFTER window_max_km,
  ADD COLUMN cycle_action_code VARCHAR(32) NULL AFTER after_top_up_km,
  ADD COLUMN interval_count SMALLINT NULL AFTER cycle_action_code;

-- the base release stored the liquid-wax window as "interval = window end, warn = window length"
UPDATE service_rules SET trigger_kind = 'CYCLE_WINDOW', window_min_km = interval_km - COALESCE(warn_km, 0), window_max_km = interval_km,
  cycle_action_code = 'WAX_HOT', interval_km = NULL, warn_km = 25
  WHERE rule_code = 'CHAIN_LIQUID_WAX' AND trigger_kind = 'INTERVAL' AND interval_km IS NOT NULL;

UPDATE service_rules SET after_top_up_km = 200 WHERE rule_code = 'CHAIN_HOT_WAX' AND component_type = 'CHAIN' AND after_top_up_km IS NULL;

INSERT IGNORE INTO service_rules (user_id, rule_code, name, component_type, action_code, reset_actions, trigger_kind, interval_count,
  origin, active, notes, created_at, updated_at)
  SELECT id, 'QUICK_LINK_CHAINS', 'Replace quick link', 'QUICK_LINK', 'QUICK_LINK_CHECK', '', 'PARENT_COUNT', 2, 'DEFAULT', 1,
  'Wippermann Connex links are sold as reusable many times; no official limit was found. Replace after 2 chains (your choice) or as soon as it closes noticeably looser than new.',
  UTC_TIMESTAMP(), UTC_TIMESTAMP() FROM users;

-- chains that take turns on one bike (Chain A, Chain B ...): which bike's rotation a stored chain belongs to
ALTER TABLE components ADD COLUMN rotation_bike_id INT UNSIGNED NULL AFTER work_session_id,
  ADD CONSTRAINT fk_comp_rotation FOREIGN KEY (rotation_bike_id) REFERENCES bikes(id) ON DELETE SET NULL;
