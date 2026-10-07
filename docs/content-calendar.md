# Content calendar

The content calendar (`/helpdesk/content`, route `ContentCalendar`) is where the content team
plans, staffs and ships social posts (`HD Content Post`) for customers.

- Page: `desk/src/pages/content/ContentCalendar.vue`, with its views and dialogs in
  `desk/src/pages/content/components/` and shared types and rules in
  `desk/src/pages/content/constants.ts`.
- Data: posts come from `frappe.client.get_list` on `HD Content Post`, so everyone only sees
  posts they can read. The team on each card comes from
  `helpdesk.api.content_board.get_team_task_status`, occasions from
  `helpdesk.api.content_board.get_occasions`. Every number on the page is worked out in the
  browser from the posts loaded for the period and filters on screen; there is no separate
  stats call.

## Filters and navigation

The filter bar (customer, channel, status, person, **My posts**, Clear) applies to every view.
Cancelled posts are hidden unless the status filter asks for them; the Board and Sheet views
load them and show them behind their own chip.

Board and Sheet have a **Day / Week / Month** period switch, Today, previous/next (← / →, T for
today) and a date picker. The Calendar view has its own navigation.

## Views

| View | What it is |
| --- | --- |
| **Board** (default) | Stat tiles, a progress bar and a day-grouped list of entry cards for the period. Follows the owner's mockup in the TBO light theme. |
| **Calendar** | frappe-ui month/week calendar. Drag a post to reschedule it; click an empty cell to add an entry. |
| **Sheet** | A table of the period's posts. |

The chosen view and period are remembered per browser.

## Board view

`desk/src/pages/content/components/ContentBoard.vue`.

### Occasions strip

Above the board (Board and Sheet): festivals and national days in the period, from
`HD Content Occasion` for the regions in the customer's package. Each chip shows the date and
name; clicking it opens Add entry on that date.

### Stat tiles

| Tile | Value | Line below | Tint |
| --- | --- | --- | --- |
| Month progress (Day/Week progress) | Published ÷ planned, as % and a ring. Planned = posts in the period that aren't cancelled. | "X of Y published" | Neutral; the ring is green (success). |
| On-time rate | Published on or before their planned day ÷ published. "—" when nothing is published. | "X of Y on the planned day" | Same thresholds as the delivery report: green ≥ 95%, amber ≥ 80%, red below, neutral when nothing is published. |
| Postponed | Posts in the period postponed at least once (`times_postponed > 0`). | "this month", plus "N moves" when some were postponed more than once. | Amber when above 0, otherwise neutral. |
| Next post | Date and time of the next post that isn't published or cancelled and hasn't passed yet. | Title · platforms | Info (blue) when there is one, neutral otherwise. |

A post postponed out of the period counts in the period it now sits in.

### Progress bar and chips

A segmented bar (no gradient) with a legend: **Published on time** (green), **Published late**
(amber, published after the planned day, the same rule as the delivery report), **Missed**
(red, past its time and not published or cancelled), **Upcoming** (blue). Cancelled posts are
left out. Segments with nothing in them are hidden.

The chips below filter the list: All, Missed, Upcoming, Published, Cancelled, each with its
count; empty ones are hidden unless selected. A red banner offers "Show them" when posts are
missed.

### Entry cards

Grouped by day (day number, weekday, number of entries that day), sorted by time.

- **Header:** title (opens the post), format · customer (customer hidden when the customer
  filter is set), and on the right the platforms (brand mark + name, from
  `ChannelIcon.vue`, coloured with the `--channel-*` tokens), time and the status pill.
- **Warning line** "Goes live within 2 days and isn't approved yet." when the post isn't
  Approved/Scheduled/Published and goes live within 48 hours.
- **Post content** and **Brief** side by side ("Not written yet" / "No brief yet" when empty).
- **Roles:** Writer, Designer, Video editor, Digital marketer. Each assigned person shows with
  their task status (and "late" when the task is past due); an empty role shows an amber
  **+ Assign** chip. Either opens the assign dialog.
- **Footer:** "Goes live …" (or the published / missed / cancelled line), then **Mark
  published** (green), **Postpone**, and a cancel icon button, all through
  `EntryActionDialog.vue`. Published posts link to the live post instead.

Card tints carry meaning:

| Tint | When |
| --- | --- |
| Red (danger) | Missed, or going live within 2 days without approval |
| Green (success) | Published |
| Neutral gray | Cancelled |
| Blue (info) | Anything else still upcoming |

## Colour rules

From `desk/src/theme.css`: the brand violet is only for the primary action (Add entry), the
selected view/period/chip and today's date. Status colours appear only where they mean
something and always with a label or icon. Numbers, dates and times use Geist Mono with
tabular figures.
