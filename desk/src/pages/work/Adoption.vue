<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="__('Adoption')"
      :subtitle="__('Who is using the system, and what is stuck.')"
    >
      <template #right-header>
        <Button
          size="md"
          :loading="adoption.loading && !!adoption.data"
          :aria-label="__('Refresh')"
          @click="refresh"
        >
          <template #icon>
            <LucideRefreshCw class="size-[18px]" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="relative flex-1 overflow-auto">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <ViewTabs
          v-model="period"
          class="hidden self-start sm:inline-flex"
          :aria-label="__('Period')"
          :options="PERIODS.map((p) => ({ label: p.label, value: p.key }))"
        />
        <FormControl
          v-model="period"
          class="sm:hidden"
          type="select"
          :label="__('Period')"
          :options="PERIODS.map((p) => ({ label: p.label, value: p.key }))"
        />

        <div
          v-if="adoption.error && !adoption.data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base"
        >
          <TaskyState
            class="py-10"
            :icon="LucideCircleAlert"
            :title="__('Couldn\'t load Adoption')"
            :message="
              errorText(
                adoption.error,
                __('Check your connection and try again.')
              )
            "
            error
          >
            <Button :label="__('Retry')" @click="adoption.reload()" />
          </TaskyState>
        </div>

        <div v-else-if="!data" class="flex flex-col gap-3" aria-busy="true">
          <span class="sr-only">{{ __("Loading") }}</span>
          <span
            v-for="i in 4"
            :key="i"
            class="h-14 animate-pulse rounded-xl bg-surface-gray-3"
          />
        </div>

        <template v-else>
          <p
            class="text-[14px] font-medium text-ink-gray-9"
            :aria-busy="adoption.loading"
            aria-live="polite"
          >
            {{ summary }}
          </p>

          <div
            v-if="!(data.counts.attention || data.counts.watch)"
            class="rounded-xl border border-outline-gray-2 bg-surface-base"
          >
            <TaskyState
              class="py-10"
              :icon="LucideCircleCheck"
              :title="EVERYONE_USING[data.period]"
              :message="__('Nothing needs a manager\'s attention right now.')"
            />
          </div>

          <section
            v-for="group in groups"
            :key="group.key"
            :aria-labelledby="`${uid}-${group.key}`"
          >
            <h2
              :id="`${uid}-${group.key}`"
              class="flex items-center gap-2 text-base font-semibold"
              :class="INK[group.tone]"
            >
              <component :is="group.icon" class="size-4" aria-hidden="true" />
              {{ group.label }}
              <span class="font-mono tabular-nums text-ink-gray-5">
                {{ group.items.length }}
              </span>
            </h2>
            <ul
              role="list"
              class="mt-3 divide-y divide-outline-gray-1 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
            >
              <li v-for="f in group.items" :key="f.id">
                <button
                  type="button"
                  class="flex min-h-11 w-full items-start gap-3 px-4 py-3 text-left hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight"
                  :aria-expanded="open.has(f.id)"
                  :aria-controls="`${uid}-${f.id}`"
                  @click="toggle(f.id)"
                >
                  <component
                    :is="group.icon"
                    class="mt-0.5 size-4 shrink-0"
                    :class="INK[group.tone]"
                    aria-hidden="true"
                  />
                  <span class="min-w-0 flex-1">
                    <span class="block text-[13px] font-medium text-ink-gray-9">
                      {{ f.title }}
                    </span>
                    <span class="mt-0.5 block text-p-sm text-ink-gray-6">
                      {{ f.action_hint }}
                    </span>
                  </span>
                  <TaskyBadge
                    class="mt-0.5 hidden sm:inline-flex"
                    :label="AREA_LABELS[f.area]"
                  />
                  <LucideChevronDown
                    class="mt-0.5 size-4 shrink-0 text-ink-gray-5 transition-transform"
                    :class="open.has(f.id) ? 'rotate-180' : ''"
                    aria-hidden="true"
                  />
                </button>
                <div
                  v-if="open.has(f.id)"
                  :id="`${uid}-${f.id}`"
                  class="flex flex-col gap-3 border-t border-outline-gray-1 bg-surface-gray-1 px-4 py-3 pl-12"
                >
                  <p class="text-p-sm text-ink-gray-7">{{ f.detail }}</p>
                  <div v-if="f.who.length">
                    <p class="text-xs text-ink-gray-5">{{ __("Who") }}</p>
                    <ul role="list" class="mt-1 flex flex-wrap gap-1.5">
                      <li v-for="p in f.who" :key="p.user">
                        <TaskyBadge :label="p.name" />
                      </li>
                    </ul>
                  </div>
                  <div>
                    <Button
                      :route="f.link"
                      :label="LINK_LABELS[f.link] || __('Open')"
                    >
                      <template #suffix>
                        <LucideArrowRight class="size-4" aria-hidden="true" />
                      </template>
                    </Button>
                  </div>
                </div>
              </li>
            </ul>
          </section>

          <p v-if="!data.sales_available" class="text-p-sm text-ink-gray-6">
            {{
              __(
                "Sales results are not shown: the sales system isn't connected right now."
              )
            }}
          </p>

          <SectionCard
            class="overflow-hidden"
            :title="__('People')"
            :description="
              __(
                'Everyone with an active account. People who did nothing in the system are listed first.'
              )
            "
            :count="rows.length"
          >
            <table class="hidden w-full text-sm md:table">
              <caption class="sr-only">
                {{
                  __("What each person did in the system")
                }}
              </caption>
              <thead>
                <tr
                  class="h-11 border-b border-outline-gray-2 bg-surface-gray-1 text-left text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6"
                >
                  <th
                    v-for="col in COLUMNS"
                    :key="col.key"
                    scope="col"
                    class="px-3 first:pl-4 last:pr-4 md:first:pl-4 md:last:pr-5"
                    :class="col.key === 'name' ? '' : 'text-right'"
                    :aria-sort="ariaSort(col.key)"
                  >
                    <button
                      type="button"
                      class="inline-flex items-center gap-1 rounded hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                      @click="sortBy(col.key)"
                    >
                      {{ col.label }}
                      <component
                        :is="sortIcon(col.key)"
                        class="size-3.5"
                        aria-hidden="true"
                      />
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="p in rows"
                  :key="p.user"
                  class="border-b border-outline-gray-1 last:border-b-0 hover:bg-surface-gray-1"
                >
                  <th
                    scope="row"
                    class="px-3 py-3 pl-4 text-left font-normal md:pl-4"
                  >
                    <span class="flex flex-wrap items-center gap-2">
                      <PersonAvatar :name="p.name" size="md" />
                      <span class="font-medium text-ink-gray-9">{{
                        p.name
                      }}</span>
                      <TaskyBadge
                        v-if="p.quiet"
                        tone="warning"
                        :icon="LucideMoon"
                        :label="__('Quiet')"
                      />
                      <TaskyBadge
                        v-else-if="p.on_leave"
                        :icon="LucidePlane"
                        :label="__('On leave')"
                      />
                    </span>
                  </th>
                  <td class="px-3 py-3 text-right font-mono tabular-nums">
                    {{ p.tasks_done }}
                  </td>
                  <td class="px-3 py-3 text-right font-mono tabular-nums">
                    {{ p.hours }}
                  </td>
                  <td class="px-3 py-3 text-right font-mono tabular-nums">
                    {{ p.standups_written }}
                  </td>
                  <td class="px-3 py-3 text-right font-mono tabular-nums">
                    {{ p.calls ?? "–" }}
                  </td>
                  <td class="px-3 py-3 text-right font-mono tabular-nums">
                    {{ p.outcomes ?? "–" }}
                  </td>
                  <td
                    class="px-3 py-3 pr-4 text-right tabular-nums text-ink-gray-7 md:pr-4"
                  >
                    {{ lastSeen(p) }}
                  </td>
                </tr>
              </tbody>
            </table>

            <ul role="list" class="md:hidden">
              <li
                v-for="p in rows"
                :key="p.user"
                class="flex flex-col gap-1 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
              >
                <span class="flex flex-wrap items-center gap-2">
                  <PersonAvatar :name="p.name" size="md" />
                  <span class="text-sm font-medium text-ink-gray-9">{{
                    p.name
                  }}</span>
                  <TaskyBadge
                    v-if="p.quiet"
                    tone="warning"
                    :icon="LucideMoon"
                    :label="__('Quiet')"
                  />
                  <TaskyBadge
                    v-else-if="p.on_leave"
                    :icon="LucidePlane"
                    :label="__('On leave')"
                  />
                </span>
                <span class="text-p-sm tabular-nums text-ink-gray-6">
                  {{ personLine(p) }}
                </span>
              </li>
            </ul>
          </SectionCard>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import PersonAvatar from "@/components/PersonAvatar.vue";
