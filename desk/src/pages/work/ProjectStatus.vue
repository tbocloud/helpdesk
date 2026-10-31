<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">
          {{ __("Project status") }}
        </div>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :loading="report.loading && !!report.data"
          :aria-label="__('Refresh')"
          @click="report.reload()"
        >
          <template #icon>
            <LucideRefreshCw class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          :label="__('Download PDF')"
          :disabled="!shown.length"
          @click="printReport"
        >
          <template #prefix>
            <LucideDownload class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          v-if="data?.can_write_any"
          variant="solid"
          :label="__('Paste or record a full update')"
          @click="splitOpen = true"
        >
          <template #prefix>
            <LucideMic class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-7xl px-4 py-5 md:px-6">
        <p class="text-p-sm text-ink-gray-6">
          {{
            __(
              "Where each open project stands: the written status beside what the tasks say. Projects that need someone come first."
            )
          }}
        </p>

        <div
          class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4"
          role="group"
          :aria-label="__('Filter projects')"
        >
          <FormControl
            v-model="filters.department"
            type="select"
            :label="__('Department')"
            :options="options('department')"
          />
          <FormControl
            v-model="filters.lead"
            type="select"
            :label="__('Lead')"
            :options="options('lead')"
          />
          <FormControl
            v-model="filters.stage"
            type="select"
            :label="__('Stage')"
            :options="stageFilter"
          />
          <FormControl
            v-model="filters.waiting"
            type="select"
            :label="__('Waiting on')"
            :options="waitingFilter"
          />
        </div>
        <div class="mt-2 flex items-center justify-between gap-2">
          <p
            v-if="data"
            class="text-sm text-ink-gray-6"
            role="status"
            aria-live="polite"
          >
            {{ summary }}
          </p>
          <Button
            v-if="hasFilters"
            class="ml-auto"
            variant="ghost"
            :label="__('Clear filters')"
            @click="clear"
          >
            <template #prefix>
              <LucideX class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>

        <TaskyState
          v-if="report.error && !data"
          class="mt-6"
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the project status')"
          :message="__('Check your connection and try again.')"
          error
        >
          <Button :label="__('Retry')" @click="report.reload()" />
        </TaskyState>

        <SectionCard
          v-else
          :title="__('Projects')"
          :count="data ? shown.length : undefined"
          class="mt-4 overflow-hidden"
          :aria-busy="report.loading"
        >
          <div
            class="hidden gap-3 border-b border-outline-gray-2 bg-surface-gray-1 px-4 py-2 text-xs text-ink-gray-5 xl:grid"
            :class="GRID"
            aria-hidden="true"
          >
            <span>{{ __("No.") }}</span>
            <span>{{ __("Project") }}</span>
            <span>{{ __("Status") }}</span>
            <span>{{ __("Details") }}</span>
            <span>{{ __("Next step") }}</span>
            <span>{{ __("Updated") }}</span>
          </div>

          <div v-if="!data" :aria-label="__('Loading')">
            <div
              v-for="i in 5"
              :key="i"
              class="flex flex-col gap-2 border-b border-outline-gray-1 px-4 py-4 last:border-b-0"
            >
              <div
                class="h-3.5 w-1/4 animate-pulse rounded bg-surface-gray-2"
              />
              <div class="h-3 w-3/5 animate-pulse rounded bg-surface-gray-2" />
            </div>
          </div>

          <TaskyState
            v-else-if="!data.rows.length"
            :icon="LucideFolderKanban"
            :title="__('No open projects')"
            :message="
              __('Projects you are on show up here while they are open.')
            "
          />

          <TaskyState
            v-else-if="!shown.length"
            :icon="LucideFolderKanban"
            :title="__('No project matches')"
            :message="__('Try fewer filters.')"
          >
            <Button :label="__('Clear filters')" @click="clear" />
          </TaskyState>

          <ol v-else role="list">
            <li
              v-for="(row, index) in shown"
              :key="row.project"
              class="flex flex-col gap-2 border-b border-outline-gray-1 px-4 py-3.5 last:border-b-0 xl:grid xl:gap-3"
              :class="GRID"
            >
              <span
                class="hidden font-mono text-sm tabular-nums text-ink-gray-5 xl:block"
                >{{ index + 1 }}</span
              >

              <!-- Project -->
              <div class="min-w-0">
                <RouterLink
                  :to="{
                    name: 'TaskyProject',
                    params: { projectId: row.project },
                  }"
                  class="block truncate rounded text-base-semibold text-ink-gray-9 hover:underline focus-visible:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                  :title="__('Open {0}', row.project_name)"
                >
                  {{ row.project_name }}
                </RouterLink>
                <div
                  v-if="row.customer"
                  class="truncate text-sm text-ink-gray-6"
                >
                  {{ row.customer }}
                </div>
                <div
                  v-if="row.lead_name"
                  class="truncate text-xs text-ink-gray-5"
                >
                  {{ __("Lead") }}: {{ row.lead_name }}
                </div>
              </div>

              <!-- Status -->
              <div
                class="flex min-w-0 flex-wrap content-start items-start gap-1.5"
              >
                <TaskyBadge
                  v-if="row.stage"
                  :tone="stageTone(row)"
                  :icon="stageIcon(row)"
                  :label="__(row.stage)"
                />
                <TaskyBadge
                  v-else
                  tone="warning"
                  :icon="LucideCircleHelp"
                  :label="__('No update')"
                />
                <TaskyBadge
                  v-if="isWaiting(row)"
                  :tone="row.waiting_on === 'Client' ? 'warning' : 'neutral'"
                  :icon="LucideHourglass"
                >
                  {{ __("Waiting on {0}", __(row.waiting_on!)) }}
                  <span
                    v-if="
                      row.waiting_on === 'Client' && row.facts.client_wait_days
                    "
                    class="font-mono tabular-nums"
                    >· {{ row.facts.client_wait_days }}{{ __("d") }}</span
                  >
                </TaskyBadge>
              </div>

              <!-- Details: what was written, then what the tasks say -->
              <div class="min-w-0">
                <ul
                  v-if="updateLines(row).length"
                  class="list-disc pl-4 text-p-sm text-ink-gray-8"
                >
                  <li v-for="line in updateLines(row)" :key="line">
                    {{ line }}
                  </li>
                </ul>
                <p v-else class="text-p-sm text-ink-gray-5">
                  {{ __("Nothing written yet.") }}
                </p>
                <p class="mt-1 font-mono text-xs tabular-nums text-ink-gray-5">
                  {{ factsLine(row) }}
                </p>
                <p
                  v-if="row.facts.next_milestone"
                  class="mt-0.5 text-xs text-ink-gray-5"
                >
                  {{ __("Next milestone") }}:
                  {{ row.facts.next_milestone.subject }}
                  <span
                    v-if="row.facts.next_milestone.due"
                    class="font-mono tabular-nums"
                    :class="
                      row.facts.next_milestone.is_overdue ? 'text-danger' : ''
                    "
                    >· {{ formatDate(row.facts.next_milestone.due) }}</span
                  >
                </p>
                <p
                  v-for="flag in row.flags"
                  :key="flag.code"
                  class="mt-1 flex items-start gap-1.5 text-xs-medium text-danger"
                >
                  <LucideTriangleAlert
                    class="mt-0.5 size-3.5 shrink-0"
                    aria-hidden="true"
                  />
                  {{ flag.text }}
                </p>
              </div>

              <!-- Next step -->
              <div class="min-w-0 text-p-sm text-ink-gray-8">
                <template v-if="row.next_step">
                  {{ row.next_step }}
                  <span
                    v-if="row.next_step_date"
                    class="block font-mono text-xs tabular-nums text-ink-gray-5"
                    >{{ formatDate(row.next_step_date) }}</span
                  >
                </template>
                <span v-else class="text-ink-gray-5">{{
                  __("None written")
                }}</span>
              </div>

              <!-- Update age and actions -->
              <div
                class="flex flex-wrap items-center gap-2 xl:flex-col xl:items-start"
              >
                <TaskyBadge
                  v-if="row.stale"
                  tone="warning"
                  :icon="LucideClock"
                  :label="
                    row.update_age === null
                      ? __('No update yet')
                      : __('Stale: {0} days', String(row.update_age))
                  "
                />
                <span
                  v-else-if="row.update_age !== null"
                  class="font-mono text-xs tabular-nums text-ink-gray-5"
                  >{{ ageLabel(row.update_age) }}</span
                >
                <div class="flex gap-1">
                  <Button
                    v-if="row.can_write"
                    size="sm"
                    :label="__('Update status')"
                    @click="editRow(row)"
                  />
                  <Button
                    size="sm"
                    variant="ghost"
                    :label="__('History')"
                    :disabled="row.update_age === null"
                    @click="historyRow = row"
                  />
                </div>
              </div>
            </li>
          </ol>
        </SectionCard>
      </div>
    </div>

    <ProjectStatusDialog
      v-model:open="editOpen"
      :row="editing"
      :stages="data?.stages ?? []"
      :waiting-on="data?.waiting_on ?? []"
      @saved="report.reload()"
    />
    <ProjectStatusSplitDialog
      v-model:open="splitOpen"
      :rows="writableRows"
      :stages="data?.stages ?? []"
      :waiting-on="data?.waiting_on ?? []"
      :ai-available="data?.ai_available ?? false"
      @saved="report.reload()"
    />
    <ProjectStatusHistory
      :open="!!historyRow"
      :project="historyRow"
      @update:open="(o) => !o && (historyRow = null)"
    />
    <ProjectStatusPrint v-if="data" :rows="shown" :date="data.date" />
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import SectionCard from "@/components/SectionCard.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { Button, createResource, dayjs, FormControl } from "frappe-ui";
import { computed, reactive, ref, type Component } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDot from "~icons/lucide/circle-dot";
import LucideCircleHelp from "~icons/lucide/circle-help";
import LucideClock from "~icons/lucide/clock";
import LucideDownload from "~icons/lucide/download";
import LucideFolderKanban from "~icons/lucide/folder-kanban";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideMic from "~icons/lucide/mic";
import LucidePause from "~icons/lucide/pause";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import LucideX from "~icons/lucide/x";
import ProjectStatusDialog from "./components/ProjectStatusDialog.vue";
import ProjectStatusHistory from "./components/ProjectStatusHistory.vue";
import ProjectStatusPrint from "./components/ProjectStatusPrint.vue";
import ProjectStatusSplitDialog from "./components/ProjectStatusSplitDialog.vue";
import {
  factsLine,
  isWaiting,
  needsAttention,
  stageTone,
  updateLines,
  type StatusReport,
  type StatusRow,
} from "./projectStatusMeta";

