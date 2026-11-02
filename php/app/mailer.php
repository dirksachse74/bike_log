<?php
declare(strict_types=1);

// Sends plain-text emails: through SMTP (STARTTLS or SSL, AUTH LOGIN), PHP mail(), or a log file for testing.
// A failed send is logged and never shown to the visitor (it would reveal whether an account exists).

final class Mailer
{
    /** @var array<int, array{to:string, subject:string, body:string}> emails "sent" in this request (tests) */
    public static array $sent = [];

    public static function send(string $to, string $subject, string $body): bool
    {
        $to = trim($to);
        if (!filter_var($to, FILTER_VALIDATE_EMAIL)) {
            return false;
        }
        $subject = self::clean($subject);
        self::$sent[] = ['to' => $to, 'subject' => $subject, 'body' => $body];
        $transport = (string)Config::get('mail.transport', 'log');
        try {
            return match ($transport) {
                'smtp' => self::smtp($to, $subject, $body),
                'mail' => self::phpMail($to, $subject, $body),
                default => self::log($to, $subject, $body),
            };
        } catch (Throwable $e) {
            error_log('Bike Log mail to ' . $to . ' failed: ' . $e->getMessage());
            return false;
        }
    }

    /** No header injection: remove line breaks from anything that ends up in a header. */
    private static function clean(string $s): string
    {
        return trim(str_replace(["\r", "\n"], ' ', $s));
    }

    private static function from(): array
    {
        return [self::clean((string)Config::get('mail.from', 'bikelog@localhost')), self::clean((string)Config::get('mail.from_name', 'Bike Log'))];
    }

    private static function encodeHeader(string $s): string
    {
        return preg_match('/[^\x20-\x7e]/', $s) ? '=?UTF-8?B?' . base64_encode($s) . '?=' : $s;
    }

    private static function headers(string $to, string $subject): array
    {
        [$from, $fromName] = self::from();
        $domain = substr(strrchr($from, '@') ?: '@localhost', 1);
        return [
            'Date' => date('r'),
            'From' => self::encodeHeader($fromName) . " <$from>",
            'To' => "<$to>",
            'Subject' => self::encodeHeader($subject),
            'Message-ID' => '<' . bin2hex(random_bytes(12)) . '@' . $domain . '>',
            'MIME-Version' => '1.0',
            'Content-Type' => 'text/plain; charset=UTF-8',
            'Content-Transfer-Encoding' => 'base64',
            'Auto-Submitted' => 'auto-generated',
        ];
    }

    private static function log(string $to, string $subject, string $body): bool
    {
        $dir = (string)Config::get('storage_dir', __DIR__ . '/../storage');
        $entry = "==== " . gmdate('c') . "\nTo: $to\nSubject: $subject\n\n$body\n";
        return file_put_contents($dir . '/mail.log', $entry, FILE_APPEND | LOCK_EX) !== false;
    }

    private static function phpMail(string $to, string $subject, string $body): bool
    {
        $h = self::headers($to, $subject);
        unset($h['To'], $h['Subject'], $h['Date']);
        $lines = [];
        foreach ($h as $k => $v) {
            $lines[] = "$k: $v";
        }
        [$from] = self::from();
        return mail($to, self::encodeHeader($subject), chunk_split(base64_encode($body)), implode("\r\n", $lines), '-f' . $from);
    }

    private static function smtp(string $to, string $subject, string $body): bool
    {
        $host = (string)Config::get('mail.smtp_host');
        $port = (int)Config::get('mail.smtp_port', 587);
        $secure = (string)Config::get('mail.smtp_secure', 'tls');
        $ctx = stream_context_create(['ssl' => ['verify_peer' => true, 'verify_peer_name' => true, 'SNI_enabled' => true]]);
        $remote = ($secure === 'ssl' ? 'ssl://' : 'tcp://') . $host . ':' . $port;
        $fp = @stream_socket_client($remote, $errno, $errstr, 15, STREAM_CLIENT_CONNECT, $ctx);
        if (!$fp) {
            throw new RuntimeException("connect $remote: $errstr");
        }
        stream_set_timeout($fp, 20);
        $ehloName = preg_replace('/[^A-Za-z0-9.-]/', '', (string)parse_url((string)Config::get('base_url'), PHP_URL_HOST)) ?: 'localhost';
        try {
            self::expect($fp, 220);
            self::cmd($fp, "EHLO $ehloName", 250);
            if ($secure === 'tls') {
                self::cmd($fp, 'STARTTLS', 220);
                if (!stream_socket_enable_crypto($fp, true, STREAM_CRYPTO_METHOD_TLSv1_2_CLIENT | STREAM_CRYPTO_METHOD_TLSv1_3_CLIENT)) {
                    throw new RuntimeException('STARTTLS failed');
                }
                self::cmd($fp, "EHLO $ehloName", 250);
            }
            $user = (string)Config::get('mail.smtp_user', '');
            if ($user !== '') {
                self::cmd($fp, 'AUTH LOGIN', 334);
                self::cmd($fp, base64_encode($user), 334);
                self::cmd($fp, base64_encode((string)Config::get('mail.smtp_pass', '')), 235, true);
            }
            [$from] = self::from();
            self::cmd($fp, "MAIL FROM:<$from>", 250);
            self::cmd($fp, "RCPT TO:<$to>", [250, 251]);
            self::cmd($fp, 'DATA', 354);
            $msg = '';
            foreach (self::headers($to, $subject) as $k => $v) {
                $msg .= "$k: $v\r\n";
            }
            $msg .= "\r\n" . rtrim(chunk_split(base64_encode($body), 76, "\r\n")) . "\r\n.";
            self::cmd($fp, $msg, 250);
            self::cmd($fp, 'QUIT', 221);
        } finally {
            fclose($fp);
        }
        return true;
    }

    private static function cmd($fp, string $line, int|array $expect, bool $secret = false): string
    {
        fwrite($fp, $line . "\r\n");
        try {
            return self::expect($fp, $expect);
        } catch (RuntimeException $e) {
            throw new RuntimeException(($secret ? '[credentials]' : strtok($line, "\r\n")) . ' -> ' . $e->getMessage());
        }
    }

    private static function expect($fp, int|array $expect): string
    {
        $resp = '';
        while (($line = fgets($fp, 1024)) !== false) {
            $resp .= $line;
            if (strlen($line) < 4 || $line[3] === ' ') {
                break;
            }
        }
        $code = (int)substr($resp, 0, 3);
        if (!in_array($code, (array)$expect, true)) {
            throw new RuntimeException('SMTP ' . trim($resp));
        }
        return $resp;
    }
}