import SectionCard from "@/components/SectionCard.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import ViewTabs from "@/components/ViewTabs.vue";
import { INK } from "@/components/tone";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, dayjs, FormControl } from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideArrowDown from "~icons/lucide/arrow-down";
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideArrowUp from "~icons/lucide/arrow-up";
import LucideArrowUpDown from "~icons/lucide/arrow-up-down";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideMoon from "~icons/lucide/moon";
import LucidePlane from "~icons/lucide/plane";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import {
  AREA_LABELS,
  EVERYONE_USING,
  LINK_LABELS,
  PERIODS,
  SEVERITIES,
  type AdoptionReport,
  type Period,
  type PersonRow,
} from "./adoptionMeta";

type SortKey =
  | "name"
  | "tasks_done"
  | "hours"
  | "standups_written"
  | "calls"
  | "outcomes"
  | "last_activity";

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "name", label: __("Person") },
  { key: "tasks_done", label: __("Tasks done") },
  { key: "hours", label: __("Timer hours") },
  { key: "standups_written", label: __("Stand-ups written") },
  { key: "calls", label: __("Calls") },
  { key: "outcomes", label: __("Call results") },
  { key: "last_activity", label: __("Last active") },
];

const route = useRoute();
const router = useRouter();
const uid = useId();

