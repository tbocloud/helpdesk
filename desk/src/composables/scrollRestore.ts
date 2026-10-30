import { nextTick, onActivated, watch, type Ref } from "vue";
import { onBeforeRouteLeave, useRoute } from "vue-router";

// per history entry (its position and path): Back to that entry restores, a fresh visit to
// the same page is a new entry and starts at the top. In this tab's sessionStorage, so a
// reload keeps them like the history itself; in memory too, for when storage is blocked
const STORE_PREFIX = "hd-scroll:";
const positions = new Map<string, number>();

function entryKey(path: string) {
  return `${window.history.state?.position ?? ""}:${path}`;
}

function keep(key: string, top: number) {
  positions.set(key, top);
  try {
    sessionStorage.setItem(STORE_PREFIX + key, String(top));
  } catch {}
}

// memory first: it has the latest save even when storage refused it; storage after a reload
function savedAt(key: string): number | undefined {
  if (positions.has(key)) return positions.get(key);
  try {
    const stored = sessionStorage.getItem(STORE_PREFIX + key);
    if (stored !== null) return Number(stored);
  } catch {}
  return undefined;
}

/** Whether the person moves the panel themselves from now on (a scroll event can't tell). */
function watchForMoves(el: HTMLElement) {
  let moved = false;
  const events = ["wheel", "touchstart", "keydown", "pointerdown"];
  const mark = () => (moved = true);
  events.forEach((e) => el.addEventListener(e, mark, { passive: true }));
  return {
    moved: () => moved,
    stop: () => events.forEach((e) => el.removeEventListener(e, mark)),
  };
}

/**
 * Keeps a scrolling panel's position when the person leaves the page and puts it back on
 * Back. The router restores only the window's scroll, and pages scroll inside a panel.
 * A page kept alive comes back with its content, so the position is put back at once;
 * otherwise `ready` turns true once the content is in, so it lands on the full list.
 * `onReturn` runs when a kept-alive page shows again, with whether it's Back to the same
 * entry (`false`: a fresh visit, e.g. from the sidebar); the promise it may return is its
 * refresh, after which the position is put back again.
 */
export function useScrollRestore(
  panel: Ref<HTMLElement | null | undefined>,
  ready: Ref<boolean>,
  onReturn?: (back: boolean) => Promise<unknown> | void
) {
  const route = useRoute();

  // the path as it is on leaving: filters kept in the query change it in place
  onBeforeRouteLeave((_to, from) => {
    if (panel.value) keep(entryKey(from.fullPath), panel.value.scrollTop);
  });

  // only coming back to an entry: a fresh visit can reuse a history position that an
  // earlier entry, now gone, had saved under, but has no page ahead of it
  function saved() {
    if (!window.history.state?.forward) return undefined;
    return savedAt(entryKey(route.fullPath));
  }

  let restored = false;
  watch(
    ready,
    async (isReady) => {
      if (!isReady || restored) return;
      restored = true;
      const top = saved();
      if (top === undefined) return;
      await nextTick();
      if (panel.value) panel.value.scrollTop = top;
    },
    { immediate: true }
  );

  // also called on the first mount, which the watch above covers
  let mounted = false;
  onActivated(async () => {
    if (!mounted) {
      mounted = true;
      return;
    }
    const top = saved();
    const refreshed = onReturn?.(top !== undefined);
    await nextTick();
    if (!panel.value) return;
    panel.value.scrollTop = top ?? 0;
    if (top === undefined || !refreshed) return;
    // the refresh can change the content's height: the place again once it's in, unless
    // the person has moved on by then
    const moves = watchForMoves(panel.value);
    await refreshed;
    await nextTick();
    moves.stop();
    // left again meanwhile: the panel is off the page, and the next Back restores it
    if (!moves.moved() && panel.value?.isConnected) panel.value.scrollTop = top;
  });
}
