<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">{{ __("Home") }}</div>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="home.loading"
          :aria-label="__('Refresh')"
          @click="home.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div
        class="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-5 md:px-6"
      >
        <!-- Greeting -->
        <div class="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h1 class="text-xl-semibold text-ink-gray-9">
              {{ __("Hey, {0}", userFirstName || "") }}
            </h1>
            <p class="mt-1 text-p-sm text-ink-gray-6">{{ todayLabel }}</p>
          </div>
          <router-link
            v-if="data?.company"
            :to="{ name: 'MyWork' }"
            class="rounded text-p-sm text-ink-gray-7 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          >
            {{ myWorkLabel }}
          </router-link>
        </div>

        <TaskyState
          v-if="home.error && !data"
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the dashboard')"
          :message="__('Check your connection and try again.')"
          error
        >
          <Button :label="__('Retry')" @click="home.reload()" />
        </TaskyState>

        <template v-else>
          <!-- At a glance -->
          <section :aria-label="__('At a glance')">
            <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
              <component
                :is="tile.to ? 'router-link' : 'div'"
                v-for="tile in tiles"
                :key="tile.key"
                :to="tile.to"
                class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 bg-surface-base p-4 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                :class="tile.to ? 'hover:border-outline-gray-3' : ''"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="text-sm text-ink-gray-6">{{ tile.label }}</span>
                  <component
                    :is="tile.icon"
                    class="size-4 shrink-0"
                    :class="
                      tile.alert ? TONE_TEXT[tile.tone] : 'text-ink-gray-5'
                    "
                    aria-hidden="true"
                  />
                </div>
                <span
                  v-if="home.loading && !data"
                  class="h-8 w-12 animate-pulse rounded bg-surface-gray-2"
                />
                <span
                  v-else
                  class="font-mono text-2xl-semibold tabular-nums"
                  :class="tile.alert ? TONE_TEXT[tile.tone] : 'text-ink-gray-9'"
                >
                  {{ tile.value }}
                </span>
                <span v-if="tile.hint" class="text-p-xs text-ink-gray-5">
                  {{ tile.hint }}
                </span>
              </component>
            </div>
          </section>

          <!-- Needs attention + tickets by customer -->
          <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <section
              class="rounded-lg border border-outline-gray-2 bg-surface-base lg:col-span-2"
              :aria-labelledby="`${uid}-attention`"
            >
              <header class="flex items-center justify-between gap-2 px-4 py-3">
                <h2
                  :id="`${uid}-attention`"
                  class="text-base-medium text-ink-gray-9"
                >
                  {{ data?.company ? __("Needs attention") : __("Your work") }}
                </h2>
                <router-link
                  :to="{ name: data?.company ? 'WorkOverview' : 'MyWork' }"
                  class="rounded text-p-sm text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                >
                  {{ __("See all") }}
                </router-link>
              </header>
              <ul
                v-if="attention.length"
                role="list"
                class="border-t border-outline-gray-2"
              >
                <li
                  v-for="item in attention"
                  :key="itemKey(item)"
                  class="border-b border-outline-gray-1 last:border-b-0"
                >
                  <WorkItemRow :item="item" :show-assignees="!!data?.company" />
                </li>
              </ul>
              <p
                v-else-if="data"
                class="flex items-center gap-2 border-t border-outline-gray-2 px-4 py-6 text-p-sm text-ink-gray-6"
              >
                <LucideCircleCheck
                  class="size-4 text-success"
                  aria-hidden="true"
                />
                {{
                  data.company
                    ? __("Nothing is overdue or at risk.")
                    : __("You have no open work.")
                }}
              </p>
            </section>

            <section
              v-if="data?.company"
              class="rounded-lg border border-outline-gray-2 bg-surface-base"
              :aria-labelledby="`${uid}-customers`"
            >
              <header class="flex items-center justify-between gap-2 px-4 py-3">
                <h2
                  :id="`${uid}-customers`"
                  class="text-base-medium text-ink-gray-9"
                >
                  {{ __("Open tickets by customer") }}
                </h2>
                <router-link
                  :to="{ name: 'TicketsAgent' }"
                  class="rounded text-p-sm text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                >
                  {{ __("Tickets") }}
                </router-link>
              </header>
              <ul
                v-if="tickets?.by_customer.length"
                role="list"
                class="border-t border-outline-gray-2"
              >
                <li
                  v-for="row in tickets.by_customer"
                  :key="row.customer || '-'"
                  class="flex items-center justify-between gap-3 border-b border-outline-gray-1 px-4 py-2.5 text-sm last:border-b-0"
                >
                  <router-link
                    v-if="row.customer"
                    :to="{ name: 'Customer', params: { id: row.customer } }"
                    class="truncate rounded text-ink-gray-8 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                  >
                    {{ row.customer }}
                  </router-link>
                  <span v-else class="truncate text-ink-gray-6">
                    {{ __("No customer") }}
                  </span>
                  <span class="font-mono tabular-nums text-ink-gray-8">
                    {{ row.open }}
                  </span>
                </li>
              </ul>
              <p
                v-else
                class="border-t border-outline-gray-2 px-4 py-6 text-p-sm text-ink-gray-6"
              >
                {{ __("No open tickets.") }}
              </p>
            </section>
          </div>

          <!-- Projects -->
          <section
            v-if="data?.company"
            class="rounded-lg border border-outline-gray-2 bg-surface-base"
            :aria-labelledby="`${uid}-projects`"
          >
            <header class="flex items-center justify-between gap-2 px-4 py-3">
              <h2
                :id="`${uid}-projects`"
                class="text-base-medium text-ink-gray-9"
              >
                {{ __("Projects") }}
                <span
                  class="ml-1 font-mono text-sm tabular-nums text-ink-gray-5"
                >
                  {{ data.company.project_count }}
                </span>
              </h2>
              <router-link
                :to="{ name: 'TaskyProjects' }"
                class="rounded text-p-sm text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
              >
                {{ __("See all") }}
              </router-link>
            </header>
            <ul
              v-if="data.company.projects.length"
              role="list"
              class="border-t border-outline-gray-2"
            >
              <li
                v-for="project in data.company.projects"
                :key="project.name"
                class="border-b border-outline-gray-1 last:border-b-0"
              >
                <router-link
                  :to="{
                    name: 'TaskyProject',
                    params: { projectId: project.name },
                  }"
                  class="grid grid-cols-1 items-center gap-2 px-4 py-3 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_8rem_auto]"
                >
                  <div class="min-w-0">
                    <div class="truncate text-sm text-ink-gray-9">
                      {{ project.project_name }}
                    </div>
                    <div class="truncate text-p-xs text-ink-gray-5">
                      {{
                        [
                          project.customer,
                          project.lead_name &&
                            __("Lead: {0}", project.lead_name),
                        ]
                          .filter(Boolean)
                          .join(" · ")
                      }}
                    </div>
                  </div>
                  <div class="flex items-center gap-2">
                    <div
                      class="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-gray-2"
                      role="progressbar"
                      :aria-valuenow="project.progress"
                      aria-valuemin="0"
                      aria-valuemax="100"
                      :aria-label="__('{0} done', project.project_name)"
                    >
                      <div
                        class="h-full rounded-full bg-surface-gray-7"
                        :style="{ width: `${project.progress}%` }"
                      />
                    </div>
                    <span
                      class="w-9 text-right font-mono text-xs tabular-nums text-ink-gray-6"
                    >
                      {{ project.progress }}%
                    </span>
                  </div>
                  <span class="text-p-xs text-ink-gray-6">
                    <span class="font-mono tabular-nums">{{
                      project.open
                    }}</span>
                    {{ __("open") }}
                    <template v-if="project.overdue">
                      ·
                      <span class="inline-flex items-center gap-1 text-danger">
                        <LucideTriangleAlert
                          class="size-3"
                          aria-hidden="true"
                        />
                        <span class="font-mono tabular-nums">{{
                          project.overdue
                        }}</span>
                        {{ __("overdue") }}
                      </span>
                    </template>
                  </span>
                  <span
                    class="font-mono text-xs tabular-nums text-ink-gray-6 sm:text-right"
                  >
                    {{
                      project.expected_end_date
                        ? shortDate(project.expected_end_date)
                        : "—"
                    }}
                  </span>
                </router-link>
              </li>
            </ul>
            <p
              v-else
              class="border-t border-outline-gray-2 px-4 py-6 text-p-sm text-ink-gray-6"
            >
              {{ __("No open projects.") }}
            </p>
          </section>

          <!-- Team + systems -->
          <div
            v-if="data?.company"
            class="grid grid-cols-1 gap-6 lg:grid-cols-2"
          >
            <section
              class="rounded-lg border border-outline-gray-2 bg-surface-base"
              :aria-labelledby="`${uid}-team`"
            >
              <header class="flex items-center justify-between gap-2 px-4 py-3">
                <h2
                  :id="`${uid}-team`"
                  class="text-base-medium text-ink-gray-9"
                >
                  {{ __("Team") }}
                </h2>
                <router-link
                  :to="{ name: 'TeamWorkload' }"
                  class="rounded text-p-sm text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                >
                  {{ __("See all") }}
                </router-link>
              </header>
              <ul
                v-if="data.company.people.length"
                role="list"
                class="border-t border-outline-gray-2"
              >
                <li
                  v-for="person in data.company.people"
                  :key="person.user"
                  class="flex items-center justify-between gap-3 border-b border-outline-gray-1 px-4 py-2.5 last:border-b-0"
                >
                  <div class="min-w-0">
                    <div class="truncate text-sm text-ink-gray-9">
                      {{ person.full_name }}
                    </div>
                    <div class="truncate text-p-xs text-ink-gray-5">
                      {{ person.projects.join(", ") }}
                    </div>
                  </div>
                  <span class="shrink-0 text-p-xs text-ink-gray-6">
                    <span class="font-mono tabular-nums">{{
                      person.open
                    }}</span>
                    {{ __("open") }}
                    <template v-if="person.working">
                      ·
                      <span class="font-mono tabular-nums">{{
                        person.working
                      }}</span>
                      {{ __("in progress") }}
                    </template>
                  </span>
                </li>
              </ul>
              <p
                v-else
                class="border-t border-outline-gray-2 px-4 py-6 text-p-sm text-ink-gray-6"
              >
                {{ __("Nobody has open project work.") }}
              </p>
              <p
                v-if="data.company.people_free"
                class="border-t border-outline-gray-2 px-4 py-2.5 text-p-xs text-ink-gray-6"
              >
                {{
                  __(
                    "{0} people have no open project work.",
                    String(data.company.people_free)
                  )
                }}
              </p>
            </section>

            <section
              v-if="systems"
              class="rounded-lg border border-outline-gray-2 bg-surface-base"
              :aria-labelledby="`${uid}-systems`"
            >
              <header class="px-4 py-3">
                <h2
                  :id="`${uid}-systems`"
                  class="text-base-medium text-ink-gray-9"
                >
                  {{ __("Systems") }}
                </h2>
              </header>
              <ul role="list" class="border-t border-outline-gray-2">
                <li
                  v-for="row in systemRows"
                  :key="row.key"
                  class="flex items-start justify-between gap-3 border-b border-outline-gray-1 px-4 py-2.5 last:border-b-0"
                >
                  <div class="min-w-0">
                    <div class="truncate text-sm text-ink-gray-9">
                      {{ row.label }}
                    </div>
                    <div
                      v-if="row.detail"
                      class="truncate text-p-xs text-ink-gray-5"
                      :title="row.detail"
                    >
                      {{ row.detail }}
                    </div>
                  </div>
                  <span
                    class="inline-flex shrink-0 items-center gap-1.5 rounded px-1.5 py-0.5 text-xs"
                    :class="TONE_CLASSES[row.tone]"
                  >
                    <component
                      :is="TONE_ICON[row.tone]"
                      class="size-3"
                      aria-hidden="true"
                    />
                    {{ row.status }}
                  </span>
                </li>
              </ul>
            </section>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyState from "@/pages/tasky/components/TaskyState.vue";
