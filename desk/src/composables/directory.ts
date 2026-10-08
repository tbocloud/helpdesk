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

interface DirectoryRequest {
  /** bumps with every request; only the latest one's answer is used */
  id: number;
  search: string;
  sort: Sort;
  start: number;
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
  const loading = ref(false);
  const error = ref<unknown>(null);

  const resource = createResource({ url, method: "GET" });
  // only the latest request may touch the list: a slow "Show more" for the old
  // search must not append to (or replace) the results of the new one
  let generation = 0;
  let current: DirectoryRequest | null = null;

  /** Asks for the page at `start`: 0 starts over, anything else appends. */
  function fetchPage(start: number) {
    const request: DirectoryRequest = {
      id: ++generation,
      search: search.value.trim(),
      sort: sort.value,
      start,
    };
    current = request;
    loading.value = true;
    error.value = null;
    const isCurrent = () =>
      current === request &&
      request.id === generation &&
      request.search === search.value.trim() &&
      request.sort === sort.value;

    resource
      .fetch(
        { search: request.search, sort: request.sort, start: request.start },
        {
          onSuccess(data: DirectoryPage<T>) {
            if (!isCurrent()) return;
            rows.value = request.start
              ? [...rows.value, ...data.rows]
              : data.rows;
            total.value = data.total;
            hasMore.value = data.has_more;
          },
          onError(err: unknown) {
            if (isCurrent()) error.value = err;
          },
        }
      )
      .finally(() => {
        if (current === request) loading.value = false;
      });
  }

  function reload() {
    fetchPage(0);
  }

  function more() {
    fetchPage(rows.value.length);
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
    loading,
    error,
    searching: computed(() => !!search.value.trim()),
    reload,
    more,
  };
}
