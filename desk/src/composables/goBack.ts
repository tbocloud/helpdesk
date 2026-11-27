import { onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter, type RouteLocationRaw } from "vue-router";

/**
 * How many components on screen draw their own Back button. The app header's Back
 * (HeaderBack) stays out while any do, so a page never shows two.
 */
export const ownBackButtons = ref(0);

/** Call from a component that draws its own Back button. */
export function useOwnBackButton() {
  onMounted(() => ownBackButtons.value++);
  onBeforeUnmount(() => ownBackButtons.value--);
}

/**
 * Back to the page the person came from (a filtered list, a tab, a page of results),
 * as the browser's Back would. vue-router keeps the previous in-app address in
 * history.state.back; with none (a page opened directly, a new tab) there is no
 * previous page here, so it goes to `fallback`.
 */
export function useGoBack(fallback: RouteLocationRaw) {
  const router = useRouter();
  const fallbackHref = router.resolve(fallback).href;
  useOwnBackButton();

  function goBack(event?: MouseEvent) {
    // a modified click opens the fallback link in a new tab, as any link would
    if (event && (event.metaKey || event.ctrlKey || event.shiftKey)) return;
    event?.preventDefault();
    if (window.history.state?.back) router.back();
    else router.push(fallback);
  }

  return { goBack, fallbackHref };
}
