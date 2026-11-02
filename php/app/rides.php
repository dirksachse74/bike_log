<?php
declare(strict_types=1);

// Ride options beyond the form: leave a ride out of the km, wheels used on one ride, several rides at once,
// and the CSV import (same columns as the desktop app, plus Strava's own "Download your data" activities.csv).

final class Rides
{
    /** Positions a ride can set to a different part than the fitted one. */
    public const EQUIPMENT_SLOTS = ['WHEELSET', 'FRONT_WHEEL', 'REAR_WHEEL'];
    public const KM_PER_MILE = 1.609344;
    public const MAX_CSV = 20 * 1024 * 1024;
    private const TRUE = ['1', 'yes', 'y', 'true', 'ja', 'x'];

    public static function get(int $uid, int $id): array
    {
        return Db::one('SELECT * FROM rides WHERE id = ? AND user_id = ?', [$id, $uid]) ?? throw new NotFound('Ride not found.');
    }

    public static function exclude(int $uid, int $id, string $reason): void
    {
        if (trim($reason) === '') {
            throw new UserError('Say why it should not count (e.g. “rented bike”).');
        }
        self::get($uid, $id);
        Db::updateOwned('rides', $id, $uid, ['excluded_reason' => mb_substr(trim($reason), 0, 255), 'updated_at' => now_utc()]);
    }

    public static function include(int $uid, int $id): void
    {
        self::get($uid, $id);
        Db::updateOwned('rides', $id, $uid, ['excluded_reason' => null, 'updated_at' => now_utc()]);
    }

    /** Wheel positions of the ride's bike on the ride day: what was fitted, what the ride says, what could be picked. */
    public static function equipment(int $uid, array $ride): array
    {
        if (!$ride['bike_id']) {
            return [];
        }
        $set = [];
        foreach (Db::all('SELECT e.*, c.label, c.mark FROM ride_equipment e LEFT JOIN components c ON c.id = e.component_id WHERE e.ride_id = ? AND e.user_id = ?',
            [$ride['id'], $uid]) as $e) {
            $set[$e['slot']] = $e;
        }
        $out = [];
        foreach (self::EQUIPMENT_SLOTS as $slot) {
            $fitted = Db::one('SELECT c.* FROM installations i JOIN components c ON c.id = i.component_id WHERE i.user_id = ? AND i.bike_id = ? AND i.slot = ?
                AND i.voided_at IS NULL AND i.installed_on <= ? AND (i.removed_on IS NULL OR i.removed_on > ?) ORDER BY i.installed_on DESC LIMIT 1',
                [$uid, $ride['bike_id'], $slot, $ride['ride_date'], $ride['ride_date']]);
            if (!$fitted && !isset($set[$slot]) && !($slot === 'WHEELSET' || self::hasFitted($uid, (int)$ride['bike_id'], $slot))) {
                continue;
            }
            $types = array_keys(array_filter(Catalog::types(), fn($t) => in_array($slot, $t['slots'], true)));
            $in = implode(',', array_fill(0, count($types), '?'));
            $cands = Db::all("SELECT * FROM components WHERE user_id = ? AND status = 'ACTIVE' AND component_type IN ($in) ORDER BY label", array_merge([$uid], $types));
            $out[$slot] = ['slot' => $slot, 'fitted' => $fitted, 'set' => $set[$slot] ?? null, 'candidates' => $cands];
        }
        // a bike with a wheelset does not offer single wheels and the other way round, unless the ride already says so
        if (isset($out['WHEELSET']) && ($out['WHEELSET']['fitted'] || $out['WHEELSET']['set'])) {
            foreach (['FRONT_WHEEL', 'REAR_WHEEL'] as $s) {
                if (isset($out[$s]) && !$out[$s]['fitted'] && !$out[$s]['set']) {
                    unset($out[$s]);
                }
            }
        } elseif (isset($out['WHEELSET']) && !$out['WHEELSET']['set'] && (isset($out['FRONT_WHEEL']) || isset($out['REAR_WHEEL']))) {
            unset($out['WHEELSET']);
        }
        return $out;
    }

    private static function hasFitted(int $uid, int $bikeId, string $slot): bool
    {
        return (bool)Db::value('SELECT 1 FROM installations WHERE user_id = ? AND bike_id = ? AND slot = ? AND voided_at IS NULL LIMIT 1', [$uid, $bikeId, $slot]);
    }

