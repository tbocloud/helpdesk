# UI guidelines: deliberate, human-designed interfaces

The owner's standing rule for every screen people use: the helpdesk app (`desk/`) and the
server-rendered portals and pages (`helpdesk/www/`, e.g. the content portal). Read it together
with [engineering-guardrails.md](engineering-guardrails.md), and with the TBO theme in
`desk/src/theme.css` and `AGENTS.md`.

Interfaces must be deliberate, intuitive, fast, accessible, responsive, consistent,
maintainable and visually distinctive. **They must never look like a generic AI-generated
dashboard.**

**Loop:** INSPECT → UNDERSTAND → REUSE → DESIGN → IMPLEMENT → TEST → AUDIT → CLEAN → VERIFY.
Never CREATE → DUPLICATE → PATCH → IGNORE → SHIP.

## 1. Understand before building

For each screen, decide:
- who uses it;
- their primary task and the most important action;
- what must be visible immediately and what is secondary;
- the worst mistake a user could make;
- what follows the primary action;
- what happens on network failure, with empty data, or without permission.

Then give the screen **one purpose, one clear hierarchy, and one dominant primary action**.
Not everything is important.

## 2. Inspect the product first

Before building, search for existing components, tokens, typography, spacing, icons, layouts,
composables and API patterns. Reuse first, extend second, create only for a real need. TBO
building blocks already exist; consolidate them rather than adding more:
- page headers (`LayoutHeader`);
- cards (`HomeCard`);
- stat tiles (`StatTile` in performance, the Overview tiles);
- empty and error states (`TaskyState`);
- badges (`TaskyBadge`);
- charts (`desk/src/pages/performance/chartTheme.ts`);
- settings pages (`SettingsLayoutBase`, `SettingsSection`, `SettingRow`, `SettingsList`; see
  [settings-ui.md](settings-ui.md)).

## 3. Zero duplication, zero dead code, zero needless dependencies

These follow [engineering-guardrails.md](engineering-guardrails.md). If several versions of
one concept exist, pick the canonical one and consolidate when it's safe.

## 4. Design system first

Use the TBO theme:
- **Colours:** v2 tokens `bg-surface-*`, `text-ink-*`, `border-outline-*`; `brand` (the TBO
  logo teal) for the one accent; `highlight` (the logo orange) only for the focus ring and
  the calendars' "today" ring; `success`, `warning`, `danger` and `info` (plus their soft variants) for
  meaning. Values and contrast are in §8.
- **Fonts:** Geist, and Geist Mono with `tabular-nums` for numbers.
- **Radii and icons:** the existing radii; Lucide icons.

Don't invent colours, font sizes, spacing values, radii or shadows. If a new token is truly
needed, add it to the theme, use it consistently, and say why.

## 5. Design all the states

Cover:
- default, hover, focus, active and disabled;
- loading, success and error;
- empty, offline, partial data and permission denied.

The happy path alone is not a finished UI.

## 6. Spacing and layout

- Use a 4px grid: 4, 8, 12, 16, 24, 32, 48.
- Spacing, size and position express importance; don't space every section the same.
- Labels go left and numbers go right. Align icons optically with their text, and group
  related information predictably.
- Avoid needless centring.

## 7. Typography

- Keep to the existing type scale, with readable body text.
- Use `tabular-nums` for statistics, money, counts and times.
- Never truncate a number. Long text may truncate only when the full value stays reachable.

## 8. Colour: one accent plus neutrals

- **Brand** is only for the primary action, the current selection and key interaction
  states.
- **Highlight** (the logo orange) is only a ring or marker: the keyboard `focus-visible`
  ring and the "today" ring on calendars (the Content board's date page, the Content week
  strip and the Work calendar). Never a fill, a button or text, so it can't be read as
  `warning` (brown text on cream).
- **Red** only for errors, destructive actions and overdue work. **Green** only for success
  and done.
- **Never colour alone:** always pair colour with an icon, text or shape. Keep contrast
  accessible.
- **Avoid:** purple-to-blue gradients, gradient text, decorative blobs, rainbow stat cards
  and colour used as decoration. (Pastel icon tiles on stat cards, per-stage pill colours
  and person colours are allowed by the Leads redesign exception below.)

