import { useRouter, type RouteLocationRaw } from "vue-router";

/**
 * Back to the page the person came from (a filtered list, a tab, a page of results),
 * as the browser's Back would. vue-router keeps the previous in-app address in
 * history.state.back; with none (a page opened directly, a new tab) there is no
 * previous page here, so it goes to `fallback`.
 */
export function useGoBack(fallback: RouteLocationRaw) {
  const router = useRouter();
  const fallbackHref = router.resolve(fallback).href;

  function goBack(event?: MouseEvent) {
    // a modified click opens the fallback link in a new tab, as any link would
    if (event && (event.metaKey || event.ctrlKey || event.shiftKey)) return;
    event?.preventDefault();
    if (window.history.state?.back) router.back();
    else router.push(fallback);
  }

  return { goBack, fallbackHref };
}