import { TONE_CLASSES, shortDate, type Tone } from "@/pages/tasky/taskMeta";
import WorkItemRow from "@/pages/work/components/WorkItemRow.vue";
import { itemKey, type WorkItem } from "@/pages/work/workMeta";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { Button, createResource, dayjs } from "frappe-ui";
import { storeToRefs } from "pinia";
import { computed, useId, type Component } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCircle from "~icons/lucide/circle";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleX from "~icons/lucide/circle-x";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucideInfo from "~icons/lucide/info";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideStar from "~icons/lucide/star";
import LucideTicket from "~icons/lucide/ticket";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideUserX from "~icons/lucide/user-x";

interface TicketSummary {
  open: number;
  new_today: number;
  unassigned: number;
  sla_breached: number;
  by_customer: { customer: string | null; open: number }[];
}

interface ProjectRow {
  name: string;
  project_name: string;
  customer: string | null;
  lead_name: string | null;
  progress: number;
  open: number;
  overdue: number;
  expected_end_date: string | null;
}

interface Systems {
  connections: {
    name: string;
    customer_name: string | null;
    site_url: string | null;
    connection_status: string | null;
    last_error: string | null;
  }[];
  mailboxes: {
    name: string;
    email_id: string;
    enable_incoming: number;
    no_failed: number;
  }[];
  teams: { enabled: boolean; platform: string | null };
  chat: { enabled: boolean; open: number };
  ai: { calls_today: number; triage_failed: number };
}

