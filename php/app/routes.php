<?php
declare(strict_types=1);

final class Routes
{
    /** route name => handler. Each handler checks sign-in / admin itself (require_user, require_admin). */
    public static function all(): array
    {
        return [
            // public
            'install' => 'page_install', 'login' => 'page_login', 'logout' => 'page_logout', 'register' => 'page_register',
            'verify' => 'page_verify', 'resend' => 'page_resend', 'forgot' => 'page_forgot', 'reset' => 'page_reset',
            'confirm_email' => 'page_confirm_email_change', 'notfound' => 'page_notfound',
            // signed in
            'home' => 'page_home', 'reminders' => 'page_reminders', 'snooze' => 'page_snooze',
            'bikes' => 'page_bikes', 'bike' => 'page_bike', 'bike_edit' => 'page_bike_edit', 'bike_status' => 'page_bike_status',
            'parts' => 'page_parts', 'part' => 'page_part', 'part_edit' => 'page_part_edit', 'part_install' => 'page_part_install',
            'part_status' => 'page_part_status', 'inst_remove' => 'page_inst_remove', 'inst_void' => 'page_inst_void', 'adjust' => 'page_adjust',
            'rides' => 'page_rides', 'ride_edit' => 'page_ride_edit', 'ride_status' => 'page_ride_status',
            'maintenance' => 'page_maintenance', 'log' => 'page_log', 'event_void' => 'page_event_void',
            'rules' => 'page_rules', 'rule_edit' => 'page_rule_edit', 'rule_delete' => 'page_rule_delete',
            'supplies' => 'page_supplies', 'supply' => 'page_supply', 'supply_edit' => 'page_supply_edit',
            'groupset' => 'page_groupset', 'ws' => 'page_ws', 'ws_undo' => 'page_ws_undo', 'spares' => 'page_spares', 'stock_take' => 'page_stock_take',
            'my_settings' => 'page_my_settings', 'ride' => 'page_ride', 'incident_log' => 'page_incident_log', 'incidents' => 'page_incidents',
            'incident' => 'page_incident', 'incident_fix' => 'page_incident_fix', 'punctures' => 'page_punctures', 'spoke' => 'page_spoke', 'journal' => 'page_journal',
            'account' => 'page_account', 'export' => 'page_export',
            // admin
            'admin' => 'page_admin', 'admin_users' => 'page_admin_users', 'admin_user' => 'page_admin_user', 'admin_invite' => 'page_admin_invite',
            'admin_audit' => 'page_admin_audit', 'admin_settings' => 'page_admin_settings', 'admin_system' => 'page_admin_system',
        ];
    }
}
