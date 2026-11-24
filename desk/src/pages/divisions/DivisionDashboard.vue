<template>
  <div class="flex h-full flex-col">
    <LayoutHeader
      :title="card?.division_name || division"
      :subtitle="
        card
          ? [card.country, card.currency].filter(Boolean).join(' · ')
          : __('Division dashboard')
      "
    >
      <template #right-header>
        <Button
          size="md"
          :label="__('All divisions')"
          :route="{ name: 'DivisionsHome', query: periodQuery }"
        >
          <template #prefix>
            <LucideArrowLeft class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          size="md"
          :aria-label="__('Refresh')"
          :loading="dash.loading"
          @click="dash.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          size="md"
          :label="__('Lead status')"
          :route="{
            name: 'DivisionLeads',
            query: { ...periodQuery, division },
          }"
        >
          <template #prefix>
            <LucideChartPie class="size-[18px]" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <DivisionFilters
          :division="division"
          v-model:period="period"
          v-model:custom="custom"
          :options="dash.data?.options || []"
          :loading="dash.loading"
          @update:division="openDivision"
        />

        <TaskyState
          v-if="dash.error && !dash.data"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          error
          :icon="noAccess ? LucideLock : LucideCircleAlert"
          :title="
            noAccess
              ? __('This division isn\'t yours to see')
              : __('Couldn\'t load the division')
          "
          :message="
            noAccess
              ? __(
                  'Its dashboard is for Super Admins and its managers. Ask a Super Admin if you need it.'
                )
              : errorText(dash.error, __('Try again in a minute.'))
          "
        >
          <Button
            :label="noAccess ? __('Back to divisions') : __('Try again')"
            @click="
              noAccess
                ? router.push({ name: 'DivisionsHome' })
                : dash.reload()
            "
          />
        </TaskyState>

        <TaskyState
          v-else-if="!range"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          :icon="LucideCalendarRange"
          :title="__('Pick both dates')"
          :message="__('Choose a from and a to date to see that period.')"
        />

        <div
          v-else-if="!dash.data"
          class="flex flex-col gap-4"
          aria-busy="true"
          :aria-label="__('Loading')"
        >
          <div class="h-16 animate-pulse rounded-xl bg-surface-gray-3" />
          <div
            class="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-4"
          >
            <div
              v-for="i in 6"
              :key="i"
              class="h-[104px] animate-pulse rounded-xl bg-surface-gray-3"
            />
          </div>
          <div class="h-72 animate-pulse rounded-xl bg-surface-gray-3" />
        </div>

        <template v-else-if="card && data">
          <!-- who runs it and how its ERP site stands -->
          <section
            :aria-label="__('Profile')"
            class="flex flex-wrap gap-x-6 gap-y-2 rounded-xl border border-outline-gray-2 bg-surface-base px-5 py-3.5 text-p-sm text-ink-gray-7"
            :class="dash.loading ? 'opacity-60' : ''"
          >
            <span
              v-for="fact in facts"
              :key="fact.key"
              class="flex min-w-0 items-center gap-2"
              :class="fact.ink"
            >
              <component
                :is="fact.icon"
                class="size-4 shrink-0"
                :class="fact.ink || 'text-ink-gray-6'"
                aria-hidden="true"
              />
              <a
                v-if="fact.href"
                :href="fact.href"
                target="_blank"
                rel="noopener"
                class="truncate text-brand-ink underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              >
                {{ fact.text }}
              </a>
              <span v-else class="truncate">{{ fact.text }}</span>
            </span>
          </section>

          <section
            :aria-label="__('Key figures')"
            class="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-4"
            :class="dash.loading ? 'opacity-60' : ''"
          >
            <StatTile
              v-for="kpi in kpis"
              :key="kpi.key"
              :label="kpi.label"
              :value="kpi.value"
              :sub="kpi.sub"
              :icon="kpi.icon"
              :icon-tone="kpi.tone"
            />
          </section>

          <div
            class="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]"
            :class="dash.loading ? 'opacity-60' : ''"
          >
            <!-- leads by status -->
            <section
              class="flex flex-col rounded-xl border border-outline-gray-2 bg-surface-base"
              aria-labelledby="division-leads"
            >
              <header
                class="flex items-baseline justify-between gap-2 border-b border-outline-gray-2 px-5 py-4"
              >
                <h2
                  id="division-leads"
                  class="text-base font-semibold text-ink-gray-9"
                >
                  {{ __("Leads by status") }}
                </h2>
                <RouterLink
                  :to="{
                    name: 'DivisionLeads',
                    query: { ...periodQuery, division },
                  }"
                  class="rounded text-sm text-brand-ink underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                >
                  {{ __("All lead status") }}
                </RouterLink>
              </header>
              <p
                v-if="!card.site"
                class="px-5 py-10 text-center text-p-sm text-ink-gray-6"
              >
                {{
                  __(
                    "No ERP site yet, so no leads. A Super Admin sets it in Settings → Divisions."
                  )
                }}
              </p>
              <p
                v-else-if="!leadTotal"
                class="px-5 py-10 text-center text-p-sm text-ink-gray-6"
              >
                {{ __("No leads in this period.") }}
              </p>
              <div v-else class="flex flex-col gap-4 px-5 py-4">
                <!-- the groups as one bar, each named below with its count -->
                <div
                  class="flex h-3 overflow-hidden rounded-full bg-surface-gray-3"
                  aria-hidden="true"
                >
                  <div
                    v-for="g in groups"
                    :key="g.group"
                    :class="GROUP_LOOK[g.group].dot"
                    :style="{ width: `${g.share}%` }"
                  />
                </div>
                <ul class="flex flex-wrap gap-x-4 gap-y-1.5 text-p-sm">
                  <li
                    v-for="g in groups"
                    :key="g.group"
                    class="flex items-center gap-1.5 text-ink-gray-7"
                  >
                    <GroupLabel :group="g.group" />
                    <span class="font-mono tabular-nums text-ink-gray-9">
                      {{ count(g.count) }}
                    </span>
                    <span class="text-ink-gray-6">({{ g.share }}%)</span>
                  </li>
                </ul>
                <ol class="flex flex-col">
                  <li
                    v-for="s in topStatuses"
                    :key="s.status"
                    class="flex items-center gap-3 border-t border-outline-gray-1 py-2 text-sm"
                  >
                    <span
                      class="size-2 shrink-0 rounded-full"
                      :class="GROUP_LOOK[s.group].dot"
                      aria-hidden="true"
                    />
                    <span class="min-w-0 flex-1 truncate text-ink-gray-8">
                      {{ s.status }}
                      <span class="sr-only">
                        ({{ GROUP_LOOK[s.group].label }})
                      </span>
                    </span>
                    <span
                      class="font-mono tabular-nums text-ink-gray-9"
                    >
                      {{ count(s.total) }}
                    </span>
                  </li>
                </ol>
                <p
                  v-if="data.statuses.length > TOP"
                  class="text-p-xs text-ink-gray-6"
                >
                  {{
                    __(
                      "And {0} more statuses on the Lead status page.",
                      String(data.statuses.length - TOP)
                    )
                  }}
                </p>
              </div>
            </section>

            <!-- people -->
            <section
              class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
              aria-labelledby="division-people"
            >
              <h2
                id="division-people"
                class="border-b border-outline-gray-2 px-5 py-4 text-base font-semibold text-ink-gray-9"
              >
                {{ __("People") }}
              </h2>
              <p
                v-if="!data.people.length"
                class="px-5 py-10 text-center text-p-sm text-ink-gray-6"
              >
                {{ __("No one is in this division yet.") }}
              </p>
              <div v-else class="overflow-x-auto">
                <table class="w-full text-sm">
                  <thead>
                    <tr :class="HEAD_ROW">
                      <th scope="col" class="pl-5 pr-3 text-left">
                        {{ __("Person") }}
                      </th>
                      <th
                        v-for="c in PEOPLE_COLUMNS"
                        :key="c.key"
                        scope="col"
                        class="whitespace-nowrap px-3 text-right last:pr-5"
                      >
                        {{ c.label }}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="p in data.people"
                      :key="p.user"
                      class="h-14 border-b border-outline-gray-1 last:border-0 hover:bg-surface-gray-1"
                    >
                      <th scope="row" class="pl-5 pr-3 text-left">
                        <span class="flex items-center gap-2.5">
                          <PersonAvatar :name="p.full_name" size="sm" />
                          <span class="min-w-0">
                            <span
                              class="block truncate font-medium text-ink-gray-9"
                            >
                              {{ p.full_name }}
                            </span>
                            <span
                              class="block truncate text-p-xs font-normal text-ink-gray-6"
                            >
                              {{ p.role }}
                            </span>
                          </span>
                        </span>
                      </th>
                      <td
                        v-for="c in PEOPLE_COLUMNS"
                        :key="c.key"
                        class="whitespace-nowrap px-3 text-right font-mono tabular-nums last:pr-5"
                        :class="
                          c.key === 'overdue' && p.overdue
                            ? 'text-danger'
                            : 'text-ink-gray-8'
                        "
                      >
                        {{ c.value(p) }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <div
            class="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]"
            :class="dash.loading ? 'opacity-60' : ''"
          >
            <!-- live projects -->
            <section
              class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
              aria-labelledby="division-projects"
            >
              <h2
                id="division-projects"
                class="border-b border-outline-gray-2 px-5 py-4 text-base font-semibold text-ink-gray-9"
              >
                {{ __("Open and on-hold projects") }}
              </h2>
              <p
                v-if="!data.projects.length"
                class="px-5 py-10 text-center text-p-sm text-ink-gray-6"
              >
                {{
                  __(
                    "No open projects in this division. Projects join it in Settings → Divisions."
                  )
                }}
              </p>
              <ul v-else>
                <li
                  v-for="project in data.projects"
                  :key="project.name"
                  class="border-b border-outline-gray-1 last:border-0"
                >
                  <RouterLink
                    :to="{
                      name: 'TaskyProject',
                      params: { projectId: project.name },
                    }"
                    class="flex items-center gap-3 px-5 py-3 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight"
                  >
                    <span class="min-w-0 flex-1">
                      <span
                        class="block truncate text-sm font-medium text-ink-gray-9"
                      >
                        {{ project.project_name }}
                      </span>
                      <span class="block truncate text-p-xs text-ink-gray-6">
                        {{
                          [
                            project.project_lead &&
                              __("Lead: {0}", project.project_lead),
                            project.expected_end_date &&
                              __(
                                "Due {0}",
                                dayjs(project.expected_end_date).format(
                                  "D MMM YYYY"
                                )
                              ),
                          ]
                            .filter(Boolean)
                            .join(" · ")
                        }}
                      </span>
                    </span>
                    <Badge
                      :label="project.status"
                      :theme="project.status === 'On hold' ? 'orange' : 'gray'"
                    />
                  </RouterLink>
                </li>
              </ul>
            </section>

            <!-- teams and departments -->
            <section
              class="flex flex-col gap-4 rounded-xl border border-outline-gray-2 bg-surface-base px-5 py-4"
              aria-labelledby="division-units"
            >
              <h2
                id="division-units"
                class="text-base font-semibold text-ink-gray-9"
              >
                {{ __("Teams and departments") }}
              </h2>
              <div v-for="unit in units" :key="unit.label">
                <h3 class="mb-2 text-xs font-medium text-ink-gray-6">
                  {{ unit.label }}
                </h3>
                <ul v-if="unit.items.length" class="flex flex-wrap gap-1.5">
                  <li
                    v-for="item in unit.items"
                    :key="item"
                    class="rounded-md bg-surface-gray-2 px-2 py-1 text-sm text-ink-gray-8"
                  >
                    {{ item }}
                  </li>
                </ul>
                <p v-else class="text-p-sm text-ink-gray-6">
                  {{ unit.empty }}
                </p>
              </div>
            </section>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import PersonAvatar from "@/components/PersonAvatar.vue";
