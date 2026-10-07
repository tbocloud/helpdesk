# Engineering guardrails: zero mess policy

The owner's standing rule for every change in this repo, by a person or an AI agent.
`AGENTS.md` points here; CodeRabbit reviews against it.

Your job is not only to make the requested change work. Keep the whole codebase clean,
reusable, maintainable, minimal, consistent, production-safe, and free of duplication and
technical debt.

**Golden rule: SEARCH → UNDERSTAND → REUSE → MODIFY → CLEAN UP → VERIFY.**
Never CREATE → DUPLICATE → PATCH → LEAVE MESS.

## 1. Search before you create

Before creating any component, page, function, hook, composable, utility, service, API
client, type, schema, constant, style, package or configuration, search the repository for
something that already exists and can be reused, extended or refactored. Never create a
duplicate because it is faster.

## 2. No duplicate components

- Check shared components (`desk/src/components/`), feature folders, composables and utils.
- Reuse when possible. When an existing component is close, extend it with props or variants
  instead of creating a second version.
- Never copy a component into a new file and tweak it. Keep one canonical implementation per
  concept: one `Button` with variants, not `PrimaryButton`, `ActionButton` and `SubmitButton`.

## 3. No dead code

After every change remove:
- unused imports, variables, functions, composables and components;
- obsolete files, unreachable code, commented-out old code, debug logs and temporary code;
- obsolete configuration and API endpoints no longer called.

Git is the history; don't keep code "just in case".

## 4. No unused dependencies

Before adding a package:
- check whether the project, Frappe or frappe-ui already provides it, or whether a small
  internal utility is enough;
- weigh its size, dependency tree, maintenance, security and licence;
- never add a large package for a trivial feature.

When a feature is removed, remove its dependencies, imports and configuration too, and keep
the lockfile correct.

## 5. Follow the existing architecture

Use the existing patterns, and don't introduce a competing one without a strong reason:
- frappe-ui components and `createResource`;
- Pinia stores;
- the API layout in `helpdesk/api/` and `helpdesk/tasky/`;
- folder and naming conventions;
- error handling;
- the TBO theme tokens.

Consistency beats personal preference.

## 6. Minimal change

Make the smallest clean change that solves the problem. Don't:
- rewrite or refactor unrelated files;
- rename things without a reason;
- add layers or abstractions you don't need.

Do clean up duplication or dead code that the change itself exposes.

## 7. Single source of truth

One canonical home for each constant, type, validation, business rule, API call and piece of
configuration. Reuse when repetition is real; abstract when it improves clarity; don't
abstract only to save lines.

## 8. Before modifying a file

Know what it does, who imports it, what it imports, whether it is shared and what else a
change affects. Never edit blindly based on a file name.

## 9. Cleanup pass after every change

Check before calling a change done:
- **Components:** none duplicated, and none that should have been reused.
- **Code:** no unused imports, variables or functions, no dead code, and no debug or
  temporary code left.
- **Dependencies:** nothing unnecessary added, nothing left unused, and no two libraries
  doing the same job.
- **Architecture:** no competing pattern, no needless abstraction, and no duplicated
  business logic.
- **Files:** no unnecessary new files, and obsolete ones deleted.
- **Types:** no duplicate or inconsistent types for the same concept.

## 10. Never hide technical debt

- Debt directly related to the change: fix it when it's safe.
- Unrelated debt: don't refactor it; mention it in the PR description.

## 11. Production quality check

Before saying "done", run whatever applies:
- `vite build` (CI does **not** build the frontend);
- pre-commit (black, flake8, prettier, isort);
- semgrep with the frappe rules;
- the backend tests, which run in CI.

No new warnings and no leftovers. If a check couldn't run, say so. Never claim a check passed
that you didn't run.

## 12. When an existing component isn't perfect

Work down this order and stop at the first that works:
1. Reuse it as it is.
2. Configure it with props.
3. Extend it safely.
4. Make a small refactor so it fits.
5. Only then create a new component, and justify it.

## 13. New dependency justification

In the PR, state:
- why existing code can't do it;
- why the package is needed;
- whether a smaller alternative exists;
- whether it duplicates an existing dependency (if so, don't add it).

## 14. Don't copy-paste

If you're copying more than a few lines, stop and make the original reusable: a component,
composable, function, service or shared config.

## 15. Optimise for the codebase, not the error

Don't aim to make the current error disappear. Aim to solve the problem while keeping the
codebase healthy. A fix that adds duplication, dead code, extra dependencies or inconsistent
architecture is not a successful fix.

## 16. Report format (PR description or agent report)

- **Changed:** what was implemented.
- **Reused:** existing components, functions and services used.
- **Removed:** dead code, obsolete files, imports and dependencies.
- **Added dependencies:** or "None."
- **Verification:** Build / Typecheck / Lint / Tests, each PASS or NOT RUN. Never PASS unless
  it was run.
- **Technical debt:** known issues that remain.