### The TBO palette (2026-11-14: the Leads redesign)

The owner asked for the "Leads (all) — redesigned" mockup across the whole app, with the
mockup's colours winning over the earlier rules. So the brand moved from the logo teal
(`#3a748d`) to the mockup's deeper teal, the neutrals are the mockup's slate grays, and the
page sits on a light gray canvas with white cards. The tokens live in `desk/src/theme.css`
(mirrored in `helpdesk/templates/portal_base.html`).

| Token | Light | Dark |
| --- | --- | --- |
| `brand` | `#17657f` | `#6fb4cf` |
| `brand-hover` | `#125469` | `#8dc5da` |
| `brand-soft` / `brand-soft-border` | `#e6f2f5` / `#cfe5eb` | `#15303b` / `#1f4654` |
| `brand-ink` / `brand-ink-hover` (links, current menu item) | `#17657f` / `#0e4a5e` | `#a6d5e6` / `#c4e4ef` |
| `canvas` (page background) | `#f4f6f8` | `oklch(0.169 0.006 271)` |
| `surface-sidebar` (menu panel) | `#ffffff` | `oklch(0.205 0.008 275)` |
| rail | `#0f172a`, icons `#94a3b8` | unchanged |
| `ink-gray-9` / `-8` / `-7` / `-6` | `#0f172a` / `#1f2937` / `#3b4453` / `#5b6474` | unchanged |
| `outline-gray-1` / `-2` / `-3` | `#eef1f4` / `#e3e7ec` / `#d5dbe2` | unchanged |
| `info` / `success` / `warning` / `danger` | `#1e4fb8` / `#136b4a` / `#8a5300` / `#b42318` | unchanged |
| `violet` (proposal stage) | `#5b32b4` on `#f1eafe` | `#c4b0ff` on `#251d3d` |
| `hot` (lead score) | `#b4410a`, bar `#e8590c` | `#ffad7a`, bar `#f07a35` |
| `person-1` … `person-6` (avatars) | slate-teal, violet, rust, green, blue, slate | lighter tints |
| `highlight` (focus ring, today ring) | `#c8641a` | `#f59a4a` |

WCAG contrast (light): `brand` on white 6.55, `on-brand` on `brand` 6.55, `brand-ink` on
`brand-soft` 5.74, `ink-gray-6` on white 5.97 and on the canvas 5.51, `danger` on
`danger-soft` 5.76, `warning` on `warning-soft` 5.81, `success` on `success-soft` 5.75,
`info` on `info-soft` 6.39, `violet` on `violet-soft` 7.01, the person colours on their
soft fills 6.47–8.35, the rail icons 6.96. Every text pair passes 4.5:1; the highlight
ring passes 3:1 (3.97 on white, 3.66 on the canvas).

### The owner's exception: the Leads redesign everywhere (2026-11-14)

The owner asked for the mockup's look on every page and chose the mockup over the colour
rules above where the two disagreed. What that allows, and nothing beyond it:

- **Stat cards** (`StatTile`): the label top left, the icon on a soft 28 px square at the
  right (`iconTone` picks the tone, so a stat may carry a pastel tile), a 22 px bold value
  and a 12 px line under it.
- **Stage pills** (`stagePillClass` in `pages/leads/leads.ts`): one tone per stage, as the
  mockup draws them — blue new, amber contacted, green meetings and won, violet proposal,
  gray lost; a dot or icon and the stage's name always beside the colour.
- **People** (`PersonAvatar`): initials on one of six person colours, picked by a hash of
  the name so a person keeps theirs everywhere; leads and companies are neutral gray.
- **Page views** (`ViewTabs`): pills in one white strip, the current one filled near-black
  (`surface-gray-10`) with its count. Small in-card toggles stay frappe-ui `TabButtons`,
  now the mockup's segmented look (the checked option white on a light track).
- **Bulk selection**: a near-black bar across the table with outlined white buttons.

### Page recipe (every page)

- **Type**: a compact scale (`desk/tailwind.config.js`): every frappe-ui size is about 1 px
  smaller than stock (`text-base` 13 px, `text-sm` 12.5 px, `text-xs` 11.5 px, `text-lg`
  15 px) with no added letter-spacing, the weighted variants included. Arbitrary sizes in
  templates stay at 12–14 px for body text.