import StatTile from "@/components/StatTile.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Badge,
  Button,
  createResource,
  dayjs,
  usePageMeta,
} from "frappe-ui";
import { computed, watch, type Component } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import LucideArrowLeft from "~icons/lucide/arrow-left";
import LucideBanknote from "~icons/lucide/banknote";
import LucideCalendarRange from "~icons/lucide/calendar-range";
import LucideChartPie from "~icons/lucide/chart-pie";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideClock from "~icons/lucide/clock";
import LucideDatabase from "~icons/lucide/database";
import LucideExternalLink from "~icons/lucide/external-link";
import LucideFolderOpen from "~icons/lucide/folder-open";
import LucideLanguages from "~icons/lucide/languages";
import LucideListTodo from "~icons/lucide/list-todo";
import LucideLock from "~icons/lucide/lock";
import LucidePercent from "~icons/lucide/percent";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideShieldUser from "~icons/lucide/shield-user";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideUsers from "~icons/lucide/users";
import DivisionFilters from "./DivisionFilters.vue";
import GroupLabel from "./LeadGroupLabel.vue";
import { formatValue } from "./chartLook";
import { OVERVIEW_API, siteHealth, type DivisionCard } from "./divisions";
import { GROUP_LOOK, type LeadGroup, type LeadStatusData } from "./leadStatus";
import { useDivisionFilters } from "./useDivisionFilters";

