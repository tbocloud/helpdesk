<template>
  <aside class="flex flex-col gap-4" :aria-label="__('Figures')">
    <div
      v-if="!tickets && !tasks && !projects.length"
      class="rounded-lg border border-outline-gray-2 bg-surface-base p-4 text-p-sm text-ink-gray-5"
    >
      {{ __("No figures were saved with this summary.") }}
    </div>

    <section
      v-for="group in tileGroups"
      :key="group.key"
      class="rounded-lg border border-outline-gray-2 bg-surface-base p-4"
      :aria-labelledby="`summary-stats-${group.key}`"
    >
      <h2
        :id="`summary-stats-${group.key}`"
        class="mb-3 flex items-center gap-1.5 text-sm-medium text-ink-gray-8"
      >
        <component
          :is="group.icon"
          class="size-3.5 text-ink-gray-5"
          aria-hidden="true"
        />
        {{ group.title }}
      </h2>
      <dl class="grid grid-cols-2 gap-2">
        <div
          v-for="tile in group.tiles"
          :key="tile.label"
          class="flex flex-col gap-0.5 rounded-md px-2.5 py-2"
          :class="tile.alert ? tile.alert.bg : 'bg-surface-gray-1'"
        >
          <dt
            class="flex items-center gap-1 text-xs"
            :class="tile.alert ? tile.alert.text : 'text-ink-gray-6'"
          >
            <component
              :is="tile.alert.icon"
              v-if="tile.alert"
              class="size-3 shrink-0"
              aria-hidden="true"
            />
            {{ tile.label }}
          </dt>
          <dd
            class="font-mono text-lg tabular-nums"
            :class="tile.alert ? tile.alert.text : 'text-ink-gray-9'"
          >
            {{ tile.value }}
          </dd>
        </div>
      </dl>
    </section>

    <section
      v-for="list in taskLists"
      :key="list.key"
      class="rounded-lg border border-outline-gray-2 bg-surface-base p-4"
      :aria-labelledby="`summary-stats-${list.key}`"
    >
      <h2
        :id="`summary-stats-${list.key}`"
        class="mb-2 flex items-center gap-1.5 text-sm-medium text-ink-gray-8"
      >
        <component
          :is="list.icon"
          class="size-3.5 text-ink-gray-5"
          aria-hidden="true"
        />
        {{ list.title }}
        <span class="ml-auto font-mono text-xs tabular-nums text-ink-gray-5">
          {{ list.total }}
        </span>
      </h2>
      <p v-if="!list.items.length" class="text-p-sm text-ink-gray-5">
        {{ list.empty }}
      </p>
      <ul v-else role="list" class="flex flex-col">
        <li
          v-for="(task, i) in list.items"
          :key="i"
          class="flex items-start gap-2 border-b border-outline-gray-1 py-2 last:border-b-0 last:pb-0"
        >
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-1 text-sm text-ink-gray-8">
              <LucideStar
                v-if="task.is_key && list.key !== 'key'"
                class="size-3 shrink-0 text-ink-gray-6"
                :aria-label="__('Key task')"
              />
              <span class="truncate" :title="task.subject">
                {{ task.subject }}
              </span>
            </div>
            <div class="truncate text-xs text-ink-gray-5">
              {{ task.project }}
            </div>
          </div>
          <span
            v-if="task.due"
            class="shrink-0 font-mono text-xs tabular-nums text-ink-gray-6"
          >
            {{ formatDay(task.due) }}
          </span>
        </li>
      </ul>
      <p
        v-if="list.total > list.items.length"
        class="mt-2 text-xs text-ink-gray-5"
      >
        {{
          __(
            "Showing {0} of {1}",
            String(list.items.length),
            String(list.total)
          )
        }}
      </p>
    </section>

    <section
      v-if="projects.length"
      class="rounded-lg border border-outline-gray-2 bg-surface-base p-4"
      aria-labelledby="summary-stats-projects"
    >
      <h2
        id="summary-stats-projects"
        class="mb-3 flex items-center gap-1.5 text-sm-medium text-ink-gray-8"
      >
        <LucideFolderKanban
          class="size-3.5 text-ink-gray-5"
          aria-hidden="true"
        />
        {{ __("Projects") }}
      </h2>
      <ul role="list" class="flex flex-col gap-3">
        <li v-for="project in projects" :key="project.project">
          <div class="flex items-baseline justify-between gap-2">
            <span class="truncate text-sm text-ink-gray-8">
              {{ project.project }}
            </span>
            <span
              class="shrink-0 font-mono text-xs tabular-nums text-ink-gray-6"
            >
              {{ project.completed }}/{{ project.tasks }}
            </span>
          </div>
          <div class="mt-1.5 flex items-center gap-2">
            <div
              class="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-gray-2"
              role="progressbar"
              :aria-valuenow="project.progress"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-label="
                __(
                  '{0}: {1} of {2} tasks completed',
                  project.project,
                  String(project.completed),
                  String(project.tasks)
                )
              "
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
          <div
            v-if="project.status !== 'Open'"
            class="mt-1 text-xs text-ink-gray-5"
          >
            {{ __(project.status) }}
          </div>
        </li>
      </ul>
    </section>

    <p v-if="stats?.as_of" class="text-xs text-ink-gray-5">
      {{ __("Figures as of") }}
      <span class="font-mono tabular-nums">{{ formatDay(stats.as_of) }}</span>
    </p>
  </aside>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { computed, type Component } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucideListChecks from "~icons/lucide/list-checks";
