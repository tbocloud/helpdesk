# UI audit: dark mode and mobile (320–640px)

A static audit of `desk/src` against [ui-guidelines.md](ui-guidelines.md) §16 (accessibility),
§17 (responsive), §18 (dark mode) and §22 (CSS). No site was running, so nothing was rendered
in a browser. Findings come from the source and from the built CSS.

## Method

- **Classes that compile to nothing.** Every colour, border, ring and shadow utility in
  `desk/src` was checked against a fresh `vite build`'s CSS. A class that is missing from the
  CSS is a v1 or invented token.
- **Hard-coded colours.** `#hex`, `rgb()`, `white` and `black` in templates, scoped styles,
  `index.css` and SVG fills; raw Tailwind palette greys (`bg-gray-*`, `text-black`, …).
- **Theme tokens.** Every TBO token in `theme.css` has a dark value (none is light-only).
  Dark mode is `:root[data-theme="dark"]`, which `index.css` also uses for its shadows.
- **Mobile.** Grids without a phone column count, fixed and arbitrary widths, `1fr` tracks that
  stop `truncate` working, `whitespace-nowrap` rows, tables without a phone layout, sticky
  headers, header action counts, hover-only controls, and touch targets.

## Contrast of the TBO tokens

WCAG ratios, computed from the `theme.css` values. `surface-base` is white in light mode.
Changed pairs are covered too: the settings radios now use `ink-gray-9` on `surface-base`.

| Pair | Light | Dark |
| --- | --- | --- |
| `brand-ink` on `brand-soft` | 7.42 | 8.23 |
| `on-brand` on `brand` | 6.24 | 6.09 |
| `brand` on `surface-base` | 6.24 | 5.96 |
| `success` on `success-soft` | 5.02 | 7.13 |
| `warning` on `warning-soft` | 5.20 | 8.34 |
| `danger` on `danger-soft` | 4.90 | 7.17 |
| `info` on `info-soft` | 5.27 | 6.68 |
| `ink-gray-9` on `note` | 17.15 | 13.77 |
| `ink-gray-5` on `surface-base` | 5.44 | 5.37 |
| `ink-gray-5` on `surface-gray-2` | 4.86 | 4.53 |
| `ink-gray-9` on `surface-base` (radios, checked fill) | 17.92 | 15.44 |
| channel colours on `surface-base` (lowest of eight) | 5.37 | 7.53 |
| `champion` on `champion-soft` (champion card label and trophy) | 5.76 | 9.22 |
| `ink-gray-6` on `champion-soft` (champion card text) | 6.39 | 6.59 |
| `success` on `champion-soft` (reason checks) | 5.33 | 7.21 |

The current sidebar item and the Settings nav use `brand-ink` on `brand-soft`; the checked
segmented-control option uses `on-brand` on `brand` (both above).

Every text pair passes 4.5:1. `ink-gray-4` (3.11 light, 3.69 dark) is only used for
placeholders, disabled text and icons, where 3:1 applies.

Charts (`pages/performance/chartTheme.ts`) already have their own dark categorical palette,
read the rest of their colours from the theme tokens, and re-read them when `data-theme`
changes. All five chart components use it.

## Findings