interface DashboardData {
  options: { name: string; division_name: string }[];
  currency: string | null;
  card: DivisionCard;
  profile: {
    status: string;
    workspace_url: string | null;
    time_zone: string | null;
    language: string | null;
    crm_source: string | null;
  };
  people: {
    user: string;
    full_name: string;
    role: string;
    done: number;
    open: number;
    overdue: number;
    hours: number;
    leads: number;
    won_leads: number;
  }[];
  teams: string[];
  departments: string[];
  projects: {
    name: string;
    project_name: string;
    status: string;
    project_lead: string | null;
    expected_end_date: string | null;
  }[];
  lead_groups: Record<LeadGroup, number>;
  statuses: LeadStatusData["statuses"];
}

const props = defineProps<{ division: string }>();

const TOP = 8;
const HEAD_ROW =
  "h-11 bg-surface-gray-1 text-xs font-semibold uppercase tracking-[0.04em] text-ink-gray-6";

const route = useRoute();
const router = useRouter();
const { period, custom, range } = useDivisionFilters();

const periodQuery = computed(() => {
  const { period: p, from, to } = route.query;
  return Object.fromEntries(
    Object.entries({ period: p, from, to }).filter(([, v]) => v)
  ) as Record<string, string>;
});

const dash = createResource<DashboardData>({
  url: `${OVERVIEW_API}.get_division_dashboard`,
  makeParams: () => ({ division: props.division, ...(range.value || {}) }),
});

