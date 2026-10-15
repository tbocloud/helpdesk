import { useNow } from "@vueuse/core";
import { dayjs } from "frappe-ui";
import { computed } from "vue";

/**
 * Today's date as "YYYY-MM-DD", kept current: a page left open overnight or over a weekend
 * moves on to the new day instead of keeping the day it was opened.
 */
export function useToday() {
  const now = useNow({ interval: 60_000 });
  return computed(() => dayjs(now.value).format("YYYY-MM-DD"));
}