| Page / area | Issue found | Status |
| --- | --- | --- |
| Sidebar (agent) | Customer-portal banner used `bg-surface-modal`, which compiles to nothing, so the card had no background | Fixed: `bg-surface-base` |
| Agent status dot | "Black" status used `bg-ink-gray-9`, which doesn't exist (`ink-*` is text-only), so the dot was invisible | Fixed: `bg-surface-gray-9` (flips in dark) |
| Dropdown "danger" options (`utils.ts` `TemplateOption`) | `hover:bg-ink-red-1` doesn't exist, so there was no hover state | Fixed: `hover:bg-surface-red-2` |
| Search | Corrected query used `text-primary`, which doesn't exist | Fixed: `text-ink-gray-9` |
| Ticket page, replied content | Collapse toggle hard-coded `#e8eaed` / `#dadce0`, a light chip on dark | Fixed: `--surface-gray-3` / `--surface-gray-4` |
| Ticket page, typing indicator | Dots hard-coded `#6b7280` | Fixed: `--ink-gray-5` |
| Settings: SLA policy, SLA holidays, holiday list | Radios were white, black and `#c5c2c2` in both themes, and `outline: none` hid the keyboard focus ring | Fixed: theme tokens; focus ring kept for keyboard (`:focus:not(:focus-visible)`) |
| Call log detail | Audio player light grey and white in dark, and `outline: none` hid focus | Fixed: `--surface-gray-2`; outline rule removed |
| Dialog forms: call log, new/edit contact, new customer, postpone post, email account, Twilio, Exotel | Two-column field grids squeezed to ~130px fields at 320px | Fixed: one column below `sm` |
| Keyboard shortcuts dialog | Two columns with a 40px gap at phone width | Fixed: one column below `md` |
| Customer and contact detail pages, ticket activity panel | Tab labels such as "Support hours" wrapped onto two lines in the scrolling tab bar | Fixed: `whitespace-nowrap shrink-0` |
| Project pages (Overview, Board, Files, Sign-off, Recurring, Checklist) | Header actions ("Edit project", "Lead: …", "Generate checklist", "New task") were wider than a phone, beside the breadcrumb | Fixed: secondary actions show only their icons below `md`, and the label stays as the accessible name; "New task" keeps its label |
| Content plans dialog | Plan rows (`1fr 1fr 5.5rem auto`) overflowed the dialog at 320px | Fixed: `minmax(0,1fr)` tracks and a 4rem count below `sm` |
| Settings → Profile → emails | `4fr` tracks stopped `truncate` working, so long emails overflowed | Fixed: `min-w-0` on the cells |
| Avatar upload (`ImageAvatar`) | Replace and remove buttons were hover-only; the remove button was invisible on touch and had no focus ring | Fixed: shown on `focus-visible` and on `hover:none` devices; focus ring restored |
| Settings modal (phones) | Page picker was 32px tall | Fixed: 44px (`h-11`) |
| Home, Overview, Team + Capacity, Summaries, My Work, Timesheets, Calendar, Customers/Contacts lists, Customer report, Performance stat grids, Knowledge base, portal KB pages | Checked: responsive grid columns, `min-w-0` / `minmax(0,1fr)` rows, mobile rows or agenda layouts | No issues found |
| Content report, Content sheet, Performance tables | Wide tables (720–900px minimum) with no phone layout | Left: they scroll inside their own `overflow-x-auto` card, so the page doesn't scroll sideways. Turning them into card rows means reworking the templates, not just the styling (§14) |
| Kanban board | 288px columns | Left: the board scrolls sideways on purpose; one column fits a 320px screen |
| Ticket status icons (`stores/ticketStatus.ts`) | Raw palette `!text-{color}-500` doesn't adapt to dark mode | Left (P2): mid-tone 500 shades stay visible on dark surfaces; moving them to tokens means changing the colour-map API |
| Call log detail fields | Dynamic `text-{color}-600` classes are raw palette and may not be generated | Left (P2): upstream telephony code, and the colour comes from the field definition |
| Dropdown popovers (`ring-black ring-opacity-5`) | The ring disappears on dark | Left: same as frappe-ui's own popovers; the elevated surface and dark shadow still separate them |
| Duration field / picker | Step arrows are hover-only | Left (P2): the number inputs stay typeable, and the arrows are a shortcut |
| Holiday calendar (settings) | Day details open on hover, in a 320px-wide popover | Left (P2): desktop settings screen; clicking a day still edits it |
| Editor tables (`tiptap-extensions.ts`) | Inline `#d1d5db` borders | Left: the HTML goes out in emails, so it has to carry its own colours |
| `components/desk/global/CustomIcons.vue` | Hard-coded SVG colours | Left: the file isn't imported anywhere (dead code; remove it in a separate change) |
| frappe-ui `Button` (`sm`, 28px) | Most page and dialog actions are under 44px on phones | Fixed: see "44px touch targets" below |
| Support hours page, customer Support hours tab, Settings → CRM | Checked only, not edited (another change in progress): phone layouts and responsive grids are already in place | No issues found |

## 44px touch targets (resolved)

**Decision (owner, 2026-10-10):** every control in the app and the portals has a hit area of
at least 44×44px on phones and touch screens. Desktop pointers keep the dense sizes.