interface HomeData {
  mine: {
    counts: { total: number; overdue: number; key: number; at_risk: number };
    items: WorkItem[];
  };
  company: {
    tickets: TicketSummary;
    work: Record<string, number>;
    attention: WorkItem[];
    projects: ProjectRow[];
    project_count: number;
    people: {
      user: string;
      full_name: string;
      open: number;
      working: number;
      projects: string[];
    }[];
    people_free: number | null;
  } | null;
  systems: Systems | null;
}

interface Tile {
  key: string;
  label: string;
  value: number;
  icon: Component;
  tone: Tone;
  alert: boolean;
  hint?: string;
  to?: { name: string };
}

interface SystemRow {
  key: string;
  label: string;
  detail?: string;
  status: string;
  tone: Tone;
}

// full class strings so Tailwind's scanner keeps them
const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-ink-gray-7",
  info: "text-info",
  warning: "text-warning",
  success: "text-success",
  danger: "text-danger",
};

const TONE_ICON: Record<Tone, Component> = {
  neutral: LucideCircle,
  info: LucideInfo,
  warning: LucideTriangleAlert,
  success: LucideCircleCheck,
  danger: LucideCircleX,
};

const uid = useId();
const { userFirstName } = storeToRefs(useAuthStore());

const home = createResource({
  url: "helpdesk.api.home.get_home",
  auto: true,
});

