<?php
declare(strict_types=1);

// Reference data shared with the Python app: part types, slots, maintenance actions, default rules.
// Source of truth is backend/bikelog/catalog.py; scripts/export_php_catalog.py writes catalog.json.

final class Catalog
{
    private static ?array $data = null;
    private static array $types = [];
    private static array $actions = [];

    // Parts that do not wear on an indoor (trainer) ride: the wheels and everything on them, and the brakes.
    public const INDOOR_EXCLUDED = ['WHEELSET', 'FRONT_WHEEL', 'REAR_WHEEL', 'HUB', 'HUB_BEARINGS', 'SPOKES', 'RIM',
        'RIM_TAPE', 'TUBELESS_VALVE', 'TIRE', 'INNER_TUBE', 'BRAKE_ROTOR', 'BRAKE_PADS', 'BRAKE_CIRCUIT'];

    public const CONSUMABLE_KINDS = ['WAX' => 'Wax', 'LUBE' => 'Chain lube', 'SEALANT' => 'Tire sealant',
        'BRAKE_FLUID' => 'Brake fluid', 'GREASE' => 'Grease / paste', 'CLEANER' => 'Cleaner / degreaser',
        'COIN_CELL' => 'Coin cell battery', 'PATCHES' => 'Tube patches', 'OTHER' => 'Other'];

    private static function load(): void
    {
        if (self::$data !== null) {
            return;
        }
        self::$data = json_decode((string)file_get_contents(__DIR__ . '/catalog.json'), true, 32, JSON_THROW_ON_ERROR);
        foreach (self::$data['component_types'] as $t) {
            self::$types[$t['code']] = $t;
        }
        foreach (self::$data['actions'] as $a) {
            self::$actions[$a['code']] = $a;
        }
    }

    /** Any other top-level part of catalog.json (groupset_templates, dispositions, incident_types ...). */
    public static function raw(string $key): array
    {
        self::load();
        return self::$data[$key] ?? [];
    }

    public static function types(): array
    {
        self::load();
        return self::$types;
    }

    public static function type(string $code): ?array
    {
        self::load();
        return self::$types[$code] ?? null;
    }

    public static function typeName(string $code): string
    {
        if ($code === 'BIKE') {
            return 'Whole bike';
        }
        return self::type($code)['name'] ?? $code;
    }

    /** Types grouped by category for a <select>. */
    public static function typesByCategory(): array
    {
        $out = [];
        foreach (self::types() as $t) {
            $out[$t['category']][$t['code']] = $t['name'];
        }
        return $out;
    }

    public static function slots(string $type): array
    {
        $s = self::type($type)['slots'] ?? [];
        return $s ?: ['OTHER'];
    }

    public static function parentTypes(string $type): array
    {
        return self::type($type)['parent_types'] ?? [];
    }

    public static function actions(): array
    {
        self::load();
        return self::$actions;
    }

    public static function action(string $code): ?array
    {
        self::load();
        return self::$actions[$code] ?? null;
    }

    public static function actionName(string $code): string
    {
        return self::action($code)['name'] ?? $code;
    }

    /** Actions that can be logged for a part type ('BIKE' for the whole bike). */
    public static function actionsFor(string $type): array
    {
        $out = [];
        foreach (self::actions() as $a) {
            if (in_array($type, $a['targets'], true) || ($type !== 'BIKE' && $a['targets'] === ['*'])) {
                $out[$a['code']] = $a;
            }
        }
        return $out;
    }

    public static function defaultRules(): array
    {
        self::load();
        return self::$data['default_rules'];
    }

    /** Outcome from a measurement and the action's limits (worst limit reached first), or null. */
    public static function outcomeFromMeasurement(array $action, ?float $value): ?string
    {
        if ($value === null || empty($action['limits'])) {
            return null;
        }
        foreach ($action['limits'] as $l) {
            $reached = $l['below'] ? $value <= $l['value'] : $value >= $l['value'];
            if ($reached) {
                return $l['outcome'];
            }
        }
        return 'OK';
    }

    public static function slotName(string $slot): string
    {
        return ucfirst(strtolower(str_replace('_', ' ', $slot)));
    }

    public static function label(string $code): string
    {
        return ucfirst(strtolower(str_replace('_', ' ', $code)));
    }
}