    /** $choice: '' = as fitted (no override), 'none' = nothing there, or a part id. */
    public static function setEquipment(int $uid, int $rideId, string $slot, string $choice): void
    {
        $ride = self::get($uid, $rideId);
        if (!in_array($slot, self::EQUIPMENT_SLOTS, true) || !$ride['bike_id']) {
            throw new UserError('Pick a wheel position of the ride’s bike.');
        }
        Db::tx(function () use ($uid, $ride, $slot, $choice) {
            Db::run('DELETE FROM ride_equipment WHERE ride_id = ? AND slot = ? AND user_id = ?', [$ride['id'], $slot, $uid]);
            if ($choice === '') {
                ChangeLog::note($uid, 'ride', (int)$ride['id'], Catalog::slotName($slot) . ': as fitted', (int)$ride['bike_id']);
                return;
            }
            $cid = null;
            if ($choice !== 'none') {
                $c = Domain::component($uid, (int)$choice);
                if (!in_array($slot, Catalog::slots($c['component_type']), true)) {
                    throw new UserError(Catalog::typeName($c['component_type']) . ' does not go in that position.');
                }
                $cid = (int)$c['id'];
            }
            Db::insert('ride_equipment', ['user_id' => $uid, 'ride_id' => $ride['id'], 'slot' => $slot, 'component_id' => $cid, 'created_at' => now_utc()]);
            ChangeLog::note($uid, 'ride', (int)$ride['id'], Catalog::slotName($slot) . ' on this ride: ' . ($cid ? Domain::componentName($c) : 'none'),
                (int)$ride['bike_id'], $cid);
        });
    }

    /** Several rides at once: assign a bike, remove, restore, leave out of the km, count again. Returns the number changed. */
    public static function bulk(int $uid, array $ids, string $do, ?int $bikeId = null, string $reason = ''): int
    {
        $ids = array_values(array_unique(array_filter(array_map('intval', $ids))));
        if (!$ids) {
            throw new UserError('Tick the rides first.');
        }
        if (count($ids) > 500) {
            throw new UserError('At most 500 rides at once.');
        }
        if ($do === 'bike') {
            $b = Domain::bike($uid, (int)$bikeId);
            if ($b['status'] !== 'ACTIVE') {
                throw new UserError('This bike is retired.');
            }
        }
        if ($do === 'exclude' && trim($reason) === '') {
            throw new UserError('Say why they should not count.');
        }
        return Db::tx(function () use ($uid, $ids, $do, $bikeId, $reason) {
            $n = 0;
            foreach ($ids as $id) {
                $r = Db::one('SELECT * FROM rides WHERE id = ? AND user_id = ?', [$id, $uid]);
                if (!$r) {
                    continue;
                }
                $row = match ($do) {
                    'bike' => (int)$r['bike_id'] === $bikeId ? null : ['bike_id' => $bikeId],
                    'remove' => $r['removed_at'] ? null : ['removed_at' => now_utc()],
                    'restore' => $r['removed_at'] ? ['removed_at' => null] : null,
                    'exclude' => ['excluded_reason' => mb_substr(trim($reason), 0, 255)],
                    'include' => $r['excluded_reason'] !== null ? ['excluded_reason' => null] : null,
                    default => throw new UserError('Unknown action.'),
                };
                if ($row === null) {
                    continue;
                }
                if ($do === 'bike') {
                    Db::run('DELETE FROM ride_equipment WHERE ride_id = ? AND user_id = ?', [$id, $uid]);   // wheels of the old bike
                }
                Db::updateOwned('rides', $id, $uid, $row + ['updated_at' => now_utc()]);
                $n++;
            }
            if ($do === 'bike' && $n) {
                Inventory::ensureFrame($uid, (int)$bikeId);
            }
            return $n;
        });
    }

    // ------------------------------------------------------------------ CSV import

    private static function num(?string $s, bool $decimalComma, string $field): ?float
    {
        if ($s === null || trim($s) === '') {
            return null;
        }
        $raw = trim($s);
        $t = $decimalComma ? str_replace(['.', ','], ['', '.'], $raw) : str_replace(',', '', $raw);
        if (!is_numeric($t)) {
            throw new UserError("$field '$raw' is not a number");
        }
        return (float)$t;
    }

    /** A date or a date and time from a CSV cell -> [local date, local time or null]. Times with Z/offset are converted. */
    private static function when(string $s, DateTimeZone $tz, bool $utc = false): array
    {
        $s = trim($s);
        if (preg_match('/^\d{4}-\d{2}-\d{2}$/', $s)) {
            return [$s, null];
        }
        try {
            $d = $utc ? new DateTimeImmutable($s, new DateTimeZone('UTC')) : new DateTimeImmutable($s, $tz);
        } catch (Exception) {
            throw new UserError("date '$s' is not a date (use 2026-05-01 or 2026-05-01 07:30)");
        }
        $d = $d->setTimezone($tz);
        return [$d->format('Y-m-d'), $d->format('H:i:s')];
    }