- **Header**: `LayoutHeader` with `title` (22 px bold) and a one-sentence `subtitle`; its
  actions are `size="md"` buttons, refresh as an icon button first, the solid primary last.
  Pages with breadcrumbs keep the `left-header` slot.
- **Body**: `flex flex-col gap-4 px-4 pb-8 pt-4 md:px-8` on the canvas, full width. Reading
  and form pages (an article, a settings form, a single document) keep a max width.
- **Cards**: `rounded-xl border border-outline-gray-2 bg-surface-base`, `p-4` inside; a
  card's heading is `text-base font-semibold text-ink-gray-9`. `theme.css` gives every card
  a soft two-layer shadow (none in dark mode), and a card that is a link or button lifts
  1 px with a deeper shadow on hover.
- **Stat rows**: `grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4` of `StatTile`s
  (13 px label, a 28 px icon square, a 22 px figure).
- **Tables** sit in a card: filters in a `border-b px-4 py-4` bar (inputs `size="md"`,
  search first and widest), then the table — headings
  `h-11 bg-surface-gray-1 text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6`,
  rows `border-b border-outline-gray-1 hover:bg-surface-gray-1` at 56–64 px, cells `px-3`
  with `pl-4` at the edges — then a `border-t px-4 py-3.5` footer ("Showing 1–20 of 386"
  and Previous / Next). The row's main action is a 36 px `brand-soft` icon button; the
  rest sit in an ellipsis menu.
