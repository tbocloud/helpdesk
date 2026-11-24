import { useAuthStore } from "@/stores/auth";
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { periodRange } from "./divisions";

/** The overview's and the reports' division and period, kept in the URL so a view can
 * be shared and survives a reload. With no division in the URL they open on the active
 * division (the sidebar switcher's); an empty one means every division the person may
 * see (the server decides which). */
export function useDivisionFilters() {
  const route = useRoute();
  const router = useRouter();
  const auth = useAuthStore();

  function setQuery(values: Record<string, string>) {
    router.replace({ query: { ...route.query, ...values } });
  }

  const division = computed({
    get: () =>
      route.query.division === undefined
        ? auth.overviewDivision || ""
        : String(route.query.division || ""),
    set: (value: string) => setQuery({ division: value }),
  });
  const period = computed({
    get: () => String(route.query.period || "this_year"),
    set: (value: string) => setQuery({ period: value }),
  });
  const custom = computed({
    get: () => ({
      from: String(route.query.from || ""),
      to: String(route.query.to || ""),
    }),
    set: (value: { from: string; to: string }) =>
      setQuery({ from: value.from, to: value.to }),
  });
  const range = computed(() => periodRange(period.value, custom.value));
  const params = computed(() => ({
    division: division.value || null,
    ...(range.value || {}),
  }));

  return { division, period, custom, range, params };
}