const data = computed<HomeData | null>(() => home.data ?? null);
const tickets = computed(() => data.value?.company?.tickets ?? null);
const systems = computed(() => data.value?.systems ?? null);

const todayLabel = computed(() => dayjs().format("dddd, D MMMM YYYY"));

const myWorkLabel = computed(() => {
  const counts = data.value?.mine.counts;
  if (!counts?.total) return __("You have no open work");
  return counts.overdue
    ? __(
        "Your work: {0} open, {1} overdue",
        String(counts.total),
        String(counts.overdue)
      )
    : __("Your work: {0} open", String(counts.total));
});

const attention = computed<WorkItem[]>(() =>
  data.value?.company
    ? data.value.company.attention
    : data.value?.mine.items ?? []
);

const tiles = computed<Tile[]>(() => {
  const company = data.value?.company;
  if (!company) {
    const counts = data.value?.mine.counts;
    return [
      tile(
        "open",
        __("Open work"),
        counts?.total,
        LucideFolderKanban,
        "neutral",
        { name: "MyWork" }
      ),
      tile(
        "overdue",
        __("Overdue"),
        counts?.overdue,
        LucideTriangleAlert,
        "danger",
        { name: "MyWork" }
      ),
      tile(
        "at_risk",
        __("At risk"),
        counts?.at_risk,
        LucideCircleAlert,
        "warning",
        { name: "MyWork" }
      ),
      tile("key", __("Key"), counts?.key, LucideStar, "warning", {
        name: "MyWork",
      }),
    ];
  }
  const t = company.tickets;
  return [
    {
      ...tile("tickets", __("Open tickets"), t.open, LucideTicket, "neutral", {
        name: "TicketsAgent",
      }),
      hint: __("{0} new today", String(t.new_today)),
    },
    tile(
      "sla",
      __("SLA breached"),
      t.sla_breached,
      LucideAlarmClock,
      "danger",
      { name: "TicketsAgent" }
    ),
    tile(
      "unassigned",
      __("Unassigned tickets"),
      t.unassigned,
      LucideUserX,
      "warning",
      { name: "TicketsAgent" }
    ),
    tile(
      "overdue",
      __("Overdue work"),
      company.work.overdue,
      LucideTriangleAlert,
      "danger",
      { name: "WorkOverview" }
    ),
    tile(
      "at_risk",
      __("At risk"),
      company.work.at_risk,
      LucideCircleAlert,
      "warning",
      { name: "WorkOverview" }
    ),
    {
      ...tile(
        "projects",
        __("Open projects"),
        company.project_count,
        LucideFolderKanban,
        "neutral",
        { name: "TaskyProjects" }
      ),
      hint: __("{0} people busy", String(company.people.length)),
    },
  ];
});

