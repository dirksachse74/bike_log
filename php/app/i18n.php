<?php
declare(strict_types=1);

// Languages. The English text in the code is the key; app/lang/<code>.php maps it to the translation.
// A text without a translation is shown in English, never as an error.
//
//   t('Bikes')                                    → "Fahrräder" in German
//   t('Every {km} km', ['km' => '300'])           → placeholders in {braces}, filled after translating
//
// Which language: the signed-in user's choice (users.lang), else the switch on the sign-in pages
// (cookie bikelog_lang), else the site default (Admin → Settings), else the browser's language, else English.

final class I18n
{
    public const LANGS = ['en' => 'English', 'de' => 'Deutsch'];
    public const COOKIE = 'bikelog_lang';

    private static ?string $lang = null;
    private static array $dicts = [];

    public static function lang(): string
    {
        if (self::$lang === null) {
            self::$lang = self::detect();
        }
        return self::$lang;
    }

    /** Force the language for the rest of this request (tests, e-mails to another user). */
    public static function set(?string $lang): void
    {
        self::$lang = ($lang !== null && isset(self::LANGS[$lang])) ? $lang : null;
    }

    /** Run $fn in another language (an e-mail to a user who chose German), then switch back. */
    public static function with(?string $lang, callable $fn): mixed
    {
        $before = self::$lang;
        self::$lang = ($lang !== null && isset(self::LANGS[$lang])) ? $lang : self::lang();
        try {
            return $fn();
        } finally {
            self::$lang = $before;
        }
    }

    public static function valid(string $lang): bool
    {
        return isset(self::LANGS[$lang]);
    }

    private static function detect(): string
    {
        if (PHP_SAPI === 'cli') {
            return 'en';
        }
        $u = class_exists('Auth') ? Auth::user() : null;
        if ($u && self::valid((string)($u['lang'] ?? ''))) {
            return (string)$u['lang'];
        }
        $c = (string)($_COOKIE[self::COOKIE] ?? '');
        if (self::valid($c)) {
            return $c;
        }
        $site = class_exists('Settings') ? Settings::get('default_language') : '';
        if (self::valid($site)) {
            return $site;
        }
        foreach (explode(',', (string)($_SERVER['HTTP_ACCEPT_LANGUAGE'] ?? '')) as $part) {
            $code = strtolower(substr(trim($part), 0, 2));
            if (self::valid($code)) {
                return $code;
            }
        }
        return 'en';
    }

    /** The translation table for a language (English has none: the key is the text). */
    public static function dict(string $lang): array
    {
        if ($lang === 'en') {
            return [];
        }
        if (!isset(self::$dicts[$lang])) {
            $file = __DIR__ . '/lang/' . $lang . '.php';
            self::$dicts[$lang] = (preg_match('/^[a-z]{2}$/', $lang) && is_file($file)) ? (array)require $file : [];
        }
        return self::$dicts[$lang];
    }

    /** Remember a choice made on the sign-in pages (no account yet). */
    public static function rememberInCookie(string $lang): void
    {
        if (PHP_SAPI !== 'cli' && !headers_sent()) {
            setcookie(self::COOKIE, $lang, ['expires' => time() + 365 * 86400, 'path' => '/', 'secure' => Request::isHttps(),
                'httponly' => true, 'samesite' => 'Lax']);
        }
        $_COOKIE[self::COOKIE] = $lang;
    }
}

/** Translate a UI text. Placeholders like {name} are filled after translating, so the order can change per language. */
function t(string $text, array $vars = []): string
{
    $lang = I18n::lang();
    if ($lang !== 'en') {
        $text = I18n::dict($lang)[$text] ?? $text;
    }
    if ($vars) {
        $repl = [];
        foreach ($vars as $k => $v) {
            $repl['{' . $k . '}'] = (string)$v;
        }
        $text = strtr($text, $repl);
    }
    return $text;
}

/** Translate each value of a code => label list (for <select> options). Nested groups are translated too. */
function t_list(array $labels): array
{
    $out = [];
    foreach ($labels as $k => $v) {
        $out[is_array($v) ? t((string)$k) : $k] = is_array($v) ? t_list($v) : t((string)$v);
    }
    return $out;
}

/** A decimal number in the user's language: 1 234.5 in English, 1 234,5 in German. */
function num(float $v, int $dec = 0): string
{
    return number_format($v, $dec, I18n::lang() === 'de' ? ',' : '.', ' ');
}
