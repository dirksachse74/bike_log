<?php
declare(strict_types=1);

// Reference data shared with the Python app: part types, slots, maintenance actions, default rules.
// Source of truth is backend/bikelog/catalog.py; scripts/export_php_catalog.py writes catalog.json.

final class Catalog
{
    private static ?array $data = null;
    private static array $types = [];
    private static array $actions = [];

    // Parts that do not wear on an indoor ride on a direct-drive trainer (the desktop app's usage profile
    // DIRECT_DRIVE_TRAINER): the wheels and everything on them, the cassette (the trainer has its own), the brakes.
    public const INDOOR_EXCLUDED = ['WHEELSET', 'FRONT_WHEEL', 'REAR_WHEEL', 'CASSETTE', 'HUB', 'HUB_BEARINGS', 'SPOKES', 'RIM',
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
        $v = self::$data[$key] ?? [];
        // label lists are shown on screen: translate them (the codes stay)
        return match ($key) {
            'dispositions', 'incident_types', 'tire_setups' => t_list($v),
            'stock_units' => array_map(fn($u) => [t($u[0]), t($u[1])], $v),
            'incident_options' => array_map(fn($opts) => array_map(fn($o) => ['label' => t($o['label'])] + $o, $opts), $v),
            'product_spec_fields' => array_map(fn($fs) => array_map(fn($f) => ['description' => t((string)$f['description'])] + $f, $fs), $v),
            default => $v,
        };
    }

    /** The untranslated catalog data (imports, exports, tests). */
    public static function rawData(string $key): array
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
            return t('Whole bike');
        }
        $n = self::type($code)['name'] ?? null;
        return $n === null ? $code : t($n);
    }

    /** Plural of a type name for sentences ("chains", "Ketten"). German plurals come from lang/de.php as 'plural:<name>'. */
    public static function typePlural(string $code): string
    {
        $n = self::type($code)['name'] ?? ($code === 'part' ? 'Part' : $code);
        if (I18n::lang() !== 'en') {
            return I18n::dict(I18n::lang())['plural:' . $n] ?? t($n);
        }
        return str_ends_with($n, 's') ? $n : $n . 's';
    }

    /** Types grouped by category for a <select>. */
    public static function typesByCategory(): array
    {
        $out = [];
        foreach (self::types() as $t) {
            $out[t($t['category'])][$t['code']] = t($t['name']);
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
        $n = self::action($code)['name'] ?? null;
        return $n === null ? $code : t($n);
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
        return t(ucfirst(strtolower(str_replace('_', ' ', $slot))));
    }

    public static function label(string $code): string
    {
        return t(ucfirst(strtolower(str_replace('_', ' ', $code))));
    }

    /** Consumable kinds with translated labels, for a <select>. */
    public static function consumableKinds(): array
    {
        return t_list(self::CONSUMABLE_KINDS);
    }
}
