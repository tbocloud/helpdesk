import { __ } from "@/translation";
import { watchDebounced } from "@vueuse/core";
import { createResource } from "frappe-ui";
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

interface SortOption {
  value: string;
  label: string;
}

/** The sorts helpdesk.api.directory accepts. */
export const DIRECTORY_SORTS: readonly SortOption[] = [
  { value: "name", label: __("Name") },
  { value: "newest", label: __("Newest first") },
];
/** Customers can also be sorted by health, at risk first. */
export const CUSTOMER_SORTS: readonly SortOption[] = [
  ...DIRECTORY_SORTS,
  { value: "health", label: __("Health, worst first") },
];
const DEFAULT_SORT = "name";

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
  sort: string;
  filter: string;
  start: number;
}

interface DirectoryPage<T> {
  rows: T[];
  has_more: boolean;
  total: number;
}

interface DirectoryOptions {
  /** the sorts this list offers; DIRECTORY_SORTS by default */
  sorts?: readonly SortOption[];
  /** one more filter, kept in the URL and sent to the API under this name */
  filterKey?: string;
}

/**
 * One of the directory lists (helpdesk.api.directory): search, sort and the
 * optional filter kept in the URL as `q`, `sort` and `filterKey`, and "Show
 * more" adding the next page.
 */
export function useDirectory<T extends { name: string }>(
  url: string,
  options: DirectoryOptions = {}
) {
  const sorts = options.sorts ?? DIRECTORY_SORTS;
  const filterKey = options.filterKey;
  const route = useRoute();
  const router = useRouter();

  const queryValue = (key: string) =>
    typeof route.query[key] === "string" ? (route.query[key] as string) : "";

  const search = ref(queryValue("q"));
  const sort = ref<string>(
    sorts.find((s) => s.value === queryValue("sort"))?.value ?? DEFAULT_SORT
  );
  const filter = ref(filterKey ? queryValue(filterKey) : "");
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
      filter: filter.value,
      start,
    };
    current = request;
    loading.value = true;
    error.value = null;
    const isCurrent = () =>
      current === request &&
      request.id === generation &&
      request.search === search.value.trim() &&
      request.sort === sort.value &&
      request.filter === filter.value;

    resource
      .fetch(
        {
          search: request.search,
          sort: request.sort,
          start: request.start,
          ...(filterKey ? { [filterKey]: request.filter } : {}),
        },
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
    [search, sort, filter],
    () => {
      router.replace({
        query: {
          ...route.query,
          q: search.value.trim() || undefined,
          sort: sort.value === DEFAULT_SORT ? undefined : sort.value,
          ...(filterKey ? { [filterKey]: filter.value || undefined } : {}),
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
    filter,
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
