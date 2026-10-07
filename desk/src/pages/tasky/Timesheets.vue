<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <div class="text-lg-medium text-ink-gray-9">{{ __("Timesheets") }}</div>
      </template>
      <template #right-header>
        <Button
          variant="ghost"
          :label="__('Refresh')"
          :loading="timesheets.loading && !!timesheets.data"
          @click="timesheets.reload()"
        >
          <template #icon><LucideRefreshCw class="size-4" /></template>
        </Button>
        <Button
          :label="__('Download CSV')"
          :tooltip="__('One row per time log, with the filters below')"
          @click="downloadCsv"
        >
          <template #prefix
            ><LucideDownload class="size-4" aria-hidden="true"
          /></template>
        </Button>
        <Button variant="solid" :label="__('Log time')" @click="openForm">
          <template #prefix
            ><LucidePlus class="size-4" aria-hidden="true"
          /></template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-5xl px-4 py-5 md:px-6">
        <TaskyState
          v-if="timesheets.error && !timesheets.data"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load your timesheets')"
          :message="__('Check your connection and try again.')"
        >
          <Button :label="__('Retry')" @click="timesheets.reload()" />
        </TaskyState>

        <template v-else>
          <!-- Mine / team (leads and managers) -->
          <div
            v-if="canSeeTeam"
            class="mb-5 inline-flex gap-1 rounded-lg bg-surface-gray-2 p-0.5"
            role="tablist"
            :aria-label="__('Whose timesheets')"
          >
            <button
              v-for="option in SCOPES"
              :key="option.key"
              type="button"
              role="tab"
              :aria-selected="scope === option.key"
              class="rounded-md px-3 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
              :class="
                scope === option.key
                  ? 'bg-surface-base text-ink-gray-9 shadow-sm'
                  : 'text-ink-gray-6 hover:text-ink-gray-8'
              "
              @click="scope = option.key"
            >
              {{ option.label }}
            </button>
          </div>

          <!-- Filters: who (team view) and when -->
          <div
            class="mb-5 flex flex-wrap items-end gap-3"
            role="group"
            :aria-label="__('Filter timesheets')"
          >
            <div v-if="scope === 'team'" class="w-full sm:w-60">
              <FormControl
                v-model="filters.agent"
                type="select"
                :label="__('Agent')"
                :options="agentOptions"
              />
            </div>
            <div class="w-40">
              <FormControl
                v-model="filters.from_date"
                type="date"
                :label="__('From')"
              />
            </div>
            <div class="w-40">
              <FormControl
                v-model="filters.to_date"
                type="date"
                :label="__('To')"
              />
            </div>
            <Button
              v-if="filters.agent || filters.from_date || filters.to_date"
              variant="ghost"
              :label="__('Clear')"
              @click="clearFilters"
            />
          </div>

          <!-- Summary -->
          <div class="grid grid-cols-2 gap-3 md:grid-cols-3">
            <div
              v-for="stat in stats"
              :key="stat.key"
              class="flex flex-col gap-3 rounded-lg border border-outline-gray-2 bg-surface-base p-4"
            >
              <div class="flex items-center justify-between">
                <span class="text-sm text-ink-gray-6">{{ stat.label }}</span>
                <component
                  :is="stat.icon"
                  class="size-4 text-ink-gray-5"
                  aria-hidden="true"
                />
              </div>
              <span class="text-2xl-semibold tabular-nums text-ink-gray-9">
                <span
                  v-if="!timesheets.data"
                  class="inline-block h-7 w-10 animate-pulse rounded bg-surface-gray-2"
                />
                <template v-else>{{ stat.value }}</template>
              </span>
            </div>
          </div>

          <div
            class="mt-6 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base shadow-sm"
          >
            <div
              class="hidden grid-cols-[1fr_7rem_5rem_6rem] gap-4 border-b border-outline-gray-2 bg-surface-gray-1 px-4 py-2 text-xs text-ink-gray-5 md:grid"
            >
              <span>{{ __("Timesheet") }}</span>
              <span>{{ __("Status") }}</span>
              <span class="text-right">{{ __("Hours") }}</span>
              <span class="text-right">{{ __("Updated") }}</span>
            </div>

            <!-- Loading -->
            <template v-if="!timesheets.data">
              <div
                v-for="i in 5"
                :key="i"
                class="flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3.5 last:border-b-0"
                aria-hidden="true"
              >
                <div class="flex flex-1 flex-col gap-2">
                  <div
                    class="h-3.5 w-2/5 animate-pulse rounded bg-surface-gray-2"
                  />
                  <div
                    class="h-3 w-1/4 animate-pulse rounded bg-surface-gray-2"
                  />
                </div>
                <div class="h-3 w-10 animate-pulse rounded bg-surface-gray-2" />
              </div>
            </template>

            <!-- Empty -->
            <TaskyState
              v-else-if="!timesheets.data.length"
              :icon="LucideClock"
              :title="__('No timesheets yet')"
              :message="
                __(
                  'Log time against a project or task, or complete a task on the board to record hours.'
                )
              "
            >
              <Button variant="solid" :label="__('Log time')" @click="openForm">
                <template #prefix
                  ><LucidePlus class="size-4" aria-hidden="true"
                /></template>
              </Button>
            </TaskyState>

            <ul v-else role="list">
              <li
                v-for="ts in timesheets.data"
                :key="ts.name"
                class="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 border-b border-outline-gray-1 px-4 py-3 last:border-b-0 md:grid-cols-[1fr_7rem_5rem_6rem]"
              >
                <div class="min-w-0">
                  <div class="truncate text-sm text-ink-gray-9">
                    {{ ts.title || ts.name }}
                  </div>
                  <div
                    class="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-1.5 text-xs text-ink-gray-5"
                  >
                    <template v-if="scope === 'team'">
                      <span class="text-ink-gray-7">{{
                        ts.owner_name || ts.owner
                      }}</span>
                      <span aria-hidden="true">·</span>
                    </template>
                    <span class="font-mono">{{ ts.name }}</span>
                    <template v-if="ts.project_name || ts.projects?.length">
                      <span aria-hidden="true">·</span>
                      <span class="truncate">{{
                        ts.project_name || ts.projects[0]
                      }}</span>
                    </template>
                  </div>
                </div>
                <span class="hidden md:block">
                  <TaskyBadge
                    :tone="ts.status === 'Submitted' ? 'success' : 'neutral'"
                    :icon="
                      ts.status === 'Submitted'
                        ? LucideCircleCheck
                        : LucideCircleDashed
                    "
                    :label="__(ts.status)"
                  />
                </span>
                <span
                  class="text-right font-mono text-sm tabular-nums text-ink-gray-8"
                >
                  {{ formatHours(ts.total_hours) }}
                </span>
                <span
                  class="hidden text-right text-sm tabular-nums text-ink-gray-5 md:block"
                >
                  {{ formatDate(ts.modified) }}
                </span>
              </li>
            </ul>
          </div>
        </template>
      </div>
    </div>

    <Dialog v-model:open="showForm" :title="__('Log time')" size="lg">
      <form
        id="tasky-new-timesheet"
        class="flex flex-col gap-4"
        novalidate
        @submit.prevent="onCreate"
      >
        <TextInput
          v-model="form.title"
          :label="__('Title')"
          :placeholder="__('e.g. Weekly meeting, Bug fix…')"
          required
        />
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormControl
            v-model="form.project"
            type="select"
            :label="__('Project')"
            :options="projectOptions"
          />
          <FormControl
            v-model="form.task"
            type="select"
            :label="__('Task (optional)')"
            :options="taskOptions"
            :disabled="!form.project || taskResource.loading"
          />
          <TextInput
            v-model.number="form.hours"
            type="number"
            step="0.25"
            min="0.25"
            :label="__('Hours')"
          />
          <TextInput v-model="form.notes" :label="__('Notes')" />
        </div>
        <div
          v-if="createTs.error"
          role="alert"
          class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-p-sm text-danger"
        >
          <LucideCircleAlert
            class="mt-0.5 size-4 shrink-0"
            aria-hidden="true"
          />
          {{ errorText(createTs.error, __("Couldn't create the timesheet.")) }}
        </div>
      </form>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="close" />
          <Button
            variant="solid"
            type="submit"
            form="tasky-new-timesheet"
            :label="__('Create timesheet')"
            :loading="createTs.loading"
            :disabled="!form.title.trim()"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { errorText } from "@/utils";
