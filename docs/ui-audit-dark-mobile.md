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
| frappe-ui `Button` (`sm`, 28px) | Most page and dialog actions are under 44px on phones | Left (P1): raising every button needs a project-wide decision; the composer, capacity planner, recurring dialog and settings picker already use 44px on phones |
| Support hours page, customer Support hours tab, Settings → CRM | Checked only, not edited (another change in progress): phone layouts and responsive grids are already in place | No issues found |
