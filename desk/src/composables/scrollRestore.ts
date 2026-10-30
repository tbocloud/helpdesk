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

function savedAt(key: string): number | undefined {
  try {
    const stored = sessionStorage.getItem(STORE_PREFIX + key);
    if (stored !== null) return Number(stored);
  } catch {}
  return positions.get(key);
}

/**
 * Keeps a scrolling panel's position when the person leaves the page and puts it back on
 * Back. The router restores only the window's scroll, and pages scroll inside a panel.
 * A page kept alive comes back with its content, so the position is put back at once;
 * otherwise `ready` turns true once the content is in, so it lands on the full list.
 * `onReturn` runs when a kept-alive page shows again, with whether it's Back to the same
 * entry (`false`: a fresh visit, e.g. from the sidebar).
 */
export function useScrollRestore(
  panel: Ref<HTMLElement | null | undefined>,
  ready: Ref<boolean>,
  onReturn?: (back: boolean) => void
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
    onReturn?.(top !== undefined);
    await nextTick();
    if (panel.value) panel.value.scrollTop = top ?? 0;
  });
}