    /** Rows of a CSV file: [source kind, rows]; each row is ['row' => n, 'ref', 'values'] or with 'error' / 'skip'. */
    public static function parseCsv(string $content, DateTimeZone $tz): array
    {
        if (strlen($content) > self::MAX_CSV) {
            throw new UserError('The file is larger than 20 MB.');
        }
        if (str_starts_with($content, "\xEF\xBB\xBF")) {
            $content = substr($content, 3);
        }
        if (!mb_check_encoding($content, 'UTF-8')) {
            $content = mb_convert_encoding($content, 'UTF-8', 'Windows-1252');
        }
        $sample = substr($content, 0, 4096);
        $delim = substr_count($sample, ';') > substr_count($sample, ',') ? ';' : ',';
        $fh = fopen('php://memory', 'r+');
        fwrite($fh, $content);
        rewind($fh);
        $header = fgetcsv($fh, 0, $delim, '"', '');
        if (!$header || $header === [null]) {
            throw new UserError('The file is empty.');
        }
        $header = array_map(fn($h) => strtolower(trim((string)$h)), $header);
        $idx = [];
        foreach ($header as $i => $h) {
            $idx[$h] ??= $i;   // Strava's export repeats some headers; the first is in display units
        }
        $strava = isset($idx['activity id'], $idx['activity date']);
        if (!$strava && (!isset($idx['source_id'], $idx['date']) || (!isset($idx['distance_km']) && !isset($idx['distance_mi'])))) {
            throw new UserError('Unrecognised CSV. Required columns: source_id, date, distance_km (or distance_mi). Found: ' . implode(', ', $header));
        }
        $sports = Catalog::raw('ride_sport_types');
        $rows = [];
        $n = 1;
        while (($row = fgetcsv($fh, 0, $delim, '"', '')) !== false) {
            $n++;
            if (!array_filter($row, fn($c) => trim((string)$c) !== '')) {
                continue;
            }
            $get = function (string $k) use ($row, $idx): ?string {
                $i = $idx[$k] ?? null;
                $v = $i !== null && isset($row[$i]) ? trim((string)$row[$i]) : '';
                return $v === '' ? null : $v;
            };
            try {
                if ($strava) {
                    $sport = str_replace(' ', '', (string)$get('activity type'));
                    if (!in_array($sport, $sports, true)) {
                        $rows[] = ['row' => $n, 'ref' => $get('activity id'), 'skip' => 'NOT_CYCLING'];
                        continue;
                    }
                    $d = DateTimeImmutable::createFromFormat('M j, Y, g:i:s A', (string)$get('activity date'), new DateTimeZone('UTC'));
                    if (!$d) {
                        throw new UserError("Activity Date '" . $get('activity date') . "' is not a date");
                    }
                    $local = $d->setTimezone($tz);
                    $elapsed = $get('elapsed time');
                    $rows[] = ['row' => $n, 'ref' => $get('activity id'), 'values' => ['date' => $local->format('Y-m-d'), 'time' => $local->format('H:i:s'),
                        'km' => self::num($get('distance'), false, 'Distance'), 'duration' => $elapsed !== null ? (int)self::num($elapsed, false, 'Elapsed Time') : null,
                        'name' => $get('activity name'), 'bike' => $get('activity gear'), 'indoor' => $sport === 'VirtualRide']];
                    continue;
                }
                $ref = $get('source_id') ?? throw new UserError('source_id is empty');
                [$date, $time] = self::when($get('date') ?? throw new UserError('date is empty'), $tz);
                $dc = $delim === ';';
                $km = self::num($get('distance_km'), $dc, 'distance_km');
                if ($km === null && $get('distance_mi') !== null) {
                    $km = self::num($get('distance_mi'), $dc, 'distance_mi') * self::KM_PER_MILE;
                }
                $dur = null;
                if ($get('duration_s') !== null) {
                    $dur = (int)self::num($get('duration_s'), $dc, 'duration_s');
                } elseif ($get('duration_min') !== null) {
                    $dur = (int)round(self::num($get('duration_min'), $dc, 'duration_min') * 60);
                }
                $sport = $get('sport_type') ?? 'Ride';
                $rows[] = ['row' => $n, 'ref' => mb_substr($ref, 0, 64), 'values' => ['date' => $date, 'time' => $time, 'km' => $km, 'duration' => $dur,
                    'name' => $get('name'), 'bike' => $get('bike'), 'indoor' => in_array(strtolower((string)$get('trainer')), self::TRUE, true) || $sport === 'VirtualRide',
                    'elevation' => $get('elevation_m') !== null ? (int)self::num($get('elevation_m'), $dc, 'elevation_m') : null,
                    'wet' => in_array(strtolower((string)$get('wet')), self::TRUE, true)]];
            } catch (UserError $e) {
                $rows[] = ['row' => $n, 'ref' => null, 'error' => $e->getMessage()];
            }
        }
        fclose($fh);
        return [$strava ? 'STRAVA_CSV' : 'CSV', $rows];
    }