**When:** `(max-width: 639.98px), (pointer: coarse)`, so phones, and tablets used by touch at
any width. The query lives in `desk/src/theme.css`, `TOUCH_TARGET_QUERY` in
`composables/screen.ts` (for script) and `helpdesk/templates/portal_base.html`.

**How (one rule, no per-page sizes):**

- **Grow.** Buttons (frappe-ui `Button`, `NativeButton`, plain `<button>`), links laid out as
  blocks, tabs, menu items, options, `<select>`, `<summary>` and labels that wrap a checkbox or
  radio get `min-height` and `min-width` 44px. The rule sits in `:where()`, so it has no
  specificity and a utility such as `min-h-0` still opts a control out. Inline links in running
  text aren't affected (min sizes don't apply to inline boxes).
- **Expand without moving.** Checkboxes, radios and switches keep their drawn size, and an
  invisible `::after` centred on them takes the taps. The `touch-target` class does the same
  for any other control that must stay small inside a dense card.
- **Rows.** List rows (`ListViewBuilder`) are 44px on touch, so row checkboxes' hit areas
  don't overlap. Sidebar items are 44px.
- **No overlap.** Grown controls are real boxes, so they can't overlap. `touch-target` is used
  only in a strip with nothing else to tap (the Kanban hold and timer strips), or on a control
  that sits on top of a larger one (an input's clear button, a photo's remove badge).

Checked in the built CSS with headless Chromium and WebKit at 360px (touch) and 1280px (mouse):
icon buttons 28px → 44px on touch and 28px on desktop, `min-h-0` opt-out still 28px, a
`touch-target` button stays 24px and takes taps 18px above its centre, checkbox 14px with a
44px tap area, no horizontal scroll at 360px. Real screens weren't rendered (no site).

| Screen | What changed |
| --- | --- |
| Sidebar, mobile header | Sidebar items 44px tall; the menu button 44px |
| Home, Overview | Tiles were already 44px or more. "See all" links, section actions and row menus grow to 44px |
| Scoreboard | No file changes; its links and buttons grow through the theme rule |
| My Work | Task rows, timer and row-menu buttons grow to 44px |
| Board (Kanban) | Card "…" menus grow to 44px. The play, pause and resume buttons in the hold and timer strips keep their 24px look and get a 44px `touch-target` |
| Checklist | "Generate checklist" and "Clear filter" buttons: per-file `min-h-11 … md:min-h-0` classes removed; the theme rule now covers them, on touch tablets too |
| Timeline | Buttons and links grow through the theme rule |
| Files | Comment, preview and file-menu buttons: per-file classes removed, theme rule instead. The download link was already 44px |
| Tickets list | List rows 44px on touch; the phone's stacked rows are links that grow to 44px; view controls grow |
| Ticket detail | Header actions, composer and activity buttons grow (the composer was already 44px) |
| Settings | Nav items and every button grow. SLA, SLA-holiday and holiday radios get a 44px tap area; their no-op `:checked::after` rules were removed, because on touch they would have painted a 44px square over the radio. Chip lists grow with their remove buttons (`min-h-7` instead of `h-7`). The profile photo's remove badge and the clear buttons in the assignee search and multi-select inputs keep their size with `touch-target` |
| Dialogs | frappe-ui close buttons and actions grow. Move-to-folder radios (label rule), mention options and comment edit/delete buttons lost their per-file classes. Post dialog image download/remove buttons grow; the add-option chip grows while editing (`min-h-7`) |
| Customer portal (`/helpdesk/my-tickets`) | Same theme rule as the agent app |
| Content calendar (app) | Chips, view toggles and post actions grow through the theme rule |
| Content portal (`/content-portal`) | `.btn`, `.chip`, `.select`, `.input`, `.link-btn`, `.check` and the image viewer arrows are 44px; filter chips 8px apart on touch |
| Project sign-off (`/project-signoff`) | Same portal rule; its choices and sign-off button were already 44px |

**Left:** two small controls sit on top of a larger one, so their tap areas overlap it by
design, with the small one on top: the profile photo's remove badge (on the "change photo"
button) and the clear buttons inside the assignee search and multi-select inputs. The build's CSS minifier warns
about a nested `li` rule; that comes from existing CSS, not this change.