watch(
  () => [props.division, range.value],
  () => {
    if (range.value) dash.reload();
  },
  { immediate: true, deep: true }
);

// "All divisions" in the picker goes back to the cards
function openDivision(value: string) {
  router.push(
    value
      ? {
          name: "DivisionDashboard",
          params: { division: value },
          query: route.query,
        }
      : { name: "DivisionsHome", query: periodQuery.value }
  );
}

const data = computed(() => dash.data as DashboardData | undefined);
const card = computed(() => data.value?.card);
const noAccess = computed(() => dash.error?.exc_type === "PermissionError");

usePageMeta(() => ({
  title: card.value?.division_name || __("Division dashboard"),
}));

const count = (v: number | null) => formatValue("count", v, null);

const facts = computed(() => {
  const c = card.value!;
  const p = data.value!.profile;
  const health = siteHealth(c.site);
  const list: {
    key: string;
    icon: Component;
    text: string;
    ink?: string;
    href?: string;
  }[] = [
    {
      key: "admins",
      icon: LucideShieldUser,
      text: c.admins.length
        ? __("Run by {0}", c.admins.join(", "))
        : __("No Division Admin yet"),
    },
    {
      key: "site",
      icon: health.tone ? LucideTriangleAlert : LucideDatabase,
      text: health.label,
      ink: health.tone ? TONE_INK[health.tone] : undefined,
    },
  ];
  if (p.time_zone) {
    list.push({ key: "tz", icon: LucideClock, text: p.time_zone });
  }
  if (p.language) {
    list.push({ key: "lang", icon: LucideLanguages, text: p.language });
  }
  if (p.workspace_url) {
    list.push({
      key: "url",
      icon: LucideExternalLink,
      text: p.workspace_url,
      href: p.workspace_url,
    });
  }
  return list;
});
// full class names, so Tailwind finds them
const TONE_INK = { danger: "text-danger", warning: "text-warning" };