const keys = PERIODS.map((p) => p.key);
const queried = route.query.period;
const period = ref<Period>(
  typeof queried === "string" && keys.includes(queried as Period)
    ? (queried as Period)
    : "this_week"
);

const adoption = createResource({
  url: "helpdesk.api.adoption.get_adoption",
  makeParams: () => ({ period: period.value }),
  auto: true,
});

watch(period, () => {
  router.replace({ query: { ...route.query, period: period.value } });
  adoption.reload();
});

function refresh() {
  adoption.submit({ period: period.value, fresh: 1 });
}

const data = computed<AdoptionReport | null>(() => adoption.data ?? null);

const groups = computed(() =>
  SEVERITIES.map((s) => ({
    ...s,
    items: (data.value?.findings ?? []).filter((f) => f.severity === s.key),
  })).filter((g) => g.items.length)
);

const summary = computed(() => {
  const counts = data.value?.counts ?? {};
  const parts = [];
  if (counts.attention) parts.push(__("{0} need attention", counts.attention));
  if (counts.watch) parts.push(__("{0} worth watching", counts.watch));
  return parts.length ? parts.join(", ") : __("All clear");
});

const open = reactive(new Set<string>());
function toggle(id: string) {
  if (!open.delete(id)) open.add(id);
}

const sort = ref<{ key: SortKey | null; desc: boolean }>({
  key: null,
  desc: false,
});

function sortBy(key: SortKey) {
  sort.value =
    sort.value.key === key
      ? { key, desc: !sort.value.desc }
      : { key, desc: key !== "name" };
}

function ariaSort(key: SortKey) {
  if (sort.value.key !== key) return "none";
  return sort.value.desc ? "descending" : "ascending";
}

function sortIcon(key: SortKey) {
  if (sort.value.key !== key) return LucideArrowUpDown;
  return sort.value.desc ? LucideArrowDown : LucideArrowUp;
}

// unsorted, the server's order: quiet people first, then by name
const rows = computed<PersonRow[]>(() => {
  const people = [...(data.value?.people ?? [])];
  const { key, desc } = sort.value;
  if (!key) return people;
  const value = (p: PersonRow) => p[key] ?? (desc ? -1 : "");
  return people.sort((a, b) => {
    const [x, y] = [value(a), value(b)];
    const order =
      typeof x === "string" && typeof y === "string"
        ? x.localeCompare(y)
        : Number(x) - Number(y);
    return desc ? -order : order;
  });
});

function lastSeen(p: PersonRow) {
  return p.last_activity
    ? dayjs(p.last_activity).format("D MMM")
    : __("Not in 90 days");
}

function personLine(p: PersonRow) {
  const parts = [
    __("{0} tasks done", p.tasks_done),
    __("{0} h on timers", p.hours),
    __("{0} stand-ups written", p.standups_written),
  ];
  if (p.is_sales)
    parts.push(__("{0} calls, {1} results", p.calls ?? 0, p.outcomes ?? 0));
  parts.push(__("Last active: {0}", lastSeen(p)));
  return parts.join(" · ");
}
</script>
