import type { Router } from "vue-router";

/**
 * Pages scroll in their own box, not the window, so vue-router's scrollBehavior can't
 * put them back. This keeps, per history entry, which box was scrolled and how far, and
 * on Back/Forward scrolls it there again once the page's data has drawn enough to.
 * Spec: docs/ui-guidelines.md §13, "Back on every page".
 */
type Spot = { path: number[]; top: number };

const spots = new Map<number, Spot>();
let popped = false;
let lastEntry: number | undefined;
let restoring: AbortController | null = null;

/** vue-router's index of the current history entry */
const currentEntry = (): number | undefined => window.history.state?.position;

const appRoot = () => document.getElementById("app");

/** a page's own scroll box, not a dropdown's list or a table's sideways scroll */
const isPageBox = (el: Element) => el.clientHeight > window.innerHeight / 2;

/** child indexes from #app down to `el`; the page draws the same tree when it's back */
function pathTo(el: Element): number[] | null {
  const root = appRoot();
  const path: number[] = [];
  let node: Element = el;
  while (node !== root) {
    const parent = node.parentElement;
    if (!parent) return null;
    path.unshift(Array.prototype.indexOf.call(parent.children, node));
    node = parent;
  }
  return path;
}

function find(path: number[]): Element | null {
  let node: Element | null = appRoot();
  for (const i of path) node = node?.children[i] ?? null;
  return node;
}

function restore(spot: Spot) {
  restoring?.abort();
  const ctrl = new AbortController();
  restoring = ctrl;
  // the person scrolling or typing first wins
  for (const type of ["wheel", "touchstart", "keydown", "pointerdown"])
    window.addEventListener(type, () => ctrl.abort(), {
      capture: true,
      passive: true,
      signal: ctrl.signal,
    });
  // the page's data loads after it mounts; keep trying until it's tall enough
  const until = performance.now() + 4000;
  const tick = () => {
    if (ctrl.signal.aborted) return;
    const el = find(spot.path);
    if (el && isPageBox(el)) {
      el.scrollTop = spot.top;
      if (Math.abs(el.scrollTop - spot.top) < 2) return ctrl.abort();
    }
    if (performance.now() < until) requestAnimationFrame(tick);
    else ctrl.abort();
  };
  requestAnimationFrame(tick);
}

export function rememberScroll(router: Router) {
  document.addEventListener(
    "scroll",
    (event) => {
      const el = event.target;
      const entry = currentEntry();
      if (!(el instanceof Element) || entry === undefined || !isPageBox(el))
        return;
      const path = pathTo(el);
      if (path) spots.set(entry, { path, top: el.scrollTop });
    },
    { capture: true, passive: true }
  );
  window.addEventListener("popstate", () => (popped = true));

  router.afterEach((_to, _from, failure) => {
    const wasPop = popped;
    popped = false;
    const entry = currentEntry();
    if (failure || entry === undefined) return;
    if (wasPop) {
      const spot = spots.get(entry);
      if (spot) restore({ ...spot });
    } else if (entry !== lastEntry) {
      // a new page in the place of one left behind by Back: it starts at the top
      restoring?.abort();
      spots.delete(entry);
    }
    lastEntry = entry;
  });
}