const kpis = computed(() => {
  const c = card.value!;
  const tiles: {
    key: string;
    label: string;
    value: string;
    sub?: string;
    icon: Component;
    tone?: "brand" | "success" | "danger" | "info";
  }[] = [
    {
      key: "people",
      label: __("People"),
      value: count(c.people),
      sub: __("Members of the division"),
      icon: LucideUsers,
    },
    {
      key: "leads",
      label: __("Leads"),
      value: c.site ? count(c.leads) : "—",
      sub: __("Created in the period"),
      icon: LucideUsers,
      tone: "brand",
    },
    {
      key: "conversion",
      label: __("Conversion"),
      value: formatValue("percent", c.conversion_rate, null),
      sub: __("Won or converted"),
      icon: LucidePercent,
      tone: "info",
    },
    {
      key: "won_value",
      label: __("Won value"),
      value: c.site
        ? formatValue("money", c.won_value, data.value!.currency, "short")
        : "—",
      sub: __("Of won leads"),
      icon: LucideBanknote,
      tone: "success",
    },
    {
      key: "projects",
      label: __("Open projects"),
      value: count(c.active_projects),
      sub: c.on_hold_projects
        ? __("{0} on hold", count(c.on_hold_projects))
        : undefined,
      icon: LucideFolderOpen,
    },
    {
      key: "pending",
      label: __("Pending tasks"),
      value: count(c.pending_tasks),
      sub: __("{0} done in the period", count(c.done_tasks)),
      icon: LucideListTodo,
    },
    {
      key: "overdue",
      label: __("Overdue tasks"),
      value: count(c.overdue_tasks),
      icon: LucideCircleX,
      tone: c.overdue_tasks ? "danger" : undefined,
    },
  ];
  return tiles;
});

const leadTotal = computed(() =>
  Object.values(data.value?.lead_groups || {}).reduce((a, b) => a + b, 0)
);
const groups = computed(() =>
  (Object.entries(data.value?.lead_groups || {}) as [LeadGroup, number][])
    .filter(([, n]) => n)
    .map(([group, n]) => ({
      group,
      count: n,
      share: Math.round((100 * n) / (leadTotal.value || 1)),
    }))
);
const topStatuses = computed(() => (data.value?.statuses || []).slice(0, TOP));

type Person = DashboardData["people"][number];
const PEOPLE_COLUMNS: {
  key: string;
  label: string;
  value: (p: Person) => string;
}[] = [
  { key: "leads", label: __("Leads"), value: (p) => count(p.leads) },
  { key: "won", label: __("Won"), value: (p) => count(p.won_leads) },
  { key: "open", label: __("Open tasks"), value: (p) => count(p.open) },
  { key: "overdue", label: __("Overdue"), value: (p) => count(p.overdue) },
  { key: "done", label: __("Done"), value: (p) => count(p.done) },
  {
    key: "hours",
    label: __("Hours"),
    value: (p) => formatValue("count", p.hours, null),
  },
];

const units = computed(() => [
  {
    label: __("Teams"),
    items: data.value?.teams || [],
    empty: __("No teams yet. A Super Admin moves them in Settings → Divisions."),
  },
  {
    label: __("Departments"),
    items: data.value?.departments || [],
    empty: __("No departments yet."),
  },
]);
</script>
