<?php
declare(strict_types=1);

// Rendering and small form helpers. Every value printed into HTML goes through h().

final class View
{
    public static string $title = '';
    public static string $active = '';

    public static function render(string $view, array $vars = [], string $title = '', string $active = ''): void
    {
        self::$title = $title;
        self::$active = $active;
        $content = self::partial($view, $vars);
        echo self::partial('layout', ['content' => $content]);
    }

    public static function partial(string $view, array $vars = []): string
    {
        $file = __DIR__ . '/views/' . $view . '.php';
        if (!preg_match('#^[a-z_/]+$#', $view) || !is_file($file)) {
            throw new RuntimeException("view $view missing");
        }
        extract($vars, EXTR_SKIP);
        ob_start();
        include $file;
        return (string)ob_get_clean();
    }
}

function require_user(): array
{
    $u = Auth::user();
    if (!$u) {
        $_SESSION['after_login'] = $_SERVER['QUERY_STRING'] ?? '';
        Session::flash('info', 'Please sign in.');
        redirect('login');
    }
    return $u;
}

function require_admin(): array
{
    $u = require_user();
    if ($u['role'] !== 'ADMIN') {
        http_response_code(403);
        throw new NotFound('This page is for admins.');
    }
    return $u;
}

/** <option> list. $options: value => label, or group => [value => label]. */
function options(array $options, mixed $selected, bool $blank = false, string $blankLabel = '—'): string
{
    $html = $blank ? '<option value="">' . h($blankLabel) . '</option>' : '';
    foreach ($options as $value => $label) {
        if (is_array($label)) {
            $html .= '<optgroup label="' . h($value) . '">' . options($label, $selected) . '</optgroup>';
            continue;
        }
        $sel = ((string)$value === (string)$selected) ? ' selected' : '';
        $html .= '<option value="' . h($value) . '"' . $sel . '>' . h($label) . '</option>';
    }
    return $html;
}

function field(string $name, string $label, mixed $value = '', string $type = 'text', array $attr = []): string
{
    $a = '';
    foreach ($attr as $k => $v) {
        $a .= $v === true ? ' ' . h($k) : ' ' . h($k) . '="' . h($v) . '"';
    }
    $help = '';
    if (isset($attr['data-help'])) {
        $help = '<small>' . h($attr['data-help']) . '</small>';
    }
    if ($type === 'textarea') {
        return '<label>' . h($label) . '<textarea name="' . h($name) . '"' . $a . '>' . h($value) . '</textarea>' . $help . '</label>';
    }
    return '<label>' . h($label) . '<input type="' . h($type) . '" name="' . h($name) . '" value="' . h($value) . '"' . $a . '>' . $help . '</label>';
}

function status_badge(string $status): string
{
    $labels = ['OVERDUE' => 'Due now', 'SOON' => 'Due soon', 'ATTENTION' => 'Needs attention', 'UNKNOWN' => 'Not enough info',
        'OK' => 'OK for now', 'SNOOZED' => 'Snoozed', 'ACTIVE' => 'Active', 'RETIRED' => 'Retired', 'BLOCKED' => 'Blocked',
        'ADMIN' => 'Admin', 'USER' => 'User'];
    return '<span class="badge b-' . h(strtolower($status)) . '">' . h($labels[$status] ?? $status) . '</span>';
}

function post_button(string $route, array $params, string $label, string $class = 'btn', ?string $confirm = null, array $hidden = []): string
{
    $html = '<form method="post" action="' . h(url($route, $params)) . '" class="inline"' . ($confirm ? ' data-confirm="' . h($confirm) . '"' : '') . '>' . Csrf::field();
    foreach ($hidden as $k => $v) {
        $html .= '<input type="hidden" name="' . h($k) . '" value="' . h($v) . '">';
    }
    return $html . '<button class="' . h($class) . '">' . h($label) . '</button></form>';
}

function rule_summary(array $r): string
{
    if ($r['trigger_kind'] === 'ONCE_AFTER_INSTALL') {
        return 'once after fitting' . ((int)$r['active'] ? '' : ' (off)');
    }
    if ($r['trigger_kind'] === 'CYCLE_WINDOW') {
        return 'once ' . number_format((float)$r['window_min_km'], 0, '.', ' ') . '–' . number_format((float)$r['window_max_km'], 0, '.', ' ')
            . ' km after ' . mb_strtolower(Catalog::actionName((string)$r['cycle_action_code'])) . ((int)$r['active'] ? '' : ' (off)');
    }
    if ($r['trigger_kind'] === 'PARENT_COUNT') {
        $p = mb_strtolower(Catalog::typeName(Catalog::parentTypes((string)$r['component_type'])[0] ?? 'CHAIN'));
        return 'replace after ' . (int)$r['interval_count'] . ' ' . $p . 's' . ((int)$r['active'] ? '' : ' (off)');
    }
    $p = [];
    if ($r['interval_km'] !== null) {
        $p[] = 'every ' . number_format((float)$r['interval_km'], 0, '.', ' ') . ' km';
    }
    if ($r['interval_months'] !== null) {
        $p[] = 'every ' . (int)$r['interval_months'] . ' months';
    }
    if ($r['interval_hours'] !== null) {
        $p[] = 'every ' . number_format((float)$r['interval_hours'], 0) . ' h';
    }
    if ($r['after_top_up_km'] !== null && $r['interval_km'] !== null) {
        $p[] = 'or ' . number_format((float)$r['after_top_up_km'], 0, '.', ' ') . ' km after a top-up';
    }
    return implode(' or ', $p) . ((int)$r['active'] ? '' : ' (off)');
}
