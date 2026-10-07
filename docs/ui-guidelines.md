# UI guidelines: deliberate, human-designed interfaces

The owner's standing rule for every screen in the helpdesk app (`desk/`). Read it together
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
- charts (`desk/src/pages/performance/chartTheme.ts`).

## 3. Zero duplication, zero dead code, zero needless dependencies

These follow [engineering-guardrails.md](engineering-guardrails.md). If several versions of
one concept exist, pick the canonical one and consolidate when it's safe.

## 4. Design system first

Use the TBO theme:
- **Colours:** v2 tokens `bg-surface-*`, `text-ink-*`, `border-outline-*`; `brand` for the
  one accent; `success`, `warning`, `danger` and `info` (plus their soft variants) for
  meaning.
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
- **Red** only for errors, destructive actions and overdue work. **Green** only for success
  and done.
- **Never colour alone:** always pair colour with an icon, text or shape. Keep contrast
  accessible.
- **Avoid:** purple-to-blue gradients, gradient text, decorative blobs, **pastel icon tiles**
  (a soft-coloured square behind every icon), rainbow stat cards and colour used as
  decoration.

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

- Keep the sidebar hierarchy clear and its sections meaningful.
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