function tile(
  key: string,
  label: string,
  value: number | undefined,
  icon: Component,
  tone: Tone,
  to?: { name: string }
): Tile {
  const count = value ?? 0;
  return {
    key,
    label,
    value: count,
    icon,
    tone,
    alert: tone !== "neutral" && count > 0,
    to,
  };
}

const systemRows = computed<SystemRow[]>(() => {
  const s = systems.value;
  if (!s) return [];
  const rows: SystemRow[] = s.connections.map((c) => ({
    key: `conn-${c.name}`,
    label: c.customer_name || c.name,
    detail:
      c.connection_status === "Connected"
        ? hostOf(c.site_url)
        : c.last_error || hostOf(c.site_url),
    status: __(c.connection_status || "Unknown"),
    tone:
      c.connection_status === "Connected"
        ? "success"
        : c.connection_status === "Error"
        ? "danger"
        : "neutral",
  }));
  for (const box of s.mailboxes) {
    rows.push({
      key: `mail-${box.name}`,
      label: box.email_id,
      detail: box.no_failed
        ? __("{0} failed attempts", String(box.no_failed))
        : __("Email to tickets"),
      status: box.enable_incoming ? __("Receiving") : __("Paused"),
      tone: box.enable_incoming
        ? box.no_failed
          ? "warning"
          : "success"
        : "warning",
    });
  }
  rows.push({
    key: "teams",
    label: __("Notifications in {0}", s.teams.platform || __("chat")),
    status: s.teams.enabled ? __("On") : __("Off"),
    tone: s.teams.enabled ? "success" : "neutral",
  });
  rows.push({
    key: "chat",
    label: __("TBO Chat"),
    detail: s.chat.enabled
      ? __("{0} open chats", String(s.chat.open))
      : undefined,
    status: s.chat.enabled ? __("On") : __("Off"),
    tone: s.chat.enabled ? "success" : "neutral",
  });
  rows.push({
    key: "ai",
    label: __("AI triage"),
    detail: __("{0} AI calls today", String(s.ai.calls_today)),
    status: s.ai.triage_failed
      ? __("{0} failed", String(s.ai.triage_failed))
      : __("OK"),
    tone: s.ai.triage_failed ? "warning" : "success",
  });
  return rows;
});

function hostOf(url: string | null) {
  if (!url) return undefined;
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}
</script>