    /**
     * Import (or with $dryRun only count) the rows. A ride is identified by the file's id (source_id / Activity ID):
     * a ride imported before is left as it is (your edits win, a removed ride stays removed). Unknown bike
     * names are listed; those rides come in without a bike.
     */
    public static function importCsv(int $uid, string $content, bool $dryRun = false): array
    {
        $tz = user_tz();
        [$kind, $rows] = self::parseCsv($content, $tz);
        $bikes = [];
        foreach (Db::all('SELECT id, name, status FROM bikes WHERE user_id = ?', [$uid]) as $b) {
            $bikes[mb_strtolower($b['name'])] = $b;
        }
        $counts = ['CREATED' => 0, 'EXISTS' => 0, 'ERROR' => 0, 'SKIPPED' => 0];
        $errors = [];
        $unknown = [];
        $run = function () use ($uid, $kind, $rows, $bikes, $dryRun, &$counts, &$errors, &$unknown) {
            $prev = ChangeLog::$source;
            ChangeLog::$source = 'CSV_IMPORT';
            $touched = [];
            try {
                foreach ($rows as $r) {
                    if (isset($r['error'])) {
                        $counts['ERROR']++;
                        $errors[] = "Row {$r['row']}: {$r['error']}";
                        continue;
                    }
                    if (isset($r['skip'])) {
                        $counts['SKIPPED']++;
                        continue;
                    }
                    if ($r['ref'] === null || $r['ref'] === '') {
                        $counts['ERROR']++;
                        $errors[] = "Row {$r['row']}: no id";
                        continue;
                    }
                    if (Db::value('SELECT id FROM rides WHERE user_id = ? AND source_kind = ? AND source_ref = ?', [$uid, $kind, $r['ref']])) {
                        $counts['EXISTS']++;
                        continue;
                    }
                    $v = $r['values'];
                    if ($v['km'] !== null && ($v['km'] < 0 || $v['km'] > 2000)) {
                        $counts['ERROR']++;
                        $errors[] = "Row {$r['row']}: distance {$v['km']} km is not plausible";
                        continue;
                    }
                    $bikeId = null;
                    if ($v['bike'] !== null) {
                        $b = $bikes[mb_strtolower($v['bike'])] ?? null;
                        if ($b) {
                            $bikeId = (int)$b['id'];
                        } else {
                            $unknown[$v['bike']] = ($unknown[$v['bike']] ?? 0) + 1;
                        }
                    }
                    $counts['CREATED']++;
                    if ($dryRun) {
                        continue;
                    }
                    Db::insert('rides', ['user_id' => $uid, 'bike_id' => $bikeId, 'ride_date' => $v['date'], 'start_time' => $v['time'],
                        'name' => $v['name'] !== null ? mb_substr($v['name'], 0, 200) : null, 'distance_km' => $v['km'] !== null ? round($v['km'], 2) : null,
                        'duration_s' => $v['duration'], 'elevation_m' => $v['elevation'] ?? null, 'kind' => $v['indoor'] ? 'INDOOR' : 'OUTDOOR',
                        'conditions' => !empty($v['wet']) ? 'WET' : null,
                        'notes' => $bikeId === null && $v['bike'] !== null ? 'Bike in the file: ' . mb_substr($v['bike'], 0, 120) : null,
                        'source_kind' => $kind, 'source_ref' => $r['ref'], 'created_at' => now_utc(), 'updated_at' => now_utc()]);
                    if ($bikeId) {
                        $touched[$bikeId] = true;
                    }
                }
                foreach (array_keys($touched) as $b) {
                    Inventory::ensureFrame($uid, $b);   // older rides move the automatic frame back
                }
            } finally {
                ChangeLog::$source = $prev;
            }
        };
        $dryRun ? $run() : Db::tx($run);
        if (!$dryRun && $counts['CREATED']) {
            ChangeLog::note($uid, 'ride', null, "CSV import: {$counts['CREATED']} rides added, {$counts['EXISTS']} were there already");
        }
        return ['kind' => $kind, 'rows' => count($rows), 'counts' => $counts, 'errors' => array_slice($errors, 0, 100), 'unknown_bikes' => $unknown, 'dry_run' => $dryRun];
    }
}
