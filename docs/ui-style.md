# Look and feel

Bike Log uses a bright, sporty "activity feed" style, inspired by the feel of popular cycling apps
(Dirk asked for a look similar to strava.com on 2026-11-01). It is a similar *feel*, not a copy: we
use our own logo, name and colours, and no fonts, icons, images or wording from any other app.
strava.com could not be opened from the build environment, so the style was worked out from general
knowledge of that look.

All of it lives in `frontend/src/index.css` (tokens on `:root`). The page skeleton is in
`frontend/src/App.tsx`. The app is **always light** with a white page, even when Windows or the browser
is set to dark mode (Dirk 2026-11-01): there is no dark-mode block, and `color-scheme: light` keeps form
fields and scrollbars light too.

## Building blocks

| Element | How it looks | CSS |
|---|---|---|
| Top bar | White bar across the top: logo + "Bike Log" left, text navigation, version on the right. The current page is bold with an orange underline. | `.topbar`, `.topbar-inner`, `.navlink.active` |
| Phone (≤ 760 px) | Slim top bar with the logo; the navigation becomes a bottom tab bar with icons, current page in orange. | `@media (max-width: 760px)` |
| Page | White background, content centred, max 1200 px wide. | `.main` |
| Cards | Flat white boxes, thin grey border, 6 px corners, bold title. | `.card`, `.card-head` |
| Accent | One signal orange (`--accent`, #f4511e) for the main action on a screen, the active tab/nav item and selected chips. Links are blue (`--link`) so orange stays special. | `--accent`, `.btn-primary`, `.chip-on` |
| Long task lists | "Log done" is an orange *outline* there (fills on hover), so a list of ten tasks is not a wall of orange. | `.task-actions .btn-primary` |
| Stat blocks | Big light number, small grey label under it, thin divider between stats (dividers dropped on phones). | `.stats`, `.stat` |
| Bike cards | Orange line on top, bike name bold, distance as the headline number. | `.tile` |
| Tabs | Grey text, current tab bold with a 3 px orange underline. | `.tabs`, `.tab-on` |
| Tables | Small uppercase grey column headers, light row hover. | `.table th` |
| Notices | Light orange box with an orange stripe on the left (sample-data banner, toast). | `.demo-banner`, `.toast` |
| Buttons | 4 px corners, bold text; primary = filled orange, others white with a grey border. | `.btn`, `.btn-primary` |

Folded sections (`<details>` with the triangle) stay as they were: little on screen, unfold for more.

## Changing the colours

Change the tokens at the top of `index.css` (`--accent`, `--accent-hover`, `--accent-soft`, `--link`,
`--bg`, `--panel`, `--ink`, `--muted`, `--line`). The status
colours (`--ok`, `--soon`, `--due`, `--info`) mean due/overdue/ok and should stay as they are.
