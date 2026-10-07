import { __ } from "@/translation";
import { watchDebounced } from "@vueuse/core";
import { createResource } from "frappe-ui";
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

/** The sorts helpdesk.api.directory accepts. */
export const DIRECTORY_SORTS = [
  { value: "name", label: __("Name") },
  { value: "newest", label: __("Newest first") },
] as const;
type Sort = (typeof DIRECTORY_SORTS)[number]["value"];
const DEFAULT_SORT: Sort = "name";

/** "1 open ticket" / "3 open tickets", for the two-line rows on small screens. */
export function openTicketsLabel(count: number) {
  return count === 1
    ? __("1 open ticket")
    : __("{0} open tickets", String(count));
}

interface DirectoryPage<T> {
  rows: T[];
  has_more: boolean;
  total: number;
}

/**
 * One of the directory lists (helpdesk.api.directory): search and sort kept in
 * the URL as `q` and `sort`, and "Show more" adding the next page.
 */
export function useDirectory<T extends { name: string }>(url: string) {
  const route = useRoute();
  const router = useRouter();

  const queryValue = (key: string) =>
    typeof route.query[key] === "string" ? (route.query[key] as string) : "";

  const search = ref(queryValue("q"));
  const sort = ref<Sort>(
    DIRECTORY_SORTS.find((s) => s.value === queryValue("sort"))?.value ??
      DEFAULT_SORT
  );
  const rows = ref<T[]>([]) as { value: T[] };
  const total = ref<number>();
  const hasMore = ref(false);
  // the offset of the page being asked for: 0 starts over, otherwise it appends
  let start = 0;

  const resource = createResource({
    url,
    method: "GET",
    makeParams: () => ({
      search: search.value.trim(),
      sort: sort.value,
      start,
    }),
    onSuccess(data: DirectoryPage<T>) {
      rows.value = start ? [...rows.value, ...data.rows] : data.rows;
      total.value = data.total;
      hasMore.value = data.has_more;
    },
  });

  function reload() {
    start = 0;
    resource.reload();
  }

  function more() {
    start = rows.value.length;
    resource.reload();
  }

  watchDebounced(
    [search, sort],
    () => {
      router.replace({
        query: {
          ...route.query,
          q: search.value.trim() || undefined,
          sort: sort.value === DEFAULT_SORT ? undefined : sort.value,
        },
      });
      reload();
    },
    { debounce: 300 }
  );

  reload();

  return {
    search,
    sort,
    rows,
    total,
    hasMore,
    loading: computed(() => resource.loading as boolean),
    error: computed(() => resource.error),
    searching: computed(() => !!search.value.trim()),
    reload,
    more,
  };
}