import LucidePause from "~icons/lucide/pause";
import LucideShieldAlert from "~icons/lucide/shield-alert";
import LucideStar from "~icons/lucide/star";
import LucideTicket from "~icons/lucide/ticket";
import {
  formatDay,
  type SummaryProject,
  type SummaryStats,
  type SummaryTask,
} from "../summaryMeta";

const props = defineProps<{ stats: SummaryStats | null | undefined }>();

interface Alert {
  icon: Component;
  bg: string;
  text: string;
}

interface Tile {
  label: string;
  value: number;
  alert?: Alert;
}

// full class strings so Tailwind's scanner picks them up
const DANGER = { bg: "bg-danger-soft", text: "text-danger" };
const WARNING = { bg: "bg-warning-soft", text: "text-warning" };

const tickets = computed(() => props.stats?.tickets);
const tasks = computed(() => props.stats?.tasks);
const projects = computed<SummaryProject[]>(() => props.stats?.projects ?? []);

function alertIf(count: number, alert: Alert): Alert | undefined {
  return count > 0 ? alert : undefined;
}

const tileGroups = computed(() => {
  const groups: {
    key: string;
    title: string;
    icon: Component;
    tiles: Tile[];
  }[] = [];
  const t = tickets.value;
  if (t) {
    groups.push({
      key: "tickets",
      title: __("Tickets"),
      icon: LucideTicket,
      tiles: [
        { label: __("Opened"), value: t.opened },
        { label: __("Resolved"), value: t.resolved },
        { label: __("Still open"), value: t.open },
        {
          label: __("SLA breached"),
          value: t.sla_breached,
          alert: alertIf(t.sla_breached, {
            ...DANGER,
            icon: LucideShieldAlert,
          }),
        },
      ],
    });
  }
  const k = tasks.value;
  if (k) {
    groups.push({
      key: "tasks",
      title: __("Tasks"),
      icon: LucideListChecks,
      tiles: [
        { label: __("Completed"), value: k.completed },
        { label: __("Open"), value: k.open },
        {
          label: __("Overdue"),
          value: k.overdue,
          alert: alertIf(k.overdue, { ...DANGER, icon: LucideAlarmClock }),
        },
        {
          label: __("On hold"),
          value: k.on_hold,
          alert: alertIf(k.on_hold, { ...WARNING, icon: LucidePause }),
        },
      ],
    });
  }
  return groups;
});

const taskLists = computed(() => {
  const k = tasks.value;
  if (!k) return [];
  const lists: {
    key: string;
    title: string;
    icon: Component;
    items: SummaryTask[];
    total: number;
    empty: string;
  }[] = [
    {
      key: "key",
      title: __("Key tasks"),
      icon: LucideStar,
      items: k.key_open_list ?? [],
      total: k.key_open ?? 0,
      empty: __("No open key tasks."),
    },
    {
      key: "due",
      title: __("Due in the next 7 days"),
      icon: LucideCalendarClock,
      items: k.due_next_7_days_list ?? [],
      total: k.due_next_7_days ?? 0,
      empty: __("Nothing due in the next 7 days."),
    },
  ];
  return lists;
});
</script>