const GRID =
  "xl:grid-cols-[2.5rem_minmax(0,12rem)_minmax(0,10rem)_minmax(0,1fr)_minmax(0,11rem)_minmax(0,9rem)]";
const NO_UPDATE = "__none";

const route = useRoute();
const router = useRouter();

const report = createResource({
  url: "helpdesk.api.project_status.get_project_status",
  auto: true,
  onSuccess: openRequested,
});
const data = computed(() => report.data as StatusReport | undefined);

const filters = reactive({ department: "", lead: "", stage: "", waiting: "" });
const hasFilters = computed(() => Object.values(filters).some(Boolean));

function clear() {
  Object.assign(filters, { department: "", lead: "", stage: "", waiting: "" });
}

const all = [{ label: __("All"), value: "" }];

function options(key: "department" | "lead") {
  const seen = new Map<string, string>();
  for (const row of data.value?.rows ?? []) {
    const value = row[key];
    if (value) seen.set(value, key === "lead" ? row.lead_name || value : value);
  }
  const found = [...seen].map(([value, label]) => ({ value, label }));
  return [...all, ...found.sort((a, b) => a.label.localeCompare(b.label))];
}

const stageFilter = computed(() => [
  ...all,
  ...(data.value?.stages ?? []).map((value) => ({ label: __(value), value })),
  { label: __("No update"), value: NO_UPDATE },
]);
const waitingFilter = computed(() => [
  ...all,
  ...(data.value?.waiting_on ?? []).map((value) => ({
    label: __(value),
    value,
  })),
]);