- **Lists that aren't tables**: a card with `divide-y divide-outline-gray-1` rows, `px-4
  py-3`.
- **Empty, error and loading** states sit inside the card they replace (`TaskyState`
  with `py-10`; skeletons in `bg-surface-gray-3`).
- **Fields** are white with a slate border and 10 px corners; focus is the brand border
  with a soft brand ring (`theme.css` restyles frappe-ui's subtle inputs). Secondary
  buttons are white and outlined.
- **Menu**: the dark 64 px rail, then the white panel — the workspace name, search, the
  groups under 11 px uppercase headings, 36 px rows (the current one `brand-soft`), counts
  as brand pills, and the "Needs your attention" card at the foot.

### The owner's exception: soft status circles (2026-10-10)

The owner asked for the Scoreboard mockup's feel across the app, so a soft tinted circle
behind an icon is allowed **only where the colour carries meaning**. The reason: a status
read at a glance (done, overdue, time) helps people scan a row of numbers, while colour that
means nothing is noise. The mapping is fixed:

| Meaning | Tone |
| --- | --- |
| Done, completed, published | `success` |
| Overdue, risk, missed, failed | `danger` |
| Time, hours, dates coming up | `info` |
| On-time rate | `onTimeTone`: success at 95% and up, warning from 80%, danger below; a date, not an outcome, is `info` |

- `StatTile` draws the circle from `iconTone` (`TONE_CLASSES` in `tone.ts`). Without a
  meaning the circle stays neutral gray, never a pastel.
- **Brand fill** is for the current selection: the active segmented control option
  (frappe-ui `TabButtons`, themed in `theme.css`) and the selected rail area (`brand` fill,
  `on-brand` icon). The current panel item is tinted `brand-soft` with `brand-ink` text.
- **The sidebar rail** is dark in both themes with neutral icons; only the selected area is
  filled in `brand`. There are no tinted icon tiles; the old per-group tones are gone.
- **Champion gold** (`champion`, `champion-soft`, `champion-border`) is only for the
  Scoreboard's champion card, with a trophy and a badge: it marks an award, not a status.
- Everything else stays neutral: decorative and section
  icons, and tiles whose number isn't a status. Still no gradients, rainbow cards or
  decorative colour, and every tone keeps an icon or text next to it.

### The owner's exception: the Daily report is colourful (2026-10-26)

The owner asked for the Leads **Daily report** tab to be colourful, so its sections each
carry a tone, **on that screen only**. The reason: the report is read top to bottom by
sales managers, and a tone per section tells the parts apart at a glance. The mapping is
fixed and uses the existing tokens, never a new colour:

| Section | Tone |
| --- | --- |
| Daily call performance | `info` |
| Positive leads | `success` |
| New quotations | `warning` |
| New leads generated | `brand` |
| This week vs target | neutral frame; each ring is `success` at or above pace, `warning` behind it |

- Each section is a card with a 4 px left border in its tone, a soft tinted heading strip
  and a heading icon in the tone; the big figures stay `font-mono tabular-nums` in
  neutral ink (the team table tints its columns the same way).
- A target behind pace is `warning` with its words ("Behind by 4 meetings"), **never
  `danger`**: it isn't a failure to shame. Every tone has its icon or words beside it.
- No gradients, no tone outside the table above, and the rest of the app is unchanged.

### The owner's exception: the CRM dashboards are colourful (2026-11-13)

The owner asked for the CRM dashboards page to be colourful, so each metric carries a tone
**on that screen only** ([crm-dashboard.md](crm-dashboard.md)). The reason: the page is
scanned for a dozen figures at once, and a tone per kind of figure tells won from lost from
money still to win at a glance. The mapping is fixed, uses the existing tokens, and lives in
one place (`METRIC_LOOK` in `desk/src/pages/crm-dashboard/crmDashboard.ts`):

| Metric | Tone (icon circle, chart card heading) | Chart series |
| --- | --- | --- |
| Total leads, open leads | `brand` (leads, as on the Daily report) | slot 0 (blue) |
| Won, converted, won sales value, average deal value | `success` | slot 2 (green) |
| Lost leads | `danger` | slot 1 (orange) |
| Expected revenue, pending sales value | `warning` | slot 3 (amber) |
| Conversion rate, closing time | `info` | slot 4 (pink), always alone in its chart |

- The three headline KPI cards are filled with their tone's soft colour (`StatTile`'s `tint`),
  the icon on the solid tone, and a mini trend in the tone's colour; every other KPI card is a
  compact `StatTile` with a 4 px left edge and its icon in the tone. Values stay neutral ink.
  The page sits on the gray canvas like every page, the filters are a light bar of
  outlined selects with no box around them, and a chart card is a section as on the Daily
  report: a 4 px left border, a soft heading strip and the heading icon in the tone of the
  chart's metric.
- **Series colours come from `chartTheme`'s validated palette, never the status tones:** the
  status tones failed the colour-vision checks as series (red beside green and amber). Each
  metric keeps its slot from chart to chart; two series whose slots don't pass together in
  both themes (orange with amber, green with pink) fall back to blue and orange. Bars carry
  their value at the end and lines their last figure, because the lighter slots sit below 3:1
  on white. A table's columns carry a dot of their metric's colour beside the name.
- A card's change against the period before is `success` when it is good news, `warning`
  when it isn't, never `danger` (as on the Daily report, a slower stretch is not a failure),
  and neutral for figures where neither is (open leads, pending value); it always reads in
  words with its arrow.
- Every tone has its icon and words beside it. No gradients (a line's area wash is one flat
  colour), and the rest of the app is unchanged.

## 9. Components

Reusable, composable, predictable, accessible and responsive, without over-abstracting.
Reuse when repetition is real; abstract only when it improves clarity.

## 10. Forms

- **Labels:** visible and above the field, with useful help text. A placeholder is never
  the only label.
- **Validation and errors:** predictable validation. Errors say what happened and how to fix
  it, and are announced to screen readers.
- **Submit buttons:**
  - prevent double submits and show a loading state with a stable width;
  - recover after a failure;
  - use outcome labels: "Create task", "Save changes", "Delete project", not
    "Submit / Confirm / Yes".

## 11. Feedback and system status

- **Loading:** nothing for instant operations; skeletons when the layout is known; inline
  spinners for short waits; progress bars for long ones. No needless full-page spinners.
- **Optimistic UI:** only for low-risk changes. Never for money, irreversible or critical
  operations.
- **Errors:** every recoverable error offers a way forward: Retry, Fix, Undo, an alternative,
  or contacting support. No dead ends.

## 12. Empty states

- Tell apart first use, no results, filtered to zero, error, and offline.
- Say what's happening, why, and the one next step.

## 13. Navigation

- The sidebar is a rail (areas) plus a panel (that area's pages, grouped under small
  uppercase headings, sub-items as a tree with a guide line and dots). Neutral icons; brand
  only for the selected area and the current page (`aria-current`).
- The panel never collapses by itself: only its own button closes it, the choice is
  remembered per person, and it defaults to open. Below 1024px (a tablet) it defaults to
  folded to icons, since open it leaves the page too narrow; the person's own choice still
  wins. Expanded groups stay expanded. Only the mobile drawer closes after a page is picked.
- Keep every control reachable by keyboard with a visible `ring-highlight` focus ring,
  `aria-expanded` on folding items and `aria-current` on the current page.
- On mobile, primary destinations must stay reachable.
- The command palette must never be the only way to get somewhere.
- Keep meaningful state in the URL: tab, filters, search and page.

## 14. Tables and dense data

Built for scanning:
- right-aligned tabular numbers;
- sticky headers where useful;
- predictable row heights;
- visible sorting and selection;
- meaningful empty states.

On mobile, turn rows into cards or two-line rows that show the fields that matter. Don't
just shrink the table.

## 15. Destructive actions

- **Undo is better than a confirmation** where it's safe.
- **Irreversible actions:** add friction in proportion to the risk; name the action
  explicitly, and for the worst cases ask the user to type to confirm.
- **Placement:** never put a destructive action where the primary action usually sits.

## 16. Accessibility (non-negotiable)

- Full keyboard use, with visible `focus-visible` rings.
- Semantic HTML before ARIA, in a correct DOM order.
- Accessible names and screen-reader announcements.
- Accessible contrast and touch targets of at least 44px.
- Never remove an outline without an equivalent.

## 17. Responsive

- Design for mobile, tablet, desktop and large screens.
- Re-think navigation, hierarchy, tables, actions, forms and dialogs at each size; don't
  just scale down.
- Hover must never be required.
- No horizontal page scroll: use `min-w-0` on flex and grid children.

## 18. Dark mode

- Near-black backgrounds, surfaces that get lighter as they rise, readable text tiers,
  subtle borders, and adjusted brand colours.
- Never just invert. Check each component.

## 19. Motion

- Short, purposeful motion that explains cause and effect.
- Animate `transform` and `opacity`, not layout.
- Respect `prefers-reduced-motion`.
- Productivity screens should feel fast, not playful.

## 20. Human-designed feel

- Before building, settle the audience, the feeling (for TBO: calm, precise, professional)
  and a reference product (e.g. Linear, Height, Attio).
- Use real domain content: customers, tickets, tasks, SLA. Never Lorem ipsum, "John Doe" or
  invented statistics.
- Ask: "Could this screen belong to any product?" If yes, make more product-specific
  decisions.

## 21. Copy

Write like a person, and be specific. Avoid "Operation failed", "Invalid input", "An error
occurred" and "Supercharge your workflow". Every important message says what happened and
what to do next.

## 22. CSS engineering

- Use `min-width: 0` on flex and grid children, and deliberate overflow.
- Keep a defined z-index layering; no `z-index: 9999`.
- Use responsive containers and handle text wrapping.

## 23. Performance

Avoid:
- needless re-renders and requests;
- huge dependencies;
- oversized assets;
- layout thrashing;
- animating everything.

Virtualise only genuinely large lists, and prefer what the platform already provides.

## 24. Security in the UI

- Never expose secrets, tokens, private data or records the user may not see.
- Frontend permission checks are only for UX; the backend decides.

## 25. Severity when auditing

- **P0, blocks shipping:**
  - a broken primary flow, data loss or a security issue;
  - an inaccessible critical flow;
  - a broken build or a severe regression.
- **P1, should fix:**
  - a major UX or accessibility problem;
  - duplicate architecture or an unnecessary dependency;
  - a significant responsive bug.
- **P2, polish:** spacing, micro-interactions, copy, alignment.

## 26. Final report (PR description or agent report)

- **Changed:** what was implemented.
- **Reused:** components, patterns and tokens used.
- **Removed:** dead code, files, duplicate logic and dependencies.
- **Dependencies:** what was added, or "None."
- **Verification:** Build / Typecheck / Lint / Tests, each PASS or NOT RUN. Never PASS
  unless it was run.
- **Audit:** the remaining P0, P1 and P2 issues, or "No known P0/P1/P2 issues found."

**Goal:** beautiful, usable, accessible, responsive, fast, reusable, maintainable and
production-safe.