import LayoutHeader from "@/components/LayoutHeader.vue";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import {
  Button,
  Dialog,
  FormControl,
  TextInput,
  createResource,
  dayjs,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleDashed from "~icons/lucide/circle-dashed";
import LucideClock from "~icons/lucide/clock";
import LucideDownload from "~icons/lucide/download";
import LucideFileClock from "~icons/lucide/file-clock";
import LucidePlus from "~icons/lucide/plus";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideTimer from "~icons/lucide/timer";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";

const showForm = ref(false);

const form = reactive({
  title: "",
  project: "",
  task: "",
  hours: 1,
  notes: "",
});

const authStore = useAuthStore();
const canSeeTeam = computed(() => authStore.canSeeOverview);

const SCOPES = [
  { key: "mine", label: __("Mine") },
  { key: "team", label: __("Team") },
] as const;
const scope = ref<"mine" | "team">("mine");

const filters = reactive({ agent: "", from_date: "", to_date: "" });

function filterParams() {
  const team = scope.value === "team";
  return {
    team: team ? 1 : 0,
    ...(team && filters.agent ? { agent: filters.agent } : {}),
    ...(filters.from_date ? { from_date: filters.from_date } : {}),
    ...(filters.to_date ? { to_date: filters.to_date } : {}),
  };
}

const timesheets = createResource({
  url: "helpdesk.tasky.api.get_my_timesheets",
  makeParams: () => ({ ...filterParams(), limit: 500 }),
  auto: true,
  transform: (d: any[]) => d ?? [],
  onError() {},
});

watch([scope, filters], () => timesheets.reload());

const agents = createResource({
  url: "helpdesk.tasky.api.get_timesheet_agents",
  transform: (d: any[]) => d ?? [],
  onError() {},
});
watch(
  scope,
  (value) => {
    if (value === "team" && !agents.data) agents.reload();
  },
  { immediate: true }
);
const agentOptions = computed(() => [
  { label: __("All agents"), value: "" },
  ...(agents.data ?? []).map((a: { user: string; full_name: string }) => ({
    label: a.full_name,
    value: a.user,
  })),
]);

function clearFilters() {
  Object.assign(filters, { agent: "", from_date: "", to_date: "" });
}

function downloadCsv() {
  const params = new URLSearchParams(
    Object.entries(filterParams()).map(([k, v]) => [k, String(v)])
  );
  window.open(
    `/api/method/helpdesk.tasky.api.export_timesheets_csv?${params}`,
    "_blank"
  );
}

const projectList = createResource({
  url: "helpdesk.tasky.api.get_projects",
  auto: true,
  transform: (d: any[]) => d ?? [],
});

const taskResource = createResource({
  url: "helpdesk.tasky.api.get_project_tasks",
  auto: false,
  transform: (d: any[]) => d ?? [],
});

const taskList = computed(() => taskResource.data ?? []);

const projectOptions = computed(() => [
  { label: __("None"), value: "" },
  ...(projectList.data ?? []).map((p: any) => ({
    label: p.project_name || p.name,
    value: p.name,
  })),
]);

const taskOptions = computed(() => [
  {
    label: taskResource.loading ? __("Loading tasks…") : __("None"),
    value: "",
  },
  ...taskList.value.map((t: any) => ({ label: t.subject, value: t.name })),
]);

watch(
  () => form.project,
  (val) => {
    form.task = "";
    if (val) {
      taskResource.submit({ project: val });
    }
  }
);

const createTs = createResource({
  url: "helpdesk.tasky.api.create_timesheet",
  onSuccess() {
    toast.success(__("Timesheet created"));
    resetForm();
    showForm.value = false;
    timesheets.reload();
  },
  // shown inline in the dialog
  onError() {},
});

const stats = computed(() => {
  const list: any[] = timesheets.data ?? [];
  const hours = list.reduce(
    (sum, ts) => sum + (Number(ts.total_hours) || 0),
    0
  );
  return [
    {
      key: "count",
      label: __("Timesheets"),
      value: list.length,
      icon: LucideFileClock,
    },
    {
      key: "hours",
      label: __("Hours logged"),
      value: formatHours(hours),
      icon: LucideTimer,
    },
    {
      key: "drafts",
      label: __("Drafts"),
      value: list.filter((ts) => ts.status === "Draft").length,
      icon: LucideCircleDashed,
    },
  ];
});

function resetForm() {
  form.title = "";
  form.project = "";
  form.task = "";
  form.hours = 1;
  form.notes = "";
}

function openForm() {
  createTs.reset();
  showForm.value = true;
}

function onCreate() {
  if (!form.title.trim() || createTs.loading) return;
  createTs.submit({
    title: form.title.trim(),
    project: form.project || null,
    task: form.task || null,
    hours: form.hours || 1,
    notes: form.notes,
  });
}

function formatHours(h: number | string | null | undefined) {
  const n = Number(h) || 0;
  return `${Math.round(n * 100) / 100}h`;
}

function formatDate(d: string) {
  return d ? dayjs(d).format("D MMM") : "—";
}
</script>