// the server's order is the attention order
const shown = computed<StatusRow[]>(() =>
  (data.value?.rows ?? []).filter(
    (r) =>
      (!filters.department || r.department === filters.department) &&
      (!filters.lead || r.lead === filters.lead) &&
      (!filters.stage ||
        (filters.stage === NO_UPDATE ? !r.stage : r.stage === filters.stage)) &&
      (!filters.waiting || r.waiting_on === filters.waiting)
  )
);
const writableRows = computed(() =>
  (data.value?.rows ?? []).filter((r) => r.can_write)
);

const summary = computed(() => {
  const needing = shown.value.filter(needsAttention).length;
  return needing
    ? __(
        "{0} projects, {1} need attention",
        String(shown.value.length),
        String(needing)
      )
    : __("{0} projects, none need attention", String(shown.value.length));
});

const editOpen = ref(false);
const editing = ref<StatusRow | null>(null);
const splitOpen = ref(false);
const historyRow = ref<StatusRow | null>(null);

function editRow(row: StatusRow) {
  editing.value = row;
  editOpen.value = true;
}

// a reminder links here with ?project=: open that project's update to write it
function openRequested() {
  const project = route.query.project;
  if (typeof project !== "string") return;
  router.replace({ query: { ...route.query, project: undefined } });
  const row = writableRows.value.find((r) => r.project === project);
  if (row) editRow(row);
}

function stageIcon(row: StatusRow): Component {
  const tone = stageTone(row);
  if (tone === "danger") return LucideTriangleAlert;
  if (tone === "warning") return LucideHourglass;
  if (tone === "success") return LucideCircleCheck;
  return row.stage === "On hold" ? LucidePause : LucideCircleDot;
}

function formatDate(date: string) {
  return dayjs(date).format("D MMM YYYY");
}

function ageLabel(days: number) {
  if (days === 0) return __("Today");
  return days === 1 ? __("1 day ago") : __("{0} days ago", String(days));
}

// the PDF is the browser's print of ProjectStatusPrint; the file takes the report's name
// for the length of the dialog
function printReport() {
  const title = document.title;
  document.title = `Project Status Report ${dayjs(data.value!.date).format(
    "D MMM YYYY"
  )}`;
  window.addEventListener("afterprint", () => (document.title = title), {
    once: true,
  });
  window.print();
}
</script>
